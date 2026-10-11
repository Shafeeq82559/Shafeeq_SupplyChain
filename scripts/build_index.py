"""One-time build: preprocess dataset, write sample data, build ChromaDB vector index and BM25 keyword index.

Usage:  python -m scripts.build_index            (indexes all rows, or INDEX_SAMPLE_SIZE from .env)
        python -m scripts.build_index --sample 20000
"""
import argparse
import time

from src.config import settings
from src.rag.keyword_index import build_keyword_index
from src.rag.preprocessing import load_dataset, stratified_sample
from src.rag.vector_store import build_collection
from src.utils.logger import get_logger

log = get_logger("build_index")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=settings.INDEX_SAMPLE_SIZE, help="0 = all rows")
    args = p.parse_args()
    t0 = time.time()
    if settings.PROCESSED_PATH.exists():
        settings.PROCESSED_PATH.unlink()  # always rebuild from the CSV
    load_dataset.cache_clear()
    df = load_dataset()
    log.info("Dataset: %d rows", len(df))

    settings.SAMPLE_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw_cols = [c for c in df.columns if c in pd_cols()]
    stratified_sample(df, 1000)[raw_cols].to_csv(settings.SAMPLE_DATA_PATH, index=False)

    idx_df = stratified_sample(df, args.sample)
    log.info("Indexing %d rows", len(idx_df))
    build_keyword_index(idx_df)
    log.info("BM25 index built (%.0fs)", time.time() - t0)
    build_collection(idx_df)
    log.info("Done in %.0fs", time.time() - t0)


def pd_cols():
    return ["disruption_id", "disruption_type", "industry", "supplier_tier", "supplier_region", "supplier_size",
            "has_backup_supplier", "disruption_severity", "production_impact_pct", "revenue_loss_usd", "response_type",
            "response_time_days", "partial_recovery_days", "full_recovery_days", "permanent_supplier_change"]


if __name__ == "__main__":
    main()
