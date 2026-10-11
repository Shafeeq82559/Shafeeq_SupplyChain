"""Dataset-level analytics for the dashboard and /stats endpoint."""
from functools import lru_cache

from src.rag.preprocessing import load_dataset


@lru_cache(maxsize=1)
def dataset_stats() -> dict:
    df = load_dataset()

    def breakdown(col):
        g = df.groupby(col)
        return {str(k): {"count": int(len(v)), "avg_production_impact_pct": round(float(v["production_impact_pct"].mean()), 1),
                         "avg_revenue_loss_usd": round(float(v["revenue_loss_usd"].mean()), 0),
                         "avg_full_recovery_days": round(float(v["full_recovery_days"].mean()), 1),
                         "supplier_change_rate": round(float(v["permanent_supplier_change"].mean()), 3)}
                for k, v in g}

    resp = df.groupby(["disruption_type", "response_type"])["full_recovery_days"].mean().round(1).unstack()
    return {
        "total_records": int(len(df)),
        "totals": {"total_revenue_loss_usd": round(float(df["revenue_loss_usd"].sum()), 0),
                   "avg_production_impact_pct": round(float(df["production_impact_pct"].mean()), 1),
                   "median_full_recovery_days": float(df["full_recovery_days"].median()),
                   "backup_supplier_rate": round(float(df["has_backup_supplier"].mean()), 3),
                   "permanent_supplier_change_rate": round(float(df["permanent_supplier_change"].mean()), 3)},
        "by_disruption_type": breakdown("disruption_type"),
        "by_industry": breakdown("industry"),
        "by_region": breakdown("supplier_region"),
        "by_severity": breakdown("disruption_severity"),
        "by_tier": breakdown("supplier_tier"),
        "by_response_type": breakdown("response_type"),
        "by_backup_supplier": breakdown("has_backup_supplier"),
        "recovery_days_by_type_and_response": {t: row.dropna().to_dict() for t, row in resp.iterrows()},
    }
