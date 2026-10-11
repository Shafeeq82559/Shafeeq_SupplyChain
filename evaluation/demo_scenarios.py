"""Demo scenarios: 10 realistic, slightly complex disruption descriptions for the live demo.

Each scenario is written from a real dataset record (so it has ground truth and a reference answer built the same way
as the golden set) but phrased the way an operations manager would report it: several sentences with mixed signals such
as stock runway, a backup that only covers part of the volume, a restart already under way or a customer deadline.
Together they cover all six disruption types, every industry and region twice, severities 1-5, and backup / no backup.

Run (needs an LLM for the judge and the deep check; results -> evaluation/results/demo_scenarios_results.json):
  python -m evaluation.demo_scenarios               # full workflow + judge for each scenario
  python -m evaluation.demo_scenarios --deep-check  # also the DeepEval deep check shown in the UI
"""
import argparse
import json
import time
from pathlib import Path

from src.config import settings

SCENARIOS_PATH = Path(__file__).parent / "demo_scenarios.json"
RESULTS_PATH = settings.EVAL_DIR / "demo_scenarios_results.json"

# (dataset record, short title, description)
SCENARIOS = [
    ("DIS-042906", "Ice storm at a deep-tier substrate supplier",
     "An ice storm knocked out power overnight at a Tier-4 wafer substrate supplier in Ohio, United States, that feeds our "
     "Tier-1 circuit board assembler. Power came back after about 12 hours and they are already shipping again. We have a "
     "qualified second source for the substrate. Do we need to do anything beyond monitoring, and what happened in similar cases?"),
    ("DIS-070086", "Ransomware at a sole-source brake supplier",
     "A ransomware attack has encrypted the ERP and order systems of a small Tier-3 brake component maker in Sao Paulo, "
     "Brazil. They expect to be down for about four weeks while they rebuild their systems. They are our sole supplier for "
     "caliper castings, and our Tier-1 assembler says its line will stop once its two weeks of inventory runs out. How should we respond?"),
    ("DIS-053729", "Strike at an active-ingredient supplier",
     "Workers at our Tier-2 pharmaceutical active ingredient supplier near Hyderabad, India have been on strike for ten days, "
     "and the union says the walkout could continue. Output of the ingredient is down by about a quarter. We have no qualified "
     "second source, and switching would need a lengthy regulatory approval. What should we do?"),
    ("DIS-088515", "Rotterdam congestion holding aerospace forgings",
     "Congestion at the port of Rotterdam in the Netherlands is holding three containers of titanium forgings from our Tier-2 "
     "aerospace supplier; vessels are waiting two to three days for a berth. We have a qualified backup supplier in Spain "
     "that could send parts by truck. Our final assembly line has enough inventory for about a week. What is the best response?"),
    ("DIS-016391", "Export restrictions block packaging from Egypt",
     "A new export ban imposed by the government in Egypt has stopped our Tier-1 packaging supplier from sending cartons and "
     "labels to our consumer goods plants for the past two weeks. They are our sole supplier, and officials say the review "
     "could take longer. Two of our product lines are already running at reduced output. How have similar trade restrictions been handled?"),
    ("DIS-015937", "Fire destroys an aerospace fastener plant",
     "A fire destroyed the heat-treatment building at our Tier-3 aerospace fastener supplier in Nagoya, Japan, and the plant "
     "will be out of action for several months. We already have a qualified backup supplier for these fasteners, but it can "
     "only cover about half of our volume. What do similar cases suggest, and how should we plan the recovery?"),
    ("DIS-072800", "Floods cut off a sterile vial supplier",
     "Flooding in southern Chile has cut road access to our Tier-3 supplier of sterile vials and stoppers for our pharmaceutical "
     "fill-finish lines, and production there has been halted for about a month. We have a qualified backup supplier for the "
     "vials elsewhere in the region, but it needs time to ramp up. What should our plan be?"),
    ("DIS-072464", "Malware outage at a board contract manufacturer",
     "Our Tier-1 electronics contract manufacturer in Guadalajara, Mexico was hit by malware that took their manufacturing "
     "execution system and label printing offline for two days. They are restarting today but have a pile of delayed orders, "
     "and output this week is roughly half of plan. We have no backup supplier qualified for these circuit boards. "
     "How do we catch up on the delayed orders?"),
    ("DIS-041803", "One-day walkout at a harness supplier",
     "There was a one-day union walkout at our Tier-3 wiring harness supplier for our automotive plants in Durban, South Africa. "
     "Work resumed the next morning and they lost roughly one shift of output. We have an approved second supplier for the "
     "harnesses. Is this worth escalating, and what did similar cases do?"),
    ("DIS-087483", "Hamburg backlog delays packaging before a launch",
     "A short backlog at the port of Hamburg, Germany delayed one shipment of printed boxes for our consumer goods products "
     "from our Tier-2 packaging supplier by about a day. That supplier is our single source for these boxes. The delayed "
     "containers are now on their way, but our customer launch is next week. How cautious should we be?"),
]


