"""Pydantic models for API request/response schemas."""

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for the /chat endpoint."""

    question: str = Field(
        ...,
        description="The user's question about the manuals",
        min_length=1,
        max_length=2000,
    )
    session_id: Optional[str] = Field(
        None,
        description="Optional session ID for conversation tracking",
    )
    user_id: Optional[str] = Field(
        None,
        description="Optional user ID for audit logging",
    )
    manual_filter: Optional[str] = Field(
        None,
        description="Optional manual name to restrict search to",
    )


class Citation(BaseModel):
    """A citation referencing a source chunk."""

    manual_name: str = Field(
        ...,
        description="Name of the source manual PDF",
    )
    page: int = Field(
        ...,
        description="Page number in the manual (1-indexed)",
    )
    chunk_id: str = Field(
        ...,
        description="Unique identifier of the source chunk",
    )
    quote: str = Field(
        ...,
        description="Short excerpt from the source (1-2 lines)",
        max_length=500,
    )


class ChatResponse(BaseModel):
    """Response model for the /chat endpoint.

    This response format is designed to be PowerApps-friendly with:
    - Stable JSON keys that never change
    - Citations array always present (even if empty)
    - Short request_id for troubleshooting
    """

    answer: str = Field(
        ...,
        description="The generated answer based on retrieved content",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="List of citations supporting the answer (always present, may be empty)",
    )
    confidence: str = Field(
        ...,
        description="Confidence level: high, medium, or low",
        pattern="^(high|medium|low)$",
    )
    follow_up_question: Optional[str] = Field(
        None,
        description="Optional follow-up question to clarify user intent",
    )
    request_id: str = Field(
        default="",
        description="Unique request identifier for troubleshooting",
    )


class RetrievalResult(BaseModel):
    """Model for a single retrieval result (internal use)."""

    id: str
    manual_name: str
    page: int
    chunk_id: str
    content: str
    section_title: Optional[str] = None
    image_caption: Optional[str] = None
    score: float
    reranker_score: Optional[float] = None


class ChatResponseWithMetadata(ChatResponse):
    """Extended response model with metadata for audit logging (internal use)."""

    request_id: str = Field(
        ...,
        description="Unique request identifier for tracking",
    )
    retrieval_metadata: list[dict] = Field(
        default_factory=list,
        description="Metadata from retrieval results (no content)",
    )


class HealthResponse(BaseModel):
    """Response model for the /health endpoint."""

    status: str = Field(
        ...,
        description="Health status of the API",
    )
