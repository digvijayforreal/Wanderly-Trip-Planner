"""Pydantic models: structured LLM outputs and the API request body."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.config import MAX_MESSAGE_LENGTH


class TripDetails(BaseModel):
    """What the supervisor extracts from the conversation."""
    destination: Optional[str] = Field(None, description="Where the user wants to go.")
    origin: Optional[str] = Field(None, description="Starting city, if mentioned.")
    days: Optional[int] = Field(None, description="Trip length in days.")
    travelers: Optional[int] = Field(None, description="Number of people travelling.")
    budget: Optional[float] = Field(None, description="Total budget for the whole group, in INR.")
    start_date: Optional[str] = Field(None, description="Start date or month, if mentioned.")
    # Optional (not list default): models often send null here, which would fail schema validation.
    interests: Optional[list[str]] = Field(None, description="Things the user enjoys, e.g. beaches, food, trekking.")
    special_requests: Optional[str] = Field(None, description="Constraints or change requests, e.g. 'make it cheaper', 'vegetarian'.")


class Decision(BaseModel):
    """The supervisor's choice of what happens next."""
    next: Literal["researcher", "itinerary_builder", "budget_planner", "packing_expert", "ask_user", "finish"] = Field(
        description="The one next step: a team member, 'ask_user', or 'finish'.",
    )
    reason: Optional[str] = Field(None, description="One short sentence explaining the choice, e.g. 'User wants a cost estimate'.")
    message_to_user: Optional[str] = Field(
        None,
        description="Only for 'ask_user': one short, friendly Markdown message asking for ALL missing details at once, "
                    "or explaining what you can help with.",
    )


class Review(BaseModel):
    """The supervisor's verdict on one worker's output."""
    approved: bool = Field(description="True only if the work passes every checklist item.")
    feedback: Optional[str] = Field(None, description="Empty if approved. Otherwise specific, actionable fixes as short bullet points.")
    send_to: Optional[Literal["same_agent", "itinerary_builder"]] = Field(
        "same_agent",
        description="Use 'itinerary_builder' only when reviewing a budget that prices an itinerary and the total "
                    "is over the user's budget.",
    )


class ChatRequest(BaseModel):
    """Body of POST /api/chat."""
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    session_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
