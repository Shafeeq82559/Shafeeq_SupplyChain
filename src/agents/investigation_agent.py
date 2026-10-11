"""Investigation Agent: finds similar historical disruptions via hybrid RAG and completes the profile.

Filters come from the classification (type, industry, region), a severity band around the disruption's severity,
and any user-specified filters. If too few cases match, filters are relaxed step by step (region -> wider severity
band -> industry -> severity) so the agent always returns evidence, and it records which relaxations it made.
It also returns a larger pool of comparable cases (`strategy_pool`) that the response planner uses to compare
strategies; the closest cases (`similar_cases`) are the examples that are shown and cited.
"""
import re

import pandas as pd

from src.rag.hybrid_retriever import filter_mask, hybrid_search, indexed_frame
from src.rag.preprocessing import load_dataset
from src.services import feedback
from src.services.recommendation import historical_summary

PROFILE_FIELDS = ["disruption_type", "industry", "supplier_tier", "supplier_region", "supplier_size",
                  "has_backup_supplier", "disruption_severity"]
MIN_CASES = 5
SEVERITY_BAND = 1  # similar cases must be within +-1 severity of the disruption being analysed
POOL_MIN, POOL_MAX = 30, 1000  # size limits of the pool strategies are compared on
POOL_COLUMNS = ["disruption_id", "response_type", "full_recovery_days", "partial_recovery_days", "production_impact_pct",
                "revenue_loss_usd", "permanent_supplier_change", "response_time_days", "response_effectiveness"]

