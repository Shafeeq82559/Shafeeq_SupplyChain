"""Disruption Classification Agent.

Turns a free-text incident description into structured attributes that match the dataset vocabulary
(disruption type, industry, region, tier, size, backup availability, estimated severity), which then
drive metadata filters, ML predictions and prioritization. Uses the LLM when available and a keyword
rule engine otherwise; LLM output is validated field-by-field against the allowed values.
"""
import re

from src.services import llm_client
from src.utils.constants import (DISRUPTION_TYPES, INDUSTRIES, INDUSTRY_KEYWORDS, REGION_KEYWORDS, REGIONS,
                                 SUPPLIER_SIZES, TYPE_KEYWORDS)

SEVERITY_CUES = [
    (5, ["catastroph", "complete shutdown", "total shutdown", "destroyed", "critical", "all production", "months"]),
    (4, ["severe", "shut down", "shutdown", "halted", "stopped", "major", "weeks", "closed"]),
    (3, ["significant", "serious", "substantial", "disrupted"]),
    (2, ["moderate", "partial", "slowdown", "delays", "delayed"]),
    (1, ["minor", "small", "slight", "brief", "limited"]),
]

_TIER_WORDS = {"one": 1, "first": 1, "two": 2, "second": 2, "three": 3, "third": 3, "four": 4, "fourth": 4}
# "tier 1", "tier-2", "tier one" and the other order: "1 tier", "2-tier", "first-tier", "third tier"
_TIER_RE = re.compile(r"\btier[\s-]?([1-4]|one|two|three|four)\b|\b([1-4]|first|second|third|fourth)(?:st|nd|rd|th)?[\s-]?tier\b")
_NO_BACKUP_RE = re.compile(
    r"\bno (?:[a-z-]+ ){0,2}?(?:backup|alternative|alternate|second|secondary|substitute)|single[- ]source|"
    r"sole (tier[\s-]?\d )?(supplier|source)|only supplier|neither is (currently )?qualified|"
    r"(?:supplier|source) alone")
# strict "there is one" wording ("searching for an alternative supplier" is not a backup)
_HAS_BACKUP_RE = re.compile(
    r"(we (already )?have|there is|with|have) (a |an |one )?(fully |currently )?(pre-?)?(qualified |approved |ready )?"
    r"(backup|second|secondary|alternat\w+) (supplier|source)")

# Severity reading for the offline classifier. Explicit magnitude words win over event verbs ("shut down", "halted");
# the cues below are removed first because they are not about how bad the event is.
_STOCK_DURATION = re.compile(r"\b(?:stock|inventory|buffer)\b[^.]{0,40}?\b(?:days?|weeks?|months?)\b|"
                             r"\b(?:days?|weeks?|months?) (?:of |worth of )?(?:safety )?(?:stock|inventory|supply)\b")
_NEGATED_SHUTDOWN = re.compile(r"\bno (?:[a-z-]+ ){0,2}?(?:shutdown|shut down|stoppage|disruption)\b[^.]*")
_CRITICAL_ITEM = re.compile(r"\bcritical (?:[a-z-]+ )?(?:components?|parts?|materials?|supplies|items?|skus?|goods|inputs?)\b")
_CALM = re.compile(r"operating normally|unaffected|not (?:expected to )?(?:affect|impact)|no (?:production )?(?:shutdown|stoppage) is expected")


_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "eleven": 11, "twelve": 12, "a couple of": 2, "couple of": 2, "a few": 3, "few": 3, "several": 5}
_UNIT_DAYS = {"hour": 1 / 24, "day": 1.0, "week": 7.0, "month": 30.0}
_DURATION = re.compile(r"\b(\d+(?:\.\d+)?|a couple of|couple of|a few|several|eleven|twelve|three|four|five|six|seven|eight|nine|ten|one|two|an|a)"
                       r"[\s-]*(hour|day|week|month)s?\b")
# durations that are not "how long the event lasts": stock runway, things that still work, and forecasts
_NOT_OUTAGE = re.compile(r"\b(?:can|could|will|should|may|might|would)\s+(?:still\s+)?(?:continue|keep|run|operate|last|cover|support|sustain)\b[^.]{0,60}|"
                         r"\b(?:next|within|over the next|in the next|for the next)\b[^.]{0,25}?(?:hour|day|week|month)s?\b|"
                         r"\b(?:expects?|expected|estimated|forecast|anticipated)\b[^.]{0,60}")


