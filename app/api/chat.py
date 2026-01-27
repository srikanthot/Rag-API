"""Chat endpoint for RAG-based question answering."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from app.models import ChatRequest, ChatResponse
from app.services.audit import generate_request_id, get_audit_service
from app.services.auth import get_current_user
from app.services.rag_service import get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
) -> ChatResponse:
    """Process a chat request and return a grounded answer with citations.

    This endpoint:
    1. Retrieves relevant chunks from Azure AI Search using hybrid search
    2. Validates retrieval quality for grounding
    3. Generates an answer using Azure OpenAI with strict grounding rules
    4. Extracts and validates citations from the response
    5. Returns the answer with citations and confidence level
    6. Logs audit metadata to Cosmos DB (if enabled)

    If no relevant content is found, returns "I don't know based on the available manuals."

    Args:
        request: ChatRequest with question and optional session/user IDs.

    Returns:
        ChatResponse with answer, citations, confidence, and optional follow-up.

    Raises:
        HTTPException: If an error occurs during processing.
    """
    request_id = generate_request_id()
    start_time = time.time()
    auth_mode = current_user.get("auth_mode", "unknown")

    try:
        logger.info(
            f"Chat request received "
            f"(request_id={request_id}, session={request.session_id}, "
            f"user={request.user_id}, auth_mode={auth_mode})"
        )

        rag_service = get_rag_service()
        response = rag_service.process_chat(request, request_id=request_id)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Chat response generated "
            f"(request_id={request_id}, confidence={response.confidence}, "
            f"citations={len(response.citations)}, latency_ms={latency_ms:.2f})"
        )

        # Log to audit service (async, non-blocking)
        audit_service = get_audit_service()
        audit_service.log_chat_request(
            request_id=request_id,
            session_id=request.session_id,
            user_id=request.user_id,
            question=request.question,
            retrieval_metadata=response.retrieval_metadata,
            response_metadata={
                "confidence": response.confidence,
                "latency_ms": latency_ms,
                "citation_count": len(response.citations),
            },
            auth_mode=auth_mode,
        )

        # Return the response with request_id for troubleshooting
        return ChatResponse(
            answer=response.answer,
            citations=response.citations,
            confidence=response.confidence,
            follow_up_question=response.follow_up_question,
            request_id=request_id,
        )

    except Exception as e:
        logger.error(f"Chat processing error (request_id={request_id}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your request. Please try again.",
        )
