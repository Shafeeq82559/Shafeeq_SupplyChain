"""Response Planning Agent: ranks response strategies using comparable past cases, ML what-if
predictions and feedback, then produces an evidence-grounded action plan (revisable after judging).

Strategies are compared on a large pool of comparable cases (`pool`, from the investigation agent), not just the
handful of closest cases shown to the user: ten cases are too few to count which strategy works best, and the
search wording can skew them. The closest cases remain the examples that are shown, cited and given to the LLM."""
from src.services import feedback, ml_models
from src.services.recommendation import close_call, generate_plan, rank_strategies, use_shown_examples


def plan_response(query: str, profile: dict, cases: list[dict], judge_feedback: str | None = None, *,
                  pool: dict | None = None, headline: dict | None = None, priority: dict | None = None) -> dict:
    what_if = ml_models.predict_by_response(profile)
    compare_on = pool["cases"] if pool else cases
    ranked = rank_strategies(compare_on, what_if, feedback.strategy_multipliers(), profile.get("has_backup_supplier"))
    if pool:
        use_shown_examples(ranked, cases)
    q = query if not judge_feedback else f"{query}\n\nReviewer feedback to address in this revision: {judge_feedback}"
    plan = generate_plan(q, ranked, cases, few_shot=feedback.few_shot_examples(), headline=headline, profile=profile,
                         priority=priority)
    note = close_call(ranked)
    if note:
        plan["close_call"] = note
    basis = {"comparable_cases": len(compare_on),
             "description": pool["description"] if pool else f"the {len(cases)} closest cases"}
    return {"strategy_ranking": ranked, "plan": plan, "basis": basis}
