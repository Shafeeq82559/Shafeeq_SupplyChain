"""Retrieval and classification evaluation (no LLM judge required).

Retrieval relevance: a retrieved case is relevant if it has the same disruption type and industry as the
scenario and severity within +/-1. Compares keyword-only, semantic-only and hybrid retrieval, and hybrid
with classifier-derived metadata filters. Metrics: Precision@k, Hit@1, Hit@k, MRR, nDCG@k.
Classification: accuracy per attribute and severity MAE for the rule engine and the LLM agent.
"""
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from src.agents.classifier_agent import classify, rule_classify
from src.rag.hybrid_retriever import hybrid_search
from src.services import llm_client


def _relevant(case: dict, exp: dict) -> bool:
    return (case["disruption_type"] == exp["disruption_type"] and case["industry"] == exp["industry"]
            and abs(case["disruption_severity"] - exp["disruption_severity"]) <= 1)


def _metrics(rels: list[list[int]], k: int) -> dict:
    p = [sum(r[:k]) / k for r in rels]
    hit1 = [r[0] if r else 0 for r in rels]
    hitk = [int(any(r[:k])) for r in rels]
    mrr = [next((1 / (i + 1) for i, x in enumerate(r) if x), 0) for r in rels]
    ndcg = []
    for r in rels:
        dcg = sum(x / math.log2(i + 2) for i, x in enumerate(r[:k]))
        ideal = sum(1 / math.log2(i + 2) for i in range(min(k, max(1, sum(r)))))
        ndcg.append(dcg / ideal if ideal else 0)
    return {f"precision@{k}": round(float(np.mean(p)), 4), "hit@1": round(float(np.mean(hit1)), 4),
            f"hit@{k}": round(float(np.mean(hitk)), 4), "MRR": round(float(np.mean(mrr)), 4),
            f"nDCG@{k}": round(float(np.mean(ndcg)), 4)}


def evaluate_retrieval(golden: list[dict], k: int = 10) -> dict:
    configs = {"keyword (BM25)": dict(mode="keyword"), "semantic (vector)": dict(mode="semantic"),
               "hybrid (RRF)": dict(mode="hybrid")}
    results, examples = {}, []
    for name, cfg in configs.items():
        rels = []
        for g in golden:
            res = hybrid_search(g["query"], top_k=k + 1, **cfg)["results"]
            res = [c for c in res if c["disruption_id"] != g["id"]][:k]
            rels.append([int(_relevant(c, g["expected"])) for c in res])
        results[name] = _metrics(rels, k)
    # Hybrid + metadata filters derived by the (rule-based) classification agent
    rels = []
    for g in golden:
        c = rule_classify(g["query"])
        f = {k2: [v] for k2, v in (("disruption_type", c["disruption_type"]), ("industry", c["industry"])) if v}
        res = [x for x in hybrid_search(g["query"], top_k=k + 1, filters=f)["results"] if x["disruption_id"] != g["id"]][:k]
        rels.append([int(_relevant(x, g["expected"])) for x in res])
        if len(examples) < 3:
            examples.append({"query": g["query"], "filters": f,
                             "top3": [{key: x[key] for key in ("disruption_id", "disruption_type", "industry",
                                                                 "disruption_severity", "hybrid_score")} for x in res[:3]]})
    results["hybrid + auto metadata filters"] = _metrics(rels, k)
    # Sensitivity of hybrid fusion to the semantic weight alpha (no filters)
    sweep = {}
    for alpha in (0.3, 0.5, 0.6, 0.7, 0.8, 0.9):
        rels = []
        for g in golden:
            res = [c for c in hybrid_search(g["query"], top_k=k + 1, alpha=alpha)["results"] if c["disruption_id"] != g["id"]][:k]
            rels.append([int(_relevant(c, g["expected"])) for c in res])
        sweep[str(alpha)] = _metrics(rels, k)
    return {"k": k, "n_queries": len(golden), "relevance_definition": "same type & industry, severity +/-1",
            "results": results, "alpha_sweep": sweep, "examples": examples}


def evaluate_classification(golden: list[dict], use_llm: bool = True) -> dict:
    fields = ["disruption_type", "industry", "supplier_region", "supplier_tier", "has_backup_supplier"]
    out = {}
    engines = {"rules": rule_classify}
    if use_llm and llm_client.llm_available():
        engines["llm_agent"] = classify
    for name, fn in engines.items():
        with ThreadPoolExecutor(max_workers=4) as pool:
            preds = list(pool.map(lambda g: fn(g["query"]), golden))
        acc = {f: round(float(np.mean([p.get(f) == g["expected"][f] for p, g in zip(preds, golden)])), 4) for f in fields}
        sev_err = [abs(p["estimated_severity"] - g["expected"]["disruption_severity"]) for p, g in zip(preds, golden)]
        out[name] = {"accuracy": acc, "severity_MAE": round(float(np.mean(sev_err)), 3),
                     "severity_within_1": round(float(np.mean([e <= 1 for e in sev_err])), 4)}
    return {"n_queries": len(golden), "results": out}
