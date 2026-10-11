"""Golden evaluation set.

Scenarios are generated from real dataset records (stratified by disruption type), phrased the way an
operations manager would describe an incident - using synonyms ("typhoon", "ransomware") and countries
rather than dataset labels - so retrieval and classification are tested on realistic free text.
Ground truth per scenario: the record's attributes plus a reference answer built from the historical
best-performing response for that disruption type / industry / severity, and the set of acceptable
responses (within ACCEPTABLE_MARGIN of the best). The set is synthetic: queries come from templates and the
reference is derived from the same dataset the system retrieves from, so it checks consistency with the data,
not real-world correctness.
"""
import json
import random
from pathlib import Path

import pandas as pd

from src.rag.preprocessing import load_dataset
from src.services.recommendation import NEEDS_BACKUP

GOLDEN_PATH = Path(__file__).parent / "golden_set.json"

PHRASES = {
    "Natural Disaster": ["a typhoon flooded", "an earthquake damaged", "severe flooding hit", "a hurricane struck"],
    "Cyber Attack": ["a ransomware attack locked the systems of", "hackers breached the ERP of", "a malware outage took down"],
    "Labor Strike": ["workers walked out at", "a union strike stopped work at", "industrial action halted"],
    "Port Congestion": ["port congestion is delaying containers from", "a shipping backlog at the port is holding shipments from",
                        "vessel queues at the harbour are delaying"],
    "Geopolitical": ["new export sanctions have blocked", "a trade embargo cut off", "sudden tariffs and border restrictions hit"],
    "Factory Incident": ["a fire broke out at the plant of", "an equipment breakdown stopped the production line at",
                         "a contamination issue shut down the factory of"],
}
PLACES = {"Asia-Pacific": ["Taiwan", "Vietnam", "Japan", "India"], "Europe": ["Germany", "Poland", "Italy"],
          "North America": ["Mexico", "Texas", "Canada"], "South America": ["Brazil", "Chile"],
          "Africa/Middle East": ["South Africa", "the UAE", "Egypt"]}
PRODUCTS = {"Electronics": "semiconductor", "Automotive": "auto parts", "Consumer Goods": "consumer goods packaging",
            "Pharmaceuticals": "pharma active ingredient", "Aerospace": "aerospace components"}
SEVERITY_TEXT = {1: "It is a minor, brief slowdown.", 2: "There are moderate delays.",
                 3: "Output is significantly disrupted.", 4: "Production is severely halted for weeks.",
                 5: "It is a catastrophic complete shutdown expected to last months."}


ACCEPTABLE_MARGIN = 0.15  # a strategy within 15% of the best median recovery time is an acceptable answer


MIN_STRATEGY_CASES = 5  # a strategy needs this many comparable cases to count as the best one


def _reference(df: pd.DataFrame, r) -> tuple[str, list[str]]:
    """Reference answer built from the same comparable-case pool the system compares strategies on (same type,
    industry, region, severity band and backup status), stated the way the system's evidence sheet states it. It
    contains only claims the data can support: the profile, the pool size, and the strategy with the fastest median
    full recovery (plus the strategies within ACCEPTABLE_MARGIN of it). Without a backup supplier, Alternative Supplier is
    not an immediate option (the same rule the system ranks by), so it is left out of the expected answers."""
    from src.agents.investigation_agent import _strategy_pool
    sev, backup = int(r.disruption_severity), bool(r.has_backup_supplier)
    filters = {"disruption_type": r.disruption_type, "industry": r.industry, "supplier_region": r.supplier_region,
               "min_severity": max(1, sev - 1), "max_severity": min(5, sev + 1)}
    pool = _strategy_pool(filters, {"has_backup_supplier": backup})
    if pool:
        rows, n = pd.DataFrame(pool["cases"]), pool["size"]
    else:  # too few comparable cases: fall back to type + industry + severity band
        rows = df[(df.disruption_type == r.disruption_type) & (df.industry == r.industry)
                  & (df.disruption_severity.between(sev - 1, sev + 1))]
        n = len(rows)
    stats = rows.groupby("response_type")["full_recovery_days"].agg(["median", "size"])
    if not backup and len(stats.drop(index=NEEDS_BACKUP, errors="ignore")):
        stats = stats.drop(index=NEEDS_BACKUP, errors="ignore")
    perf = stats[stats["size"] >= MIN_STRATEGY_CASES]["median"].sort_values()
    if perf.empty:
        perf = stats["median"].sort_values()
    best = perf.index[0]
    acceptable = [s for s, v in perf.items() if v <= perf.iloc[0] * (1 + ACCEPTABLE_MARGIN)]
    others = [s for s in acceptable if s != best]
    text = (f"This is a {r.disruption_type} disruption (severity {sev}) affecting a Tier-{r.supplier_tier} "
            f"{r.industry} supplier in {r.supplier_region}, {'with a backup supplier' if backup else 'no backup supplier'}. "
            f"Among {n:,} comparable past cases, {best} had the fastest median full recovery ({perf.iloc[0]:.0f} days)"
            + (" among the options available without a backup supplier" if not backup else "") + ". "
            f"Recommended: {best}"
            + (f"; {', '.join(others)} would also be acceptable (within {ACCEPTABLE_MARGIN:.0%} of the best median recovery)"
               if others else "") + ".")
    return text, acceptable


def _pick(df: pd.DataFrame, per_type: int, seed: int) -> pd.DataFrame:
    """Per disruption type, rows with distinct (industry, severity) so no two scenarios share the same evidence,
    interleaved across types so any prefix of the set (e.g. the 10 scenarios sent to the LLM stages) covers every type."""
    per = []
    for _, g in df.groupby("disruption_type"):
        g = g.sample(frac=1, random_state=seed).drop_duplicates(["industry", "disruption_severity"]).head(per_type)
        per.append(g.reset_index(drop=True))
    return pd.concat(per).assign(_k=lambda d: d.groupby(d.disruption_type).cumcount()).sort_values(
        ["_k", "disruption_type"], kind="stable").drop(columns="_k")


def build(n: int = 30, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    df = load_dataset()
    picks = _pick(df, max(1, n // 6), seed)
    items = []
    for r in picks.itertuples():
        reference, acceptable = _reference(df, r)
        backup = "We have a backup supplier." if r.has_backup_supplier else "We have no backup supplier."
        query = (f"{rng.choice(PHRASES[r.disruption_type]).capitalize()} our Tier-{r.supplier_tier} "
                 f"{r.supplier_size.lower()} {PRODUCTS[r.industry]} supplier in {rng.choice(PLACES[r.supplier_region])}. "
                 f"{SEVERITY_TEXT[r.disruption_severity]} {backup} What happened in similar cases and how should we respond?")
        items.append({"id": r.disruption_id, "query": query,
                      "expected": {"disruption_type": r.disruption_type, "industry": r.industry,
                                   "supplier_region": r.supplier_region, "disruption_severity": int(r.disruption_severity),
                                   "supplier_tier": int(r.supplier_tier), "has_backup_supplier": bool(r.has_backup_supplier)},
                      "acceptable_responses": acceptable, "reference_answer": reference})
    GOLDEN_PATH.write_text(json.dumps(items, indent=2))
    return items


def load(n: int | None = None) -> list[dict]:
    items = json.loads(GOLDEN_PATH.read_text()) if GOLDEN_PATH.exists() else build()
    return items[:n] if n else items
