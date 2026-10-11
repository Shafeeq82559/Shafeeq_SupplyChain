"""Feedback loop for continuous improvement (SQLite).

Captured: rating (1-5), thumbs up/down, comment, the strategy recommended vs. the strategy actually
chosen, cited cases, and optionally the real outcome of the disruption.

Used to improve the system in three ways:
1. Strategy re-ranking: per-strategy multipliers from average ratings (bounded 0.85-1.15).
2. Case boosts: cases cited in highly rated answers get a small retrieval boost.
3. Few-shot memory: top-rated plans are injected as examples into the planning prompt.
4. Retraining: user-reported real outcomes are appended to the ML training data (/feedback/retrain).
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pandas as pd

from src.config import settings

SCHEMA = """CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    query TEXT,
    endpoint TEXT,
    rating INTEGER,
    helpful INTEGER,
    comment TEXT,
    recommended_strategy TEXT,
    chosen_strategy TEXT,
    cited_cases TEXT,
    plan_text TEXT,
    outcome TEXT
)"""


@contextmanager
def _conn():
    con = sqlite3.connect(settings.FEEDBACK_DB)
    try:
        con.execute(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def add_feedback(item: dict) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO feedback (created_at, query, endpoint, rating, helpful, comment, recommended_strategy, "
            "chosen_strategy, cited_cases, plan_text, outcome) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), item.get("query"), item.get("endpoint", "analyze"),
             item.get("rating"), None if item.get("helpful") is None else int(item["helpful"]), item.get("comment"),
             item.get("recommended_strategy"), item.get("chosen_strategy"), json.dumps(item.get("cited_cases") or []),
             item.get("plan_text"), json.dumps(item["outcome"]) if item.get("outcome") else None))
        return cur.lastrowid


def _frame() -> pd.DataFrame:
    with _conn() as con:
        return pd.read_sql_query("SELECT * FROM feedback", con)


def strategy_multipliers() -> dict[str, float]:
    df = _frame()
    if df.empty:
        return {}
    df = df.dropna(subset=["rating"])
    out = {}
    for col in ("recommended_strategy", "chosen_strategy"):
        for s, g in df.dropna(subset=[col]).groupby(col):
            # rating 3 = neutral; each point above/below shifts the score by 5%, bounded, shrunk for few votes
            shift = (g["rating"].mean() - 3) * 0.05 * min(1.0, len(g) / 5)
            out[s] = out.get(s, 1.0) + shift
    return {k: round(min(1.15, max(0.85, v)), 3) for k, v in out.items()}


def case_boosts() -> dict[str, float]:
    df = _frame()
    boosts: dict[str, float] = {}
    for _, r in df.dropna(subset=["rating"]).iterrows():
        delta = 0.03 if r["rating"] >= 4 else (-0.03 if r["rating"] <= 2 else 0)
        for cid in json.loads(r["cited_cases"] or "[]"):
            boosts[cid] = boosts.get(cid, 1.0) + delta
    return {k: min(1.2, max(0.8, v)) for k, v in boosts.items()}


def few_shot_examples(n: int = 2) -> list[str]:
    df = _frame()
    if df.empty:
        return []
    good = df[(df["rating"] >= 5) & df["plan_text"].notna()].sort_values("created_at", ascending=False)
    return good["plan_text"].head(n).tolist()


def outcome_rows() -> pd.DataFrame:
    """Real outcomes reported by users, in training-data format."""
    rows = []
    for o in _frame()["outcome"].dropna():
        try:
            rows.append(json.loads(o))
        except json.JSONDecodeError:
            continue
    return pd.DataFrame(rows)


def stats() -> dict:
    df = _frame()
    if df.empty:
        return {"total_feedback": 0, "average_rating": None, "helpful_rate": None, "by_strategy": {},
                "strategy_multipliers": {}, "recent": [], "outcomes_reported": 0}
    df["day"] = df["created_at"].str[:10]
    return {
        "total_feedback": int(len(df)),
        "average_rating": round(float(df["rating"].mean()), 2) if df["rating"].notna().any() else None,
        "helpful_rate": round(float(df["helpful"].mean()), 3) if df["helpful"].notna().any() else None,
        "by_strategy": {k: {"count": int(len(g)), "avg_rating": round(float(g["rating"].mean()), 2)}
                        for k, g in df.dropna(subset=["recommended_strategy"]).groupby("recommended_strategy")},
        "rating_trend": df.groupby("day")["rating"].mean().round(2).to_dict(),
        "strategy_multipliers": strategy_multipliers(),
        "outcomes_reported": int(df["outcome"].notna().sum()),
        "recent": df.sort_values("created_at", ascending=False).head(10)[
            ["id", "created_at", "rating", "helpful", "recommended_strategy", "chosen_strategy", "comment"]
        ].to_dict("records"),
    }
