"""Multi-agent supply chain disruption workflow (LangGraph).

guardrails -> classification -> investigation -> impact assessment -> response planning
           -> recovery analysis -> judge --(fails, 1 revision max)--> response planning
                                         --(passes)--> report

Agents communicate through a shared typed state; every node appends a trace entry
(agent, status, duration, summary) so the UI can show what each agent did.
"""
import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.classifier_agent import classify
from src.agents.impact_agent import assess_impact
from src.agents.investigation_agent import investigate
from src.agents.judge_agent import judge
from src.agents.recovery_agent import analyze_recovery
from src.agents.response_agent import plan_response
from src.services.guardrails import validate_input

MAX_REVISIONS = 1


class WorkflowState(TypedDict, total=False):
    query: str
    overrides: dict
    known_impact: dict
    filters: dict
    top_k: int
    guardrail: dict
    classification: dict
    investigation: dict
    impact: dict
    response: dict
    recovery: dict
    judgement: dict
    revisions: int
    trace: list[dict]
    report: dict


def _trace(state: WorkflowState, agent: str, t0: float, summary: str, status: str = "ok") -> list[dict]:
    return state.get("trace", []) + [{"agent": agent, "status": status, "duration_ms": round(1000 * (time.time() - t0)),
                                      "summary": summary}]


def guardrail_node(s: WorkflowState) -> dict:
    t0 = time.time()
    g = validate_input(s["query"]).to_dict()
    summary = "Input accepted" if g["allowed"] else "Blocked: " + "; ".join(g["violations"])
    return {"guardrail": g, "query": g["sanitized_text"], "revisions": 0,
            "trace": _trace(s, "Guardrails", t0, summary + (f" ({'; '.join(g['warnings'])})" if g["warnings"] else ""),
                            "ok" if g["allowed"] else "blocked")}


def classify_node(s: WorkflowState) -> dict:
    t0 = time.time()
    c = classify(s["query"])
    return {"classification": c, "trace": _trace(
        s, "Classification Agent", t0, f"{c['disruption_type']} | severity {c['estimated_severity']} | "
        f"{c.get('industry') or '?'} | {c.get('supplier_region') or '?'} (conf {c['confidence']}, {c['method']})")}


def investigate_node(s: WorkflowState) -> dict:
    t0 = time.time()
    inv = investigate(s["query"], s["classification"], s.get("overrides"), s.get("top_k", 10), s.get("filters"))
    return {"investigation": inv, "trace": _trace(
        s, "Investigation Agent", t0, f"{len(inv['similar_cases'])} similar cases retrieved from "
        f"{inv['total_matching_filters']:,} matching records; filters {inv['filters_applied']}"
        + (f"; {'; '.join(inv['relaxations'])}" if inv["relaxations"] else ""))}


def impact_node(s: WorkflowState) -> dict:
    t0 = time.time()
    imp = assess_impact(s["investigation"]["profile"], s.get("known_impact"))
    p, pr = imp["predictions"], imp["priority"]
    return {"impact": imp, "trace": _trace(
        s, "Impact Assessment Agent", t0, f"Impact {p['production_impact_pct']['predicted']:.1f}%, loss "
        f"${p['revenue_loss_usd']['predicted']:,.0f}, full recovery {p['full_recovery_days']['predicted']:.0f}d -> "
        f"{pr['priority_level']} {pr['priority_label']} ({pr['priority_score']})")}


def response_node(s: WorkflowState) -> dict:
    t0 = time.time()
    feedback = None
    revisions = s.get("revisions", 0)
    if s.get("judgement") and not s["judgement"]["passed"]:
        feedback = s["judgement"].get("overall_feedback")
        revisions += 1
    r = plan_response(s["query"], s["investigation"]["profile"], s["investigation"]["similar_cases"], feedback,
                      pool=s["investigation"].get("strategy_pool"), headline=s["impact"]["predictions"],
                      priority=s["impact"]["priority"])
    sev = s["investigation"]["profile"]["disruption_severity"]
    if sev <= 2 and s["impact"]["priority"]["priority_level"] in ("P3", "P4"):
        r["plan"]["minor_event_note"] = (f"This looks like a minor event (severity {sev}). {r['plan']['recommended_strategy']} is the best-scoring "
                                         "option in the historical data, but check the real impact first and treat it as the escalation "
                                         "step if the delays continue or come back.")
    label = "Response Planning Agent" + (" (revision)" if feedback else "")
    return {"response": r, "revisions": revisions, "trace": _trace(
        s, label, t0, f"Recommended {r['plan']['recommended_strategy']} ({r['plan']['generated_by']}); "
        f"{len(r['strategy_ranking'])} strategies ranked")}


def recovery_node(s: WorkflowState) -> dict:
    t0 = time.time()
    rec = analyze_recovery(s["investigation"]["profile"], s["response"]["plan"]["recommended_strategy"],
                           s["investigation"]["similar_cases"])
    return {"recovery": rec, "trace": _trace(
        s, "Recovery Analysis Agent", t0, f"Full recovery ~{rec['timeline']['full_recovery_days']['predicted']:.0f}d; "
        f"supplier change p={rec['supplier_change_probability']:.2f}; resilience {rec['resilience']['resilience_score']}")}


