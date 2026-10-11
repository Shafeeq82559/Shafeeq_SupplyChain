"""DeepEval evaluation of disruption-analysis and recommendation quality.

The system's own LLM endpoint (OpenAI-compatible, gpt-5-nano by default) is wrapped as a DeepEval custom
model. Metrics per test case:
- AnswerRelevancy, Faithfulness (grounded in retrieved cases), ContextualPrecision, ContextualRecall
- G-Eval "Recommendation Quality" and "Disruption Analysis Correctness" (custom rubrics)
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from deepeval.metrics import (AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,
                              FaithfulnessMetric, GEval)
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from src.agents.classifier_agent import classify
from src.agents.investigation_agent import investigate
from src.agents.judge_agent import judge
from src.agents.response_agent import plan_response
from src.config import settings
from src.services import llm_client

WORKERS = int(os.getenv("EVAL_WORKERS", "4"))  # parallel scenarios (each LLM call is throttled globally)


class CompatibleLLM(DeepEvalBaseLLM):
    """DeepEval adapter for the project's OpenAI-compatible endpoint."""

    def __init__(self):
        # DeepEval's base class strips provider prefixes ("nvidia/x" -> "x"), which breaks namespaced model IDs,
        # so the exact API model ID is kept separately.
        self.api_model = settings.JUDGE_MODEL
        super().__init__(self.api_model)

    def load_model(self):
        return self

    def generate(self, prompt: str, schema=None):
        if schema is not None:
            out = llm_client.complete_json("You are an evaluation assistant. Follow the requested JSON format exactly.",
                                           prompt, max_tokens=3000, model=self.api_model)
            if out is None:
                raise ValueError("LLM returned no JSON")
            return schema.model_validate(out)
        return llm_client.complete_text("You are an evaluation assistant.", prompt, max_tokens=3000, model=self.api_model) or ""

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self):
        return f"{self.api_model} (OpenAI-compatible)"


def plan_to_text(plan: dict) -> str:
    parts = [f"Recommended strategy: {plan.get('recommended_strategy')}.", f"Rationale: {plan.get('rationale')}"]
    if plan.get("immediate_actions"):
        parts.append("Immediate actions: " + "; ".join(map(str, plan["immediate_actions"])))
    if plan.get("recovery_plan"):
        parts.append("Recovery plan: " + "; ".join(map(str, plan["recovery_plan"])))
    if plan.get("risks"):
        parts.append("Risks: " + "; ".join(map(str, plan["risks"])))
    return "\n".join(parts)


def evidence_contexts(cases: list[dict], ranking: list[dict], summary: str) -> list[str]:
    ctx = [f"Case {c['disruption_id']}: {c['narrative']}" for c in cases]
    ctx.append(f"Historical summary of the similar cases: {summary}")
    for s in ranking:
        h = s.get("historical") or {}
        ctx.append(
            f"Strategy evidence - {s['response_type']} (rank {s['rank']}): expected full recovery ~{s['expected_full_recovery_days']:.0f} "
            f"days, expected revenue loss ${s['expected_revenue_loss_usd']:,.0f}, supplier-change risk "
            f"{100 * s['supplier_change_risk']:.0f}%, used in {s['evidence_cases']} of the similar cases"
            + (f" (historical avg full recovery {h['avg_full_recovery_days']} days, partial {h['avg_partial_recovery_days']} days; "
               f"example cases {', '.join(h.get('example_cases', []))})" if h else "")
            + (f"; model-predicted partial recovery ~{s['predicted']['predicted_partial_recovery_days']:.0f} days"
               if s.get("predicted") else "") + ".")
    return ctx


