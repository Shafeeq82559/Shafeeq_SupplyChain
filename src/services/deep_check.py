"""On-demand DeepEval check of ONE analysis ("Run deep check"). Optional and separate from the normal workflow: it never
runs unless asked, and it reuses the same DeepEval setup as the offline evaluation (evaluation/deepeval_suite.py).

Only reference-free metrics can run on a live question, because a new question has no reference answer:
answer relevancy, faithfulness, and two G-Eval rubrics (analysis correctness, evidence relevance). Contextual precision
and recall need a reference answer and are only available in the offline evaluation.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor

from src.config import settings
from src.services import llm_client

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # no usage reporting from a local app

# DeepEval installs a signal handler when it is first imported, and Python only allows that in the main thread. Requests run
# in worker threads, so it is imported here, once, when the API starts.
try:
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams as P
    from evaluation.deepeval_suite import CompatibleLLM
except ImportError:  # DeepEval is optional for running the app
    AnswerRelevancyMetric = FaithfulnessMetric = GEval = LLMTestCase = P = CompatibleLLM = None


def plan_to_text(plan: dict) -> str:
    parts = [f"Recommended strategy: {plan.get('recommended_strategy')}.", f"Rationale: {plan.get('rationale')}"]
    for label, key in (("Immediate actions", "immediate_actions"), ("Recovery plan", "recovery_plan"), ("Risks", "risks")):
        if plan.get(key):
            parts.append(f"{label}: " + "; ".join(map(str, plan[key])))
    return "\n".join(parts)


def contexts_from(fact_sheet: str) -> list[str]:
    """Same split as the offline evaluation: one context per fact-sheet line."""
    return [ln.lstrip("- ").strip() for ln in fact_sheet.splitlines() if ln.strip()]


def _metric_factories(model):
    return {
        "answer_relevancy": lambda: AnswerRelevancyMetric(model=model, threshold=0.7, async_mode=False),
        "faithfulness": lambda: FaithfulnessMetric(model=model, threshold=0.7, async_mode=False),
        "analysis_correctness": lambda: GEval(
            name="Disruption Analysis Correctness", model=model, threshold=0.6, async_mode=False,
            criteria="Check that the actual output correctly characterises the disruption described in the input (type, industry, "
                     "severity) and that its claims about similar historical cases are supported by the retrieval context.",
            evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT, P.RETRIEVAL_CONTEXT]),
        "evidence_relevance": lambda: GEval(
            name="Evidence Relevance", model=model, threshold=0.6, async_mode=False,
            criteria="Judge whether the retrieval context contains evidence that is relevant to the disruption in the input and "
                     "sufficient to support the actual output's recommendation, timelines and numbers.",
            evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT, P.RETRIEVAL_CONTEXT]),
    }


def _score(query: str, plan: dict, contexts: list[str]) -> dict:
    model = CompatibleLLM()
    factories = _metric_factories(model)
    answer = plan_to_text(plan)

    def one(name):
        tc = LLMTestCase(input=query, actual_output=answer, retrieval_context=contexts)
        m = factories[name]()
        try:
            m.measure(tc)
            return name, {"score": round(float(m.score), 4), "passed": bool(m.is_successful()), "reason": (m.reason or "")[:400]}, None
        except Exception as e:  # one failing metric must not hide the others
            msg = str(e)
            return name, None, ("the checker model gave no usable reply" if "no JSON" in msg or type(e).__name__ in ("ValidationError", "JSONDecodeError")
                                else f"{type(e).__name__}: {msg[:120]}")

    with ThreadPoolExecutor(max_workers=len(factories)) as pool:
        results = list(pool.map(one, factories))
    return {"scores": {n: v for n, v, _ in results}, "errors": {n: e for n, _, e in results if e}}


def _why_failed(first_error: str) -> str:
    """A plain-words reason: if the model rejected the calls themselves (quota, rate limit, bad key), say so."""
    err = (llm_client.last_failure.get("error") or "").lower()
    model = settings.JUDGE_MODEL
    if "429" in err or "quota" in err or "rate limit" in err or "resource_exhausted" in err:
        return (f"The checker model ({model}) refused the calls because its request quota or rate limit is used up. "
                "The deep check makes around ten calls, which is more than a free tier sometimes allows. Try again later or pick another model.")
    if "401" in err or "403" in err or "api key" in err or "authentication" in err:
        return f"The checker model ({model}) rejected the API key. Check the key for this provider."
    if err:
        return f"The checker model ({model}) did not answer: {err[:140]}"
    return f"The checker model could not score this answer ({first_error})."


def run(query: str, plan: dict) -> dict:
    """Score one plan. Raises RuntimeError when no LLM is available or every metric failed."""
    if not (settings.LLM_ENABLED and llm_client.llm_available()):
        raise RuntimeError("The deep check needs a language model, and none is available. Pick one in the model selector.")
    if CompatibleLLM is None:
        raise RuntimeError("DeepEval is not installed, so the deep check is unavailable.")
    contexts = contexts_from(plan.get("fact_sheet") or "")
    if not contexts:
        raise RuntimeError("This analysis has no saved evidence to check the answer against.")
    t0 = time.time()
    llm_client.last_failure["error"] = None
    out = _score(query, plan, contexts)
    if all(v is None for v in out["scores"].values()):
        raise RuntimeError(_why_failed(next(iter(out["errors"].values()), "unknown error")))
    return {"framework": "DeepEval", "judge_model": settings.JUDGE_MODEL, "n_contexts": len(contexts),
            "seconds": round(time.time() - t0, 1), **out}