def _outage_days(t: str) -> float | None:
    """Longest stated length of the event itself ("1 day power outage", "stuck for two weeks"), in days; None if none is stated."""
    days = []
    for m in _DURATION.finditer(_NOT_OUTAGE.sub(" ", t)):
        n = float(m.group(1)) if m.group(1)[0].isdigit() else _NUMBER_WORDS[m.group(1)]
        days.append(n * _UNIT_DAYS[m.group(2)])
    if re.search(r"\bovernight\b", t):
        days.append(0.5)
    return max(days) if days else None


def _days_to_level(d: float) -> int:
    return 1 if d <= 1.5 else 2 if d <= 4 else 3 if d <= 14 else 4 if d <= 35 else 5


def _rule_severity_info(text: str) -> tuple[int, str]:
    """(severity 1-5, where it came from: explicit wording, a stated duration, broad cue words, or just the default of 3)."""
    t = _CRITICAL_ITEM.sub(" ", _NEGATED_SHUTDOWN.sub(" ", _STOCK_DURATION.sub(" ", text)))
    explicit = [lvl for lvl, words in _STRICT_SEVERITY if _cue_hits(t, words)]
    if explicit:
        level, source = max(explicit), "explicit"
    elif (days := _outage_days(t)) is not None:
        level, source = _days_to_level(days), "duration"
    else:
        cue = next((lvl for lvl, cues in SEVERITY_CUES if any(c in t for c in cues)), None)
        level, source = (cue, "cues") if cue else (3, "default")
    return (min(level, 2) if _CALM.search(text) else level), source


def _rule_severity(text: str) -> int:
    return _rule_severity_info(text)[0]


# explicit severity wording only (the broad SEVERITY_CUES also match "weeks", "closed"... which are not reliable here)
_STRICT_SEVERITY = [(5, ["catastrophic", "complete shutdown", "total shutdown"]), (4, ["severe", "severely"]),
                    (3, ["significant", "significantly"]), (2, ["moderate", "moderately"]), (1, ["minor", "slight", "slightly"])]

SYSTEM_PROMPT = f"""You are a supply chain disruption classification agent.
Extract structured attributes from an incident description. Use ONLY these allowed values:
- disruption_type: {DISRUPTION_TYPES}
- industry: {INDUSTRIES} or null if unknown
- supplier_region: {REGIONS} or null if unknown
- supplier_tier: 1-4 (1 = direct supplier) or null if not stated
- supplier_size: {SUPPLIER_SIZES}, or null unless the description explicitly states the supplier's size (never infer it from
  phrases like "a major manufacturer" or "a small number of suppliers")
- has_backup_supplier: true only if the description says a second source is ALREADY qualified and usable now. Candidate or
  prospective suppliers that are not yet qualified, "sole"/"single-source" suppliers, and alternative ports or routes are
  NOT a backup supplier (false). null only if nothing is said about alternative sourcing.
- estimated_severity: integer 1 (minor) to 5 (critical), judged from the described scale and duration. When a duration is stated
  use it as a guide for how long the EVENT lasts: up to about 1 day = 1; 2 to 3 days = 2; about 1 to 2 weeks = 3; 3 to 6 weeks = 4;
  months = 5. Ignore durations that are not the length of the event: how long stock or inventory will last, how long a line
  "can keep running", and forecasts of future recovery. An unknown restart date is not by itself "open-ended".
  If the text says nothing about scale or duration, use 3
Return JSON with keys: disruption_type, industry, supplier_region, supplier_tier, supplier_size,
has_backup_supplier, estimated_severity, confidence (0-1), reasoning (one or two sentences)."""


def _best_match(text: str, lexicon: dict[str, list[str]]) -> tuple[str | None, int]:
    """Entry with the most keyword hits; on a tie, the one whose keyword appears first in the text (so "pharmaceutical
    packaging" is Pharmaceuticals and "automotive manufacturer ... electronic components" is Automotive)."""
    def hits(w: str) -> int:
        # short plain words must be whole words ("port" must not match "export"); longer stems and phrases may match inside
        if len(w) <= 5 and w.isalpha():
            return len(re.findall(rf"\b{re.escape(w)}(?:s|es|ed|ing|er|ers)?\b", text))
        return text.count(w)

    scores = {k: sum(hits(w) for w in words) for k, words in lexicon.items()}
    top = max(scores.values())
    if top == 0:
        return None, 0
    tied = [k for k, v in scores.items() if v == top]
    return min(tied, key=lambda k: min(text.find(w) for w in lexicon[k] if w in text)), top


