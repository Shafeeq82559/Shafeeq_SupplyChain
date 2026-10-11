"""Semantic retrieval: sentence-transformer embeddings stored in a persistent ChromaDB collection."""
from functools import lru_cache

import chromadb
import numpy as np
import pandas as pd

from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)

METADATA_FIELDS = ["disruption_type", "industry", "supplier_tier", "supplier_region", "supplier_size",
                   "has_backup_supplier", "disruption_severity", "response_type"]


@lru_cache(maxsize=1)
def get_embedder():
    from sentence_transformers import SentenceTransformer
    log.info("Loading embedding model %s", settings.EMBEDDING_MODEL)
    try:  # local cache first: skips a network check that can stall for minutes when the model hub is slow
        return SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu", local_files_only=True)
    except Exception:  # first run on a new machine: download it
        return SentenceTransformer(settings.EMBEDDING_MODEL, device="cpu")


def embed(texts: list[str], batch_size: int = 256, show_progress: bool = False) -> np.ndarray:
    return get_embedder().encode(texts, batch_size=batch_size, normalize_embeddings=True,
                                 show_progress_bar=show_progress, convert_to_numpy=True)


def _client():
    return chromadb.PersistentClient(path=str(settings.CHROMA_DIR))


def build_collection(df: pd.DataFrame, batch: int = 5000):
    client = _client()
    try:
        client.delete_collection(settings.COLLECTION_NAME)
    except Exception:
        pass
    (settings.ARTIFACTS_DIR / "embeddings_cache.npz").unlink(missing_ok=True)  # the in-memory copy is rebuilt from the new index
    col = client.create_collection(settings.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    log.info("Embedding %d narratives (one-time)...", len(df))
    vectors = embed(df["narrative"].tolist(), show_progress=True)
    metas = df[METADATA_FIELDS].to_dict("records")
    for m in metas:
        m["supplier_tier"] = int(m["supplier_tier"])
        m["disruption_severity"] = int(m["disruption_severity"])
        m["has_backup_supplier"] = bool(m["has_backup_supplier"])
    ids = df["disruption_id"].tolist()
    for i in range(0, len(df), batch):
        col.add(ids=ids[i:i + batch], embeddings=vectors[i:i + batch].tolist(),
                metadatas=metas[i:i + batch], documents=df["narrative"].iloc[i:i + batch].tolist())
        log.info("  added %d/%d", min(i + batch, len(df)), len(df))
    return col


@lru_cache(maxsize=1)
def get_collection():
    return _client().get_collection(settings.COLLECTION_NAME)


@lru_cache(maxsize=1)
def get_vectors() -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """All case embeddings in memory (ids, unit-length float32 matrix, id -> row). Used for exact filtered search:
    ChromaDB's metadata filtering over 100k rows costs 0.3-6 s per query, a matrix product over the allowed rows ~30 ms.
    Cached on disk next to the index; the cache is ignored when the collection size differs."""
    cache = settings.ARTIFACTS_DIR / "embeddings_cache.npz"
    col = get_collection()
    n = col.count()
    if cache.exists():
        try:
            z = np.load(cache, allow_pickle=False)
            if len(z["ids"]) == n:
                ids = z["ids"]
                return ids, z["vectors"], {i: k for k, i in enumerate(ids.tolist())}
        except Exception:  # unreadable cache: rebuild it below
            pass
    ids_l, parts = [], []
    for off in range(0, n, 10000):
        r = col.get(limit=10000, offset=off, include=["embeddings"])
        ids_l += r["ids"]
        parts.append(np.asarray(r["embeddings"], dtype=np.float32))
    ids, vectors = np.array(ids_l), np.vstack(parts)
    try:
        np.savez(cache, ids=ids, vectors=vectors)
    except OSError:
        pass
    return ids, vectors, {i: k for k, i in enumerate(ids_l)}


def exact_search(query: str, n: int, allowed_ids: np.ndarray) -> list[tuple[str, float]]:
    """Cosine ranking of `query` against only the cases in `allowed_ids` (exact, unlike the approximate HNSW index)."""
    _, vectors, row = get_vectors()
    rows = np.fromiter((row[i] for i in allowed_ids.tolist() if i in row), dtype=np.int64)
    if not len(rows):
        return []
    sims = vectors[rows] @ embed([query])[0].astype(np.float32)
    n = min(n, len(rows))
    top = np.argpartition(-sims, n - 1)[:n]
    top = top[np.argsort(-sims[top])]
    kept = allowed_ids[[k for k, i in enumerate(allowed_ids.tolist()) if i in row]]
    return [(str(kept[j]), round(float(sims[j]), 4)) for j in top]


def to_chroma_where(filters: dict | None) -> dict | None:
    """Translate API filters into a Chroma `where` clause."""
    if not filters:
        return None
    clauses = []
    for field in ["disruption_type", "industry", "supplier_region", "supplier_size", "response_type"]:
        v = filters.get(field)
        if v:
            clauses.append({field: {"$in": v}} if isinstance(v, list) else {field: {"$eq": v}})
    if filters.get("supplier_tier") is not None:
        v = filters["supplier_tier"]
        clauses.append({"supplier_tier": {"$in": v}} if isinstance(v, list) else {"supplier_tier": {"$eq": int(v)}})
    if filters.get("has_backup_supplier") is not None:
        clauses.append({"has_backup_supplier": {"$eq": bool(filters["has_backup_supplier"])}})
    if filters.get("disruption_severity") is not None:
        clauses.append({"disruption_severity": {"$eq": int(filters["disruption_severity"])}})
    if filters.get("min_severity") is not None:
        clauses.append({"disruption_severity": {"$gte": int(filters["min_severity"])}})
    if filters.get("max_severity") is not None:
        clauses.append({"disruption_severity": {"$lte": int(filters["max_severity"])}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def semantic_search(query: str, n: int, filters: dict | None = None) -> list[tuple[str, float]]:
    """Return [(disruption_id, cosine_similarity)] ranked best-first."""
    col = get_collection()
    qv = embed([query])[0].tolist()
    res = col.query(query_embeddings=[qv], n_results=n, where=to_chroma_where(filters), include=["distances"])
    ids = res["ids"][0] if res["ids"] else []
    dists = res["distances"][0] if res.get("distances") else []
    return [(i, round(1 - d, 4)) for i, d in zip(ids, dists)]
