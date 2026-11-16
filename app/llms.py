"""Model factory. Every node gets its LLM from here"""

from functools import lru_cache

from langchain_groq import ChatGroq

from app.config import FALLBACK_MODEL, GROQ_API_KEY, MODELS

def _chat_model(model: str, temperature: float) -> ChatGroq:
    return ChatGroq(model=model, temperature=temperature, api_key=GROQ_API_KEY, max_retries = 2)

@lru_cache
def get_llm(role: str):
    """Plain text model for a role, with an automatic fallback model."""
    cfg = MODELS[role]
    primary = _chat_model(cfg["model"], cfg["temperature"])
    backup  = _chat_model(FALLBACK_MODEL, cfg["temperature"])
    return primary.with_fallbacks([backup])

@lru_cache
def get_structured_llm(role: str, schema:type):
    """Model that returns a pydantic object instead of free text."""
    cfg = MODELS[role]
    cfg = MODELS[role]
    primary = _chat_model(cfg["model"], cfg["temperature"]).with_structured_output(schema)
    backup = _chat_model(FALLBACK_MODEL, cfg["temperature"]).with_structured_output(schema)
    return primary.with_fallbacks([backup])
