"""Shared state that flows through the graph, plus the worker order."""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

# Worker nodes in the order they run.
# Node names must differ from state keys (LangGraph rule), hence "itinerary_builder" vs "itinerary".
STEPS = ["researcher", "itinerary_builder", "budget_planner", "packing_expert"]

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

class TripState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]  # chat history (user ↔ supervisor only)
    trip: dict                # extracted trip details (TripDetails as dict)

    # Worker outputs (internal drafts, never shown to the user directly)
    research: str
    itinerary: str
    budget: str
    packing: str

    # Review loop bookkeeping
    current_step: str         # worker that just ran / was just reviewed
    approved: bool            # result of the latest review
    feedback: str             # supervisor's fix list
    feedback_for: str         # which worker the feedback is meant for
    revisions: dict           # {step: number of reworks used}
    review_notes: list[str]   # issues still open after max retries

    final_answer: str         # the only thing the user sees
