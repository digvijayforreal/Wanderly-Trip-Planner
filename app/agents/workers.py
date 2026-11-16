"""The four worker agents. One factory builds them all, since they share the same shape."""
from langchain_core.messages import HumanMessage, SystemMessage

from app.llms import get_llm
from app.prompts import WORKER_PROMPTS
from app.state import OUTPUT_KEY, TripState
from app.utils import clean_text, format_trip, latest_user_message

# Earlier results each worker reads, if they exist. Missing ones are simply skipped,
# e.g. the budget planner estimates typical costs when there is no itinerary.
CONTEXT_KEYS = {
    "researcher": [],
    "itinerary_builder": ["research"],
    "budget_planner": ["research", "itinerary"],
    "packing_expert": ["research", "itinerary"],
}


def make_worker(step: str):
    """Build a graph node function for one worker."""
    output_key = OUTPUT_KEY[step]

    def worker_node(state: TripState) -> dict:
        parts = [
            f"## User's latest request\n{latest_user_message(state['messages'])}",
            f"## Trip details\n{format_trip(state['trip'])}",
        ]

        for key in CONTEXT_KEYS[step]:
            if state.get(key):
                parts.append(f"## {key.title()}\n{state[key]}")

        previous = state.get(output_key, "")
        if state.get("feedback_for") == step and state.get("feedback"):
            # Rework: fix the draft using the supervisor's feedback.
            parts.append(f"## Your previous draft\n{previous}")
            parts.append(f"## Supervisor feedback (fix all of this)\n{state['feedback']}")
        elif previous:
            # Follow-up: an earlier version exists, edit it if the user asked for a change.
            parts.append(f"## Your earlier version (edit it if the user asked for a change, otherwise redo it)\n{previous}")

        result = get_llm(step).invoke([
            SystemMessage(content=WORKER_PROMPTS[step]),
            HumanMessage(content="\n\n".join(parts)),
        ])
        return {output_key: clean_text(result.content), "current_step": step}

    worker_node.__name__ = f"{step}_node"
    return worker_node
