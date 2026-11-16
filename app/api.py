"""FastAPI app: serves the frontend and streams graph progress as NDJSON."""
import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage

from app import limits
from app.config import DEFAULT_MODE, FALLBACK_MODELS, GROQ_API_KEY, LOCAL_MODEL, MODELS, RECURSION_LIMIT
from app.graph import graph
from app.schemas import ChatRequest
from app.state import STEP_TITLES

logger = logging.getLogger("trip_planner")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Trip Planner")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Friendly progress messages shown in the chat while the graph runs.
NODE_STATUS = {
    "intake": "Supervisor read your request",
    "researcher": "Researcher drafted the destination guide",
    "itinerary_builder": "Itinerary builder planned each day",
    "budget_planner": "Budget planner priced the trip",
    "packing_expert": "Packing expert made your checklist",
    "finalize": "Supervisor wrote your answer",
}

def describe(node: str, update: dict):
    """Turn a node update into (text, kind) for the UI, or None to skip."""
    if node == "supervisor":
        nxt = update.get("next_step", "")
        if nxt not in STEP_TITLES:
            return None  # ask_user / finalize are shown by their own nodes
        reason = update.get("decision_reason", "").strip().rstrip(".")
        text = f"Supervisor assigned: {STEP_TITLES[nxt]}"
        return (f"{text} ({reason})" if reason else text), "plan"
    if node == "review":
        step = update.get("current_step", "")
        title = STEP_TITLES.get(step, "work").lower()
        if update.get("approved"):
            return f"Supervisor approved the {title}", "done"
        if update.get("feedback_for") == "itinerary_builder" and step == "budget_planner":
            return "Supervisor found the budget too high, asking for a cheaper itinerary", "rework"
        return f"Supervisor sent the {title} back for rework", "rework"
    text = NODE_STATUS.get(node)
    return (text, "done") if text else None

def event_stream(message: str, session_id: str, mode: str):
    # "mode" is read by every node (llms.mode_from) to pick Groq or the local Ollama model.
    config = {"configurable": {"thread_id": session_id, "mode": mode}, "recursion_limit": RECURSION_LIMIT}
    try:
        for chunk in graph.stream({"messages": [HumanMessage(content=message)]}, config, stream_mode="updates"):
            for node, update in chunk.items():
                status = describe(node, update or {})
                if status:
                    yield json.dumps({"type": "status", "text": status[0], "kind": status[1]}) + "\n"

        final = graph.get_state(config).values.get("final_answer", "")
        yield json.dumps({"type": "final", "text": final}) + "\n"
    except Exception as exc:
        # Log details on the server; never send stack traces to the browser.
        logger.exception("Graph run failed (mode=%s)", mode)
        yield json.dumps({"type": "error", "text": friendly_error(exc, mode)}) + "\n"


def friendly_error(exc: Exception, mode: str) -> str:
    """Short, useful error text for the UI (no internals)."""
    text = str(exc).lower()
    if mode == "local" and ("connect" in text or "refused" in text):
        return f"Can't reach the local model. Is Ollama running with `{LOCAL_MODEL}`? (ollama run {LOCAL_MODEL})"
    if mode == "local" and "not found" in text:
        return f"Model `{LOCAL_MODEL}` isn't installed. Run: ollama pull {LOCAL_MODEL}"
    if "rate limit" in text or "429" in text:
        return "Groq's free limit is used up for now. Try again later, or switch to Local mode."
    return "Something went wrong while planning. Please try again."


def groq_models() -> list[str]:
    """Every Groq model the app can call (main models + fallbacks), in a stable order."""
    names = [cfg["model"] for cfg in MODELS.values()] + list(FALLBACK_MODELS)
    return list(dict.fromkeys(names))


@app.get("/api/limits")
def get_limits():
    """Latest Groq usage numbers, collected from normal calls (no API cost)."""
    return limits.snapshot(groq_models())


@app.post("/api/limits/refresh")
def refresh_limits():
    """Probe each model with a 1-token request for fresh numbers (costs a few tokens)."""
    limits.probe(groq_models(), GROQ_API_KEY)
    return limits.snapshot(groq_models())


@app.get("/api/modes")
def modes():
    """Labels for the mode switch in the UI."""
    return {"default": DEFAULT_MODE, "modes": {"groq": "Groq · cloud", "local": f"Local · {LOCAL_MODEL}"}}

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.post("/api/chat")
def chat(req: ChatRequest):
    return StreamingResponse(event_stream(req.message.strip(), req.session_id, req.mode),
                             media_type="application/x-ndjson")
