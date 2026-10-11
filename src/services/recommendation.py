"""Response & recovery recommendations grounded in similar historical cases.

1. Aggregate how each response strategy performed across the retrieved similar cases.
2. Blend in ML what-if predictions for the current disruption profile (when available).
3. Apply feedback-loop boosts from user ratings of past recommendations.
4. Rank strategies; the LLM (or a template) writes the action plan citing only retrieved case IDs.
"""
import re

import numpy as np
import pandas as pd

from src.services import llm_client
from src.services.guardrails import enforce_citations
from src.utils.constants import RESPONSE_TYPES


def strategy_stats(cases: list[dict]) -> list[dict]:
    if not cases:
        return []
    df = pd.DataFrame(cases)
    out = []
    for r, g in df.groupby("response_type"):
        out.append({
            "response_type": r, "case_count": int(len(g)),
            "avg_full_recovery_days": round(float(g["full_recovery_days"].mean()), 1),
            "median_full_recovery_days": round(float(g["full_recovery_days"].median()), 1),
            "avg_partial_recovery_days": round(float(g["partial_recovery_days"].mean()), 1),
            "avg_production_impact_pct": round(float(g["production_impact_pct"].mean()), 1),
            "avg_revenue_loss_usd": round(float(g["revenue_loss_usd"].mean()), 0),
            "supplier_change_rate": round(float(g["permanent_supplier_change"].mean()), 3),
            "avg_response_time_days": round(float(g["response_time_days"].mean()), 1),
            "avg_effectiveness": round(float(g["response_effectiveness"].mean()), 1),
            "example_cases": g.sort_values("response_effectiveness", ascending=False)["disruption_id"].head(3).tolist(),
        })
    return out


def _norm(values: list[float]) -> list[float]:
    a = np.array(values, dtype=float)
    rng = a.max() - a.min()
    return list((a - a.min()) / rng) if rng > 0 else [0.5] * len(a)


NEEDS_BACKUP = "Alternative Supplier"
NO_BACKUP_FACTOR = 0.5  # score multiplier for a strategy that needs a qualified second source the user does not have
NO_BACKUP_NOTE = ("Ranked last: there is no qualified backup supplier, so switching suppliers is not an immediate option. "
                  "Qualifying a new source can run in parallel, but it takes time (longer still for regulated inputs).")


def rank_strategies(cases: list[dict], what_if: list[dict] | None = None,
                    feedback_multipliers: dict[str, float] | None = None, has_backup: bool | None = None) -> list[dict]:
    """`has_backup=False` marks Alternative Supplier as not feasible now: its score is halved and it is ranked after
    every option that can start immediately, so it is never the recommendation or the fallback. The historical data
    records it in no-backup cases too (a new source was found later), which made it win on recovery speed alone."""
    hist = {s["response_type"]: s for s in strategy_stats(cases)}
    pred = {w["response_type"]: w for w in (what_if or [])}
    rows = []
    for r in RESPONSE_TYPES:
        h, p = hist.get(r), pred.get(r)
        if not h and not p:
            continue
        rec = [v for v in ((h or {}).get("avg_full_recovery_days"), (p or {}).get("predicted_full_recovery_days")) if v is not None]
        loss = [v for v in ((h or {}).get("avg_revenue_loss_usd"), (p or {}).get("predicted_revenue_loss_usd")) if v is not None]
        chg = [v for v in ((h or {}).get("supplier_change_rate"), (p or {}).get("supplier_change_probability")) if v is not None]
        rows.append({"response_type": r, "historical": h, "predicted": p,
                     "expected_full_recovery_days": round(float(np.mean(rec)), 1),
                     "expected_revenue_loss_usd": round(float(np.mean(loss)), 0),
                     "supplier_change_risk": round(float(np.mean(chg)), 3),
                     "evidence_cases": (h or {}).get("case_count", 0), "evidence_total": len(cases)})
    if not rows:
        return []
    rec_n = _norm([x["expected_full_recovery_days"] for x in rows])
    loss_n = _norm([x["expected_revenue_loss_usd"] for x in rows])
    for x, rn, ln in zip(rows, rec_n, loss_n):
        evidence = min(1.0, x["evidence_cases"] / 5)
        s = 100 * (0.45 * (1 - rn) + 0.25 * (1 - ln) + 0.15 * (1 - x["supplier_change_risk"]) + 0.15 * evidence)
        mult = (feedback_multipliers or {}).get(x["response_type"], 1.0)
        x["feedback_multiplier"] = round(mult, 3)
        x["strategy_score"] = round(s * mult, 1)
        x["feasible_now"] = not (has_backup is False and x["response_type"] == NEEDS_BACKUP)
        if not x["feasible_now"]:
            x["strategy_score"] = round(x["strategy_score"] * NO_BACKUP_FACTOR, 1)
            x["feasibility_note"] = NO_BACKUP_NOTE
    rows.sort(key=lambda x: (not x["feasible_now"], -x["strategy_score"]))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
    return rows


