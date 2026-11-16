"""Groq rate-limit tracker.

Every Groq call goes through one shared httpx client. A response hook reads Groq's
rate-limit headers (requests per day, tokens per minute), the token usage in the body,
and the daily-token message inside 429 errors. The UI reads the snapshot via /api/limits,
so showing usage costs no API calls. Only "refresh" sends a tiny probe request per model.

Note: Groq does not send the daily TOKEN limit in headers. It is only known once a 429
says "tokens per day ... Limit X, Used Y". Until then we show tokens used since server start.
"""
import json
import re
import threading
import time

import httpx

_lock = threading.Lock()
_stats: dict[str, dict] = {}   # model id -> latest numbers

_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_LIMIT_MSG = re.compile(
    r"on (tokens|requests) per (day|minute) \(\w+\): Limit (\d+), Used (\d+), Requested (\d+)"
    r".*?try again in ([\dhms.]+)",
    re.IGNORECASE | re.DOTALL,
)
_UNITS = {"h": 3600, "m": 60, "s": 1, "ms": 0.001}


def parse_duration(text: str | None) -> float | None:
    """'30m14.4s' / '577ms' / '1h2m' → seconds."""
    if not text:
        return None
    parts = _DURATION.findall(text)
    return sum(float(n) * _UNITS[u] for n, u in parts) if parts else None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _model_of(request: httpx.Request) -> str | None:
    try:
        return json.loads(request.content or b"{}").get("model")
    except (ValueError, AttributeError):
        return None


def _record(response: httpx.Response) -> None:
    """httpx response hook: update the stats for the model this request used."""
    if "/chat/completions" not in response.request.url.path:
        return
    model = _model_of(response.request)
    if not model:
        return
    now = time.time()
    h = response.headers

    def at(header: str) -> float | None:
        secs = parse_duration(h.get(header))
        return now + secs if secs is not None else None

    try:
        response.read()  # safe: the body is cached for the Groq client afterwards
        body = response.json()
    except Exception:
        body = {}

    with _lock:
        s = _stats.setdefault(model, {"model": model, "session_tokens": 0, "session_calls": 0})
        s["updated_at"] = now

        if "x-ratelimit-limit-requests" in h:
            s["requests_limit"] = _int(h.get("x-ratelimit-limit-requests"))
            s["requests_left"] = _int(h.get("x-ratelimit-remaining-requests"))
            s["requests_reset_at"] = at("x-ratelimit-reset-requests")
        if "x-ratelimit-limit-tokens" in h:
            s["tpm_limit"] = _int(h.get("x-ratelimit-limit-tokens"))
            s["tpm_left"] = _int(h.get("x-ratelimit-remaining-tokens"))
            s["tpm_reset_at"] = at("x-ratelimit-reset-tokens")

        if response.status_code == 200:
            s["session_calls"] += 1
            s["session_tokens"] += (body.get("usage") or {}).get("total_tokens", 0)
            # A success means we are not blocked by the daily limit any more.
            if s.get("daily_blocked_until") and s["daily_blocked_until"] < now:
                s["daily_blocked_until"] = None

        if response.status_code == 429:
            message = ((body.get("error") or {}).get("message")) or ""
            m = _LIMIT_MSG.search(message)
            if m:
                kind, period, limit, used, _req, wait = m.groups()
                if kind.lower() == "tokens" and period.lower() == "day":
                    s["daily_tokens_limit"] = int(limit)
                    s["daily_tokens_used"] = int(used)
                    s["daily_blocked_until"] = now + (parse_duration(wait) or 0)
                    s["daily_seen_at"] = now


# One shared client for all Groq calls, so every response passes through the hook.
http_client = httpx.Client(timeout=120, event_hooks={"response": [_record]})


def snapshot(models: list[str]) -> dict:
    """Current numbers for the given models (missing = not called yet)."""
    with _lock:
        return {"now": time.time(), "models": [dict(_stats.get(m, {"model": m})) for m in models]}


def probe(models: list[str], api_key: str) -> None:
    """Send a 1-token request per model to refresh the headers (costs a few tokens each)."""
    from groq import Groq

    client = Groq(api_key=api_key, http_client=http_client, max_retries=0)
    for model in models:
        try:
            client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "ok"}], max_completion_tokens=1,
            )
        except Exception:
            pass  # a 429 is still recorded by the hook; other errors are ignored here
