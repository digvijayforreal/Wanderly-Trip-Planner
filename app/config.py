""" All settings in one place. Change models or Limits here, not in agent code. """
import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY =  os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ KEY MISSING")

#Each graph node gets its own model and temperature.
# Keys must match the node names in the state.STEPS (plus "supervisor").

MODELS = {
    "supervisor":            {"model":"openai/gpt-oss-120b","temperature": 0.0},  # strict reviewer
    "researcher":            {"model":"openai/gpt-oss-20b", "temperature": 0.7},  # a bit creative
    "itinerary_builder":    {"model":"openai/gpt-oss-20b", "temperature": 0.5},
    "budget_planner":        {"model":"openai/gpt-oss-20b", "temperature": 0.0},  # consistent numbers
    "packing_expert":        {"model":"openai/gpt-oss-20b", "temperature": 0.3},
}

#Used automatically if the main model errors out (rate limit, outage).
FALLBACK_MODEL = "qwen/qwen3.8-27b"

MAX_REVISIONS       = 2        #rework attempts per worker before the supervisor accepts
RECURSION_LIMIT     = 60       #hard cap on graph steps per request
HISTORY_WINDOW      = 10       #how manys past chat messages the supervisor reads
MAX_MESSAGE_LENGTH  = 2000     # max characters per user message

CURRENCY_SYMBOL = "₹"
CURRENCY_CODE   = "INR"