def use_shown_examples(ranked: list[dict], shown_cases: list[dict]) -> None:
    """When strategies are compared on a large pool, the example case IDs quoted in the plan must still be cases the
    user can see (the closest ones), so replace the pool's examples with ones from the shown cases."""
    by_strategy: dict[str, list[str]] = {}
    for c in sorted(shown_cases, key=lambda c: -c.get("response_effectiveness", 0)):
        by_strategy.setdefault(c["response_type"], []).append(c["disruption_id"])
    for r in ranked:
        if r.get("historical"):
            r["historical"] = {**r["historical"], "example_cases": by_strategy.get(r["response_type"], [])[:3]}


def close_call(ranked: list[dict], margin: float = 5.0) -> str | None:
    """Plain-language note when the top two strategies score almost the same."""
    if len(ranked) < 2 or ranked[0]["strategy_score"] - ranked[1]["strategy_score"] >= margin:
        return None
    a, b = ranked[0], ranked[1]
    return (f"Close call: {a['response_type']} ({a['strategy_score']:.0f}) and {b['response_type']} ({b['strategy_score']:.0f}) "
            f"score within {margin:.0f} points, so the data does not clearly separate them. Check the ranking before deciding.")


def _model_figures(r: dict) -> dict:
    """Recovery and supplier-change figures from the prediction models for this strategy - the same numbers the
    headline and the recovery timeline show - falling back to the blended expectation if the models were not used."""
    p, h = r.get("predicted") or {}, r.get("historical") or {}
    return {"full": p.get("predicted_full_recovery_days", r["expected_full_recovery_days"]),
            "partial": p.get("predicted_partial_recovery_days", h.get("avg_partial_recovery_days")),
            "change": p.get("supplier_change_probability", r["supplier_change_risk"])}


def historical_summary(cases: list[dict], with_responses: bool = True) -> str:
    """Summary of the closest cases. `with_responses=False` leaves out how often each strategy was used among them,
    because ten cases are too few to say which strategy is popular (the LLM would otherwise quote 'used in 3 of 10')."""
    if not cases:
        return "No sufficiently similar historical disruptions were found."
    df = pd.DataFrame(cases)
    top = df["response_type"].value_counts()
    return (f"{len(df)} similar historical disruptions found (most common: {', '.join(df['disruption_type'].value_counts().index[:2])}). "
            + (f"Responses used in these {len(df)} cases: {', '.join(f'{k} ({v})' for k, v in top.items())}. " if with_responses else "") +
            f"Median full recovery {df['full_recovery_days'].median():.0f} days, median production impact "
            f"{df['production_impact_pct'].median():.1f}%, {100 * df['permanent_supplier_change'].mean():.0f}% ended with a "
            f"permanent supplier change.")


NO_EVIDENCE_NOTE = "Model estimate only: no comparable past case used this strategy, so it is not backed by historical outcomes."
_HISTORICAL_CLAIM = re.compile(r"\b(histor\w*|past cases?|prior cases?|similar cases?|previous\w* cases?|precedent\w*)\b", re.I)


