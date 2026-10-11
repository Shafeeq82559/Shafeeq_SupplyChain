"""Train prediction, risk and explainability models on the full dataset.

Usage:  python -m scripts.train_models
"""
import json
import time

from src.config import settings
from src.rag.preprocessing import load_dataset
from src.services.ml_models import train_all
from src.utils.logger import get_logger

log = get_logger("train_models")

if __name__ == "__main__":
    t0 = time.time()
    bundle = train_all(load_dataset())
    (settings.EVAL_DIR / "model_metrics.json").write_text(json.dumps(bundle["metrics"], indent=2))
    log.info("Models trained in %.0fs -> %s", time.time() - t0, settings.MODELS_DIR)
