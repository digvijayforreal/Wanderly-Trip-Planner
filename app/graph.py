
"""LangGraph wiring: which node runs after which."""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.supervisor import ask_user_node, finalize_node, intake_node, is_ready, review_node
from app.agents.workers import make_worker
from app.state import STEPS, TripState

def route_after_intake(state: TripState) -> str:
    """Plan if we have everything, otherwise ask the user."""
    return STEPS[0] if is_ready(state["trip"]) else "ask_user"

def route_after_review(state: TripState) -> str:
    """Rejected → back to the worker named in feedback_for. Approved → next worker or finalize."""
    if not state["approved"]:
        return state["feedback_for"]
    index = STEPS.index(state["current_step"])
    return STEPS[index + 1] if index + 1 < len(STEPS) else "finalize"

def build_graph():
    builder = StateGraph(TripState)

    # Nodes
    builder.add_node("intake", intake_node)
    builder.add_node("ask_user", ask_user_node)
    for step in STEPS:
        builder.add_node(step, make_worker(step))
    builder.add_node("review", review_node)
    builder.add_node("finalize", finalize_node)

    # Edges
    builder.add_edge(START, "intake")
    builder.add_conditional_edges("intake", route_after_intake, [STEPS[0], "ask_user"])
    for step in STEPS:
        builder.add_edge(step, "review")  # every worker is checked by the supervisor
    builder.add_conditional_edges("review", route_after_review, [*STEPS, "finalize"])
    builder.add_edge("ask_user", END)
    builder.add_edge("finalize", END)

    # MemorySaver keeps chat history per session (in memory; cleared on restart).
    return builder.compile(checkpointer=MemorySaver())

graph = build_graph()
