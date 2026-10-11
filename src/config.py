"""Central configuration, loaded from environment variables / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


# OpenAI-compatible LLM providers. Model names can be overridden with LLM_MODEL / JUDGE_MODEL.
PROVIDERS = {
    "nvidia": {"key_env": "NVIDIA_API_KEY", "url_env": "NVIDIA_BASE_URL", "base_url": "https://integrate.api.nvidia.com/v1",
               "model_env": "NVIDIA_MODEL", "model": "deepseek-ai/deepseek-v4.1-flash", "max_rpm": 35},
    "gemini": {"key_env": "GEMINI_API_KEY", "url_env": "GEMINI_BASE_URL",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "model_env": "GEMINI_MODEL", "model": "gemini-2.5-flash", "max_rpm": 9},
    "aicredits": {"key_env": "AICREDITS_API_KEY", "url_env": "AICREDITS_BASE_URL", "base_url": "https://aicredits.in/v1",
                  "model_env": "AICREDITS_MODEL", "model": "gpt-5-nano", "max_rpm": 0},
    # Anthropic's OpenAI-compatible endpoint (JSON mode is ignored there; the client falls back to prompt-only JSON)
    "anthropic": {"key_env": "CLAUDE_API_KEY", "url_env": "CLAUDE_BASE_URL", "base_url": "https://api.anthropic.com/v1/",
                  "model_env": "CLAUDE_MODEL", "model": "claude-sonnet-5-5", "max_rpm": 0},
    "ollama": {"key_env": "OLLAMA_API_KEY", "url_env": "OLLAMA_BASE_URL", "base_url": "http://localhost:11434/v1",
               "model_env": "OLLAMA_MODEL", "model": "llama3.2:3b", "max_rpm": 0},
}


class Settings:
    # Data
    DATA_PATH = Path(_env("DATA_PATH", str(ROOT_DIR / "data" / "supply_chain_disruption_recovery.csv")))
    SAMPLE_DATA_PATH = ROOT_DIR / "data" / "sample_data" / "sample_disruptions.csv"
    ARTIFACTS_DIR = Path(_env("ARTIFACTS_DIR", str(ROOT_DIR / "artifacts")))
    CHROMA_DIR = ARTIFACTS_DIR / "chroma"
    MODELS_DIR = ARTIFACTS_DIR / "models"
    BM25_PATH = ARTIFACTS_DIR / "bm25_index.pkl"
    PROCESSED_PATH = ARTIFACTS_DIR / "processed.parquet"
    FEEDBACK_DB = Path(_env("FEEDBACK_DB", str(ARTIFACTS_DIR / "feedback.db")))
    EVAL_DIR = ROOT_DIR / "evaluation" / "results"

    # Index size: 0 = index every row; otherwise a stratified sample of this many rows
    INDEX_SAMPLE_SIZE = int(_env("INDEX_SAMPLE_SIZE", "0"))
    COLLECTION_NAME = "disruptions"

    # Embeddings
    EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # LLM: any OpenAI-compatible endpoint, chosen with LLM_PROVIDER in .env.
    # Without a key the system uses deterministic rule/template fallbacks.
    LLM_PROVIDER = _env("LLM_PROVIDER", "aicredits").lower()
    _P = PROVIDERS.get(LLM_PROVIDER, PROVIDERS["aicredits"])
    LLM_API_KEY = _env(_P["key_env"], "ollama" if LLM_PROVIDER == "ollama" else "")
    LLM_BASE_URL = _env(_P["url_env"], _P["base_url"])
    LLM_MODEL = _env("LLM_MODEL", _env(_P["model_env"], _P["model"]))
    JUDGE_MODEL = _env("JUDGE_MODEL", _P.get("judge_model", LLM_MODEL))
    LLM_MAX_RPM = int(_env("LLM_MAX_RPM", str(_P["max_rpm"])))  # client-side throttle (0 = off)
    LLM_REASONING_EFFORT = _env("LLM_REASONING_EFFORT", "minimal")
    LLM_TIMEOUT = float(_env("LLM_TIMEOUT", "120"))
    LLM_ENABLED = _env("LLM_ENABLED", "true").lower() == "true" and bool(LLM_API_KEY)

    # Retrieval
    DEFAULT_TOP_K = int(_env("DEFAULT_TOP_K", "10"))
    HYBRID_ALPHA = float(_env("HYBRID_ALPHA", "0.6"))  # weight of semantic vs keyword in fusion
    RRF_K = 60
    CANDIDATE_POOL = 200  # candidates pulled from each retriever before fusion

    # Workflow
    JUDGE_PASS_THRESHOLD = float(_env("JUDGE_PASS_THRESHOLD", "3.5"))

    # API (used by the Streamlit frontend)
    API_URL = _env("API_URL", "http://127.0.0.1:8000")


settings = Settings()
for _d in (settings.ARTIFACTS_DIR, settings.MODELS_DIR, settings.EVAL_DIR):
    _d.mkdir(parents=True, exist_ok=True)
