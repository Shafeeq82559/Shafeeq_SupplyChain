"""Explainable analysis of disruption factors.

- Global: mean |SHAP| feature importance per model (computed at training time).
- Local: per-prediction SHAP contributions ("why this prediction").
- Statistical: factor-level group comparisons on the historical data with significance tests.
"""
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy import stats

from src.rag.preprocessing import load_dataset
from src.services import llm_client

FEATURE_LABELS = {"disruption_type": "Disruption type", "industry": "Industry", "supplier_tier": "Supplier tier",
                  "supplier_region": "Supplier region", "supplier_size": "Supplier size",
                  "has_backup_supplier": "Backup supplier", "disruption_severity": "Severity",
                  "response_type": "Response strategy"}
OUTCOMES = {"production_impact_pct": "Production impact %", "revenue_loss_usd": "Revenue loss (USD)",
            "full_recovery_days": "Full recovery days"}


def _shap_matrix(model, X) -> tuple[np.ndarray, float]:
    import shap
    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(X)
    base = explainer.expected_value
    if isinstance(sv, list):  # older binary classifier API: [neg, pos]
        sv, base = sv[1], base[1]
    sv = np.asarray(sv)
    if sv.ndim == 3:
        sv = sv[:, :, -1]
    base = float(np.ravel(base)[-1])
    return sv, base


def compute_global_importance(bundle: dict, X: pd.DataFrame) -> dict:
    out = {}
    models = {t: m["p50"] for t, m in bundle["regressors"].items()}
    models.update(bundle["classifiers"])
    for target, model in models.items():
        sv, _ = _shap_matrix(model, X)
        imp = np.abs(sv).mean(axis=0)
        total = imp.sum() or 1.0
        ranked = sorted(zip(X.columns, imp), key=lambda x: -x[1])
        out[target] = [{"feature": f, "label": FEATURE_LABELS.get(f, f), "mean_abs_shap": round(float(v), 5),
                        "share_pct": round(100 * float(v) / total, 1)} for f, v in ranked]
    return out


def explain_prediction(profile: dict, target: str = "full_recovery_days") -> dict:
    from src.services.ml_models import CLASSIFICATION_TARGETS, LOG_TARGETS, get_models, to_features
    m = get_models()
    X = to_features(profile)
    model = m["classifiers"][target] if target in CLASSIFICATION_TARGETS else m["regressors"][target]["p50"]
    sv, base = _shap_matrix(model, X)
    sv = sv[0]
    raw_pred = base + sv.sum()
    if target in LOG_TARGETS:
        unit = "multiplicative effect on revenue loss (%)"
        contribs = [(100 * (np.exp(v) - 1)) for v in sv]
        prediction, baseline = float(np.expm1(raw_pred)), float(np.expm1(base))
    elif target in CLASSIFICATION_TARGETS:
        unit = "log-odds contribution"
        contribs = list(sv)
        prediction, baseline = float(1 / (1 + np.exp(-raw_pred))), float(1 / (1 + np.exp(-base)))
    else:
        unit = "days" if "days" in target else "percentage points"
        contribs = list(sv)
        prediction, baseline = float(raw_pred), float(base)
    rows = []
    for f, c in zip(X.columns, contribs):
        val = X.iloc[0][f]
        if f == "has_backup_supplier":
            val = "Yes" if int(val) else "No"
        rows.append({"feature": f, "label": FEATURE_LABELS.get(f, f), "value": str(val), "contribution": round(float(c), 3),
                     "direction": "increases" if c > 0 else "decreases"})
    rows.sort(key=lambda r: -abs(r["contribution"]))
    return {"target": target, "unit": unit, "baseline": round(baseline, 3), "prediction": round(prediction, 3),
            "contributions": rows, "summary": _summarize(target, rows, unit)}


def _summarize(target: str, rows: list[dict], unit: str) -> str:
    top = [r for r in rows if abs(r["contribution"]) > 0][:3]
    parts = [f"{r['label']} = {r['value']} {r['direction']} it ({r['contribution']:+.2f} {unit.split(' (')[0]})"
             for r in top]
    return f"Main drivers of {target.replace('_', ' ')}: " + "; ".join(parts) + "."


def global_importance() -> dict:
    from src.services.ml_models import get_models
    return get_models()["global_importance"]