# Response-strategy vocabulary. If it appears in the description of the user's constraints ("we have 10 days of
# inventory") the search matches past cases that merely used that strategy, and the strategy ranking then "confirms"
# itself. It is removed from the search query only; the planner and the LLM still see the full text.
_STRATEGY_WORDS = re.compile(
    r"\b(finished[- ]goods|inventor(?:y|ies)|buffer(?:s|ed|ing)?|safety stock|stock(?:s|pile\w*)?|rout\w*|trucking|"
    r"alternat\w+ (?:suppliers?|sources?|ports?|routes?)|back-?up (?:suppliers?|sources?|plans?)|production)\b", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def retrieval_query(text: str) -> str:
    """Query used for similar-case search: the first sentence (the event itself) stays untouched; strategy wording is
    stripped from the later sentences, which usually describe the user's constraints and options."""
    first, *rest = _SENTENCE_END.split(text.strip())
    cleaned = [re.sub(r"\s{2,}", " ", _STRATEGY_WORDS.sub("", s)).strip() for s in rest]
    return " ".join([first] + [s for s in cleaned if s])


def _search_with_relaxation(q: str, filters: dict, user_filters: dict, severity: int | None, top_k: int, boosts: dict):
    """Search; if too few cases match, loosen filters step by step: region, wider severity band, industry, severity.
    Filters the user set explicitly are never loosened."""
    user_filters = user_filters or {}
    sev_user = any(user_filters.get(k) is not None for k in ("disruption_severity", "min_severity", "max_severity"))
    if severity is not None and not sev_user:
        filters = {**filters, "min_severity": max(1, severity - SEVERITY_BAND), "max_severity": min(5, severity + SEVERITY_BAND)}
    relaxations = []
    res = hybrid_search(q, top_k=top_k, filters=filters, boosts=boosts)
    for key in ("supplier_region", "severity_wide", "industry", "severity"):
        if len(res["results"]) >= MIN_CASES:
            break
        if key == "severity_wide":
            if sev_user or severity is None or "min_severity" not in filters:
                continue
            filters = {**filters, "min_severity": max(1, severity - 2 * SEVERITY_BAND), "max_severity": min(5, severity + 2 * SEVERITY_BAND)}
            relaxations.append(f"Widened the severity band to +-{2 * SEVERITY_BAND} (too few exact matches)")
        elif key == "severity":
            if sev_user or "min_severity" not in filters:
                continue
            filters = {k: v for k, v in filters.items() if k not in ("min_severity", "max_severity")}
            relaxations.append("Dropped the severity filter (too few exact matches)")
        else:
            if key not in filters or user_filters.get(key):
                continue
            filters = {k: v for k, v in filters.items() if k != key}
            relaxations.append(f"Relaxed '{key}' filter (too few exact matches)")
        res = hybrid_search(q, top_k=top_k, filters=filters, boosts=boosts)
    return res, filters, relaxations


def _strategy_pool(filters: dict, profile: dict) -> dict | None:
    """Comparable past cases that response strategies are compared on: same type, industry, region and severity band
    as the search, and the same backup-supplier status (strategies are chosen very differently with and without a
    backup, so mixing them would credit a strategy for the situations it happens to be used in). Chosen by profile
    only - not by the wording of the description - so the strategy ranking cannot be skewed by it."""
    df = indexed_frame()
    for with_backup in (True, False):
        f = {"has_backup_supplier": profile["has_backup_supplier"], **filters} if with_backup else dict(filters)
        mask = filter_mask(df, f)
        if mask is not None and int(mask.sum()) >= POOL_MIN:
            break
    else:
        return None  # too few comparable cases: the caller falls back to the closest cases
    rows = df[mask][POOL_COLUMNS]
    if len(rows) > POOL_MAX:
        rows = rows.sample(POOL_MAX, random_state=0)
    parts = [f"{label} {' / '.join(f[k]) if isinstance(f[k], list) else f[k]}" for k, label in
             (("disruption_type", "type"), ("industry", "industry"), ("supplier_region", "region")) if f.get(k)]
    if f.get("disruption_severity") is not None:
        parts.append(f"severity {f['disruption_severity']}")
    elif f.get("min_severity") is not None or f.get("max_severity") is not None:
        parts.append(f"severity {f.get('min_severity', 1)}-{f.get('max_severity', 5)}")
    if "has_backup_supplier" in f:
        parts.append("with a backup supplier" if f["has_backup_supplier"] else "no backup supplier")
    return {"cases": rows.to_dict("records"), "size": len(rows), "filters": f,
            "description": f"{len(rows):,} comparable past cases ({', '.join(parts)})"}


def investigate(query: str, classification: dict, overrides: dict | None = None, top_k: int = 10,
                user_filters: dict | None = None) -> dict:
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    base = {"disruption_type": overrides.get("disruption_type") or classification.get("disruption_type"),
            "industry": overrides.get("industry") or classification.get("industry"),
            "supplier_region": overrides.get("supplier_region") or classification.get("supplier_region")}
    filters = {k: v for k, v in base.items() if v}
    filters.update({k: v for k, v in (user_filters or {}).items() if v not in (None, "", [])})
    severity = overrides.get("disruption_severity") or classification.get("estimated_severity")
    res, filters, relaxations = _search_with_relaxation(
        retrieval_query(query), filters, user_filters or {}, int(severity) if severity else None, top_k,
        feedback.case_boosts())
    cases = res["results"]

    # Complete the disruption profile: user overrides > classification > similar cases > dataset mode
    profile, assumptions = {}, []
    sim = pd.DataFrame(cases) if cases else load_dataset().head(0)
    full = load_dataset()
    for f in PROFILE_FIELDS:
        src_val = overrides.get(f)
        if src_val is None and f == "disruption_severity":
            src_val = classification.get("estimated_severity")
        elif src_val is None:
            src_val = classification.get(f)
        if src_val is None:
            pool = sim if len(sim) else full
            src_val = pool[f].mode().iloc[0]
            src_val = src_val.item() if hasattr(src_val, "item") else src_val
            assumptions.append(f"{f} not stated; assumed '{src_val}' (most common among similar cases)")
        profile[f] = src_val
    if overrides.get("disruption_severity") is None and classification.get("severity_source") == "default":
        assumptions.append("disruption_severity not stated; assumed '3' (nothing in the description says how big or how long)")
    profile["supplier_tier"] = int(profile["supplier_tier"])
    profile["disruption_severity"] = int(profile["disruption_severity"])
    profile["has_backup_supplier"] = bool(profile["has_backup_supplier"])

    return {"similar_cases": cases, "strategy_pool": _strategy_pool(filters, profile),
            "filters_applied": filters, "relaxations": relaxations,
            "total_matching_filters": res["total_matching_filters"], "historical_summary": historical_summary(cases),
            "profile": profile, "assumptions": assumptions}
