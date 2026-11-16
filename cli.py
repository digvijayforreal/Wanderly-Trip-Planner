"""Test the graph in the terminal without the web UI"""
import uuid 

from langchain_core.messages import HumanMessage

from app.config import RECURSION_LIMIT 
from app.graph import graph

def main() -> None:
    config = {
        "configurable":{"thread_id":str(uuid.uuid4())},
        "recursion_limit": RECURSION_LIMIT,
    }
    print ("Trip Planner (type 'quit' to exit)\n")

    while True:
        text = input("You: ").strip()
        if text.lower() in {"quit","exit"}:
            break
        if not text:
            continue
        
        # Print each node as it finishes so you can watch the graph run.
        for chunk in graph.stream({"messages": [HumanMessage(content=text)]}, config, stream_mode="updates"):
            for node in chunk:
                print(f"  · {node}")
        
        answer = graph.get_state(config).values.get("final_answer","")
        print(f"\nPlanner:\n{answer}\n")

if __name__=="__main__":
    main()
    