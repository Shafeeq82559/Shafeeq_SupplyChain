"""Prediction models (LightGBM).

Regressors (median + P10/P90 quantile models): production impact %, revenue loss (log scale),
full recovery days, partial recovery days.
Classifiers: high-impact disruption risk, permanent supplier change risk.

`response_type` is an input feature so the planner can run what-if predictions for every strategy.
"""
from functools import lru_cache

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score, mean_absolute_error,
                             mean_squared_error, precision_score, r2_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

from src.config import settings
from src.utils.constants import (DISRUPTION_TYPES, INDUSTRIES, REGIONS, RESPONSE_TYPES, SUPPLIER_SIZES)
from src.utils.logger import get_logger

log = get_logger(__name__)

CATEGORIES = {"disruption_type": DISRUPTION_TYPES, "industry": INDUSTRIES, "supplier_region": REGIONS,
              "supplier_size": SUPPLIER_SIZES, "response_type": RESPONSE_TYPES}
FEATURES = ["disruption_type", "industry", "supplier_tier", "supplier_region", "supplier_size",
            "has_backup_supplier", "disruption_severity", "response_type"]
REGRESSION_TARGETS = ["production_impact_pct", "revenue_loss_usd", "full_recovery_days", "partial_recovery_days"]
LOG_TARGETS = {"revenue_loss_usd"}
CLASSIFICATION_TARGETS = ["high_impact", "permanent_supplier_change"]
MODEL_PATH = settings.MODELS_DIR / "models.joblib"
DEFAULT_RESPONSE = "Alternative Supplier"  # most common historical response; used when none is given

REG_PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=50,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.9, verbose=-1)


def to_features(rows: pd.DataFrame | list[dict] | dict) -> pd.DataFrame:
    if isinstance(rows, dict):
        rows = [rows]
    X = pd.DataFrame(rows).copy()
    if "response_type" not in X:
        X["response_type"] = DEFAULT_RESPONSE
    X["response_type"] = X["response_type"].fillna(DEFAULT_RESPONSE)
    X = X[FEATURES].copy()
    for c, cats in CATEGORIES.items():
        X[c] = pd.Categorical(X[c], categories=cats)
    X["supplier_tier"] = X["supplier_tier"].astype(int)
    X["disruption_severity"] = X["disruption_severity"].astype(int)
    X["has_backup_supplier"] = X["has_backup_supplier"].astype(int)
    return X


def best_f1_threshold(y_true, proba) -> float:
    """Probability cutoff that maximises F1. The 0.5 default predicts 'no' almost always on imbalanced targets."""
    grid = np.arange(0.05, 0.95, 0.01)
    return round(float(grid[int(np.argmax([f1_score(y_true, proba >= t) for t in grid]))]), 2)


def train_all(df: pd.DataFrame, extra: pd.DataFrame | None = None) -> dict:
    """Train every model; `extra` holds feedback-supplied real outcomes appended to the training set."""
    if extra is not None and len(extra):
        df = pd.concat([df, extra], ignore_index=True)
    train, test = train_test_split(df, test_size=0.2, random_state=42)
    Xtr, Xte = to_features(train), to_features(test)
    bundle = {"regressors": {}, "classifiers": {}, "metrics": {}, "n_train": len(train), "n_test": len(test)}

    for target in REGRESSION_TARGETS:
        ytr, yte = train[target].to_numpy(float), test[target].to_numpy(float)
        if target in LOG_TARGETS:
            ytr = np.log1p(ytr)
        models = {"p50": lgb.LGBMRegressor(**REG_PARAMS).fit(Xtr, ytr)}
        for q, name in ((0.1, "p10"), (0.9, "p90")):
            models[name] = lgb.LGBMRegressor(objective="quantile", alpha=q, **REG_PARAMS).fit(Xtr, ytr)
        pred = models["p50"].predict(Xte)
        if target in LOG_TARGETS:
            pred = np.expm1(pred)
        baseline = np.full_like(yte, np.median(train[target]))
        p10 = models["p10"].predict(Xte); p90 = models["p90"].predict(Xte)
        if target in LOG_TARGETS:
            p10, p90 = np.expm1(p10), np.expm1(p90)
        bundle["regressors"][target] = models
        bundle["metrics"][target] = {
            "MAE": round(mean_absolute_error(yte, pred), 3),
            "RMSE": round(float(np.sqrt(mean_squared_error(yte, pred))), 3),
            "R2": round(r2_score(yte, pred), 4),
            "baseline_MAE": round(mean_absolute_error(yte, baseline), 3),
            "interval_coverage_p10_p90": round(float(np.mean((yte >= p10) & (yte <= p90))), 3),
        }
        log.info("%s: %s", target, bundle["metrics"][target])

    bundle["thresholds"] = {}
    for target in CLASSIFICATION_TARGETS:
        ytr, yte = train[target].astype(int), test[target].astype(int)
        # Decision threshold is tuned on a slice of the training data so the test set stays untouched. The final
        # model is left unweighted, so its probabilities stay calibrated for the UI and the strategy score.
        fit_x, val_x, fit_y, val_y = train_test_split(Xtr, ytr, test_size=0.2, random_state=1, stratify=ytr)
        thr = best_f1_threshold(val_y, lgb.LGBMClassifier(**REG_PARAMS).fit(fit_x, fit_y).predict_proba(val_x)[:, 1])
        clf = lgb.LGBMClassifier(**REG_PARAMS).fit(Xtr, ytr)
        proba = clf.predict_proba(Xte)[:, 1]
        pred = proba >= thr
        bundle["classifiers"][target] = clf
        bundle["thresholds"][target] = thr
        bundle["metrics"][target] = {
            "ROC_AUC": round(roc_auc_score(yte, proba), 4),
            "PR_AUC": round(average_precision_score(yte, proba), 4),
            "threshold": thr,
            "accuracy": round(accuracy_score(yte, pred), 4),
            "precision": round(precision_score(yte, pred, zero_division=0), 4),
            "recall": round(recall_score(yte, pred), 4),
            "F1": round(f1_score(yte, pred), 4),
            "F1_at_0.5": round(f1_score(yte, proba >= 0.5), 4),
            "positive_rate": round(float(yte.mean()), 4),
        }
        log.info("%s: %s", target, bundle["metrics"][target])

    # Global SHAP importance on a sample (stored so the API never recomputes it).
    from src.services.explainability import compute_global_importance
    bundle["global_importance"] = compute_global_importance(bundle, Xte.sample(min(3000, len(Xte)), random_state=0))
    joblib.dump(bundle, MODEL_PATH)
    get_models.cache_clear()
    return bundle


