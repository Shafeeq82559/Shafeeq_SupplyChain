"""Benchmark the production LightGBM models against a random forest and a linear baseline.

Same 80/20 split as training (random_state=42), same targets, same metrics. Nothing here changes the app.

Usage:  python -m scripts.benchmark_models
"""
import json
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split

from src.config import settings
from src.rag.preprocessing import load_dataset
from src.services.ml_models import (CLASSIFICATION_TARGETS, LOG_TARGETS, REG_PARAMS, REGRESSION_TARGETS, to_features)
from src.utils.logger import get_logger

log = get_logger("benchmark")


def make_regressors() -> dict:
    return {"LightGBM": (lgb.LGBMRegressor(**REG_PARAMS), False),
            "RandomForest": (RandomForestRegressor(n_estimators=200, min_samples_leaf=50, max_features=0.5,
                                                   n_jobs=-1, random_state=0), True),
            "Ridge": (Ridge(alpha=1.0), True)}


def make_classifiers() -> dict:
    return {"LightGBM": (lgb.LGBMClassifier(**REG_PARAMS), False),
            "RandomForest": (RandomForestClassifier(n_estimators=200, min_samples_leaf=50, max_features=0.5,
                                                    n_jobs=-1, random_state=0), True),
            "LogisticRegression": (LogisticRegression(max_iter=500), True)}


def main():
    t0 = time.time()
    train, test = train_test_split(load_dataset(), test_size=0.2, random_state=42)
    Xtr, Xte = to_features(train), to_features(test)
    # RandomForest / linear models need one-hot input; LightGBM takes the categoricals natively.
    Otr = pd.get_dummies(Xtr.astype(object)).astype(float)
    Ote = pd.get_dummies(Xte.astype(object)).astype(float).reindex(columns=Otr.columns, fill_value=0.0)
    out = {"regression": {}, "classification": {}, "note": "Same 80/20 split as the production models. Point predictions (median) only."}

    for target in REGRESSION_TARGETS:
        ytr, yte = train[target].to_numpy(float), test[target].to_numpy(float)
        log_t = target in LOG_TARGETS
        rows = {"median_baseline": {"MAE": round(mean_absolute_error(yte, np.full_like(yte, np.median(ytr))), 3), "R2": 0.0}}
        for name, (model, onehot) in make_regressors().items():
            model.fit(Otr if onehot else Xtr, np.log1p(ytr) if log_t else ytr)
            pred = model.predict(Ote if onehot else Xte)
            pred = np.expm1(pred) if log_t else pred
            rows[name] = {"MAE": round(mean_absolute_error(yte, pred), 3), "R2": round(r2_score(yte, pred), 4)}
        out["regression"][target] = rows
        log.info("%s: %s", target, rows)

    for target in CLASSIFICATION_TARGETS:
        ytr, yte = train[target].astype(int), test[target].astype(int)
        rows = {}
        for name, (model, onehot) in make_classifiers().items():
            model.fit(Otr if onehot else Xtr, ytr)
            p = model.predict_proba(Ote if onehot else Xte)[:, 1]
            rows[name] = {"ROC_AUC": round(roc_auc_score(yte, p), 4), "PR_AUC": round(average_precision_score(yte, p), 4)}
        rows["positive_rate"] = round(float(yte.mean()), 4)
        out["classification"][target] = rows
        log.info("%s: %s", target, rows)

    (settings.EVAL_DIR / "model_benchmark.json").write_text(json.dumps(out, indent=2))
    log.info("Benchmark finished in %.0fs -> %s", time.time() - t0, settings.EVAL_DIR / "model_benchmark.json")


if __name__ == "__main__":
    main()