def _template_rationale(best: dict, m: dict, ex: list[str], n_cases: int) -> str:
    head = (f"{best['response_type']} has the best overall score among the options: ~{m['full']:.0f} days to full "
            f"recovery (model estimate), permanent supplier-change risk {100 * m['change']:.0f}%")
    if not best["evidence_cases"]:
        return head + ". No comparable past case used this strategy, so this rests on the model estimate only."
    return (head + f", used in {best['evidence_cases']} of {best.get('evidence_total', n_cases)} comparable past cases"
            + (f" (e.g. {', '.join(ex)})." if ex else "."))


def template_plan(query: str, ranked: list[dict], cases: list[dict], has_backup: bool | None = None) -> dict:
    best = ranked[0]
    alt = ranked[1] if len(ranked) > 1 else None
    ex = (best.get("historical") or {}).get("example_cases", [])
    m = _model_figures(best)
    partial = m["partial"]
    actions = {
        "Alternative Supplier": ["Qualify and activate an alternative supplier for affected parts",
                                 "Negotiate expedited capacity and logistics with the alternate source"],
        "Production Reroute": ["Shift production of affected SKUs to unaffected plants/lines",
                               "Rebalance material flows and staffing to the rerouted capacity"],
        "Inventory Buffer": ["Draw down safety stock and allocate inventory to priority customers",
                             "Set a reorder trigger to rebuild buffers once supply resumes"],
        "Customer Delay": ["Notify affected customers with revised delivery dates",
                           "Prioritise orders by margin and contractual penalties"],
        "Combined Strategy": ["Combine inventory drawdown with alternate sourcing for critical parts",
                              "Reroute production where possible while the supplier recovers"],
    }[best["response_type"]]
    if has_backup is False and best["response_type"] == "Combined Strategy":
        actions = ["Combine inventory drawdown with rerouting production to unaffected plants/lines",
                   "Start qualifying a new source for critical parts in parallel (long lead time; no backup is approved yet)"]
    return {
        "recommended_strategy": best["response_type"],
        "rationale": _template_rationale(best, m, ex, len(cases)),
        **({"evidence_note": NO_EVIDENCE_NOTE} if not best["evidence_cases"] else {}),
        "immediate_actions": ["Confirm scope: affected parts, inventory on hand and customer orders at risk"] + actions,
        "recovery_plan": [f"Target partial recovery within ~{partial:.0f} days" if partial else "Track partial recovery milestones weekly",
                          f"Target full recovery within ~{m['full']:.0f} days",
                          "Review supplier performance and decide on dual-sourcing after recovery"],
        "fallback_strategy": alt["response_type"] if alt else None,
        "risks": [f"Permanent supplier change risk ~{100 * m['change']:.0f}%",
                  "Recovery may run longer if severity escalates"
                  + (" and there is no qualified backup supplier to fall back on" if has_backup is False
                     else " or backup capacity is constrained")],
        "cited_cases": ex,
        "generated_by": "template",
    }


PLAN_PROMPT = """You are a supply chain response planning agent writing for operations managers.
The response strategy has ALREADY been chosen by the scoring system (historical outcomes of similar cases +
model predictions + user feedback). Do NOT choose, change or question it - explain it and turn it into a plan.

Rules:
- Use ONLY facts and numbers from the FACT SHEET. Never invent numbers, ranges, suppliers, contracts or events.
- When you state a number, copy it from the fact sheet (e.g. "expected full recovery in ~86 days").
- Do not mention internal scores, ranks or field names.
- Cite historical case IDs (format DIS-######) only from the fact sheet.
- Recovery times for this disruption are the model estimates; the past-outcome medians are context, never a replacement.
- If the fact sheet says no comparable past case used the chosen strategy, say it rests on model estimates only; never
  describe it as historically used or proven.
- If the profile says there is no backup supplier, never tell the user to activate, switch to or negotiate with a backup
  or alternate supplier. Starting to qualify a new source may be listed only as a parallel, long-lead-time step.
- Answer the user's actual question first (for example whether to escalate, or how cautious to be), then state the
  priority level and response window from the PRIORITY line.
- Build the plan around what the user stated: stock or inventory cover, how much a backup can cover, a restart already
  under way, deadlines. Do not repeat estimates that the user's own description contradicts.
- If there is a SCALE line, the plan must be proportionate: lead with verifying and monitoring, present the chosen
  strategy as the step to take if the problem continues, and give the estimates only as an upper bound.
- Every immediate action names an owner role (e.g. procurement lead, plant manager, quality) and a deadline, and the plan
  gives at least one concrete trigger for escalating or moving to the fallback (e.g. stock cover below a stated number of
  days), using numbers from the user's description or the fact sheet.
- In regulated industries (pharmaceuticals, aerospace) include the quality or regulatory step a change would need.
Return JSON with keys: rationale (2-4 sentences: the direct answer, the priority, and why the chosen strategy fits, using
fact-sheet numbers), immediate_actions (3-5 concrete steps), recovery_plan (3-4 steps with timelines consistent with the
expected partial/full recovery days, or with the user's stated timeline for a minor event), risks (2-3 items),
cited_cases (list of IDs from the fact sheet)."""

