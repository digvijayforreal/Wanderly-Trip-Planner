"""Test the graph in the terminal without the web UI.

    uv run cli.py           # Groq (cloud)
    uv run cli.py local     # local Ollama model for every agent
"""
import sys
import uuid

from langchain_core.messages import HumanMessage

from app.config import DEFAULT_MODE, LOCAL_MODEL, MODES, RECURSION_LIMIT
from app.graph import graph


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODE
    if mode not in MODES:
        sys.exit(f"Unknown mode '{mode}'. Use one of: {', '.join(MODES)}")

    config = {
        "configurable": {"thread_id": str(uuid.uuid4()), "mode": mode},
        "recursion_limit": RECURSION_LIMIT,
    }
    label = f"local ({LOCAL_MODEL})" if mode == "local" else "groq"
    print(f"Trip Planner · mode: {label} (type 'quit' to exit)\n")

    while True:
        text = input("You: ").strip()
        if text.lower() in {"quit", "exit"}:
            break
        if not text:
            continue

        # Print each node as it finishes so you can watch the graph run.
        for chunk in graph.stream({"messages": [HumanMessage(content=text)]}, config, stream_mode="updates"):
            for node in chunk:
                print(f"  · {node}")

        answer = graph.get_state(config).values.get("final_answer", "")
        print(f"\nPlanner:\n{answer}\n")


if __name__ == "__main__":
    main()
