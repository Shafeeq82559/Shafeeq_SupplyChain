"""Input and output guardrails.

Input:  emptiness/length checks, prompt-injection detection, PII masking, profanity, domain (off-topic) check.
Output: strips citations of case IDs that were not actually retrieved (hallucinated evidence).
Structured fields (enums, numeric ranges) are validated by the Pydantic schemas in src/api/schemas.py.
"""
import re
from dataclasses import dataclass, field

from src.services import llm_client
from src.utils.constants import SUPPLY_CHAIN_TERMS, TYPE_KEYWORDS

MIN_LEN, MAX_LEN = 3, 2000

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?|rules)",
    r"disregard (all |the )?(previous|prior|above|system)",
    r"(reveal|show|print|repeat) (me )?(your|the) (system )?(prompt|instructions)",
    r"you are now (a|an|in) ", r"act as (a|an) (?!supply)", r"\bjailbreak\b", r"\bDAN mode\b",
    r"forget (everything|your instructions)", r"<\s*/?\s*(system|assistant)\s*>", r"\bsudo\b",
    r"override (the )?(safety|guardrails?|rules)",
]
PROFANITY = {"fuck", "shit", "bitch", "bastard", "asshole", "cunt"}
PII_PATTERNS = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "card_number": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"(?<!\w)(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}(?!\w)"),
}
CASE_ID_RE = re.compile(r"DIS-\d{6}")


@dataclass
class GuardrailResult:
    allowed: bool
    sanitized_text: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return {"allowed": self.allowed, "sanitized_text": self.sanitized_text,
                "violations": self.violations, "warnings": self.warnings}


def mask_pii(text: str) -> tuple[str, list[str]]:
    found = []
    for name, pat in PII_PATTERNS.items():
        if pat.search(text):
            found.append(name)
            text = pat.sub(f"[{name.upper()}_REDACTED]", text)
    return text, found


# words that say something went wrong, so a generic supply-chain word alone ("supply chain", "supplier") is not enough
INCIDENT_TERMS = ["disrupt", "delay", "shortage", "outage", "halt", "shut", "stopp", "stall", "block", "cancel", "damag", "fail",
                  "fire", "flood", "strike", "stuck", "lost", "closed", "closure", "congest", "backlog", "late", "cut off",
                  "unavailable", "affected", "impact", "slowdown", "recall", "seiz", "sanction", "attack", "breach",
                  "hacker", "hacked", "bankrupt", "insolven", "collapse", "bottleneck", "explosion", "scarcity", "quarantine", "pandemic"]


def _term_hits(text: str, terms) -> set[str]:
    """Terms found as whole words (short ones) or word starts (stems of 6+ letters), never inside another word."""
    out = set()
    for w in (x.strip() for x in terms):
        if len(w) < 3:
            continue
        pattern = rf"\b{re.escape(w)}" if len(w) >= 6 or not w.isalpha() else rf"\b{re.escape(w)}(?:s|es|ed|ing)?\b"
        if re.search(pattern, text):
            out.add(w)
    return out


def is_supply_chain_related(text: str, use_llm: bool = True) -> bool:
    """On topic = describes a supply chain disruption: a disruption-type keyword, or at least two supply-chain terms, or one
    supply-chain term together with an incident word. A single generic term ("supply chain") is not enough."""
    t = f" {text.lower()} "
    domain = _term_hits(t, SUPPLY_CHAIN_TERMS)
    typed = _term_hits(t, [w for ws in TYPE_KEYWORDS.values() for w in ws])
    incident = _term_hits(t, INCIDENT_TERMS)
    if typed or len(domain) >= 2 or (domain and incident):
        return True
    if use_llm and llm_client.llm_available():
        out = llm_client.complete_json(
            "You are a strict topic classifier for a supply chain disruption assistant.",
            f'Does this text describe a supply chain disruption or incident (something that delayed, stopped, damaged or put at risk '
            f'suppliers, production, shipping or logistics)? General questions, small talk and other topics are NOT related. '
            f'Answer {{"related": true|false}}.\nText: """{text[:500]}"""', max_tokens=50)
        if out is not None:
            return bool(out.get("related"))
    return False


def validate_input(text: str | None, check_topic: bool = True) -> GuardrailResult:
    violations, warnings = [], []
    text = (text or "").strip()
    if len(text) < MIN_LEN:
        return GuardrailResult(False, text, ["Input is empty or too short."])
    if len(text) > MAX_LEN:
        violations.append(f"Input exceeds {MAX_LEN} characters.")
    lowered = text.lower()
    if any(re.search(p, lowered) for p in INJECTION_PATTERNS):
        violations.append("Possible prompt-injection attempt detected.")
    if any(re.search(rf"\b{w}\b", lowered) for w in PROFANITY):
        violations.append("Inappropriate language detected.")
    text, pii = mask_pii(text)
    if pii:
        warnings.append(f"Personal data masked: {', '.join(pii)}.")
    if not violations and check_topic and not is_supply_chain_related(text):
        violations.append("Query does not appear to be about a supply chain disruption.")
    return GuardrailResult(not violations, text, violations, warnings)


def enforce_citations(text: str, allowed_ids: set[str]) -> tuple[str, list[str]]:
    """Remove case IDs the model cited that are not in the retrieved evidence."""
    bad = sorted({c for c in CASE_ID_RE.findall(text or "") if c not in allowed_ids})
    for c in bad:
        text = text.replace(c, "[unverified case]")
    return text, bad
