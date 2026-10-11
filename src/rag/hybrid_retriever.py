"""Hybrid retriever: semantic (Chroma) + keyword (BM25) fused with weighted Reciprocal Rank Fusion,
with metadata filtering applied to both retrievers and optional feedback-based boosts."""
from functools import lru_cache

import numpy as np
import pandas as pd

from src.config import settings
from src.rag.keyword_index import get_keyword_index
from src.rag.preprocessing import load_dataset
from src.rag.vector_store import exact_search, semantic_search

CASE_FIELDS = ["disruption_id", "disruption_type", "industry", "supplier_tier", "supplier_region", "supplier_size",
               "has_backup_supplier", "disruption_severity", "production_impact_pct", "revenue_loss_usd",
               "response_type", "response_time_days", "partial_recovery_days", "full_recovery_days",
               "permanent_supplier_change", "response_effectiveness", "narrative"]


@lru_cache(maxsize=1)
def indexed_frame() -> pd.DataFrame:
    """Rows that are present in the indexes, in keyword-index order, keyed by disruption_id."""
    df = load_dataset()
    ids = get_keyword_index().ids
    return df.set_index("disruption_id").loc[ids].reset_index()


def filter_mask(df: pd.DataFrame, filters: dict | None) -> np.ndarray | None:
    if not filters:
        return None
    m = np.ones(len(df), dtype=bool)
    for field in ["disruption_type", "industry", "supplier_region", "supplier_size", "response_type", "supplier_tier"]:
        v = filters.get(field)
        if v is None or v == [] or v == "":
            continue
        m &= df[field].isin(v if isinstance(v, list) else [v]).to_numpy()
    if filters.get("has_backup_supplier") is not None:
        m &= (df["has_backup_supplier"] == bool(filters["has_backup_supplier"])).to_numpy()
    if filters.get("disruption_severity") is not None:
        m &= (df["disruption_severity"] == int(filters["disruption_severity"])).to_numpy()
    if filters.get("min_severity") is not None:
        m &= (df["disruption_severity"] >= int(filters["min_severity"])).to_numpy()
    if filters.get("max_severity") is not None:
        m &= (df["disruption_severity"] <= int(filters["max_severity"])).to_numpy()
    return m


def clean_filters(filters: dict | None) -> dict:
    return {k: v for k, v in (filters or {}).items() if v not in (None, "", [])}


def hybrid_search(query: str, top_k: int = None, filters: dict | None = None, alpha: float = None,
                  mode: str = "hybrid", boosts: dict[str, float] | None = None) -> dict:
    """mode: 'hybrid' | 'semantic' | 'keyword'. alpha = weight of the semantic ranking in fusion."""
    top_k = top_k or settings.DEFAULT_TOP_K
    alpha = settings.HYBRID_ALPHA if alpha is None else alpha
    filters = clean_filters(filters)
    df = indexed_frame()
    mask = filter_mask(df, filters)
    matched = int(mask.sum()) if mask is not None else len(df)
    if matched == 0:
        return {"results": [], "total_matching_filters": 0, "mode": mode, "alpha": alpha}

    pool = max(settings.CANDIDATE_POOL, top_k * 5)
    if mode not in ("hybrid", "semantic"):
        sem = []
    elif mask is not None and matched < len(df):  # filtered: exact search over just the allowed cases (see vector_store.get_vectors)
        sem = exact_search(query, min(pool, matched), df["disruption_id"].to_numpy()[mask])
    else:
        sem = semantic_search(query, min(pool, matched), filters)
    kw = get_keyword_index().search(query, pool, mask) if mode in ("hybrid", "keyword") else []

    k = settings.RRF_K
    fused: dict[str, dict] = {}
    for rank, (cid, sim) in enumerate(sem, 1):
        e = fused.setdefault(cid, {"semantic_score": None, "keyword_score": None, "semantic_rank": None, "keyword_rank": None})
        e.update(semantic_score=sim, semantic_rank=rank)
    for rank, (cid, s) in enumerate(kw, 1):
        e = fused.setdefault(cid, {"semantic_score": None, "keyword_score": None, "semantic_rank": None, "keyword_rank": None})
        e.update(keyword_score=s, keyword_rank=rank)

    w_sem, w_kw = (alpha, 1 - alpha) if mode == "hybrid" else ((1.0, 0.0) if mode == "semantic" else (0.0, 1.0))
    max_rrf = (w_sem + w_kw) / (k + 1)
    for cid, e in fused.items():
        s = 0.0
        if e["semantic_rank"]:
            s += w_sem / (k + e["semantic_rank"])
        if e["keyword_rank"]:
            s += w_kw / (k + e["keyword_rank"])
        if boosts and cid in boosts:
            s *= boosts[cid]
        e["hybrid_score"] = round(s / max_rrf, 4)  # normalised to 0-1 (1 = ranked first by both)

    ranked = sorted(fused.items(), key=lambda x: -x[1]["hybrid_score"])[:top_k]
    rows = df.set_index("disruption_id").loc[[cid for cid, _ in ranked]].reset_index()
    results = []
    for (cid, scores), (_, row) in zip(ranked, rows.iterrows()):
        case = {f: (row[f].item() if hasattr(row[f], "item") else row[f]) for f in CASE_FIELDS}
        results.append({**case, **scores})
    return {"results": results, "total_matching_filters": matched, "mode": mode, "alpha": alpha}