def build() -> list[dict]:
    """Attach ground truth and the reference answer (same method as the golden set) and save the scenarios."""
    from evaluation.golden_set import _reference
    from src.rag.preprocessing import load_dataset
    df = load_dataset().set_index("disruption_id", drop=False)
    items = []
    for rid, title, query in SCENARIOS:
        r = df.loc[rid]
        reference, acceptable = _reference(df.reset_index(drop=True), r)
        items.append({"id": rid, "title": title, "query": query,
                      "expected": {"disruption_type": r.disruption_type, "industry": r.industry,
                                   "supplier_region": r.supplier_region, "disruption_severity": int(r.disruption_severity),
                                   "supplier_tier": int(r.supplier_tier), "has_backup_supplier": bool(r.has_backup_supplier)},
                      "acceptable_responses": acceptable, "reference_answer": reference})
    SCENARIOS_PATH.write_text(json.dumps(items, indent=2))
    return items


def run(deep_check: bool = False) -> list[dict]:
    """Each scenario through the same path as the UI: the full agent workflow (with the judge and its revision loop),
    then optionally the DeepEval deep check of the final plan."""
    from src.agents.workflow import run_workflow
    from src.services import deep_check as dc
    items = build()
    rows = []
    for s in items:
        t0 = time.time()
        out = run_workflow(s["query"])
        j, plan, c = out["judgement"], out["response"]["plan"], out["classification"]
        row = {"id": s["id"], "title": s["title"], "query": s["query"], "expected": s["expected"],
               "acceptable_responses": s["acceptable_responses"],
               "classification": {k: c.get(k) for k in ("disruption_type", "industry", "supplier_region", "supplier_tier",
                                                         "has_backup_supplier", "estimated_severity", "method")},
               "priority": out["impact"]["priority"]["priority_level"], "recommended": plan["recommended_strategy"],
               "plan_by": plan.get("generated_by"), "judge": {k: j.get(k) for k in ("overall_score", "passed", "scores",
                                                                                     "reasons", "overall_feedback", "judge")},
               "revisions": out.get("revisions", 0), "seconds": round(time.time() - t0, 1)}
        if deep_check:
            try:
                d = dc.run(s["query"], plan)
                row["deep_check"] = {k: (v or {}).get("score") for k, v in d["scores"].items()}
                row["deep_check_reasons"] = {k: (v or {}).get("reason") for k, v in d["scores"].items()}
            except RuntimeError as e:
                row["deep_check_error"] = str(e)
        rows.append(row)
        print(f"{s['id']} {s['title'][:40]:40} judge {j['overall_score']} {'PASS' if j['passed'] else 'FAIL'} "
              f"rev {row['revisions']} {row.get('deep_check', '')}", flush=True)
    RESULTS_PATH.write_text(json.dumps({"model": settings.LLM_MODEL, "judge_model": settings.JUDGE_MODEL,
                                        "scenarios": rows}, indent=2, default=str))
    return rows


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--deep-check", action="store_true")
    p.add_argument("--build-only", action="store_true")
    a = p.parse_args()
    build() if a.build_only else run(a.deep_check)
