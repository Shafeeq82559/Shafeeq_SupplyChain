"""Recovery Analysis Agent: projects the recovery timeline for the chosen strategy, supplier-change
risk, resilience of the affected supplier profile and the KPIs to monitor during recovery."""
from src.services import ml_models, risk_resilience


def analyze_recovery(profile: dict, strategy: str | None, cases: list[dict]) -> dict:
    pred = ml_models.predict({**profile, "response_type": strategy})
    part, full = pred["partial_recovery_days"], pred["full_recovery_days"]
    same = [c for c in cases if c["response_type"] == strategy]
    resilience = risk_resilience.assess({k: profile[k] for k in ("industry", "supplier_region", "supplier_tier",
                                                                 "supplier_size", "has_backup_supplier")},
                                        severity=profile["disruption_severity"])
    change_p = pred["supplier_change_probability"]
    milestones = [
        {"day": 0, "milestone": f"Activate {strategy or 'response'}; establish incident cell and daily stand-ups"},
        {"day": max(1, round(part["predicted"] / 2)), "milestone": "Interim capacity in place; customer allocations confirmed"},
        {"day": round(part["predicted"]), "milestone": "Partial recovery: critical production lines restored"},
        {"day": round(full["predicted"]), "milestone": "Full recovery: normal output and service levels restored"},
    ]
    return {
        "strategy": strategy,
        "timeline": {"partial_recovery_days": part, "full_recovery_days": full},
        "historical_same_strategy": {"cases": len(same),
                                     "avg_full_recovery_days": round(sum(c["full_recovery_days"] for c in same) / len(same), 1) if same else None},
        "milestones": milestones,
        "supplier_change_probability": change_p,
        "supplier_change_outlook": ("Likely permanent supplier change - start qualifying replacements now" if change_p >= 0.4
                                    else "Supplier relationship likely retained - plan joint recovery review"),
        "resilience": {k: resilience[k] for k in ("resilience_score", "resilience_grade", "disruption_risk_probability",
                                                  "risk_band", "recommendations")},
        "monitoring_kpis": ["Production output vs. plan (%)", "Customer order fill rate", "Days of inventory cover",
                            "Supplier recovery milestones met", "Expedite / premium freight cost"],
    }
