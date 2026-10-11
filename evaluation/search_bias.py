"""Does the word "supplier" in a query pull the results towards "Alternative Supplier" cases? (no LLM needed)

Case narratives end with the response that was taken ("Response: Alternative Supplier initiated after ..."), so a query
containing "supplier" could match that label instead of the disruption. A plain comparison of queries with and without
the word is confounded by phrasing (queries without it are all the short keyword style), so this runs a PAIRED test:
every evaluation query that contains the word is searched twice, as written and with the word removed, and the share of
the top-10 results whose response is "Alternative Supplier" is compared.

Run:  python -m evaluation.search_bias        -> evaluation/results/search_bias.json
"""
import json
import re
import time

import numpy as np

from evaluation.search_eval import K, build_queries
from src.config import settings
from src.rag.hybrid_retriever import hybrid_search, indexed_frame

TARGET = "Alternative Supplier"
WORD = re.compile(r"\bsuppliers?\b", re.I)


def share(query: str) -> float:
    res = hybrid_search(query, K)["results"]
    return float(np.mean([c["response_type"] == TARGET for c in res])) if res else float("nan")


def main():
    t0 = time.time()
    rng = np.random.default_rng(0)
    base = float((indexed_frame()["response_type"] == TARGET).mean())
    qs = build_queries()
    with_word = [q for q in qs if WORD.search(q["query"])]
    without_word = [q for q in qs if not WORD.search(q["query"])]
    hybrid_search("warm up", 3)

    paired = []
    for q in with_word:
        stripped = re.sub(r"\s+", " ", WORD.sub("", q["query"])).strip()
        paired.append((share(q["query"]), share(stripped)))
    a = np.array([p[0] for p in paired]); b = np.array([p[1] for p in paired])
    diffs = a - b
    boots = [diffs[rng.integers(0, len(diffs), len(diffs))].mean() for _ in range(2000)]
    out = {
        "question": f"Share of the top {K} results that are '{TARGET}' cases",
        "dataset_share_alternative_supplier": round(base, 4),
        "queries_containing_the_word": len(with_word), "queries_without_the_word": len(without_word),
        "unpaired_comparison": {
            "with_word": round(float(np.mean([share(q["query"]) for q in with_word])), 4),
            "without_word": round(float(np.mean([share(q["query"]) for q in without_word])), 4),
            "caveat": "Confounded: the queries without the word are all the short keyword phrasing."},
        "paired_test": {
            "n_pairs": len(paired), "as_written": round(float(a.mean()), 4), "word_removed": round(float(b.mean()), 4),
            "mean_difference": round(float(diffs.mean()), 4),
            "ci95": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)],
            "queries_where_share_rose": int((diffs > 0).sum()), "queries_where_share_fell": int((diffs < 0).sum())},
        "seconds": round(time.time() - t0)}
    (settings.EVAL_DIR / "search_bias.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
