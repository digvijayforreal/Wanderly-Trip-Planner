"""Small helpers shared by the agents."""
import re

from app.config import CURRENCY_SYMBOL

_THINK_TAGS = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_TRIP_LABELS = {
    "destination": "Destination",
    "origin": "Starting from",
    "days": "Days",
    "travelers": "Travelers",
    "budget": "Budget",
    "start_date": "When",
    "interests": "Interests",
    "special_requests": "Special requests",
}

def clean_text(content) -> str:
    """Turn model output into clean text: join content blocks, strip <think> reasoning."""
    if isinstance(content, list):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return _THINK_TAGS.sub("", content or "").strip()

_DAYS = re.compile(r"\b(\d{1,2})\s*(?:-\s*)?(?:days?|nights?|din)\b", re.IGNORECASE)
_PEOPLE = re.compile(r"\b(\d{1,2})\s*(?:people|persons?|pax|travell?ers?|adults?|friends|members)\b", re.IGNORECASE)
_SOLO = re.compile(r"\b(only me|just me|myself|solo|alone|1 person)\b", re.IGNORECASE)
_COUPLE = re.compile(r"\b(couple|me and my (?:wife|husband|partner|girlfriend|boyfriend))\b", re.IGNORECASE)
_MONEY = re.compile(r"[₹$]\s*\d|\b(?:rs\.?|inr)\s*\d|\b\d[\d,]*\s*(?:k|rs|rupees|inr|lakh)\b", re.IGNORECASE)


def quick_extract(text: str) -> dict:
    """Rule-based backup for days/travelers, for when a small model misses them
    (e.g. '3 days and only me'). Only fills gaps; the LLM's values win."""
    found = {}
    if m := _DAYS.search(text):
        found["days"] = int(m.group(1))
    if m := _PEOPLE.search(text):
        found["travelers"] = int(m.group(1))
    elif _SOLO.search(text):
        found["travelers"] = 1
    elif _COUPLE.search(text):
        found["travelers"] = 2
    return found


def looks_like_an_answer(text: str) -> bool:
    """True if a 'question to the user' actually contains prices or a long answer.
    The supervisor must not answer itself, so such text is replaced in code."""
    return bool(_MONEY.search(text or "")) or len(text or "") > 400


def latest_user_message(messages) -> str:
    """Text of the most recent user message."""
    for m in reversed(messages or []):
        if m.type == "human":
            return clean_text(m.content)
    return ""


def format_trip(trip: dict) -> str:
    """Trip details as a readable bullet list for prompts."""
    lines = []
    for key, label in _TRIP_LABELS.items():
        value = trip.get(key)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = ", ".join(value)
        if key == "budget":
            value = f"{CURRENCY_SYMBOL}{float(value):,.0f} total for the group"
        lines.append(f"- {label}: {value}")
    return "\n".join(lines) or "- (no details given yet)"
