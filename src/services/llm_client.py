"""Thin wrapper around an OpenAI-compatible chat endpoint (default: AICredits gpt-5-nano).

Every caller must handle a `None` return: when the LLM is disabled, unreachable or returns invalid
output, the system falls back to deterministic rule/template logic so the app always works offline.
"""
import json
import os
import re
import threading
import time
from collections import deque
from functools import lru_cache

from src.config import PROVIDERS, settings
from src.utils.logger import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI
    return OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
                  timeout=settings.LLM_TIMEOUT, max_retries=2)


def failure_reason() -> str:
    """Plain-words reason the last LLM call gave nothing (quota, key, other), for callers that fall back to rules."""
    err = (last_failure.get("error") or "").lower()
    if "429" in err or "quota" in err or "rate limit" in err or "resource_exhausted" in err:
        return "the model's request quota or rate limit is used up"
    if "401" in err or "403" in err or "api key" in err or "authentication" in err:
        return "the model rejected the API key"
    if "404" in err or "not found" in err:
        return "the model name was not found"
    if err:
        return f"the model call failed ({err[:90]})"
    return "the model's reply could not be read as the expected JSON"


def llm_available() -> bool:
    return settings.LLM_ENABLED


_lock = threading.Lock()
_call_times: deque = deque()
_no_json_mode: set[str] = set()  # models that rejected response_format
_no_reasoning_off: set[str] = set()  # Gemini models that rejected reasoning_effort="none"
_no_temperature: set[str] = set()
last_failure: dict = {"error": None}  # most recent failed call, so callers can say WHY the model gave nothing  # models that rejected the temperature setting (e.g. newer Claude models)


def _throttle():
    """Client-side rate limit so free tiers (e.g. NVIDIA ~40 RPM, Gemini ~10 RPM) never return 429."""
    rpm = settings.LLM_MAX_RPM
    if rpm <= 0:
        return
    with _lock:
        now = time.monotonic()
        while _call_times and now - _call_times[0] > 60:
            _call_times.popleft()
        if len(_call_times) >= rpm:
            time.sleep(max(0.0, 60 - (now - _call_times[0])) + 0.05)
        _call_times.append(time.monotonic())


def _chat(messages: list[dict], max_tokens: int, json_mode: bool, model: str | None) -> str | None:
    if not llm_available():
        return None
    model = model or settings.LLM_MODEL
    kwargs = dict(model=model, messages=messages)
    if model.startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["max_completion_tokens"] = max_tokens
        kwargs["reasoning_effort"] = settings.LLM_REASONING_EFFORT
    else:
        kwargs["max_tokens"] = max_tokens
        if model not in _no_temperature:
            kwargs["temperature"] = 0.2
    if "nemotron" in model.lower():
        # Nemotron 3.x are reasoning models: without this they write a long "thinking process" into the answer.
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    if model.startswith("gemini-2.5-flash") and "lite" not in model and model not in _no_reasoning_off:
        # Gemini 2.5 Flash "thinks" by default and the thinking counts against max_tokens, so replies were cut off mid-JSON.
        kwargs["reasoning_effort"] = "none"
    if json_mode and model not in _no_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        _throttle()
        resp = _client().chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        if content:
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()  # reasoning-model safety net
        last_failure["finish_reason"] = resp.choices[0].finish_reason
        if not content:
            log.warning("LLM returned empty content (finish_reason=%s)", resp.choices[0].finish_reason)
            return None
        return content
    except Exception as e:  # network, auth, rate limit, unsupported params...
        if "temperature" in kwargs and "temperature" in str(e):
            log.info("Model %s does not accept a temperature setting; retrying without it", model)
            _no_temperature.add(model)
            return _chat(messages, max_tokens, json_mode, model)
        if "reasoning_effort" in kwargs and model.startswith("gemini") and ("reasoning" in str(e).lower() or "invalid argument" in str(e).lower()):
            log.info("Model %s does not accept reasoning_effort; retrying without it", model)
            _no_reasoning_off.add(model)
            return _chat(messages, max_tokens, json_mode, model)
        if "response_format" in kwargs and "response_format" in str(e):
            log.info("Model %s does not support JSON mode; retrying with prompt-only JSON", model)
            _no_json_mode.add(model)
            return _chat(messages, max_tokens, json_mode, model)
        log.warning("LLM call failed: %s: %s", type(e).__name__, str(e)[:200])
        last_failure["error"] = f"{type(e).__name__}: {str(e)}"
        return None


def complete_text(system: str, user: str, max_tokens: int = 1500, model: str | None = None) -> str | None:
    return _chat([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens, False, model)


def complete_json(system: str, user: str, max_tokens: int = 1500, model: str | None = None) -> dict | None:
    out = _chat([{"role": "system", "content": system + "\nRespond with a single valid JSON object only."},
                 {"role": "user", "content": user}], max_tokens, True, model)
    if out is None:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", out, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    log.warning("LLM returned non-JSON output (finish_reason=%s, %d chars, ends: %r)",
                last_failure.get("finish_reason"), len(out), out[-120:])
    return None


def _provider_key(name: str) -> str:
    p = PROVIDERS[name]
    return os.getenv(p["key_env"]) or ("ollama" if name == "ollama" else "")


def list_providers() -> list[dict]:
    """Providers the UI can offer. `available` means an API key is configured (keys are never returned)."""
    return [{"provider": n, "model": os.getenv(p["model_env"]) or p["model"], "available": bool(_provider_key(n)),
             "active": settings.LLM_ENABLED and settings.LLM_PROVIDER == n} for n, p in PROVIDERS.items()]


def switch_provider(name: str) -> dict:
    """Switch the active LLM at runtime. name='off' disables the LLM so every agent uses its template fallback."""
    global _call_times
    if name == "off":
        settings.LLM_ENABLED = False
    else:
        if name not in PROVIDERS:
            raise ValueError(f"Unknown provider '{name}'")
        key = _provider_key(name)
        if not key:
            raise ValueError(f"No API key for '{name}'. Add {PROVIDERS[name]['key_env']} to .env.")
        p = PROVIDERS[name]
        settings.LLM_PROVIDER, settings.LLM_API_KEY, settings.LLM_ENABLED = name, key, True
        settings.LLM_BASE_URL = os.getenv(p["url_env"]) or p["base_url"]
        settings.LLM_MODEL = settings.JUDGE_MODEL = os.getenv(p["model_env"]) or p["model"]
        settings.LLM_MAX_RPM = p["max_rpm"]
    _client.cache_clear()  # rebuild the client with the new key / URL
    with _lock:
        _call_times = deque()
    _no_json_mode.clear()
    _no_temperature.clear()
    log.info("LLM switched to %s", name)
    return provider_info()


def provider_info() -> dict:
    return {"enabled": llm_available(), "provider": settings.LLM_PROVIDER, "model": settings.LLM_MODEL,
            "judge_model": settings.JUDGE_MODEL, "base_url": settings.LLM_BASE_URL}
