"""The four worker agents. One factory builds them all, since they share the same shape."""
from langchain_core.messages import HumanMessage, SystemMessage

from app.llms import get_llm
from app.prompts import WORKER_PROMPTS
from app.state import OUTPUT_KEY, TripState
from app.utils import clean_text, format_trip

# Which earlier results each worker needs to read.
CONTEXT_KEYS = {
    "researcher": [],
    "itinerary_builder": ["research"],
    "budget_planner": ["itinerary"],
    "packing_expert": ["research", "itinerary"],
}

def make_worker(step: str):
    """Build a graph node function for one worker step."""
    output_key = OUTPUT_KEY[step]

    def worker_node(state: TripState) -> dict:
        parts = [f"## Trip details\n{format_trip(state['trip'])}"]

        for key in CONTEXT_KEYS[step]:
            parts.append(f"## {key.title()}\n{state.get(key, '')}")

        # On a rework, show the previous draft and the supervisor's fixes.
        if state.get("feedback_for") == step and state.get("feedback"):
            parts.append(f"## Your previous draft\n{state.get(output_key, '')}")
            parts.append(f"## Supervisor feedback (fix all of this)\n{state['feedback']}")

        result = get_llm(step).invoke([
            SystemMessage(content=WORKER_PROMPTS[step]),
            HumanMessage(content="\n\n".join(parts)),
        ])
        return {output_key: clean_text(result.content), "current_step": step}

    worker_node.__name__ = f"{step}_node"
    return worker_node
