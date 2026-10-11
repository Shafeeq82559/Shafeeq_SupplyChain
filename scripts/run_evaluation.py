"""Run the full evaluation suite and write results to evaluation/results/.

Usage:
  python -m scripts.run_evaluation                 # retrieval + classification + DeepEval + RAGAS + judge
  python -m scripts.run_evaluation --no-llm        # only the metrics that need no LLM
  python -m scripts.run_evaluation --n-llm 10      # number of scenarios scored by LLM-based frameworks
  python -m scripts.run_evaluation --only ragas    # re-run one LLM stage on the saved generated outputs
"""
import argparse
import json
import time

from evaluation import golden_set
from evaluation.retrieval_eval import evaluate_classification, evaluate_retrieval
from src.config import settings
from src.services import llm_client
from src.utils.logger import get_logger

log = get_logger("evaluation")
OUT = settings.EVAL_DIR
QUICK = False  # --quick: results go only to runs/<model>-quick, never over the main results


def save(name: str, data: dict):
    """Write the latest result (read by the API/UI/docs) and keep a per-model copy so runs never overwrite each other."""
    text = json.dumps(data, indent=2, default=str)
    if not QUICK:
        (OUT / f"{name}.json").write_text(text)
    run_dir = OUT / "runs" / (settings.JUDGE_MODEL.split("/")[-1] + ("-quick" if QUICK else ""))
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"{name}.json").write_text(text)
    log.info("Saved %s (+ copy in %s)", OUT / f"{name}.json", run_dir)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--n-llm", type=int, default=10)
    p.add_argument("--rebuild-golden", action="store_true")
    p.add_argument("--reuse-outputs", action="store_true", help="Reuse generated outputs from a previous run")
    p.add_argument("--only", choices=["deepeval", "ragas"], help="Re-run a single LLM stage on the saved outputs")
    p.add_argument("--quick", action="store_true", help="Smoke check: first 3 scenarios, LLM stages only, separate folder")
    args = p.parse_args()
    global QUICK
    QUICK = args.quick
    if args.only:
        outputs = json.loads((OUT / "generated_outputs.json").read_text())
        if args.only == "deepeval":
            from evaluation.deepeval_suite import run_deepeval
            save("deepeval_results", run_deepeval(outputs))
        else:
            from evaluation.ragas_suite import run_ragas
            save("ragas_results", run_ragas(outputs))
        return
    t0 = time.time()
    golden = golden_set.build() if args.rebuild_golden or not golden_set.GOLDEN_PATH.exists() else golden_set.load()
    log.info("Golden set: %d scenarios", len(golden))

    use_llm = not args.no_llm and llm_client.llm_available()
    if not QUICK:
        save("retrieval_eval", evaluate_retrieval(golden))
        save("classification_eval", evaluate_classification(golden, use_llm=use_llm))
    if not use_llm:
        log.info("LLM disabled - skipping DeepEval, RAGAS and LLM-as-Judge. Done in %.0fs", time.time() - t0)
        return

    from evaluation.deepeval_suite import generate_outputs, run_deepeval
    out_path = OUT / ("generated_outputs_quick.json" if QUICK else "generated_outputs.json")
    subset = golden[: 3 if QUICK else args.n_llm]
    if args.reuse_outputs and out_path.exists():
        outputs = json.loads(out_path.read_text())
    else:
        outputs = generate_outputs(subset, out_path)
        save("generated_outputs", outputs)
    judge_scores = [o["judge"]["overall_score"] for o in outputs]
    save("llm_judge_eval", {"judge_model": settings.JUDGE_MODEL, "n_cases": len(outputs),
                            "mean_overall": round(sum(judge_scores) / len(judge_scores), 3),
                            "pass_rate": round(sum(o["judge"]["passed"] for o in outputs) / len(outputs), 3),
                            "mean_by_criterion": {c: round(sum(o["judge"]["scores"][c] for o in outputs) / len(outputs), 3)
                                                  for c in outputs[0]["judge"]["scores"]},
                            "per_case": [{"id": o["id"], **o["judge"]} for o in outputs]})
    save("deepeval_results", run_deepeval(outputs))
    from evaluation.ragas_suite import run_ragas
    save("ragas_results", run_ragas(outputs))
    log.info("Evaluation complete in %.0fs", time.time() - t0)


if __name__ == "__main__":
    main()
