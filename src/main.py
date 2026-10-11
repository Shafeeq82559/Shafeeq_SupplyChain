"""FastAPI entry point.

Run:  uvicorn src.main:app --reload
Docs: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.utils.logger import get_logger

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up heavy resources so the first request is fast.
    from src.rag.hybrid_retriever import indexed_frame
    from src.rag.vector_store import get_collection, get_embedder, get_vectors
    from src.services.ml_models import get_models
    try:
        indexed_frame(); get_collection(); get_embedder(); get_models(); get_vectors()
        log.info("Indexes, embedding model and ML models loaded")
    except Exception as e:
        log.error("Startup warm-up failed (run scripts/build_index.py and scripts/train_models.py): %s", e)
        yield
        return
    # Run one real retrieval + prediction so the vector index, filters and SHAP explainers are initialised now
    # instead of during the first user request (which otherwise takes 5-15 s). No LLM is called.
    try:
        from src.agents.classifier_agent import rule_classify
        from src.agents.impact_agent import assess_impact
        from src.agents.investigation_agent import investigate
        from src.rag.hybrid_retriever import hybrid_search
        q = "A typhoon flooded our Tier-1 semiconductor supplier's plant in Taiwan and production halted"
        hybrid_search(q, 3)
        hybrid_search(q, 3, {"industry": ["Electronics"], "disruption_severity": 4})
        assess_impact(investigate(q, rule_classify(q), {}, 5, {})["profile"], {})
        log.info("Warm-up queries done")
    except Exception as e:  # warm-up is an optimisation only
        log.warning("Warm-up queries skipped: %s", e)
    yield


app = FastAPI(
    title="AI-Powered Supply Chain Disruption Assistant",
    description="Hybrid RAG over historical disruptions, classification, prioritization, impact prediction, "
                "explainability, multi-agent response planning, LLM-as-Judge and a feedback loop.",
    version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "validation_error", "violations": errors})


app.include_router(router)
