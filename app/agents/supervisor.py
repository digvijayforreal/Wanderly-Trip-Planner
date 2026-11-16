"""Supervisor nodes. The supervisor is the only agent that talks to the user."""
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import CURRENCY_SYMBOL, HISTORY_WINDOW, MAX_REVISIONS
from app.llms import get_llm, get_structured_llm
from app.prompts import FINAL_PROMPT, INTAKE_PROMPT, REVIEW_CHECKLISTS, REVIEW_INPUT, REVIEW_PROMPT
from app.schemas import Review, TripDetails
from app.state import OUTPUT_KEY, STEP_TITLES, TripState
from app.utils import clean_text, format_trip

# Fields we must have before planning, with how to ask for them.
REQUIRED_FIELDS = {
    "destination": "where you'd like to go",
    "days": "how many days",
    "travelers": "how many people are travelling",
    "budget": "your total budget",
}

def is_ready(trip: dict) -> bool:
    """True when the request has everything the workers need."""
    return bool(trip.get("is_trip_request")) and all(trip.get(f) for f in REQUIRED_FIELDS)

def _transcript(messages) -> str:
    """Recent chat as plain text. Long past plans are shortened to save tokens."""
    lines = []
    for m in messages[-HISTORY_WINDOW:]:
        speaker = "User" if m.type == "human" else "Assistant"
        text = clean_text(m.content)
        if speaker == "Assistant" and len(text) > 600:
            text = text[:600] + " …(earlier trip plan shortened)"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)

# ---------- Node: intake ----------
def intake_node(state: TripState) -> dict:
    """Understand the request and reset per-run fields (state persists between chats)."""
    llm = get_structured_llm("supervisor", TripDetails)
    details = llm.invoke([
        SystemMessage(content=INTAKE_PROMPT.format(today=date.today().isoformat())),
        HumanMessage(content=_transcript(state["messages"])),
    ])
    if details is None:  # model failed to return structured output
        details = TripDetails(is_trip_request=False)

    return {
        "trip": details.model_dump(),
        "research": "", "itinerary": "", "budget": "", "packing": "",
        "current_step": "", "approved": False,
        "feedback": "", "feedback_for": "",
        "revisions": {}, "review_notes": [],
        "final_answer": "",
    }

# ---------- Node: ask the user for missing info ----------
def ask_user_node(state: TripState) -> dict:
    trip = state.get("trip", {})
    reply = trip.get("reply_to_user")

    if not reply:  # fallback if the model didn't write one
        if trip.get("is_trip_request"):
            missing = [ask for field, ask in REQUIRED_FIELDS.items() if not trip.get(field)]
            reply = "Sounds like a great trip. To plan it, I just need " + ", ".join(missing) + "."
        else:
            reply = (f"I plan trips end to end. Try something like: "
                     f"*4 days in Goa for 2 people, budget {CURRENCY_SYMBOL}30,000*.")

    return {"final_answer": reply, "messages": [AIMessage(content=reply)]}

# ---------- Node: review a worker's output ----------
def review_node(state: TripState) -> dict:
    step = state["current_step"]
    llm = get_structured_llm("supervisor", Review)
    review = llm.invoke([
        SystemMessage(content=REVIEW_PROMPT),
        HumanMessage(content=REVIEW_INPUT.format(
            title=STEP_TITLES[step],
            checklist=REVIEW_CHECKLISTS[step],
            trip=format_trip(state["trip"]),
            work=state.get(OUTPUT_KEY[step], ""),
        )),
    ])

    passed = {"current_step": step, "approved": True, "feedback": "", "feedback_for": ""}

    if review is None or review.approved:
        return passed

    revisions = dict(state.get("revisions") or {})
    used = revisions.get(step, 0)

    # Out of retries: accept the best version and remember the open issue for the user.
    if used >= MAX_REVISIONS:
        notes = list(state.get("review_notes") or [])
        notes.append(f"{STEP_TITLES[step]}: {review.feedback}")
        return {**passed, "review_notes": notes}

    revisions[step] = used + 1
    # Over budget → the itinerary must get cheaper, not just the budget sheet.
    target = "itinerary_builder" if step == "budget_planner" and review.send_to == "itinerary_builder" else step

    return {
        "current_step": step,
        "approved": False,
        "feedback": review.feedback,
        "feedback_for": target,
        "revisions": revisions,
    }

# ---------- Node: write the final answer ----------
def finalize_node(state: TripState) -> dict:
    notes = state.get("review_notes") or []
    notes_text = "\n".join(f"- {n}" for n in notes) if notes else "None"

    material = "\n\n".join([
        f"# Trip request\n{format_trip(state['trip'])}",
        f"# Research\n{state.get('research', '')}",
        f"# Itinerary\n{state.get('itinerary', '')}",
        f"# Budget\n{state.get('budget', '')}",
        f"# Packing and tips\n{state.get('packing', '')}",
        f"# Heads-up notes\n{notes_text}",
    ])

    result = get_llm("supervisor").invoke([
        SystemMessage(content=FINAL_PROMPT),
        HumanMessage(content=material),
    ])
    answer = clean_text(result.content)
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}
