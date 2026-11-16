"""LangGraph wiring: which node runs after which.

START → intake → supervisor ─┬─ worker → review ─┬─ approved → supervisor (decides again)
                             │                   └─ rejected → same worker (or itinerary if over budget)
                             ├─ ask_user → END
                             └─ finalize → END
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.supervisor import ask_user_node, finalize_node, intake_node, review_node, supervisor_node
from app.agents.workers import make_worker
from app.state import WORKERS, TripState


def route_after_supervisor(state: TripState) -> str:
    """Go wherever the supervisor decided: a worker, ask_user or finalize."""
    return state["next_step"]


def route_after_review(state: TripState) -> str:
    """The review node already worked out the route (supervisor, or a worker for rework)."""
    return state["route"]


def build_graph():
    builder = StateGraph(TripState)

    # Nodes
    builder.add_node("intake", intake_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("ask_user", ask_user_node)
    for worker in WORKERS:
        builder.add_node(worker, make_worker(worker))
    builder.add_node("review", review_node)
    builder.add_node("finalize", finalize_node)

    # Edges
    builder.add_edge(START, "intake")
    builder.add_edge("intake", "supervisor")
    builder.add_conditional_edges("supervisor", route_after_supervisor, [*WORKERS, "ask_user", "finalize"])
    for worker in WORKERS:
        builder.add_edge(worker, "review")  # every worker is checked by the supervisor
    builder.add_conditional_edges("review", route_after_review, [*WORKERS, "supervisor"])
    builder.add_edge("ask_user", END)
    builder.add_edge("finalize", END)

    # MemorySaver keeps chat history per session (in memory; cleared on restart).
    return builder.compile(checkpointer=MemorySaver())


graph = build_graph()