_NUM_UNIT = re.compile(
    r"\$\s?(\d+(?:[.,]\d+)?)\s*([mk]|million|thousand)?\b"     # money: $4.5M, $850K, $1,200,000
    r"|(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(days?|%)"  # ranges: 37-211 days
    r"|(\d+(?:\.\d+)?)\s*(days?|%)", re.I)


def _usd(v: float) -> str:
    return f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}K"


def _strategy_line(r: dict, total_cases: int) -> str:
    m = _model_figures(r)
    return (f"{r['response_type']}: model-estimated full recovery ~{m['full']:.0f} days"
            + (f", partial recovery ~{m['partial']:.0f} days" if m["partial"] else "")
            + f", permanent supplier-change risk {100 * m['change']:.0f}%, "
              f"used in {r['evidence_cases']} of the {r.get('evidence_total', total_cases)} comparable past cases"
            + ("; NO comparable past case used this strategy, so this is a model estimate only" if not r["evidence_cases"] else ""))


def is_minor_event(profile: dict | None, priority: dict | None) -> bool:
    """Severity 1-2 with a P3/P4 priority: a small event where typical-case figures would overstate the problem."""
    return bool(profile and priority and profile["disruption_severity"] <= 2 and priority.get("priority_level") in ("P3", "P4"))