@lru_cache(maxsize=1)
def factor_analysis() -> dict:
    """Group comparisons of outcomes by each factor, with significance tests (ANOVA / Welch t-test)."""
    df = load_dataset()
    result = {}
    for factor in FEATURE_LABELS:
        groups = {}
        for level, g in df.groupby(factor):
            key = ("Yes" if level else "No") if factor == "has_backup_supplier" else str(level)
            groups[key] = {"count": int(len(g)),
                           **{o: round(float(g[o].mean()), 2) for o in OUTCOMES},
                           "permanent_supplier_change_rate": round(float(g["permanent_supplier_change"].mean()), 3)}
        tests = {}
        for o in OUTCOMES:
            samples = [g[o].to_numpy() for _, g in df.groupby(factor)]
            if len(samples) == 2:
                stat, p = stats.ttest_ind(*samples, equal_var=False)
                test = "Welch t-test"
            else:
                stat, p = stats.f_oneway(*samples)
                test = "one-way ANOVA"
            # eta-squared effect size: share of outcome variance explained by this factor
            grand = df[o].mean()
            ss_between = sum(len(s) * (s.mean() - grand) ** 2 for s in samples)
            ss_total = ((df[o] - grand) ** 2).sum()
            # same factor after removing what severity already explains: does the gap survive at equal severity?
            resid = df[o] - df.groupby("disruption_severity")[o].transform("mean")
            adj_means = resid.groupby(df[factor]).mean()
            ss_adj = float((df.groupby(factor).size() * adj_means ** 2).sum())
            tests[o] = {"test": test, "p_value": float(f"{p:.3g}"), "significant": bool(p < 0.05),
                        "effect_size_eta_sq": round(float(ss_between / ss_total), 4),
                        "adjusted_eta_sq": round(ss_adj / float(ss_total), 4),
                        "adjusted_gap": round(float(adj_means.max() - adj_means.min()), 2)}
        result[factor] = {"label": FEATURE_LABELS[factor], "groups": groups, "tests": tests}
    return result


def key_insights(top_n: int = 6) -> list[str]:
    """Plain-language findings: the factors that explain the most variance in each outcome. A factor is only reported as a
    driver if its effect survives at equal severity; otherwise it is reported once as a caution ("Note: ..."), because
    severity is the real driver and some factors (e.g. disruption type) merely come with different severities."""
    fa = factor_analysis()
    lines, notes = [], []
    for o, olabel in OUTCOMES.items():
        ranked = sorted(fa.items(), key=lambda kv: -kv[1]["tests"][o]["effect_size_eta_sq"])
        kept = 0
        for factor, info in ranked:
            if kept == 2:
                break
            t = info["tests"][o]
            if not t["significant"]:
                continue
            fmt = (lambda v: f"${v / 1e6:,.2f}M") if o == "revenue_loss_usd" else \
                  (lambda v: f"{v:,.1f}%") if o == "production_impact_pct" else (lambda v: f"{v:,.0f} days")
            if factor != "disruption_severity" and t["effect_size_eta_sq"] >= 0.02 and t["adjusted_eta_sq"] < 0.005:
                notes.append(f"Note: {info['label']} looks like a driver of {olabel.split(' (')[0].lower()} "
                             f"({100 * t['effect_size_eta_sq']:.1f}% of variance), but only because it comes with different severities. "
                             f"At the same severity the gap between its groups is just {fmt(t['adjusted_gap'])}.")
                continue
            g = info["groups"]
            hi = max(g, key=lambda k: g[k][o]); lo = min(g, key=lambda k: g[k][o])
            p = "p<0.001" if t["p_value"] < 0.001 else f"p={t['p_value']:.3f}"
            name = f"severity {hi}" if factor == "disruption_severity" else hi
            name_lo = f"severity {lo}" if factor == "disruption_severity" else lo
            lines.append(f"{info['label']} is a key driver of {olabel.split(' (')[0].lower()} (explains "
                         f"{100 * t['effect_size_eta_sq']:.1f}% of variance, {p}): {name} averages {fmt(g[hi][o])} vs "
                         f"{name_lo} {fmt(g[lo][o])}.")
            kept += 1
    return lines[:top_n] + notes[:1]


def narrate(explanation: dict) -> str:
    """Optional LLM narrative of a SHAP explanation; falls back to the template summary."""
    text = llm_client.complete_text(
        "You explain machine-learning predictions to supply chain managers in 3 short sentences, plain language, "
        "no jargon, no numbers you were not given.",
        f"Target: {explanation['target']}; prediction {explanation['prediction']} (baseline {explanation['baseline']}); "
        f"contributions ({explanation['unit']}): {explanation['contributions'][:5]}", max_tokens=400)
    return text or explanation["summary"]
