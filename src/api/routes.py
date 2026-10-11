"""REST API endpoints for the Supply Chain Disruption Assistant."""
import json
import time

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agents.classifier_agent import ambiguity_notes, classify, override_conflicts
from src.agents.investigation_agent import investigate
from src.agents.judge_agent import judge
from src.agents.response_agent import plan_response
from src.agents.workflow import run_workflow, stream_workflow
from src.api import schemas as S
from src.config import settings
from src.rag.hybrid_retriever import hybrid_search
from src.rag.preprocessing import clean, derive_features, load_raw
from src.services import analytics, deep_check, explainability, feedback, ml_models, prioritization, risk_resilience
from src.services.guardrails import validate_input
from src.services.llm_client import list_providers, provider_info, switch_provider
from src.services.recommendation import historical_summary

router = APIRouter()


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def guard(text: str, check_topic: bool = True) -> tuple[str, list[str]]:
    g = validate_input(text, check_topic)
    if not g.allowed:
        raise HTTPException(status_code=422, detail={"error": "guardrail_violation", "violations": g.violations})
    return g.sanitized_text, g.warnings


def _filters(f: S.Filters | None) -> dict:
    return f.model_dump(exclude_none=True) if f else {}


@router.get("/health", tags=["System"])
def health():
    return {"status": "ok", "llm": provider_info(), "models_ready": ml_models.models_ready(),
            "index_ready": settings.BM25_PATH.exists() and settings.CHROMA_DIR.exists()}


class LLMSwitch(BaseModel):
    provider: str  # nvidia | gemini | aicredits | ollama | off


@router.get("/llm/providers", tags=["System"])
def llm_providers():
    return {"providers": list_providers(), "active": provider_info()}


@router.post("/llm/provider", tags=["System"])
def llm_switch(req: LLMSwitch):
    """Switch the LLM used by all agents at runtime ('off' = template fallbacks only)."""
    try:
        return switch_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats", tags=["Analytics"])
def stats():
    return jsonable(analytics.dataset_stats())


@router.get("/insights", tags=["Explainability"])
def insights():
    """Explainable factor analysis: statistical tests, SHAP global importance and key findings."""
    return jsonable({"key_insights": explainability.key_insights(), "factor_analysis": explainability.factor_analysis(),
                     "global_importance": explainability.global_importance(),
                     "model_metrics": ml_models.get_models()["metrics"]})


@router.post("/classify", tags=["Agents"])
def classify_endpoint(req: S.ClassifyRequest):
    text, warnings = guard(req.query)
    return {**classify(text), "guardrail_warnings": warnings}


@router.post("/search", tags=["RAG"])
def search(req: S.SearchRequest):
    text, warnings = guard(req.query)
    filters = _filters(req.filters)
    classification = None
    if req.auto_filter:
        classification = classify(text)
        for k, v in classification["suggested_filters"].items():
            filters.setdefault(k, [v])
    t0 = time.time()
    res = hybrid_search(text, req.top_k, filters, req.alpha, req.mode, feedback.case_boosts())
    return jsonable({**res, "query": text, "filters_applied": filters, "classification": classification,
                     "summary": historical_summary(res["results"]), "latency_ms": round(1000 * (time.time() - t0)),
                     "guardrail_warnings": warnings})


@router.post("/recommend", tags=["Agents"])
def recommend(req: S.RecommendRequest):
    text, warnings = guard(req.query)
    c = classify(text)
    overrides = req.profile.model_dump(exclude_none=True) if req.profile else {}
    inv = investigate(text, c, overrides, req.top_k, _filters(req.filters))
    r = plan_response(text, inv["profile"], inv["similar_cases"], pool=inv.get("strategy_pool"))
    return jsonable({"classification": c, "profile": inv["profile"], "assumptions": inv["assumptions"],
                     "historical_summary": inv["historical_summary"], "similar_cases": inv["similar_cases"],
                     "strategy_ranking": r["strategy_ranking"], "strategy_basis": r["basis"], "plan": r["plan"],
                     "guardrail_warnings": warnings})


@router.post("/prioritize", tags=["Prioritization"])
def prioritize(req: S.PrioritizeRequest):
    return {"ranked": jsonable(prioritization.prioritize_batch([i.model_dump() for i in req.items])),
            "weights": prioritization.WEIGHTS,
            "levels": [{"min_score": t, "level": c, "label": l} for t, c, l, _ in prioritization.LEVELS]}


@router.post("/predict", tags=["Prediction"])
def predict(profile: S.DisruptionProfile):
    p = profile.model_dump()
    return jsonable({"profile": p, "predictions": ml_models.predict(p),
                     "what_if_by_response": ml_models.predict_by_response(p)})


@router.post("/explain", tags=["Explainability"])
def explain(req: S.ExplainRequest):
    e = explainability.explain_prediction(req.profile.model_dump(), req.target)
    if req.narrate:
        e["narrative"] = explainability.narrate(e)
    return jsonable(e)


@router.post("/risk", tags=["Prediction"])
def risk(req: S.RiskRequest):
    profile = req.model_dump(exclude={"assumed_severity"})
    return jsonable(risk_resilience.assess(profile, req.assumed_severity))


