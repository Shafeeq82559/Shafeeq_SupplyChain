"""Supply chain resilience and disruption-risk prediction for a supplier profile.

For a supplier profile (industry, region, tier, size, backup availability) the models are run across
every disruption type at the requested severity, weighted by how often each type has historically hit
that industry/region. This yields:
- disruption risk: probability that a disruption becomes high-impact
- resilience score (0-100): ability to absorb and recover (fast recovery, low impact, low risk)
- per-disruption-type exposure and the main risk drivers (SHAP)
"""
from functools import lru_cache

import numpy as np

from src.rag.preprocessing import load_dataset
from src.services import ml_models
from src.services.explainability import explain_prediction
from src.utils.constants import DISRUPTION_TYPES

RISK_BANDS = [(0.6, "Very High"), (0.4, "High"), (0.2, "Moderate"), (0.0, "Low")]


@lru_cache(maxsize=1)
def _outcome_ranges():
    df = load_dataset()
    return {c: (float(df[c].quantile(0.05)), float(df[c].quantile(0.95)))
            for c in ("full_recovery_days", "production_impact_pct")}


def _type_weights(industry: str, region: str) -> dict[str, float]:
    df = load_dataset()
    sub = df[(df["industry"] == industry) & (df["supplier_region"] == region)]
    if len(sub) < 50:
        sub = df[df["industry"] == industry] if industry else df
    w = sub["disruption_type"].value_counts(normalize=True)
    return {t: float(w.get(t, 0.0)) for t in DISRUPTION_TYPES}


def _type_severity(industry: str, region: str) -> dict[str, float]:
    """Average severity each disruption type actually had for this industry/region in the historical record."""
    df = load_dataset()
    sub = df[(df["industry"] == industry) & (df["supplier_region"] == region)]
    if len(sub) < 50:
        sub = df[df["industry"] == industry] if industry else df
    m = sub.groupby("disruption_type")["disruption_severity"].mean()
    overall = float(sub["disruption_severity"].mean())
    return {t: float(m.get(t, overall)) for t in DISRUPTION_TYPES}


def assess(profile: dict, severity: int = 3) -> dict:
    weights = _type_weights(profile["industry"], profile["supplier_region"])
    rec_lo, rec_hi = _outcome_ranges()["full_recovery_days"]
    imp_lo, imp_hi = _outcome_ranges()["production_impact_pct"]
    typical = _type_severity(profile["industry"], profile["supplier_region"])
    per_type = []

    def predict_at(t: str, sev: int) -> dict:
        return ml_models.predict({**profile, "disruption_type": t, "disruption_severity": sev, "response_type": profile.get("response_type")})

    def vuln_of(p: dict) -> float:
        rec_n = np.clip((p["full_recovery_days"]["predicted"] - rec_lo) / (rec_hi - rec_lo), 0, 1)
        imp_n = np.clip((p["production_impact_pct"]["predicted"] - imp_lo) / (imp_hi - imp_lo), 0, 1)
        return float(0.4 * rec_n + 0.3 * imp_n + 0.3 * p["high_impact_probability"])

    for t in DISRUPTION_TYPES:
        p = predict_at(t, severity)
        vulnerability = vuln_of(p)
        # vulnerability if this type hits at the severity it usually has (interpolated between the two nearest whole levels)
        ts = min(5.0, max(1.0, typical[t])); lo = min(4, int(ts)); frac = ts - lo
        v_lo = vulnerability if lo == severity else vuln_of(predict_at(t, lo))
        v_hi = vulnerability if lo + 1 == severity else vuln_of(predict_at(t, lo + 1))
        at_typical = (1 - frac) * v_lo + frac * v_hi
        per_type.append({"disruption_type": t, "historical_frequency": round(weights[t], 3),
                         "typical_severity": round(ts, 2), "vulnerability_at_typical_severity": round(float(at_typical), 3),
                         "high_impact_probability": p["high_impact_probability"],
                         "predicted_full_recovery_days": p["full_recovery_days"]["predicted"],
                         "predicted_production_impact_pct": p["production_impact_pct"]["predicted"],
                         "predicted_revenue_loss_usd": p["revenue_loss_usd"]["predicted"],
                         "vulnerability": round(float(vulnerability), 3)})
    wsum = sum(weights.values()) or 1
    risk = sum(x["high_impact_probability"] * weights[x["disruption_type"]] for x in per_type) / wsum
    vuln = sum(x["vulnerability"] * weights[x["disruption_type"]] for x in per_type) / wsum
    resilience = round(100 * (1 - vuln), 1)
    band = next(label for th, label in RISK_BANDS if risk >= th)
    top_type = max(per_type, key=lambda x: x["vulnerability"] * (0.5 + x["historical_frequency"]))
    drivers = explain_prediction({**profile, "disruption_type": top_type["disruption_type"],
                                  "disruption_severity": severity}, target="high_impact")
    recs = []
    if not profile.get("has_backup_supplier"):
        recs.append("Qualify a backup supplier: backup availability is associated with lower impact and faster recovery.")
    if int(profile.get("supplier_tier", 1)) >= 3:
        recs.append("Map sub-tier suppliers: deep-tier disruptions are detected late; add visibility/early warning.")
    recs.append(f"Prepare a playbook for {top_type['disruption_type']} disruptions, the largest exposure for this profile.")
    if resilience < 60:
        recs.append("Increase safety stock for critical parts sourced from this supplier.")
    return {"profile": profile, "assumed_severity": severity, "disruption_risk_probability": round(float(risk), 4),
            "risk_band": band, "resilience_score": resilience,
            "resilience_grade": "A" if resilience >= 75 else "B" if resilience >= 60 else "C" if resilience >= 45 else "D",
            "exposure_by_type": sorted(per_type, key=lambda x: -x["vulnerability"]),
            "top_risk_drivers": drivers["contributions"][:5], "recommendations": recs}
