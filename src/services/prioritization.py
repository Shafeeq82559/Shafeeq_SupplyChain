"""Disruption prioritization: a transparent weighted score (0-100) mapped to P1-P4.

Factors: severity, production impact, financial loss (log-scaled against the historical distribution),
supplier tier (closer tiers hit production sooner) and absence of a backup supplier.
When impact or loss are unknown for a new incident, they are filled in from the ML predictors.
"""
from functools import lru_cache

import numpy as np

from src.rag.preprocessing import load_dataset

WEIGHTS = {"severity": 0.35, "production_impact": 0.25, "financial_loss": 0.25, "supplier_tier": 0.10, "no_backup": 0.05}
TIER_FACTOR = {1: 1.0, 2: 0.75, 3: 0.5, 4: 0.25}
LEVELS = [(70, "P1", "Critical", "Escalate immediately; activate crisis team and backup sourcing within 24h."),
          (50, "P2", "High", "Respond within 48h; secure alternative capacity and notify key customers."),
          (30, "P3", "Medium", "Plan mitigation this week; monitor supplier recovery closely."),
          (0, "P4", "Low", "Monitor; handle through standard operating procedures.")]


@lru_cache(maxsize=1)
def _loss_bounds() -> tuple[float, float]:
    loss = np.log1p(load_dataset()["revenue_loss_usd"].to_numpy())
    return float(np.percentile(loss, 1)), float(np.percentile(loss, 99))


def score(severity: int, production_impact_pct: float, revenue_loss_usd: float,
          supplier_tier: int = 2, has_backup_supplier: bool = True) -> dict:
    lo, hi = _loss_bounds()
    factors = {
        "severity": (severity - 1) / 4,
        "production_impact": min(max(production_impact_pct, 0), 100) / 100,
        "financial_loss": float(np.clip((np.log1p(max(revenue_loss_usd, 0)) - lo) / (hi - lo), 0, 1)),
        "supplier_tier": TIER_FACTOR.get(int(supplier_tier), 0.5),
        "no_backup": 0.0 if has_backup_supplier else 1.0,
    }
    contributions = {k: round(100 * WEIGHTS[k] * v, 2) for k, v in factors.items()}
    total = round(sum(contributions.values()), 1)
    threshold, code, label, action = next(l for l in LEVELS if total >= l[0])
    return {"priority_score": total, "priority_level": code, "priority_label": label,
            "recommended_action": action, "factor_contributions": contributions,
            "normalized_factors": {k: round(v, 3) for k, v in factors.items()}}


def prioritize_batch(items: list[dict]) -> list[dict]:
    """Score many disruptions and return them ranked (highest priority first)."""
    out = []
    for i, it in enumerate(items):
        s = score(it["disruption_severity"], it["production_impact_pct"], it["revenue_loss_usd"],
                  it.get("supplier_tier", 2), it.get("has_backup_supplier", True))
        out.append({"id": it.get("id") or it.get("disruption_id") or f"item-{i + 1}", **it, **s})
    out.sort(key=lambda x: -x["priority_score"])
    for rank, o in enumerate(out, 1):
        o["rank"] = rank
    return out
