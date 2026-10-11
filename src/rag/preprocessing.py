"""Data loading, cleaning, feature derivation and record -> text "chunk" generation.

The dataset is fully structured (no free text), so each disruption record becomes exactly one
retrievable chunk: a short natural-language narrative of the event, its impact, response and recovery.
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)

SEVERITY_WORDS = {1: "minor", 2: "moderate", 3: "significant", 4: "severe", 5: "critical"}
TIER_WORDS = {1: "Tier-1 (direct)", 2: "Tier-2", 3: "Tier-3", 4: "Tier-4 (deep sub-tier)"}
# Descriptors enrich chunks with vocabulary users actually type ("typhoon", "ransomware"...),
# which helps both BM25 and the embedding model connect free-text queries to the right type.
TYPE_DESCRIPTORS = {
    "Natural Disaster": "natural disaster such as earthquake, flood, typhoon, hurricane, storm or wildfire",
    "Cyber Attack": "cyber attack such as ransomware, malware, hacking or IT systems outage",
    "Labor Strike": "labor strike, union walkout or workforce industrial action",
    "Port Congestion": "port congestion, shipping backlog, container and vessel delays, logistics bottleneck",
    "Geopolitical": "geopolitical event such as sanctions, tariffs, export bans, trade restrictions or conflict",
    "Factory Incident": "factory incident such as plant fire, explosion, equipment breakdown or quality contamination",
}

BOOL_COLS = ["has_backup_supplier", "permanent_supplier_change"]
INT_COLS = ["supplier_tier", "disruption_severity", "response_time_days", "partial_recovery_days", "full_recovery_days"]
FLOAT_COLS = ["production_impact_pct", "revenue_loss_usd"]


def load_raw(path=None) -> pd.DataFrame:
    path = path or settings.DATA_PATH
    if not path.exists():
        path = settings.SAMPLE_DATA_PATH
        log.warning("Full dataset not found, falling back to sample data at %s", path)
    return pd.read_csv(path)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    before = len(df)
    df = df.drop_duplicates(subset="disruption_id").dropna(subset=["disruption_id", "disruption_type"])
    for c in BOOL_COLS:
        df[c] = df[c].astype(str).str.strip().str.upper().map({"TRUE": True, "FALSE": False, "1": True, "0": False})
        df[c] = df[c].fillna(False).astype(bool)
    for c in INT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df[c] = df[c].fillna(df[c].median()).round().astype(int)
    for c in FLOAT_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df[c] = df[c].fillna(df[c].median()).astype(float)
    df["production_impact_pct"] = df["production_impact_pct"].clip(0, 100)
    df["revenue_loss_usd"] = df["revenue_loss_usd"].clip(lower=0)
    df["disruption_severity"] = df["disruption_severity"].clip(1, 5)
    for c in ["disruption_type", "industry", "supplier_region", "supplier_size", "response_type"]:
        df[c] = df[c].astype(str).str.strip()
    log.info("Cleaned dataset: %d -> %d rows", before, len(df))
    return df.reset_index(drop=True)


def derive_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["recovery_gap_days"] = (df["full_recovery_days"] - df["partial_recovery_days"]).clip(lower=0)
    q = df["revenue_loss_usd"].quantile([0.25, 0.5, 0.9]).values
    df["loss_bucket"] = pd.cut(df["revenue_loss_usd"], bins=[-1, q[0], q[1], q[2], np.inf],
                               labels=["low", "medium", "high", "critical"]).astype(str)

    # Composite impact score (0-1): production, (log) financial loss and recovery duration.
    def norm(s):
        return (s - s.min()) / (s.max() - s.min() + 1e-9)

    df["impact_score"] = (norm(df["production_impact_pct"]) + norm(np.log1p(df["revenue_loss_usd"]))
                          + norm(df["full_recovery_days"])) / 3
    df["high_impact"] = (df["impact_score"] >= df["impact_score"].quantile(0.75)).astype(int)

    # Response effectiveness (0-100): how fast this case recovered relative to cases of the same type & severity.
    pct = df.groupby(["disruption_type", "disruption_severity"])["full_recovery_days"].rank(pct=True)
    df["response_effectiveness"] = ((1 - pct) * 100).round(1)
    return df


def money(v: float) -> str:
    return f"${v / 1e6:.2f}M" if v >= 1e6 else f"${v / 1e3:.0f}K"


def build_narrative(r) -> str:
    backup = "with a backup supplier available" if r["has_backup_supplier"] else "with no backup supplier"
    change = "the supplier was permanently replaced" if r["permanent_supplier_change"] else "the original supplier was retained"
    return (
        f"{SEVERITY_WORDS[int(r['disruption_severity'])].capitalize()} severity {r['disruption_severity']} "
        f"{r['disruption_type']} ({TYPE_DESCRIPTORS.get(r['disruption_type'], r['disruption_type'])}) "
        f"affecting a {TIER_WORDS[int(r['supplier_tier'])]} {r['supplier_size'].lower()}-sized "
        f"{r['industry']} supplier in {r['supplier_region']} {backup}. "
        f"Production dropped {r['production_impact_pct']:.1f}% with revenue loss of {money(r['revenue_loss_usd'])} "
        f"({r['loss_bucket']} loss). Response: {r['response_type']} initiated after {r['response_time_days']} days. "
        f"Partial recovery in {r['partial_recovery_days']} days, full recovery in {r['full_recovery_days']} days; {change}."
    )


@lru_cache(maxsize=1)
def load_dataset() -> pd.DataFrame:
    """Load the processed dataset (cached parquet if present)."""
    if settings.PROCESSED_PATH.exists():
        return pd.read_parquet(settings.PROCESSED_PATH)
    df = derive_features(clean(load_raw()))
    df["narrative"] = df.apply(build_narrative, axis=1)
    df.to_parquet(settings.PROCESSED_PATH, index=False)
    log.info("Processed dataset saved to %s", settings.PROCESSED_PATH)
    return df


def stratified_sample(df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    if n <= 0 or n >= len(df):
        return df
    return (df.groupby(["disruption_type", "disruption_severity"])
              .sample(frac=n / len(df), random_state=seed)
              .reset_index(drop=True))
