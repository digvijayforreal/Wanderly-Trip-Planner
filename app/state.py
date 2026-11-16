"""Shared state that flows through the graph, plus the list of worker agents."""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

# Worker agents the supervisor can call. There is no fixed order: the supervisor picks
# the next one after every step. Node names must differ from state keys (LangGraph rule),
# hence "itinerary_builder" vs "itinerary".
WORKERS = ["researcher", "itinerary_builder", "budget_planner", "packing_expert"]

# Which state key each worker writes its result to.
OUTPUT_KEY = {
    "researcher": "research",
    "itinerary_builder": "itinerary",
    "budget_planner": "budget",
    "packing_expert": "packing",
}

# Human-readable names for logs, review notes and UI status.
STEP_TITLES = {
    "researcher": "Destination research",
    "itinerary_builder": "Itinerary",
    "budget_planner": "Budget",
    "packing_expert": "Packing list",
}

# Trip details each worker needs before it can run (checked in code, not by the LLM).
REQUIRED_FIELDS = {
    "researcher": ["destination"],
    "itinerary_builder": ["destination", "days"],
    "budget_planner": ["destination", "days", "travelers"],
    "packing_expert": ["destination"],
}


class TripState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]  # chat history (user ↔ supervisor only)
    trip: dict                # extracted trip details (TripDetails as dict)

    # Worker outputs. Kept between messages so follow-ups ("make it cheaper") can reuse them.
    research: str
    itinerary: str
    budget: str
    packing: str

    # Supervisor routing (reset every user message)
    next_step: str            # what the supervisor chose: a worker, "ask_user" or "finalize"
    decision_reason: str      # supervisor's one-line reason (shown in the UI)
    ask_message: str          # question/notice for the user when next_step == "ask_user"
    done: list[str]           # workers approved during this user message

    # Review loop bookkeeping (reset every user message)
    current_step: str         # worker that just ran / was just reviewed
    approved: bool            # result of the latest review
    feedback: str             # supervisor's fix list
    feedback_for: str         # which worker the feedback is meant for
    revisions: dict           # {worker: number of reworks used}
    review_notes: list[str]   # issues still open after max retries
    return_to: str            # worker to re-run after a cheaper itinerary (over-budget case)
    route: str                # where the review sends the graph next

    final_answer: str         # the only thing the user sees
