"""Keyword retrieval: BM25 (Okapi) implemented over a sparse term matrix.

A sparse-matrix BM25 scores 100k documents in milliseconds and serializes compactly,
unlike per-document Python dictionaries.
"""
import pickle
import re
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import CountVectorizer

from src.config import settings

STOPWORDS = {"a", "an", "the", "of", "in", "on", "with", "and", "or", "to", "for", "was", "is", "at", "by",
             "after", "as", "such", "our", "we", "has", "had", "be", "been", "this", "that", "it", "its"}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.vectorizer: CountVectorizer | None = None
        self.weights: sparse.csc_matrix | None = None
        self.ids: np.ndarray | None = None

    def fit(self, ids: list[str], docs: list[str]) -> "BM25Index":
        self.vectorizer = CountVectorizer(tokenizer=tokenize, lowercase=False, token_pattern=None, ngram_range=(1, 2))
        tf = self.vectorizer.fit_transform(docs).tocsr().astype(np.float32)
        n_docs = tf.shape[0]
        doc_len = np.asarray(tf.sum(axis=1)).ravel()
        avgdl = doc_len.mean()
        df = np.bincount(tf.indices, minlength=tf.shape[1])
        idf = np.log((n_docs - df + 0.5) / (df + 0.5) + 1.0).astype(np.float32)
        # BM25 term weight per (doc, term), precomputed once.
        rows = np.repeat(np.arange(n_docs), np.diff(tf.indptr))
        denom = tf.data + self.k1 * (1 - self.b + self.b * doc_len[rows] / avgdl)
        tf.data = idf[tf.indices] * tf.data * (self.k1 + 1) / denom
        self.weights = tf.tocsc()
        self.ids = np.array(ids)
        return self

    def scores(self, query: str) -> np.ndarray:
        q = self.vectorizer.transform([query])
        cols = q.indices
        if len(cols) == 0:
            return np.zeros(len(self.ids), dtype=np.float32)
        return np.asarray(self.weights[:, cols].sum(axis=1)).ravel()

    def search(self, query: str, n: int, mask: np.ndarray | None = None) -> list[tuple[str, float]]:
        s = self.scores(query)
        if mask is not None:
            s = np.where(mask, s, -np.inf)
        n = min(n, len(s))
        top = np.argpartition(-s, n - 1)[:n]
        top = top[np.argsort(-s[top])]
        return [(self.ids[i], round(float(s[i]), 4)) for i in top if np.isfinite(s[i]) and s[i] > 0]

    def save(self, path=None):
        with open(path or settings.BM25_PATH, "wb") as f:
            pickle.dump(self, f)


def build_keyword_index(df: pd.DataFrame) -> BM25Index:
    idx = BM25Index().fit(df["disruption_id"].tolist(), df["narrative"].tolist())
    idx.save()
    return idx


@lru_cache(maxsize=1)
def get_keyword_index() -> BM25Index:
    with open(settings.BM25_PATH, "rb") as f:
        return pickle.load(f)
