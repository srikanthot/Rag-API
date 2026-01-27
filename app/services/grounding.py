"""Grounding and anti-hallucination guardrails for RAG responses."""

import logging
import re
from typing import Optional

from app.clients.search_client import SearchResult
from app.config import get_settings
from app.models import Citation

logger = logging.getLogger(__name__)


class GroundingService:
    """Service for ensuring responses are grounded in retrieved content."""

    # Standard response when no relevant content is found
    NO_ANSWER_RESPONSE = "I don't know based on the available manuals."

    # Follow-up questions for different scenarios
    FOLLOW_UP_NO_RESULTS = "Could you provide more details such as the manual name, equipment ID, or specific section you're asking about?"
    FOLLOW_UP_UNCLEAR = "Could you rephrase your question or specify which manual or topic you're interested in?"

    def __init__(self):
        """Initialize the grounding service."""
        settings = get_settings()
        self.min_grounded_score = settings.min_grounded_score

    def check_retrieval_quality(
        self,
        results: list[SearchResult],
    ) -> tuple[bool, str, Optional[str]]:
        """Check if retrieval results are sufficient for grounding.

        Args:
            results: List of search results from retrieval.

        Returns:
            Tuple of (is_grounded, reason, follow_up_question).
            - is_grounded: True if results are good enough to generate an answer
            - reason: Explanation of the decision
            - follow_up_question: Suggested follow-up if not grounded
        """
        if not results:
            logger.info("Grounding check failed: no results returned")
            return (
                False,
                "No relevant content found in the manuals",
                self.FOLLOW_UP_NO_RESULTS,
            )

        # Check top result score
        top_score = results[0].score
        if top_score < self.min_grounded_score:
            logger.info(
                f"Grounding check failed: top score {top_score:.4f} "
                f"< threshold {self.min_grounded_score}"
            )
            return (
                False,
                f"Retrieved content relevance ({top_score:.2f}) below threshold",
                self.FOLLOW_UP_UNCLEAR,
            )

        # Count results above threshold
        relevant_count = sum(
            1 for r in results if r.score >= self.min_grounded_score
        )
        logger.info(
            f"Grounding check passed: {relevant_count} results above threshold"
        )

        return (True, f"{relevant_count} relevant chunks found", None)

    def extract_quote(self, content: str, max_length: int = 150) -> str:
        """Extract a short quote from content for citation.

        Args:
            content: The full content text.
            max_length: Maximum length of the quote.

        Returns:
            A short excerpt from the content.
        """
        if not content:
            return ""

        # Clean up whitespace
        content = " ".join(content.split())

        # If content is short enough, return as-is
        if len(content) <= max_length:
            return content

        # Try to break at sentence boundary
        sentences = re.split(r'(?<=[.!?])\s+', content)
        quote = ""
        for sentence in sentences:
            if len(quote) + len(sentence) + 1 <= max_length:
                quote = f"{quote} {sentence}".strip() if quote else sentence
            else:
                break

        # If no complete sentence fits, truncate with ellipsis
        if not quote:
            quote = content[:max_length - 3].rsplit(" ", 1)[0] + "..."

        return quote

    def create_citation_from_result(self, result: SearchResult) -> Citation:
        """Create a Citation object from a SearchResult.

        Args:
            result: The search result to convert.

        Returns:
            A Citation object with extracted quote.
        """
        quote = self.extract_quote(result.content)

        return Citation(
            manual_name=result.manual_name,
            page=result.page,
            chunk_id=result.chunk_id,
            quote=quote,
        )

    def validate_citations(
        self,
        citations: list[Citation],
        retrieved_results: list[SearchResult],
    ) -> list[Citation]:
        """Validate that all citations map to retrieved chunks.

        This ensures citation integrity - every citation must correspond
        to an actual retrieved chunk, not model imagination.

        Args:
            citations: List of citations to validate.
            retrieved_results: List of retrieved search results.

        Returns:
            List of validated citations (invalid ones removed).
        """
        # Build set of valid chunk IDs from retrieval
        valid_chunk_ids = {r.chunk_id for r in retrieved_results}
        valid_citations = []

        for citation in citations:
            if citation.chunk_id in valid_chunk_ids:
                valid_citations.append(citation)
            else:
                logger.warning(
                    f"Removed invalid citation: {citation.chunk_id} "
                    "not in retrieved results"
                )

        return valid_citations

    def determine_confidence(
        self,
        results: list[SearchResult],
        citations: list[Citation],
    ) -> str:
        """Determine confidence level based on retrieval and citations.

        Args:
            results: Retrieved search results.
            citations: Citations used in the answer.

        Returns:
            Confidence level: "high", "medium", or "low".
        """
        if not results or not citations:
            return "low"

        top_score = results[0].score
        num_citations = len(citations)

        # High confidence: strong retrieval score and multiple citations
        if top_score >= 0.85 and num_citations >= 2:
            return "high"

        # Medium confidence: decent score or at least one citation
        if top_score >= self.min_grounded_score and num_citations >= 1:
            return "medium"

        return "low"

    def build_no_answer_response(
        self,
        reason: str,
        follow_up: Optional[str] = None,
    ) -> dict:
        """Build a standardized "I don't know" response.

        Args:
            reason: Reason for not being able to answer.
            follow_up: Optional follow-up question.

        Returns:
            Dictionary with response fields.
        """
        return {
            "answer": self.NO_ANSWER_RESPONSE,
            "citations": [],
            "confidence": "low",
            "follow_up_question": follow_up or self.FOLLOW_UP_NO_RESULTS,
        }


_grounding_service: Optional[GroundingService] = None


def get_grounding_service() -> GroundingService:
    """Get or create the grounding service singleton."""
    global _grounding_service
    if _grounding_service is None:
        _grounding_service = GroundingService()
    return _grounding_service
