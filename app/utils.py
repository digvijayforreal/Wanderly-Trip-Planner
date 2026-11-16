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
    return "\n".join(lines)
