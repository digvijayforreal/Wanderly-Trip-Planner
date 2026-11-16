"""Supervisor nodes. The supervisor is the only agent that talks to the user,
and it decides which worker runs next after every step. It never answers travel
questions itself: the final answer is built only from the workers' approved work."""
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import CURRENCY_SYMBOL, HISTORY_WINDOW, MAX_REVISIONS
from app.llms import get_llm, get_structured_llm
from app.prompts import (
    FINAL_PROMPT, INTAKE_PROMPT, REVIEW_CHECKLISTS, REVIEW_INPUT, REVIEW_PROMPT,
    SECTION_FORMATS, SUPERVISOR_INPUT, SUPERVISOR_PROMPT,
)
from app.schemas import Decision, Review, TripDetails
from app.state import OUTPUT_KEY, REQUIRED_FIELDS, STEP_TITLES, WORKERS, TripState
from app.utils import clean_text, format_trip, latest_user_message

# How to ask for each trip detail when it is missing.
FIELD_QUESTIONS = {
    "destination": "where you'd like to go",
    "days": "how many days",
    "travelers": "how many people are travelling",
}

OFF_TOPIC_REPLY = (
    "I plan trips: destination guides, day-by-day itineraries, budgets and packing lists. "
    f"Try something like: *4 days in Goa for 2 people, budget {CURRENCY_SYMBOL}30,000*."
)


def missing_fields(worker: str, trip: dict) -> list[str]:
    """Trip details this worker needs that are still missing."""
    return [f for f in REQUIRED_FIELDS[worker] if not trip.get(f)]


def _transcript(messages) -> str:
    """Recent chat as plain text. Long past answers are shortened to save tokens."""
    lines = []
    for m in messages[-HISTORY_WINDOW:]:
        speaker = "User" if m.type == "human" else "Assistant"
        text = clean_text(m.content)
        if speaker == "Assistant" and len(text) > 600:
            text = text[:600] + " …(earlier answer shortened)"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


# ---------- Node: intake ----------
def intake_node(state: TripState) -> dict:
    """Extract trip details and reset per-message fields.
    Worker drafts are kept so follow-ups can reuse them, unless the destination changed."""
    llm = get_structured_llm("supervisor", TripDetails)
    details = llm.invoke([
        SystemMessage(content=INTAKE_PROMPT.format(today=date.today().isoformat())),
        HumanMessage(content=_transcript(state["messages"])),
    ])
    extracted = (details or TripDetails()).model_dump()
    previous = state.get("trip") or {}

    # Merge with earlier details: a field the model left empty keeps its earlier value.
    # This stops one weak extraction (e.g. a fallback model) from erasing "Goa".
    # A different destination means a new trip, so nothing is carried over.
    old_dest = (previous.get("destination") or "").strip().lower()
    new_dest = (extracted.get("destination") or "").strip().lower()
    same_trip = not new_dest or not old_dest or new_dest == old_dest
    trip = {k: (v if v not in (None, "", []) else previous.get(k)) for k, v in extracted.items()} if same_trip else extracted

    update = {
        "trip": trip,
        "next_step": "", "decision_reason": "", "ask_message": "",
        "done": [], "current_step": "", "approved": False,
        "feedback": "", "feedback_for": "", "revisions": {}, "review_notes": [],
        "return_to": "", "route": "", "final_answer": "",
    }

    # New destination → earlier drafts are about another place, so drop them.
    if not same_trip:
        update.update({key: "" for key in OUTPUT_KEY.values()})

    return update


# ---------- Node: supervisor decides the next step ----------
def _team_status(state: TripState) -> str:
    done = state.get("done") or []
    trip = state.get("trip") or {}
    lines = []
    for worker in WORKERS:
        if worker in done:
            status = "done this turn"
        elif state.get(OUTPUT_KEY[worker]):
            status = "work available from earlier in the chat"
        else:
            status = "not run yet"
        missing = missing_fields(worker, trip)
        needs = f" (cannot run yet, missing: {', '.join(missing)})" if missing else ""
        lines.append(f"- {worker}: {status}{needs}")
    return "\n".join(lines)


def _ask_for(missing: list[str]) -> str:
    asks = [FIELD_QUESTIONS[f] for f in missing]
    return "Happy to help with that. I just need to know " + ", ".join(asks) + "."