def build_fact_sheet(ranked: list[dict], cases: list[dict], headline: dict | None = None,
                     profile: dict | None = None, priority: dict | None = None) -> str:
    """Evidence handed to the LLM. Recovery and risk figures are the model estimates the user sees in the headline
    (`headline` carries the production-impact and revenue-loss estimates shown there), so the plan cannot contradict it.
    The most relevant evidence comes first: the disruption profile, then past outcomes by strategy."""
    chosen, alt = ranked[0], (ranked[1] if len(ranked) > 1 else None)
    lines = []
    if profile:
        lines.append(f"DISRUPTION PROFILE - {profile['disruption_type']}, severity {profile['disruption_severity']}, "
                     f"Tier-{profile['supplier_tier']} {profile['industry']} supplier in {profile['supplier_region']}, "
                     f"{'with a backup supplier' if profile['has_backup_supplier'] else 'no backup supplier'}.")
    if priority:
        lines.append(f"PRIORITY - {priority['priority_level']} {priority['priority_label']} (score {priority['priority_score']:.0f} "
                     f"of 100): {priority['recommended_action']}")
    if is_minor_event(profile, priority):
        lines.append("SCALE - This looks like a minor event. The estimates below are typical outcomes for disruptions with this "
                     "profile, not a forecast of this specific event: where the user's description states the actual duration, "
                     "loss or recovery (for example one shift, or shipping again), the description takes precedence and the "
                     "estimates are only the upper bound if the problem continues or returns.")
    past =[(r["response_type"], r["historical"]) for r in ranked if r.get("historical")]
    if past:
        total = chosen.get("evidence_total", len(cases))
        lines.append(f"PAST OUTCOMES IN {total} COMPARABLE CASES (context only; recovery times for this disruption are the "
                     "model estimates below) - " + "; ".join(
                         f"{t}: used in {h['case_count']} cases, median full recovery {h['median_full_recovery_days']:.0f} days"
                         for t, h in past) + ".")
    lines.append(f"CHOSEN STRATEGY - {_strategy_line(chosen, len(cases))}.")
    ex = (chosen.get("historical") or {}).get("example_cases") or []
    if ex:
        lines.append(f"Best-recovering similar cases that used it: {', '.join(ex)}.")
    if alt:
        lines.append(f"FALLBACK STRATEGY - {_strategy_line(alt, len(cases))}.")
    others = [f"{r['response_type']} (~{_model_figures(r)['full']:.0f} days)" for r in ranked[2:] if r.get("feasible_now", True)]
    if others:
        lines.append("Other options considered: " + ", ".join(others) + ".")
    for r in ranked:
        if not r.get("feasible_now", True):
            lines.append(f"NOT AN IMMEDIATE OPTION - {r['response_type']}: {r['feasibility_note']}")
    if headline:
        pi, rl = headline["production_impact_pct"], headline["revenue_loss_usd"]
        lines.append(f"ESTIMATES FOR THIS DISRUPTION - production impact ~{pi['predicted']:.0f}% (likely {pi['low_p10']:.0f}-{pi['high_p90']:.0f}%), "
                     f"revenue loss ~{_usd(rl['predicted'])} (likely {_usd(rl['low_p10'])}-{_usd(rl['high_p90'])}).")
    elif chosen.get("predicted"):
        lines.append(f"ESTIMATE FOR THIS DISRUPTION - revenue loss ~{_usd(chosen['predicted']['predicted_revenue_loss_usd'])}.")
    lines.append(historical_summary(cases, with_responses=False))
    lines.append("CLOSEST EXAMPLES (illustrations only; how often each strategy was used is counted on the comparable cases above):")
    for c in cases[:8]:
        lines.append(f"- {c['disruption_id']}: severity {c['disruption_severity']} {c['disruption_type']}, {c['industry']}, "
                     f"production impact {c['production_impact_pct']:.1f}%, revenue loss ${c['revenue_loss_usd'] / 1e6:.2f}M, "
                     f"response {c['response_type']}, full recovery {c['full_recovery_days']} days")
    return "\n".join(lines)


def _amounts(text: str) -> list[tuple[float, str]]:
    """Numbers with a unit (days, %, $) found in text, as (value, kind)."""
    out = []
    for m in _NUM_UNIT.finditer(text or ""):
        if m.group(1):
            v = float(m.group(1).replace(",", ""))
            mult = (m.group(2) or "").lower()
            v *= 1e6 if mult in ("m", "million") else 1e3 if mult in ("k", "thousand") else 1
            out.append((v, "$"))
        elif m.group(3):
            kind = "%" if m.group(5) == "%" else "days"
            out += [(float(m.group(3)), kind), (float(m.group(4)), kind)]
        else:
            out.append((float(m.group(6)), "%" if m.group(7) == "%" else "days"))
    return out


def unsupported_numbers(text: str, source: str) -> list[str]:
    """Numbers stated in `text` that do not appear (within rounding tolerance) in `source` - likely invented."""
    allowed = _amounts(source)
    bad = []
    for v, kind in _amounts(text):
        if kind == "days" and v <= 14:  # short operational timelines ("within 7 days") are plan steps, not claims
            continue
        tol = {"$": 0.06 * v, "%": 1.5, "days": max(2.0, 0.05 * v)}[kind]
        if not any(k == kind and abs(a - v) <= tol for a, k in allowed):
            bad.append(f"{v:g}{'%' if kind == '%' else ' days' if kind == 'days' else ' USD'}")
    return bad


_SNAKE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")


def _plain(value):
    """Turn leaked internal field names (snake_case) into plain words, e.g. supplier_change_risk -> supplier change risk."""
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return _SNAKE.sub(lambda m: m.group(0).replace("_", " "), value) if isinstance(value, str) else value


