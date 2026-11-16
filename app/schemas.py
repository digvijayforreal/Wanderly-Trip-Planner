"""Pydantic models: structured LLM outputs and the API request body."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.config import MAX_MESSAGE_LENGTH

class TripDetails(BaseModel):
    """What the supervisor extracts from the conversation."""
    is_trip_request: bool = Field(description="True if the user wants a trip planned or an existing plan changed.")
    destination: Optional[str] = Field(None, description="Where the user wants to go.")
    origin: Optional[str] = Field(None, description="Starting city, if mentioned.")
    days: Optional[int] = Field(None, description="Trip length in days.")
    travelers: Optional[int] = Field(None, description="Number of people travelling.")
    budget: Optional[float] = Field(None, description="Total budget for the whole group, in INR.")
    start_date: Optional[str] = Field(None, description="Start date or month, if mentioned.")
    interests: list[str] = Field(default_factory=list, description="Things the user enjoys, e.g. beaches, food, trekking.")
    special_requests: Optional[str] = Field(None, description="Constraints or change requests, e.g. 'make it cheaper', 'vegetarian'.")
    reply_to_user: Optional[str] = Field(
        None,
        description="Only if required info is missing or the message is not about travel: one short, friendly reply in Markdown.",
    )

class Review(BaseModel):
    """The supervisor's verdict on one worker's output."""
    approved: bool = Field(description="True only if the work passes every checklist item.")
    feedback: str = Field("", description="Empty if approved. Otherwise specific, actionable fixes as short bullet points.")
    send_to: Literal["same_agent", "itinerary_builder"] = Field(
        "same_agent",
        description="Use 'itinerary_builder' only when reviewing the budget and the total is over the user's budget.",
    )

class ChatRequest(BaseModel):
    """Body of POST /api/chat."""
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    session_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,64}$")
