""" All settings in one place. Change models or Limits here, not in agent code. """
import os
import sys

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY =  os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ KEY MISSING")

#Each graph node gets its own model and temperature.
# Keys must match the node names in state.WORKERS (plus "supervisor").

MODELS = {
    "supervisor":            {"model":"openai/gpt-oss-120b","temperature": 0.0},  # strict reviewer
    "researcher":            {"model":"openai/gpt-oss-20b", "temperature": 0.7},  # a bit creative
    "itinerary_builder":    {"model":"openai/gpt-oss-20b", "temperature": 0.5},
    "budget_planner":        {"model":"openai/gpt-oss-20b", "temperature": 0.0},  # consistent numbers
    "packing_expert":        {"model":"openai/gpt-oss-20b", "temperature": 0.3},
}

#Used automatically if the main model errors out (rate limit, outage).
# Tried in order. Each model has its own rate limit, so gpt-oss-20b is a strong backup
# for the supervisor when gpt-oss-120b hits its daily limit.
FALLBACK_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

# ---------- Modes ----------
# "groq"  = cloud models above.  "local" = every agent uses the local Ollama model below.
MODES        = ("groq", "local")
DEFAULT_MODE = "groq"

LOCAL_MODEL          = os.getenv("OLLAMA_MODEL", "hermes3:3b")            # must match `ollama list`
OLLAMA_BASE_URL      = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LOCAL_CONTEXT_WINDOW = 8192   # tokens; our prompts are long, Ollama's default is too small

MAX_REVISIONS       = 2        #rework attempts per worker before the supervisor accepts
MAX_API_RETRIES     = 3        #Groq client retries (with backoff) on rate limits / network errors
# No step limit. LangGraph needs a number (its default of 25 would cut runs short),
# so we pass the largest one. Loops are prevented in code instead: a worker approved
# this turn can't be called again, and each worker has MAX_REVISIONS reworks.
RECURSION_LIMIT     = sys.maxsize
HISTORY_WINDOW      = 10       #how manys past chat messages the supervisor reads
MAX_MESSAGE_LENGTH  = 2000     # max characters per user message

CURRENCY_SYMBOL = "₹"
CURRENCY_CODE   = "INR"