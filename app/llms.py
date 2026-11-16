"""Model factory. Every node gets its LLM from here.

Two modes, picked per request (the web switch / cli flag):
- "groq":  cloud models from config.MODELS, with Groq fallbacks
- "local": every agent uses the local Ollama model (config.LOCAL_MODEL)
"""
from functools import lru_cache

from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from app import limits
from app.config import (
    DEFAULT_MODE, FALLBACK_MODELS, GROQ_API_KEY, LOCAL_CONTEXT_WINDOW, LOCAL_MODEL,
    MAX_API_RETRIES, MODELS, MODES, OLLAMA_BASE_URL,
)


def mode_from(config: RunnableConfig | None) -> str:
    """Read the mode a graph run was started with (config["configurable"]["mode"])."""
    mode = ((config or {}).get("configurable") or {}).get("mode", DEFAULT_MODE)
    return mode if mode in MODES else DEFAULT_MODE


# ---------- Groq (cloud) ----------
def _chat_model(model: str, temperature: float) -> ChatGroq:
    # max_retries: the Groq client waits and retries on rate limits (429), which the free tier hits often.
    # http_client: shared client whose hook records rate-limit headers for the usage panel.
    return ChatGroq(model=model, temperature=temperature, api_key=GROQ_API_KEY,
                    max_retries=MAX_API_RETRIES, http_client=limits.http_client)


def _backup_models(primary: str) -> list[str]:
    """Fallback models to try in order, skipping the primary itself.
    Each Groq model has its own rate limit, so a backup still works when the primary is used up."""
    return [m for m in FALLBACK_MODELS if m != primary]


# ---------- Ollama (local) ----------
def _local_model(temperature: float) -> ChatOllama:
    # num_ctx: Ollama's default context is small and would silently cut off our long prompts.
    return ChatOllama(model=LOCAL_MODEL, temperature=temperature, base_url=OLLAMA_BASE_URL,
                      num_ctx=LOCAL_CONTEXT_WINDOW)


# ---------- Public helpers ----------
@lru_cache
def get_llm(role: str, mode: str = DEFAULT_MODE):
    """Plain text model for a role."""
    cfg = MODELS[role]
    if mode == "local":
        return _local_model(cfg["temperature"])
    primary = _chat_model(cfg["model"], cfg["temperature"])
    backups = [_chat_model(m, cfg["temperature"]) for m in _backup_models(cfg["model"])]
    return primary.with_fallbacks(backups)


@lru_cache
def get_structured_llm(role: str, schema: type, mode: str = DEFAULT_MODE):
    """Model that returns a Pydantic object instead of free text."""
    cfg = MODELS[role]
    if mode == "local":
        # Ollama constrains the output to the JSON schema, which keeps small models on track.
        return _local_model(cfg["temperature"]).with_structured_output(schema, method="json_schema")
    primary = _chat_model(cfg["model"], cfg["temperature"]).with_structured_output(schema)
    backups = [_chat_model(m, cfg["temperature"]).with_structured_output(schema)
               for m in _backup_models(cfg["model"])]
    return primary.with_fallbacks(backups)
