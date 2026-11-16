"""Model factory. Every node gets its LLM from here"""

from functools import lru_cache

from langchain_groq import ChatGroq

from app.config import FALLBACK_MODELS, GROQ_API_KEY, MAX_API_RETRIES, MODELS

def _chat_model(model: str, temperature: float) -> ChatGroq:
    # max_retries: the Groq client waits and retries on rate limits (429), which the free tier hits often.
    return ChatGroq(model=model, temperature=temperature, api_key=GROQ_API_KEY, max_retries=MAX_API_RETRIES)

def _backup_models(primary: str) -> list[str]:
    """Fallback models to try in order, skipping the primary itself.
    Each Groq model has its own rate limit, so a backup still works when the primary is used up."""
    return [m for m in FALLBACK_MODELS if m != primary]


@lru_cache
def get_llm(role: str):
    """Plain text model for a role, with automatic fallback models."""
    cfg = MODELS[role]
    primary = _chat_model(cfg["model"], cfg["temperature"])
    backups = [_chat_model(m, cfg["temperature"]) for m in _backup_models(cfg["model"])]
    return primary.with_fallbacks(backups)


@lru_cache
def get_structured_llm(role: str, schema: type):
    """Model that returns a pydantic object instead of free text."""
    cfg = MODELS[role]
    primary = _chat_model(cfg["model"], cfg["temperature"]).with_structured_output(schema)
    backups = [_chat_model(m, cfg["temperature"]).with_structured_output(schema)
               for m in _backup_models(cfg["model"])]
    return primary.with_fallbacks(backups)