@lru_cache(maxsize=1)
def get_models() -> dict:
    return joblib.load(MODEL_PATH)


def models_ready() -> bool:
    return MODEL_PATH.exists()


def _inverse(target: str, v):
    return np.expm1(v) if target in LOG_TARGETS else v


def predict(profile: dict) -> dict:
    """Predict outcomes (median and P10-P90 range) plus risk probabilities for a disruption profile."""
    m = get_models()
    X = to_features(profile)
    out = {}
    for target, models in m["regressors"].items():
        vals = {k: float(_inverse(target, models[k].predict(X)[0])) for k in ("p10", "p50", "p90")}
        lo, mid, hi = sorted([vals["p10"], vals["p50"], vals["p90"]])
        if target == "production_impact_pct":
            lo, mid, hi = (min(100.0, max(0.0, v)) for v in (lo, mid, hi))
        else:
            lo, mid, hi = (max(0.0, v) for v in (lo, mid, hi))
        out[target] = {"predicted": round(mid, 2), "low_p10": round(lo, 2), "high_p90": round(hi, 2)}
    out["high_impact_probability"] = round(float(m["classifiers"]["high_impact"].predict_proba(X)[0, 1]), 4)
    out["supplier_change_probability"] = round(
        float(m["classifiers"]["permanent_supplier_change"].predict_proba(X)[0, 1]), 4)
    return out


def predict_by_response(profile: dict) -> list[dict]:
    """What-if: predicted outcome for each response strategy (used by the response planner)."""
    m = get_models()
    rows = [{**profile, "response_type": r} for r in RESPONSE_TYPES]
    X = to_features(rows)

    def mid(target: str) -> np.ndarray:
        # same point estimate as predict(): the middle of the p10/p50/p90 models, so the numbers shown for a strategy
        # here are identical to the ones in the headline and recovery timeline
        vals = np.vstack([_inverse(target, m["regressors"][target][k].predict(X)) for k in ("p10", "p50", "p90")])
        return np.maximum(0.0, np.median(vals, axis=0))

    full, part, loss = mid("full_recovery_days"), mid("partial_recovery_days"), mid("revenue_loss_usd")
    imp = np.minimum(100.0, mid("production_impact_pct"))
    chg = m["classifiers"]["permanent_supplier_change"].predict_proba(X)[:, 1]
    return [{"response_type": r, "predicted_full_recovery_days": round(float(f), 2),
             "predicted_partial_recovery_days": round(float(p), 2), "predicted_revenue_loss_usd": round(float(l), 0),
             "predicted_production_impact_pct": round(float(i), 2), "supplier_change_probability": round(float(c), 4)}
            for r, f, p, l, i, c in zip(RESPONSE_TYPES, full, part, loss, imp, chg)]