def _wording_ok(text: str) -> bool:
    """A rationale is usable only if its brackets balance and it ends like a finished sentence (not mid-clause)."""
    text = (text or "").strip()
    if not text or text[-1] not in ".!?":
        return False
    depth = {"(": 0, "[": 0}
    pairs = {")": "(", "]": "["}
    for ch in text:
        if ch in depth:
            depth[ch] += 1
        elif ch in pairs:
            depth[pairs[ch]] -= 1
            if depth[pairs[ch]] < 0:
                return False
    return all(v == 0 for v in depth.values())


def generate_plan(query: str, ranked: list[dict], cases: list[dict], few_shot: list[str] | None = None,
                  headline: dict | None = None, profile: dict | None = None, priority: dict | None = None) -> dict:
    if not ranked:
        return {"recommended_strategy": None, "rationale": "Insufficient evidence to recommend a strategy.",
                "immediate_actions": [], "recovery_plan": [], "risks": [], "cited_cases": [], "generated_by": "none"}
    # The strategy decision is deterministic (top of the evidence-based ranking); the LLM only explains it.
    fallback = template_plan(query, ranked, cases, (profile or {}).get("has_backup_supplier"))
    facts = build_fact_sheet(ranked, cases, headline, profile, priority)
    user = (f"Disruption: {query}\n\nCHOSEN STRATEGY: {ranked[0]['response_type']}\n\nFACT SHEET:\n{facts}")
    if few_shot:
        user += "\n\nExamples of plans users rated highly (style only):\n" + "\n---\n".join(few_shot[:2])
    out = llm_client.complete_json(PLAN_PROMPT, user, max_tokens=4000)
    if not isinstance(out, dict) or not out.get("rationale"):
        return {**fallback, "fact_sheet": facts}
    allowed = {c["disruption_id"] for c in cases}
    plan = {**fallback, **{k: out[k] for k in ("rationale", "immediate_actions", "recovery_plan", "risks", "cited_cases")
                           if out.get(k)}, "generated_by": "llm"}
    plan["recommended_strategy"] = fallback["recommended_strategy"]  # never taken from the LLM
    plan["fallback_strategy"] = fallback["fallback_strategy"]
    for key in ("rationale", "immediate_actions", "recovery_plan", "risks"):
        plan[key] = _plain(plan.get(key))
    plan["rationale"], removed = enforce_citations(str(plan["rationale"]), allowed)
    wording_ok = _wording_ok(plan["rationale"])
    no_evidence = not ranked[0]["evidence_cases"]
    claims_history = no_evidence and bool(_HISTORICAL_CLAIM.search(plan["rationale"]))
    if not wording_ok or claims_history:  # cut-off text, or a model-only strategy described as historical: use the template
        plan["rationale"] = fallback["rationale"]
    plan["cited_cases"] = [c for c in plan.get("cited_cases") or [] if c in allowed] or fallback["cited_cases"]
    for key in ("immediate_actions", "recovery_plan", "risks"):
        # skip null/blank entries the LLM sometimes returns (str(None) would otherwise show up as a "None" bullet)
        plan[key] = [enforce_citations(str(x), allowed)[0] for x in (plan.get(key) or [])
                     if x is not None and str(x).strip().lower() not in ("", "none", "null")][:6]
    notes = []
    if removed:
        notes.append(f"Removed unverified case citations: {removed}")
    if not wording_ok:
        notes.append("Rationale replaced: the model's wording was incomplete or had unbalanced brackets")
    elif claims_history:
        notes.append("Rationale replaced: it described a strategy with no comparable past cases as historical")
    # Output guardrail: numbers must come from the fact sheet (or the user's own description).
    invented = unsupported_numbers(plan["rationale"], facts + " " + query)
    if invented:
        plan["rationale"] = fallback["rationale"]
        notes.append(f"Rationale replaced: it stated numbers not in the evidence ({', '.join(invented)})")
    other = [n for item in plan["recovery_plan"] + plan["risks"] for n in unsupported_numbers(str(item), facts + " " + query)]
    if other:
        notes.append(f"Unverified numbers in plan steps: {', '.join(other)}")
    if notes:
        plan["guardrail_note"] = " | ".join(notes)
    plan["fact_sheet"] = facts
    return plan