def _evidence(s: WorkflowState) -> dict:
    inv = s["investigation"]
    return {"classification": s["classification"], "profile": inv["profile"], "assumptions": inv.get("assumptions") or [],
            "historical_summary": inv["historical_summary"],
            "case_ids": [c["disruption_id"] for c in inv["similar_cases"]],
            "similar_cases": [{k: c[k] for k in ("disruption_id", "disruption_type", "industry", "response_type",
                                                  "full_recovery_days", "production_impact_pct", "revenue_loss_usd")}
                              for c in inv["similar_cases"]],
            "fact_sheet": s["response"]["plan"].get("fact_sheet"),
            "impact": s["impact"]["predictions"], "priority": s["impact"]["priority"],
            "strategy_ranking": [{k: v for k, v in r.items() if k not in ("historical", "predicted")}
                                 for r in s["response"]["strategy_ranking"]],
            # Three recovery figures with different meanings sit in this evidence; say which is which.
            "figure_notes": ["strategy_ranking expected_* values average past outcomes and the model and are used only to rank "
                             "strategies; they are not the estimates shown to the user.",
                             "impact.full_recovery_days and partial_recovery_days assume the default response (Alternative "
                             "Supplier); the recovery estimate for the chosen strategy is the one in fact_sheet under CHOSEN STRATEGY."]}


def judge_node(s: WorkflowState) -> dict:
    t0 = time.time()
    answer = {"response_plan": s["response"]["plan"], "impact_assessment": s["impact"]["predictions"],
              "priority": s["impact"]["priority"], "recovery": s["recovery"]["timeline"]}
    j = judge(s["query"], _evidence(s), answer)
    return {"judgement": j, "trace": _trace(s, "Judge Agent (LLM-as-Judge)", t0,
                                            f"Overall {j['overall_score']}/5 -> {'PASS' if j['passed'] else 'FAIL'} ({j['judge']})")}


def report_node(s: WorkflowState) -> dict:
    t0 = time.time()
    inv, imp, plan, rec = s["investigation"], s["impact"], s["response"]["plan"], s["recovery"]
    p, pr = imp["predictions"], imp["priority"]
    summary = (f"{pr['priority_level']} ({pr['priority_label']}) {inv['profile']['disruption_type']} disruption affecting a "
               f"Tier-{inv['profile']['supplier_tier']} {inv['profile']['industry']} supplier in {inv['profile']['supplier_region']}. "
               f"Expected production impact {p['production_impact_pct']['predicted']:.0f}% and revenue loss "
               f"${p['revenue_loss_usd']['predicted']:,.0f}. Recommended response: {plan['recommended_strategy']}, with partial "
               f"recovery in ~{rec['timeline']['partial_recovery_days']['predicted']:.0f} days and full recovery in "
               f"~{rec['timeline']['full_recovery_days']['predicted']:.0f} days. Strategies were compared on "
               f"{s['response']['basis']['description']}. The closest cases below are shown as examples and are not used "
               f"to rank strategies: {inv['historical_summary']}")
    return {"report": {"executive_summary": summary}, "trace": _trace(s, "Report", t0, "Final report compiled")}


def after_guardrail(s: WorkflowState) -> str:
    return "classify" if s["guardrail"]["allowed"] else END


def after_judge(s: WorkflowState) -> str:
    return "response" if (not s["judgement"]["passed"] and s.get("revisions", 0) < MAX_REVISIONS) else "report"


def build_graph():
    g = StateGraph(WorkflowState)
    for name, fn in [("guardrail", guardrail_node), ("classify", classify_node), ("investigate", investigate_node),
                     ("impact", impact_node), ("response", response_node), ("recovery", recovery_node),
                     ("judge", judge_node), ("report", report_node)]:
        g.add_node(name, fn)
    g.set_entry_point("guardrail")
    g.add_conditional_edges("guardrail", after_guardrail, {"classify": "classify", END: END})
    g.add_edge("classify", "investigate")
    g.add_edge("investigate", "impact")
    g.add_edge("impact", "response")
    g.add_edge("response", "recovery")
    g.add_edge("recovery", "judge")
    g.add_conditional_edges("judge", after_judge, {"response": "response", "report": "report"})
    g.add_edge("report", END)
    return g.compile()


_GRAPH = None


def _initial_state(query: str, overrides: dict | None, known_impact: dict | None, filters: dict | None, top_k: int) -> dict:
    return {"query": query, "overrides": overrides or {}, "known_impact": known_impact or {},
            "filters": filters or {}, "top_k": top_k, "trace": []}


def run_workflow(query: str, overrides: dict | None = None, known_impact: dict | None = None,
                 filters: dict | None = None, top_k: int = 10) -> dict[str, Any]:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    t0 = time.time()
    final = _GRAPH.invoke(_initial_state(query, overrides, known_impact, filters, top_k))
    final["total_duration_ms"] = round(1000 * (time.time() - t0))
    return final


def stream_workflow(query: str, overrides: dict | None = None, known_impact: dict | None = None,
                    filters: dict | None = None, top_k: int = 10):
    """Same run as `run_workflow`, but yields ('step', node, trace_entry) as each agent finishes and ends with
    ('final', None, state), so a UI can show the agents working in real time."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    t0 = time.time()
    state = _initial_state(query, overrides, known_impact, filters, top_k)
    for update in _GRAPH.stream(state, stream_mode="updates"):
        for node, changes in update.items():
            state.update(changes)
            yield "step", node, changes["trace"][-1]
    state["total_duration_ms"] = round(1000 * (time.time() - t0))
    yield "final", None, state
