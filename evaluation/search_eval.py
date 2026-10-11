"""Evaluation of the Similar-cases search as people actually use it (no LLM needed).

The golden set in golden_set.py has 30 long templated sentences. The Search page gets short, loose queries, so this
builds 180 queries (6 disruption types x 5 industries x 6 phrasings) from real dataset records and measures:

  * retrieval quality of keyword, semantic and hybrid search, and of different semantic weights (alpha)
  * how often the top results match the type / industry (and severity, when the query states it)
  * latency (median and 95th percentile) with and without metadata filters
  * that metadata filters are always obeyed

A retrieved case is "relevant" if it has the same disruption type and industry as the scenario (loose), and for
queries that state a severity also a severity within +/-1 (strict). The set is synthetic (templated phrasing built
from the dataset's own categories), so it checks consistency with the data, not real-world relevance.

Run:  python -m evaluation.search_eval
"""
import json
import math
import random
import time

import numpy as np

from evaluation.golden_set import PHRASES, PLACES, PRODUCTS, SEVERITY_TEXT
from src.config import settings
from src.rag.hybrid_retriever import hybrid_search, indexed_frame

K = 10
SHORT_TYPE = {  # the words a user would type for each type, without the sentence around them
    "Natural Disaster": ["typhoon", "earthquake", "flooding", "hurricane"], "Cyber Attack": ["ransomware", "hackers", "malware outage"],
    "Labor Strike": ["strike", "workers walked out", "union action"], "Port Congestion": ["port congestion", "shipping backlog", "vessel queues"],
    "Geopolitical": ["export sanctions", "trade embargo", "tariffs"], "Factory Incident": ["factory fire", "equipment breakdown", "plant contamination"],
}
CONFIGS = {
    "keyword": dict(mode="keyword"), "semantic": dict(mode="semantic"),
    "hybrid a=0.4": dict(mode="hybrid", alpha=0.4), "hybrid a=0.5": dict(mode="hybrid", alpha=0.5),
    "hybrid a=0.6 (default)": dict(mode="hybrid", alpha=0.6), "hybrid a=0.7": dict(mode="hybrid", alpha=0.7),
}


def build_queries(seed: int = 11, per_cell: int = 6) -> list[dict]:
    rng = random.Random(seed)
    df = indexed_frame()
    out = []
    for (t, ind), g in df.groupby(["disruption_type", "industry"]):
        recs = g.sample(per_cell, random_state=seed).itertuples()
        for style, r in enumerate(recs):
            word, place, prod = rng.choice(SHORT_TYPE[t]), rng.choice(PLACES[r.supplier_region]), PRODUCTS[ind]
            sev = int(r.disruption_severity)
            texts = [
                (f"{word} {prod}", False),                                                        # two or three words
                (f"{word} {prod} supplier {place}", False),                                       # keywords plus place
                (f"{word} at our {prod} supplier", False),
                (f"{rng.choice(PHRASES[t])} our Tier-{r.supplier_tier} {prod} supplier in {place}", False),   # full sentence
                (f"{rng.choice(PHRASES[t])} our {prod} supplier in {place}. {SEVERITY_TEXT[sev]}", True),     # states severity
                (f"{rng.choice(PHRASES[t])} our Tier-{r.supplier_tier} {r.supplier_size.lower()} {prod} supplier in {place}. {SEVERITY_TEXT[sev]}", True),
            ]
            text, has_sev = texts[style % len(texts)]
            out.append({"id": r.disruption_id, "query": text, "type": t, "industry": ind, "severity": sev, "states_severity": has_sev,
                        "style": ["keywords", "keywords+place", "short sentence", "full sentence", "sentence+severity", "detailed+severity"][style % 6]})
    return out


def _rel(c: dict, q: dict, strict: bool) -> int:
    ok = c["disruption_type"] == q["type"] and c["industry"] == q["industry"]
    return int(ok and (not strict or abs(c["disruption_severity"] - q["severity"]) <= 1))


def _ndcg(r: list[int]) -> float:
    dcg = sum(x / math.log2(i + 2) for i, x in enumerate(r[:K]))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(K, max(1, sum(r)))))
    return dcg / ideal if ideal else 0.0