def generate_outputs(golden: list[dict], path) -> list[dict]:
    """Run the recommendation pipeline on each scenario; cached so DeepEval and RAGAS score identical outputs."""
    def one(g):
        t0 = time.time()
        c = classify(g["query"])
        inv = investigate(g["query"], c, top_k=8)
        r = plan_response(g["query"], inv["profile"], inv["similar_cases"], pool=inv.get("strategy_pool"))
        evidence = {"classification": c, "case_ids": [x["disruption_id"] for x in inv["similar_cases"]],
                    "fact_sheet": r["plan"].get("fact_sheet"),
                    "historical_summary": inv["historical_summary"],
                    "strategy_ranking": [{k: v for k, v in s.items() if k not in ("historical", "predicted")}
                                         for s in r["strategy_ranking"]]}
        j = judge(g["query"], evidence, {"response_plan": r["plan"]})
        return {"id": g["id"], "query": g["query"], "expected": g["expected"], "reference": g["reference_answer"],
                     "classification": {k: c.get(k) for k in ("disruption_type", "industry", "supplier_region",
                                                               "estimated_severity", "method")},
                     "answer": plan_to_text(r["plan"]), "plan": r["plan"],
                     # Evaluate against exactly the evidence the planner received: cited cases (with IDs) plus the
                     # strategy statistics / model predictions it reasons over.
                     "contexts": ([ln.lstrip("- ") for ln in r["plan"]["fact_sheet"].splitlines() if ln.strip()]
                                  if r["plan"].get("fact_sheet") else
                                  evidence_contexts(inv["similar_cases"], r["strategy_ranking"], inv["historical_summary"])),
                     "historical_summary": inv["historical_summary"], "judge": j,
                     "latency_s": round(time.time() - t0, 2)}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:  # LLM latency-bound: run scenarios in parallel
        rows = list(pool.map(one, golden))
    path.write_text(json.dumps(rows, indent=2, default=str))
    return rows


def run_deepeval(outputs: list[dict]) -> dict:
    model = CompatibleLLM()
    metric_factories = {
        "answer_relevancy": lambda: AnswerRelevancyMetric(model=model, threshold=0.7, async_mode=False),
        "faithfulness": lambda: FaithfulnessMetric(model=model, threshold=0.7, async_mode=False),
        "contextual_precision": lambda: ContextualPrecisionMetric(model=model, threshold=0.5, async_mode=False),
        "contextual_recall": lambda: ContextualRecallMetric(model=model, threshold=0.5, async_mode=False),
        "recommendation_quality": lambda: GEval(
            name="Recommendation Quality", model=model, threshold=0.6, async_mode=False,
            criteria="Assess whether the actual output gives a specific, actionable supply chain response and recovery "
                     "recommendation that is consistent with the expected output's recommended strategy (or one of "
                     "the acceptable alternatives it lists) and is justified with historical evidence and timelines.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT]),
        "analysis_correctness": lambda: GEval(
            name="Disruption Analysis Correctness", model=model, threshold=0.6, async_mode=False,
            criteria="Check that the actual output correctly characterises the disruption described in the input "
                     "(type, industry, severity) and that its claims about similar historical cases are supported by "
                     "the retrieval context.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT,
                               LLMTestCaseParams.RETRIEVAL_CONTEXT]),
    }
    def score_case(o):
        tc = LLMTestCase(input=o["query"], actual_output=o["answer"], expected_output=o["reference"],
                         retrieval_context=o["contexts"])
        row = {"id": o["id"]}
        for name, make in metric_factories.items():
            m = make()
            try:
                m.measure(tc)
                row[name] = {"score": round(float(m.score), 4), "passed": bool(m.is_successful()),
                             "reason": (m.reason or "")[:300]}
            except Exception as e:  # keep evaluating other metrics/cases
                row[name] = {"score": None, "error": f"{type(e).__name__}: {str(e)[:150]}"}
        return row

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        per_case = list(pool.map(score_case, outputs))
    scores = {k: [r[k]["score"] for r in per_case if r[k].get("score") is not None] for k in metric_factories}
    summary = {k: {"mean": round(sum(v) / len(v), 4) if v else None, "n": len(v)} for k, v in scores.items()}
    return {"framework": "DeepEval", "judge_model": model.get_model_name(), "n_cases": len(outputs),
            "summary": summary, "per_case": per_case}
