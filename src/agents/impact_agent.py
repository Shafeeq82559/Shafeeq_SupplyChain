"""Impact Assessment Agent: predicts production impact, financial loss and recovery time (with ranges),
explains the drivers (SHAP) and computes the disruption priority."""
from src.services import ml_models, prioritization
from src.services.explainability import explain_prediction


def assess_impact(profile: dict, known: dict | None = None) -> dict:
    """`known` may carry actual impact/loss figures already observed; they override predictions for priority."""
    known = known or {}
    pred = ml_models.predict(profile)
    impact = known.get("production_impact_pct") or pred["production_impact_pct"]["predicted"]
    loss = known.get("revenue_loss_usd") or pred["revenue_loss_usd"]["predicted"]
    priority = prioritization.score(profile["disruption_severity"], impact, loss,
                                    profile["supplier_tier"], profile["has_backup_supplier"])
    priority["inputs"] = {"production_impact_pct": round(impact, 2), "revenue_loss_usd": round(loss, 0),
                          "source": "observed" if known else "predicted"}
    explanations = {t: explain_prediction(profile, t) for t in ("production_impact_pct", "revenue_loss_usd",
                                                                 "full_recovery_days")}
    return {"predictions": pred, "priority": priority,
            "drivers": {t: {"summary": e["summary"], "top": e["contributions"][:4], "unit": e["unit"]}
                        for t, e in explanations.items()}}