def _analyze_inputs(req: S.AnalyzeRequest) -> tuple[dict, dict, dict]:
    known = {k: v for k, v in {"production_impact_pct": req.production_impact_pct,
                               "revenue_loss_usd": req.revenue_loss_usd}.items() if v is not None}
    overrides = req.profile.model_dump(exclude_none=True) if req.profile else {}
    return known, overrides, _filters(req.filters)


def _analysis_payload(out: dict, overrides: dict) -> dict:
    inv = out["investigation"]
    return jsonable({
        "query": out["query"], "executive_summary": out["report"]["executive_summary"],
        "classification": out["classification"], "profile": inv["profile"], "assumptions": inv["assumptions"],
        "override_notes": override_conflicts(overrides, out["query"]),
        "ambiguity_notes": ambiguity_notes(out["query"], overrides, out["classification"]),
        "investigation": {k: inv[k] for k in ("historical_summary", "filters_applied", "relaxations",
                                              "total_matching_filters", "similar_cases")},
        "impact_assessment": out["impact"], "response": out["response"], "recovery": out["recovery"],
        "judgement": out["judgement"], "revisions": out.get("revisions", 0), "trace": out["trace"],
        "guardrail_warnings": out["guardrail"]["warnings"], "total_duration_ms": out["total_duration_ms"]})


@router.post("/analyze", tags=["Agents"])
def analyze(req: S.AnalyzeRequest):
    """Full multi-agent workflow: guardrails -> classify -> investigate -> impact -> respond -> recover -> judge."""
    known, overrides, filters = _analyze_inputs(req)
    out = run_workflow(req.query, overrides, known, filters, req.top_k)
    if not out["guardrail"]["allowed"]:
        raise HTTPException(status_code=422, detail={"error": "guardrail_violation",
                                                     "violations": out["guardrail"]["violations"], "trace": out["trace"]})
    return _analysis_payload(out, overrides)


@router.post("/analyze/stream", tags=["Agents"])
def analyze_stream(req: S.AnalyzeRequest):
    """Same workflow as /analyze, streamed as newline-delimited JSON: one {"type": "step"} line per finished agent,
    then {"type": "result"} with the full analysis (or {"type": "error"}), so a UI can show progress live."""
    known, overrides, filters = _analyze_inputs(req)

    def _line(obj: dict) -> str:
        return json.dumps(obj) + chr(10)

    def events():
        try:
            for kind, node, data in stream_workflow(req.query, overrides, known, filters, req.top_k):
                if kind == "step":
                    yield _line({"type": "step", "node": node, "step": jsonable(data)})
                elif not data["guardrail"]["allowed"]:
                    yield _line({"type": "error", "status": 422, "violations": data["guardrail"]["violations"]})
                else:
                    yield _line({"type": "result", "data": _analysis_payload(data, overrides)})
        except Exception as e:  # surface the failure to the client instead of cutting the stream
            yield _line({"type": "error", "status": 500, "message": f"{type(e).__name__}: {e}"[:300]})

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/analyze/deep-check", tags=["Evaluation"])
def analyze_deep_check(req: S.DeepCheckRequest):
    """Optional DeepEval check of one finished analysis (answer relevancy, faithfulness, analysis correctness, evidence
    relevance). Slow: it makes about ten language-model calls, so it only runs when the user asks for it."""
    try:
        return jsonable(deep_check.run(req.query, req.plan))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/judge", tags=["Evaluation"])
def judge_endpoint(req: S.JudgeRequest):
    text, _ = guard(req.query, check_topic=False)
    return jsonable(judge(text, req.evidence, req.answer))


@router.get("/evaluation", tags=["Evaluation"])
def evaluation_results():
    """Latest offline evaluation results (retrieval, DeepEval, RAGAS, models)."""
    out = {}
    for f in sorted(settings.EVAL_DIR.glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
    return out


@router.post("/feedback", tags=["Feedback"])
def submit_feedback(req: S.FeedbackRequest):
    item = req.model_dump(exclude_none=True)
    if item.get("query"):
        item["query"] = validate_input(item["query"], check_topic=False).sanitized_text
    fid = feedback.add_feedback(item)
    return {"id": fid, "status": "recorded", "strategy_multipliers": feedback.strategy_multipliers()}


@router.get("/feedback/stats", tags=["Feedback"])
def feedback_stats():
    return jsonable(feedback.stats())


@router.post("/feedback/retrain", tags=["Feedback"])
def retrain():
    """Retrain the prediction models including user-reported real outcomes."""
    outcomes = feedback.outcome_rows()
    if outcomes.empty:
        return {"status": "skipped", "reason": "No reported outcomes yet."}
    outcomes = outcomes.assign(disruption_id=[f"FB-{i:06d}" for i in range(len(outcomes))])
    df = derive_features(clean(pd.concat([load_raw(), outcomes], ignore_index=True)))
    t0 = time.time()
    bundle = ml_models.train_all(df)
    return jsonable({"status": "retrained", "outcomes_added": len(outcomes), "duration_s": round(time.time() - t0, 1),
                     "metrics": bundle["metrics"]})
