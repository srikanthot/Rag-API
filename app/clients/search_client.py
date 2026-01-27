"""Azure AI Search client for hybrid retrieval."""

import logging
from dataclasses import dataclass
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config import get_settings
from app.clients.openai_client import get_openai_client

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result with metadata for citations."""

    id: str
    manual_name: str
    page: int
    chunk_id: str
    content: str
    section_title: Optional[str]
    image_caption: Optional[str]
    score: float
    reranker_score: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "manual_name": self.manual_name,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "content": self.content,
            "section_title": self.section_title,
            "image_caption": self.image_caption,
            "score": self.score,
            "reranker_score": self.reranker_score,
        }


class AzureSearchClient:
    """Client for Azure AI Search with hybrid retrieval support."""

    def __init__(self):
        """Initialize the Azure AI Search client."""
        settings = get_settings()
        self.client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index,
            credential=AzureKeyCredential(settings.azure_search_key),
        )
        self.openai_client = get_openai_client()
        self.top_k = settings.top_k

    def hybrid_search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_expression: Optional[str] = None,
    ) -> list[SearchResult]:
        """Perform hybrid search combining vector and keyword search.

        This method:
        1. Generates an embedding for the query using Azure OpenAI
        2. Performs vector search using the embedding
        3. Performs keyword search (BM25) on the same query
        4. Azure AI Search combines results using Reciprocal Rank Fusion (RRF)

        Args:
            query: The user's search query text.
            top_k: Number of results to return (overrides config).
            filter_expression: Optional OData filter (e.g., "manual_name eq 'Safety_Manual.pdf'").

        Returns:
            List of SearchResult objects with scores.
        """
        k = top_k or self.top_k

        # Generate query embedding
        logger.info(f"Generating embedding for query (length: {len(query)} chars)")
        query_embedding = self.openai_client.get_embedding(query)

        # Create vector query
        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=k,
            fields="content_vector",
        )

        # Perform hybrid search
        # Azure AI Search automatically combines vector and keyword results using RRF
        logger.info(f"Executing hybrid search with top_k={k}")
        results = self.client.search(
            search_text=query,  # Keyword search (BM25)
            vector_queries=[vector_query],  # Vector search
            select=["id", "manual_name", "page", "chunk_id", "content", "section_title", "image_caption"],
            filter=filter_expression,
            top=k,
        )

        # Convert to SearchResult objects
        search_results = []
        for result in results:
            search_result = SearchResult(
                id=result["id"],
                manual_name=result["manual_name"],
                page=result["page"],
                chunk_id=result["chunk_id"],
                content=result["content"],
                section_title=result.get("section_title"),
                image_caption=result.get("image_caption"),
                score=result["@search.score"],
                reranker_score=result.get("@search.reranker_score"),
            )
            search_results.append(search_result)

        logger.info(f"Retrieved {len(search_results)} results")
        return search_results

    def vector_search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_expression: Optional[str] = None,
    ) -> list[SearchResult]:
        """Perform vector-only search.

        Args:
            query: The user's search query text.
            top_k: Number of results to return.
            filter_expression: Optional OData filter.

        Returns:
            List of SearchResult objects.
        """
        k = top_k or self.top_k

        query_embedding = self.openai_client.get_embedding(query)

        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=k,
            fields="content_vector",
        )

        results = self.client.search(
            search_text=None,  # No keyword search
            vector_queries=[vector_query],
            select=["id", "manual_name", "page", "chunk_id", "content", "section_title", "image_caption"],
            filter=filter_expression,
            top=k,
        )

        search_results = []
        for result in results:
            search_result = SearchResult(
                id=result["id"],
                manual_name=result["manual_name"],
                page=result["page"],
                chunk_id=result["chunk_id"],
                content=result["content"],
                section_title=result.get("section_title"),
                image_caption=result.get("image_caption"),
                score=result["@search.score"],
            )
            search_results.append(search_result)

        return search_results

    def keyword_search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_expression: Optional[str] = None,
    ) -> list[SearchResult]:
        """Perform keyword-only search (BM25).

        Args:
            query: The user's search query text.
            top_k: Number of results to return.
            filter_expression: Optional OData filter.

        Returns:
            List of SearchResult objects.
        """
        k = top_k or self.top_k

        results = self.client.search(
            search_text=query,
            vector_queries=None,  # No vector search
            select=["id", "manual_name", "page", "chunk_id", "content", "section_title", "image_caption"],
            filter=filter_expression,
            top=k,
        )

        search_results = []
        for result in results:
            search_result = SearchResult(
                id=result["id"],
                manual_name=result["manual_name"],
                page=result["page"],
                chunk_id=result["chunk_id"],
                content=result["content"],
                section_title=result.get("section_title"),
                image_caption=result.get("image_caption"),
                score=result["@search.score"],
            )
            search_results.append(search_result)

        return search_results


_search_client: Optional[AzureSearchClient] = None


def get_search_client() -> AzureSearchClient:
    """Get or create the search client singleton."""
    global _search_client
    if _search_client is None:
        _search_client = AzureSearchClient()
    return _search_client
