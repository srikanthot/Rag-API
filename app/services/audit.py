"""Audit logging service for tracking chat requests and responses.

Stores minimal safe metadata in Cosmos DB for traceability without
storing sensitive content like full retrieved chunks or manual content.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.clients.cosmos_client import get_cosmos_client
from app.config import get_settings

logger = logging.getLogger(__name__)


class AuditService:
    """Service for audit logging to Cosmos DB."""

    def __init__(self):
        """Initialize the audit service."""
        self._cosmos_client = get_cosmos_client()
        settings = get_settings()
        self._enabled = settings.audit_enabled

    @property
    def is_enabled(self) -> bool:
        """Check if audit logging is enabled."""
        return self._enabled and self._cosmos_client.is_available

    def log_chat_request(
        self,
        request_id: str,
        session_id: Optional[str],
        user_id: Optional[str],
        question: str,
        retrieval_metadata: list[dict],
        response_metadata: dict,
        auth_mode: str,
    ) -> Optional[dict]:
        """Log a chat request with metadata to Cosmos DB.

        This method stores ONLY safe metadata, not full content:
        - Question text (allowed per requirements)
        - Retrieval metadata: manual_name, page, chunk_id, scores
        - Response metadata: confidence, token usage, latency
        - NO full chunk content
        - NO full manual content
        - NO image data

        Args:
            request_id: Unique identifier for this request.
            session_id: Optional session ID for conversation tracking.
            user_id: Optional user ID for audit purposes.
            question: The user's question (allowed to store).
            retrieval_metadata: List of retrieval results with metadata only.
            response_metadata: Response metadata (confidence, tokens, latency).
            auth_mode: Authentication mode used (api_key or managed_identity).

        Returns:
            The created audit record or None if logging is disabled/fails.
        """
        if not self.is_enabled:
            logger.debug("Audit logging disabled - skipping")
            return None

        # Build the audit record with safe metadata only
        audit_record = {
            "id": request_id,
            "session_id": session_id or "anonymous",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "retrieval_metadata": self._sanitize_retrieval_metadata(retrieval_metadata),
            "response_metadata": response_metadata,
            "auth_mode": auth_mode,
            "record_type": "chat_request",
        }

        result = self._cosmos_client.create_item(audit_record)

        if result:
            logger.info(f"Audit record created: {request_id}")
        else:
            logger.warning(f"Failed to create audit record: {request_id}")

        return result

    def _sanitize_retrieval_metadata(self, retrieval_results: list[dict]) -> list[dict]:
        """Sanitize retrieval results to include only safe metadata.

        Removes full content, keeping only:
        - manual_name
        - page
        - chunk_id
        - score
        - reranker_score (if available)

        Args:
            retrieval_results: Raw retrieval results.

        Returns:
            List of sanitized metadata dictionaries.
        """
        sanitized = []
        for result in retrieval_results:
            sanitized.append({
                "manual_name": result.get("manual_name"),
                "page": result.get("page"),
                "chunk_id": result.get("chunk_id"),
                "score": result.get("score"),
                "reranker_score": result.get("reranker_score"),
            })
        return sanitized

    def get_session_history(self, session_id: str) -> list[dict]:
        """Retrieve chat history for a session.

        Args:
            session_id: The session ID to query.

        Returns:
            List of audit records for the session.
        """
        if not self.is_enabled:
            return []

        query = "SELECT * FROM c WHERE c.session_id = @session_id ORDER BY c.timestamp DESC"
        parameters = [{"name": "@session_id", "value": session_id}]

        return self._cosmos_client.query_items(
            query=query,
            parameters=parameters,
            partition_key=session_id,
        )

    def get_user_history(self, user_id: str, limit: int = 100) -> list[dict]:
        """Retrieve chat history for a user across sessions.

        Args:
            user_id: The user ID to query.
            limit: Maximum number of records to return.

        Returns:
            List of audit records for the user.
        """
        if not self.is_enabled:
            return []

        query = f"SELECT TOP {limit} * FROM c WHERE c.user_id = @user_id ORDER BY c.timestamp DESC"
        parameters = [{"name": "@user_id", "value": user_id}]

        return self._cosmos_client.query_items(
            query=query,
            parameters=parameters,
        )


class AuditContext:
    """Context manager for tracking request timing and metadata."""

    def __init__(self, request_id: Optional[str] = None):
        """Initialize audit context.

        Args:
            request_id: Optional request ID. Generated if not provided.
        """
        self.request_id = request_id or str(uuid.uuid4())
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.retrieval_results: list[dict] = []
        self.token_usage: Optional[dict] = None
        self.confidence: Optional[str] = None

    def __enter__(self) -> "AuditContext":
        """Start timing the request."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop timing the request."""
        self.end_time = time.time()

    @property
    def latency_ms(self) -> Optional[float]:
        """Calculate request latency in milliseconds."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def set_retrieval_results(self, results: list) -> None:
        """Set retrieval results for audit logging.

        Args:
            results: List of SearchResult objects or dicts.
        """
        self.retrieval_results = []
        for r in results:
            if hasattr(r, "to_dict"):
                self.retrieval_results.append(r.to_dict())
            elif isinstance(r, dict):
                self.retrieval_results.append(r)

    def set_token_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Set token usage for audit logging.

        Args:
            prompt_tokens: Number of tokens in the prompt.
            completion_tokens: Number of tokens in the completion.
        """
        self.token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def set_confidence(self, confidence: str) -> None:
        """Set response confidence level.

        Args:
            confidence: Confidence level (high, medium, low).
        """
        self.confidence = confidence

    def get_response_metadata(self) -> dict:
        """Get response metadata for audit logging.

        Returns:
            Dictionary with response metadata.
        """
        return {
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
        }


_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get or create the audit service singleton."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


def generate_request_id() -> str:
    """Generate a unique request ID.

    Returns:
        A UUID string for request tracking.
    """
    return str(uuid.uuid4())
