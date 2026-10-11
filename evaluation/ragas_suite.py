"""RAGAS evaluation (modern `ragas.metrics.collections` API).

Metrics: Faithfulness, Answer Relevancy (local MiniLM embeddings), Context Precision (with reference)
and Context Recall, using the project's configured LLM (via its own client) as the evaluator.
"""
import asyncio
import sys
import types


def _compat_shim():
    # ragas 0.4.3 imports a Vertex AI chat model removed in langchain-community 0.4; we never use it,
    # so a placeholder lets ragas import without downgrading langchain (which LangGraph 1.x needs).
    name = "langchain_community.chat_models.vertexai"
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[name] = mod


def _client_llm(model: str):
    """RAGAS LLM backed by the project's own LLM client. The JSON schema is given in the prompt and the reply is
    validated with the pydantic model, so it works with any provider - including endpoints that refuse OpenAI-style
    `response_format` (Claude's OpenAI-compatible endpoint) - and shares the client's per-model workarounds."""
    import json

    from ragas.llms.base import InstructorBaseRagasLLM

    from src.services import llm_client

    class ClientRagasLLM(InstructorBaseRagasLLM):
        def generate(self, prompt, response_model):
            schema = json.dumps(response_model.model_json_schema())
            out = llm_client.complete_json("You are an evaluation assistant. Reply with ONLY a JSON object that follows "
                                           "this JSON schema:\n" + schema, prompt, max_tokens=4000, model=model)
            if out is None:
                raise ValueError("LLM returned no JSON")
            return response_model.model_validate(out)

        async def agenerate(self, prompt, response_model):
            return await asyncio.to_thread(self.generate, prompt, response_model)

    return ClientRagasLLM()


def run_ragas(outputs: list[dict]) -> dict:
    _compat_shim()
    from ragas.embeddings import HuggingFaceEmbeddings
    from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

    from src.config import settings

    llm = _client_llm(settings.JUDGE_MODEL)
    emb = HuggingFaceEmbeddings(model=settings.EMBEDDING_MODEL)
    faithfulness = Faithfulness(llm=llm)
    # `faithfulness` scores the whole plan (standard). `faithfulness_explanation` scores only the explanation paragraph:
    # the action steps are recommendations rather than factual claims, so no evidence can "support" them.
    metrics = {"faithfulness": faithfulness, "faithfulness_explanation": faithfulness,
               "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=emb),
               "context_precision": ContextPrecision(llm=llm), "context_recall": ContextRecall(llm=llm)}

    async def score_case(o):
        ctx = o["contexts"]
        calls = {"faithfulness": dict(user_input=o["query"], response=o["answer"], retrieved_contexts=ctx),
                 "faithfulness_explanation": dict(user_input=o["query"], response=str(o["plan"].get("rationale") or o["answer"]),
                                                  retrieved_contexts=ctx),
                 "answer_relevancy": dict(user_input=o["query"], response=o["answer"]),
                 "context_precision": dict(user_input=o["query"], reference=o["reference"], retrieved_contexts=ctx),
                 "context_recall": dict(user_input=o["query"], retrieved_contexts=ctx, reference=o["reference"])}
        row = {"id": o["id"]}
        for name, kwargs in calls.items():
            try:
                r = await metrics[name].ascore(**kwargs)
                row[name] = round(float(r.value), 4)
            except Exception as e:
                row[name] = None
                row[f"{name}_error"] = f"{type(e).__name__}: {str(e)[:150]}"
        return row

    async def main():
        sem = asyncio.Semaphore(4)  # a few cases in flight at once; LLM latency dominates

        async def bounded(o):
            async with sem:
                return await score_case(o)

        return await asyncio.gather(*(bounded(o) for o in outputs))

    per_case = asyncio.run(main())
    summary = {}
    for name in metrics:
        vals = [r[name] for r in per_case if r.get(name) is not None]
        summary[name] = {"mean": round(sum(vals) / len(vals), 4) if vals else None, "n": len(vals)}
    return {"framework": "RAGAS", "judge_model": settings.JUDGE_MODEL, "n_cases": len(outputs),
            "summary": summary, "per_case": per_case}