def rule_classify(text: str) -> dict:
    t = f" {text.lower()} "
    dtype, dscore = _best_match(t, TYPE_KEYWORDS)
    industry, _ = _best_match(t, INDUSTRY_KEYWORDS)
    region, _ = _best_match(t, REGION_KEYWORDS)
    severity, severity_source = _rule_severity_info(t)
    tier = None
    m = _TIER_RE.search(t)
    if m:
        raw = m.group(1) or m.group(2)
        tier = int(raw) if raw.isdigit() else _TIER_WORDS[raw]
    backup = None
    if _NO_BACKUP_RE.search(t):
        backup = False
    elif _HAS_BACKUP_RE.search(t) or (re.search(r"(backup|secondary) supplier", t) and not re.search(
            r"(search\w*|look\w*|find\w*|identif\w*|seek\w*|need\w*)( for)?( an?| the)? (backup|secondary|second|alternat\w+)", t)):
        backup = True
    size = next((s for s in SUPPLIER_SIZES if f"{s.lower()} supplier" in t or f"{s.lower()}-sized" in t), None)
    found = sum(x is not None for x in (dtype, industry, region))
    return {
        "disruption_type": dtype or "Factory Incident",
        "industry": industry, "supplier_region": region, "supplier_tier": tier, "supplier_size": size,
        "has_backup_supplier": backup, "estimated_severity": severity, "severity_source": severity_source,
        "confidence": round(max(0.1, min(0.9, 0.3 + 0.15 * found + 0.05 * min(dscore, 3)) - (0.15 if severity_source == "default" else 0)), 2),
        "reasoning": (f"Keyword match: type '{dtype or 'default'}'"
                      f"{f', industry {industry}' if industry else ''}{f', region {region}' if region else ''}; "
                      + {"explicit": f"severity {severity} from the size wording used.",
                         "duration": f"severity {severity} from the stated duration.",
                         "cues": f"severity {severity} inferred from scale cue words.",
                         "default": "severity 3 assumed: nothing in the text says how big or how long."}[severity_source]),
        "method": "rules",
    }


def _cue_hits(t: str, words: list[str]) -> int:
    """Keyword hits in text. Keywords of 6+ letters match as word starts (the lexicon uses stems such as "pharma");
    shorter ones must be whole words, optionally plural/-ed/-ing, so "port" does not match "report" or "war" "warehouse".
    Keywords of 2 letters or fewer are ignored because they match too much."""
    total = 0
    for w in (x.strip() for x in words):
        if len(w) < 3:
            continue
        pattern = rf"\b{re.escape(w)}" if len(w) >= 6 else rf"\b{re.escape(w)}(?:s|es|ed|ing)?\b"
        total += len(re.findall(pattern, t))
    return total


def override_conflicts(overrides: dict, text: str) -> list[str]:
    """Values the user set that the description clearly contradicts. Quiet by design: it only speaks when the text
    explicitly points to something else and never mentions the user's value. It does not compare against the
    classifier's guess (which is sometimes a default), so it cannot fire on guesses."""
    t = f" {text.lower()} "
    out = []
    for key, label, lexicon in (("disruption_type", "Type", TYPE_KEYWORDS), ("industry", "Industry", INDUSTRY_KEYWORDS),
                                ("supplier_region", "Region", REGION_KEYWORDS)):
        mine = overrides.get(key)
        if mine is None:
            continue
        hits = {k: _cue_hits(t, words) for k, words in lexicon.items()}
        others = {k: n for k, n in hits.items() if k != mine and n > 0}
        if hits.get(mine, 0) == 0 and others:
            out.append(f"{label}: you set {mine}, but the text only points to {max(others, key=others.get)}")
    m = _TIER_RE.search(t)
    stated_tier = (lambda r: int(r) if r.isdigit() else _TIER_WORDS[r])(m.group(1) or m.group(2)) if m else None
    if overrides.get("supplier_tier") is not None and stated_tier and stated_tier != int(overrides["supplier_tier"]):
        out.append(f"Tier: you set {overrides['supplier_tier']}, but the text says Tier {stated_tier}")
    stated = False if _NO_BACKUP_RE.search(t) else (True if _HAS_BACKUP_RE.search(t) else None)
    mine_b = overrides.get("has_backup_supplier")
    if mine_b is not None and stated is not None and stated != mine_b:
        out.append(f"Backup supplier: you set {'Yes' if mine_b else 'No'}, but the text says there is "
                   f"{'one' if stated else 'none'}")
    levels = {lvl for lvl, words in _STRICT_SEVERITY if _cue_hits(t, words)}
    sev = overrides.get("disruption_severity")
    if sev is not None and len(levels) == 1 and abs(next(iter(levels)) - int(sev)) >= 2:
        out.append(f"Severity: you set {sev}, but the wording suggests about {next(iter(levels))}")
    return out


