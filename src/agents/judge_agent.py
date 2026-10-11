"""LLM-as-Judge: validates disruption analyses and response recommendations.

Scores 1-5 on five criteria with a reason for each, then gives a pass/fail verdict. When no LLM is
available a transparent heuristic judge applies rule-based checks, so the workflow still self-validates.
"""
import json
import re

from src.config import settings
from src.services import llm_client
from src.utils.constants import RESPONSE_TYPES

CRITERIA = {
    "faithfulness": "Every claim and number is supported by the provided evidence (retrieved cases, statistics, predictions); no invented facts or case IDs.",
    "relevance": "The analysis addresses the specific disruption described (type, industry, region, severity).",
    "actionability": "Recommendations are concrete, prioritised and executable by an operations team, with timelines.",
    "completeness": "Covers impact, priority, response strategy, recovery timeline and key risks.",
    "safety": "Advice is responsible: no harmful, illegal or reckless actions; uncertainty is acknowledged.",
}

JUDGE_PROMPT = f"""You are an impartial, demanding senior supply chain expert acting as a judge (LLM-as-Judge).
Evaluate the ANSWER produced for a supply chain disruption, using the EVIDENCE as ground truth.
Score each criterion from 1 (very poor) to 5 (excellent):
{json.dumps(CRITERIA, indent=1)}

Scoring discipline - be critical, do not be generous:
- 5 means flawless. Most good answers deserve 3 or 4. Give a 5 only when you can name nothing to improve.
- Proportionality (relevance, actionability): the response must fit the SIZE and KIND of the problem. Deduct at least 2 points if it
  recommends replacing or onboarding suppliers for a problem that is not about a supplier (a warehouse, carrier, customs or road
  problem), or for a minor, short, already-recovering disruption. Reward steps that fix the stated problem directly.
- Stated facts only (faithfulness): the DISRUPTION text is what the user stated. Anything listed under EVIDENCE.assumptions was NOT
  stated; it was guessed by the system. Deduct from faithfulness if the answer presents an assumed region, tier, size or backup
  supplier as a fact (for example "your European supplier"), or refers to a backup supplier the user never mentioned.
- A backup or second supplier that is not yet qualified is NOT a usable backup; deduct if the answer treats it as one.
- If the user said there is no backup supplier, deduct at least 2 points from relevance and actionability when the answer tells
  them to activate, switch to or negotiate with an alternative supplier. Qualifying a new source as a parallel, long-lead step is fine.
- Deduct for generic steps that would fit any disruption, for numbers or case IDs missing from the evidence, for ignoring what the
  user said still works (e.g. production still running, stock that lasts weeks), and for overstating certainty.
- Reasons must name the specific problem, not praise. If you give 5, say why nothing needs improving.
Return JSON: {{"scores": {{"faithfulness": int, "relevance": int, "actionability": int, "completeness": int,
"safety": int}}, "reasons": {{<criterion>: one sentence}}, "overall_feedback": "2 sentences on exactly what to fix"}}"""


def _heuristic(query: str, evidence: dict, answer: dict, reason: str | None = None) -> dict:
    plan = answer.get("response_plan", answer)
    allowed = set(evidence.get("case_ids", []))
    cited = set(plan.get("cited_cases") or []) | set(re.findall(r"DIS-\d{6}", json.dumps(plan)))
    s, r = {}, {}
    bad = cited - allowed if allowed else set()
    s["faithfulness"] = 5 if cited and not bad else (3 if not cited else 2)
    r["faithfulness"] = (f"Cites {len(cited)} retrieved case(s)" + (f"; unverified: {sorted(bad)}" if bad else "")) if cited \
        else "No historical cases cited as evidence."
    cls = evidence.get("classification") or {}
    relevant = plan.get("recommended_strategy") in RESPONSE_TYPES and bool(cls.get("disruption_type"))
    s["relevance"] = 4 if relevant else 2
    r["relevance"] = "Strategy and classification align with the described disruption." if relevant else "Missing strategy or classification."
    n_actions = len(plan.get("immediate_actions") or [])
    has_timeline = any(re.search(r"\d+\s*(day|week|hour)", str(x)) for x in plan.get("recovery_plan") or [])
    s["actionability"] = min(5, 2 + (n_actions >= 3) + (n_actions >= 4) + has_timeline)
    r["actionability"] = f"{n_actions} immediate actions; timeline {'present' if has_timeline else 'missing'}."
    parts = [bool(answer.get("impact_assessment") or evidence.get("impact")), bool(answer.get("priority") or evidence.get("priority")),
             bool(plan.get("recommended_strategy")), bool(plan.get("recovery_plan")), bool(plan.get("risks"))]
    s["completeness"] = max(1, sum(parts))
    r["completeness"] = f"{sum(parts)}/5 sections present (impact, priority, strategy, recovery plan, risks)."
    s["safety"] = 5
    r["safety"] = "No unsafe recommendations detected by rule checks."
    why = f"LLM judge unavailable: {reason}." if reason else "No language model is switched on."
    return {"scores": s, "reasons": r, "overall_feedback": f"Checklist evaluation. {why}", "judge": "heuristic", "fallback_reason": reason or "no language model switched on"}


def judge(query: str, evidence: dict, answer: dict) -> dict:
    result, reason = None, None
    if llm_client.llm_available():
        llm_client.last_failure["error"] = None
        out = llm_client.complete_json(
            JUDGE_PROMPT,
            f"DISRUPTION: {query}\n\nEVIDENCE: {json.dumps(evidence, default=str)[:12000]}\n\n"
            f"ANSWER: {json.dumps(answer, default=str)[:8000]}", max_tokens=2500, model=settings.JUDGE_MODEL)
        if isinstance(out, dict) and isinstance(out.get("scores"), dict):
            scores = {}
            for c in CRITERIA:
                try:
                    scores[c] = min(5, max(1, int(out["scores"].get(c))))
                except (TypeError, ValueError):
                    scores[c] = 3
            result = {"scores": scores, "reasons": out.get("reasons", {}),
                      "overall_feedback": out.get("overall_feedback", ""), "judge": f"llm:{settings.JUDGE_MODEL}"}
        else:
            reason = llm_client.failure_reason() if out is None else "the model's reply had no scores"
    if result is None:
        result = _heuristic(query, evidence, answer, reason)
    result["overall_score"] = round(sum(result["scores"].values()) / len(CRITERIA), 2)
    result["passed"] = result["overall_score"] >= settings.JUDGE_PASS_THRESHOLD and result["scores"]["faithfulness"] >= 3
    result["threshold"] = settings.JUDGE_PASS_THRESHOLD
    return result