def _summ(rels: list[list[int]], rng: np.random.Generator) -> dict:
    p = np.array([sum(r[:K]) / K for r in rels])
    boots = [p[rng.integers(0, len(p), len(p))].mean() for _ in range(1000)]
    return {"precision@10": round(float(p.mean()), 4), "ci95": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)],
            "hit@1": round(float(np.mean([r[0] if r else 0 for r in rels])), 4), "hit@10": round(float(np.mean([int(any(r[:K])) for r in rels])), 4),
            "MRR": round(float(np.mean([next((1 / (i + 1) for i, x in enumerate(r) if x), 0) for r in rels])), 4),
            "nDCG@10": round(float(np.mean([_ndcg(r) for r in rels])), 4)}


def main():
    t_all = time.time()
    rng = np.random.default_rng(0)
    qs = build_queries()
    print(f"{len(qs)} queries")
    hybrid_search("warm up", 3)
    results, lat = {}, {}
    for name, cfg in CONFIGS.items():
        loose, strict, times = [], [], []
        for q in qs:
            t = time.time()
            res = [c for c in hybrid_search(q["query"], K + 1, **cfg)["results"] if c["disruption_id"] != q["id"]][:K]
            times.append(1000 * (time.time() - t))
            loose.append([_rel(c, q, False) for c in res])
            if q["states_severity"]:
                strict.append([_rel(c, q, True) for c in res])
        results[name] = {"loose (type + industry)": _summ(loose, rng), "strict (type + industry + severity +/-1)": _summ(strict, rng)}
        lat[name] = {"p50_ms": round(float(np.percentile(times, 50))), "p95_ms": round(float(np.percentile(times, 95)))}
        print(f"{name:24s} P@10 loose {results[name]['loose (type + industry)']['precision@10']:.3f}  strict {results[name]['strict (type + industry + severity +/-1)']['precision@10']:.3f}  p50 {lat[name]['p50_ms']} ms")

    # by phrasing style, default hybrid vs the two single retrievers
    by_style = {}
    for name in ("keyword", "semantic", "hybrid a=0.6 (default)"):
        for style in sorted({q["style"] for q in qs}):
            sub = [q for q in qs if q["style"] == style]
            rels = [[_rel(c, q, False) for c in [x for x in hybrid_search(q["query"], K + 1, **CONFIGS[name])["results"] if x["disruption_id"] != q["id"]][:K]] for q in sub]
            by_style.setdefault(style, {})[name] = round(float(np.mean([sum(r) / K for r in rels])), 4)

    # filters: latency and obedience
    filt = {}
    cases = {"1 filter (type)": lambda q: {"disruption_type": [q["type"]]},
             "2 filters (type + industry)": lambda q: {"disruption_type": [q["type"]], "industry": [q["industry"]]},
             "4 filters (+ severity band, region)": lambda q: {"disruption_type": [q["type"]], "industry": [q["industry"]], "min_severity": max(1, q["severity"] - 1),
                                                              "max_severity": min(5, q["severity"] + 1), "supplier_region": ["Asia-Pacific", "Europe"]}}
    df = indexed_frame().set_index("disruption_id")
    for name, mk in cases.items():
        times, violations, matched = [], 0, []
        for q in qs[::6]:  # 30 queries per filter setup keeps the run short
            f = mk(q)
            t = time.time(); r = hybrid_search(q["query"], K, f); times.append(1000 * (time.time() - t)); matched.append(r["total_matching_filters"])
            for c in r["results"]:
                row = df.loc[c["disruption_id"]]
                bad = any(row[k] not in v for k, v in f.items() if isinstance(v, list)) \
                    or ("min_severity" in f and not f["min_severity"] <= row["disruption_severity"] <= f["max_severity"])
                violations += int(bad)
        filt[name] = {"p50_ms": round(float(np.percentile(times, 50))), "p95_ms": round(float(np.percentile(times, 95))),
                      "median_matching_records": int(np.median(matched)), "results_breaking_a_filter": violations}
        print(f"{name:36s} p50 {filt[name]['p50_ms']} ms  p95 {filt[name]['p95_ms']} ms  violations {violations}")

    out = {"n_queries": len(qs), "k": K, "queries_stating_severity": sum(q["states_severity"] for q in qs), "seconds": round(time.time() - t_all),
           "relevance": "loose = same type and industry; strict = also severity within +/-1 (only queries that state a severity)",
           "results": results, "latency": lat, "by_phrasing_precision_loose": by_style, "filters": filt,
           "examples": [{"query": q["query"], "style": q["style"]} for q in qs[:6]]}
    path = settings.EVAL_DIR / "search_eval.json"
    path.write_text(json.dumps(out, indent=2))
    print("saved", path, f"in {out['seconds']}s")


if __name__ == "__main__":
    main()