def supervisor_node(state: TripState) -> dict:
    """Pick the ONE next step: a worker, ask_user or finalize. Called again after every approved step."""
    trip = state.get("trip") or {}
    done = state.get("done") or []

    llm = get_structured_llm("supervisor", Decision)
    decision = llm.invoke([
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=SUPERVISOR_INPUT.format(
            today=date.today().isoformat(),
            transcript=_transcript(state["messages"]),
            trip=format_trip(trip),
            status=_team_status(state),
        )),
    ])

    # Model failed to decide: finish if something was done, otherwise explain what we do.
    if decision is None:
        if done:
            return {"next_step": "finalize", "decision_reason": ""}
        return {"next_step": "ask_user", "ask_message": OFF_TOPIC_REPLY}

    choice = decision.next
    decision.reason = decision.reason or ""

    if choice in WORKERS:
        # Guard: a worker approved this turn is not called again (prevents loops).
        if choice in done:
            return {"next_step": "finalize", "decision_reason": decision.reason}
        # Guard: required details are checked in code, not trusted to the LLM.
        missing = missing_fields(choice, trip)
        if missing:
            return {"next_step": "ask_user", "ask_message": decision.message_to_user or _ask_for(missing)}
        return {"next_step": choice, "decision_reason": decision.reason}

    if choice == "ask_user":
        return {"next_step": "ask_user", "ask_message": decision.message_to_user or OFF_TOPIC_REPLY}

    # "finish": first, never leave a stale budget. If the itinerary changed this turn,
    # an earlier budget no longer matches it, so re-price it.
    if "itinerary_builder" in done and state.get("budget") and "budget_planner" not in done:
        return {"next_step": "budget_planner", "decision_reason": "The itinerary changed, so the budget needs updating"}

    # The answer must come from team work, never from the supervisor alone.
    has_work = any(state.get(key) for key in OUTPUT_KEY.values())
    if not done and not has_work:
        return {"next_step": "ask_user", "ask_message": decision.message_to_user or OFF_TOPIC_REPLY}
    return {"next_step": "finalize", "decision_reason": decision.reason}


# ---------- Node: ask the user ----------
def ask_user_node(state: TripState) -> dict:
    reply = state.get("ask_message") or OFF_TOPIC_REPLY
    return {"final_answer": reply, "messages": [AIMessage(content=reply)]}


# ---------- Node: review a worker's output ----------
def review_node(state: TripState) -> dict:
    step = state["current_step"]
    has_itinerary = bool(state.get("itinerary"))

    llm = get_structured_llm("supervisor", Review)
    review = llm.invoke([
        SystemMessage(content=REVIEW_PROMPT),
        HumanMessage(content=REVIEW_INPUT.format(
            title=STEP_TITLES[step],
            checklist=REVIEW_CHECKLISTS[step],
            request=latest_user_message(state["messages"]),
            trip=format_trip(state["trip"]),
            has_itinerary="yes" if has_itinerary else "no",
            work=state.get(OUTPUT_KEY[step], ""),
        )),
    ])

    def accept(extra: dict | None = None) -> dict:
        """Mark the step done and decide where to go next."""
        done = list(state.get("done") or [])
        if step not in done:
            done.append(step)
        update = {"current_step": step, "approved": True, "feedback": "", "feedback_for": "",
                  "done": done, "route": "supervisor"}
        # A cheaper itinerary was just approved → re-price it before asking the supervisor again.
        return_to = state.get("return_to")
        if step == "itinerary_builder" and return_to:
            update.update({"route": return_to, "return_to": ""})
        return {**update, **(extra or {})}

    if review is None or review.approved:
        return accept()

    review.feedback = review.feedback or "Did not pass the checklist."
    revisions = dict(state.get("revisions") or {})
    used = revisions.get(step, 0)

    # Out of retries: accept the best version and remember the open issue for the user.
    if used >= MAX_REVISIONS:
        notes = list(state.get("review_notes") or [])
        notes.append(f"{STEP_TITLES[step]}: {review.feedback}")
        return accept({"review_notes": notes})

    revisions[step] = used + 1
    update = {"current_step": step, "approved": False, "feedback": review.feedback,
              "feedback_for": step, "revisions": revisions, "route": step}

    # Over budget with an itinerary → make the itinerary cheaper, then re-run the budget.
    if step == "budget_planner" and review.send_to == "itinerary_builder" and has_itinerary:
        update.update({"feedback_for": "itinerary_builder", "route": "itinerary_builder",
                       "return_to": "budget_planner"})
    return update


# ---------- Node: write the final answer ----------
def finalize_node(state: TripState) -> dict:
    """Turn the team's work into one polished Markdown answer (no new facts from the supervisor)."""
    done = state.get("done") or []
    notes = state.get("review_notes") or []
    notes_text = "\n".join(f"- {n}" for n in notes) if notes else "None"

    # Only work produced for THIS request goes into the answer. Earlier drafts are still
    # used by the workers themselves (e.g. "make it cheaper" edits the old itinerary).
    ran = [w for w in WORKERS if w in done and state.get(OUTPUT_KEY[w])]
    work = [f"## {STEP_TITLES[w]}\n{state[OUTPUT_KEY[w]]}" for w in ran]

    # Allowed sections, chosen in code. The overview table only makes sense for a planned trip.
    section_keys = (["overview"] if "itinerary_builder" in ran else []) + ran
    sections = "\n\n".join(SECTION_FORMATS[k] for k in section_keys)

    material = "\n\n".join([
        f"# User's latest request\n{latest_user_message(state['messages'])}",
        f"# Trip details\n{format_trip(state['trip'])}",
        "# Approved work for this request\n" + ("\n\n".join(work) or "None"),
        f"# Heads-up notes\n{notes_text}",
    ])

    result = get_llm("supervisor").invoke([
        SystemMessage(content=FINAL_PROMPT.format(sections=sections)),
        HumanMessage(content=material),
    ])
    answer = clean_text(result.content)
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}