def ambiguity_notes(text: str, overrides: dict | None = None, classification: dict | None = None) -> list[str]:
    """Places where the description itself points two ways (e.g. "a typhoon and a ransomware attack", or a backup
    supplier that both exists and does not). Deliberately conservative: it only speaks on an exact tie between the two
    best categories, and never for a field the user has set themselves."""
    t, overrides, classification = f" {text.lower()} ", overrides or {}, classification or {}
    out = []
    for key, label, lexicon in (("disruption_type", "disruption types", TYPE_KEYWORDS), ("industry", "industries", INDUSTRY_KEYWORDS),
                                ("supplier_region", "regions", REGION_KEYWORDS)):
        if overrides.get(key) is not None:
            continue
        ranked = sorted(((n, k) for k, words in lexicon.items() if (n := _cue_hits(t, words)) > 0), reverse=True)
        if len(ranked) >= 2 and ranked[0][0] == ranked[1][0]:
            chosen = classification.get(key) or ranked[0][1]
            out.append(f"The description fits both {ranked[0][1]} and {ranked[1][1]} ({label}); the analysis used {chosen}. "
                       "Set it under 'Add details you already know' if that is not what you meant")
    if overrides.get("has_backup_supplier") is None and _NO_BACKUP_RE.search(t) and _HAS_BACKUP_RE.search(t):
        out.append("The description says there is a backup supplier and also that there is none; the analysis assumed none. "
                   "Set it under 'Add details you already know' to be sure")
    return out


def _validated(llm: dict, fallback: dict) -> dict:
    out = dict(fallback)
    if llm.get("disruption_type") in DISRUPTION_TYPES:
        out["disruption_type"] = llm["disruption_type"]
    for key, allowed in (("industry", INDUSTRIES), ("supplier_region", REGIONS), ("supplier_size", SUPPLIER_SIZES)):
        v = llm.get(key)
        if v in allowed:
            out[key] = v
        elif v is None and fallback.get(key) is None:
            out[key] = None
    if llm.get("supplier_tier") in (1, 2, 3, 4, "1", "2", "3", "4"):
        out["supplier_tier"] = int(llm["supplier_tier"])
    if isinstance(llm.get("has_backup_supplier"), bool):
        out["has_backup_supplier"] = llm["has_backup_supplier"]
    try:
        out["estimated_severity"] = min(5, max(1, int(llm.get("estimated_severity"))))
        if not (fallback.get("severity_source") == "default" and out["estimated_severity"] == 3):
            out["severity_source"] = "llm"  # else: no cue in the text and the model also said 3, so it is the default
    except (TypeError, ValueError):
        pass
    try:
        out["confidence"] = round(min(1.0, max(0.0, float(llm.get("confidence")))), 2)
    except (TypeError, ValueError):
        pass
    out["reasoning"] = str(llm.get("reasoning") or fallback["reasoning"])[:500]
    out["method"] = "llm"
    return out


def classify(text: str) -> dict:
    fallback = rule_classify(text)
    llm = llm_client.complete_json(SYSTEM_PROMPT, f'Incident description: """{text}"""', max_tokens=1200)
    result = _validated(llm, fallback) if isinstance(llm, dict) else fallback
    result["suggested_filters"] = {k: result[k] for k in ("disruption_type", "industry", "supplier_region")
                                   if result.get(k)}
    return result
