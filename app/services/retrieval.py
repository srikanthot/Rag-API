"""Retrieval service for RAG pipeline."""

import logging
from typing import Optional

from app.clients.search_client import SearchResult, get_search_client
from app.config import get_settings

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for retrieving relevant chunks from Azure AI Search."""

    def __init__(self):
        """Initialize the retrieval service."""
        self.search_client = get_search_client()
        settings = get_settings()
        self.top_k = settings.top_k
        self.min_grounded_score = settings.min_grounded_score

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        manual_filter: Optional[str] = None,
    ) -> list[SearchResult]:
        """Retrieve relevant chunks for a query using hybrid search.

        Args:
            query: The user's question or search query.
            top_k: Number of results to return (overrides config).
            manual_filter: Optional manual name to filter by.

        Returns:
            List of SearchResult objects sorted by relevance.
        """
        k = top_k or self.top_k

        # Build filter expression if manual specified
        filter_expr = None
        if manual_filter:
            filter_expr = f"manual_name eq '{manual_filter}'"

        # Perform hybrid search
        results = self.search_client.hybrid_search(
            query=query,
            top_k=k,
            filter_expression=filter_expr,
        )

        # Log retrieval metadata (not content)
        logger.info(
            f"Retrieved {len(results)} chunks for query "
            f"(top_k={k}, filter={filter_expr})"
        )
        for i, r in enumerate(results):
            logger.debug(
                f"  [{i+1}] {r.manual_name} p{r.page} ({r.chunk_id}) "
                f"score={r.score:.4f}"
            )

        return results

    def has_relevant_results(self, results: list[SearchResult]) -> bool:
        """Check if retrieval results are relevant enough for grounding.

        Args:
            results: List of search results.

        Returns:
            True if results are relevant, False otherwise.
        """
        if not results:
            return False

        # Check if top result meets minimum score threshold
        top_score = results[0].score
        return top_score >= self.min_grounded_score

    def get_context_for_prompt(
        self,
        results: list[SearchResult],
        max_chunks: Optional[int] = None,
    ) -> str:
        """Format retrieval results as context for the LLM prompt.

        Args:
            results: List of search results.
            max_chunks: Maximum number of chunks to include.

        Returns:
            Formatted context string with source citations.
        """
        if not results:
            return ""

        chunks_to_use = results[:max_chunks] if max_chunks else results
        context_parts = []

        for i, result in enumerate(chunks_to_use, 1):
            # Format each chunk with citation metadata
            source_info = f"[Source {i}: {result.manual_name}, Page {result.page}, ID: {result.chunk_id}]"
            content = result.content

            # Include image caption if present
            if result.image_caption:
                content += f"\n[Image description: {result.image_caption}]"

            context_parts.append(f"{source_info}\n{content}")

        return "\n\n---\n\n".join(context_parts)


_retrieval_service: Optional[RetrievalService] = None


def get_retrieval_service() -> RetrievalService:
    """Get or create the retrieval service singleton."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
