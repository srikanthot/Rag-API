"""RAG orchestration service for the chat endpoint."""

import logging
import re
from typing import Optional

from app.clients.openai_client import get_openai_client
from app.clients.search_client import SearchResult
from app.config import get_settings
from app.models import ChatRequest, ChatResponseWithMetadata, Citation
from app.services.grounding import get_grounding_service
from app.services.retrieval import get_retrieval_service

logger = logging.getLogger(__name__)


class RAGService:
    """Service for orchestrating RAG pipeline: retrieve, generate, validate."""

    # System prompt for grounded generation
    SYSTEM_PROMPT = """You are a helpful assistant that answers questions based ONLY on the provided source documents from technical manuals.

STRICT RULES:
1. Answer ONLY from the provided sources. Do not use any external knowledge.
2. If the sources do not contain information to answer the question, respond with: "I don't know based on the available manuals."
3. ALWAYS cite your sources using the format [Source N] where N matches the source number provided.
4. Include at least one citation for every factual claim.
5. Keep answers concise and directly relevant to the question.
6. If the question is ambiguous, ask for clarification.

CITATION FORMAT:
- Use [Source 1], [Source 2], etc. to reference the provided sources
- Each source has: manual name, page number, and chunk ID
- You must cite the specific source that supports each statement"""

    def __init__(self):
        """Initialize the RAG service."""
        self.retrieval_service = get_retrieval_service()
        self.grounding_service = get_grounding_service()
        self.openai_client = get_openai_client()
        settings = get_settings()
        self.top_k = settings.top_k
        self.temperature = settings.temperature

    def process_chat(
        self,
        request: ChatRequest,
        request_id: Optional[str] = None,
    ) -> ChatResponseWithMetadata:
        """Process a chat request through the RAG pipeline.

        Args:
            request: The chat request with user's question.
            request_id: Optional request ID for tracking.

        Returns:
            ChatResponseWithMetadata with answer, citations, confidence, and retrieval metadata.
        """
        logger.info(f"Processing chat request (session={request.session_id}, request_id={request_id})")

        # Step 1: Retrieve relevant chunks
        results = self.retrieval_service.retrieve(
            query=request.question,
            top_k=self.top_k,
            manual_filter=request.manual_filter,
        )

        # Extract retrieval metadata for audit (no content)
        retrieval_metadata = self._extract_retrieval_metadata(results)

        # Step 2: Check grounding quality
        is_grounded, reason, follow_up = self.grounding_service.check_retrieval_quality(
            results
        )

        if not is_grounded:
            logger.info(f"Grounding check failed: {reason}")
            no_answer = self.grounding_service.build_no_answer_response(
                reason=reason,
                follow_up=follow_up,
            )
            return ChatResponseWithMetadata(
                **no_answer,
                request_id=request_id or "",
                retrieval_metadata=retrieval_metadata,
            )

        # Step 3: Build context and generate response
        context = self.retrieval_service.get_context_for_prompt(results)
        answer_text = self._generate_answer(request.question, context)

        # Step 4: Parse citations from response
        citations = self._extract_citations(answer_text, results)

        # Step 5: Validate citations
        if not citations:
            # Re-prompt once to add citations
            logger.info("No citations found, re-prompting for citations")
            answer_text = self._generate_answer_with_citation_reminder(
                request.question, context, answer_text
            )
            citations = self._extract_citations(answer_text, results)

        # Validate all citations against retrieved results
        citations = self.grounding_service.validate_citations(citations, results)

        # Step 6: Determine confidence
        confidence = self.grounding_service.determine_confidence(results, citations)

        # Step 7: Clean answer text (remove citation markers for cleaner output)
        clean_answer = self._clean_answer(answer_text)

        return ChatResponseWithMetadata(
            answer=clean_answer,
            citations=citations,
            confidence=confidence,
            follow_up_question=None,
            request_id=request_id or "",
            retrieval_metadata=retrieval_metadata,
        )

    def _extract_retrieval_metadata(self, results: list[SearchResult]) -> list[dict]:
        """Extract metadata from retrieval results for audit logging.

        This extracts only safe metadata, not full content.

        Args:
            results: List of search results.

        Returns:
            List of metadata dictionaries.
        """
        metadata = []
        for r in results:
            metadata.append({
                "manual_name": r.manual_name,
                "page": r.page,
                "chunk_id": r.chunk_id,
                "score": r.score,
                "reranker_score": r.reranker_score,
            })
        return metadata

    def _generate_answer(self, question: str, context: str) -> str:
        """Generate an answer using the LLM.

        Args:
            question: The user's question.
            context: Formatted context from retrieved chunks.

        Returns:
            The generated answer text.
        """
        user_prompt = f"""Based on the following sources, answer the question.

SOURCES:
{context}

QUESTION: {question}

Remember to cite your sources using [Source N] format. If the sources don't contain the answer, say "I don't know based on the available manuals."

ANSWER:"""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = self.openai_client.chat_completion(
            messages=messages,
            temperature=self.temperature,
        )

        return response

    def _generate_answer_with_citation_reminder(
        self,
        question: str,
        context: str,
        previous_answer: str,
    ) -> str:
        """Re-generate answer with explicit citation reminder.

        Args:
            question: The user's question.
            context: Formatted context from retrieved chunks.
            previous_answer: The answer without citations.

        Returns:
            Updated answer with citations.
        """
        user_prompt = f"""Your previous answer did not include citations. Please rewrite it with proper citations.

SOURCES:
{context}

QUESTION: {question}

YOUR PREVIOUS ANSWER (without citations):
{previous_answer}

Please rewrite this answer and add [Source N] citations for each factual claim. Use the source numbers from the SOURCES section above.

ANSWER WITH CITATIONS:"""

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = self.openai_client.chat_completion(
            messages=messages,
            temperature=self.temperature,
        )

        return response

    def _extract_citations(
        self,
        answer: str,
        results: list[SearchResult],
    ) -> list[Citation]:
        """Extract citations from the answer text.

        Args:
            answer: The generated answer with [Source N] markers.
            results: The retrieved search results.

        Returns:
            List of Citation objects.
        """
        # Find all source references in the answer
        source_pattern = r'\[Source\s*(\d+)\]'
        matches = re.findall(source_pattern, answer, re.IGNORECASE)

        # Get unique source numbers
        source_numbers = sorted(set(int(m) for m in matches))

        citations = []
        for source_num in source_numbers:
            # Source numbers are 1-indexed, results are 0-indexed
            idx = source_num - 1
            if 0 <= idx < len(results):
                result = results[idx]
                citation = self.grounding_service.create_citation_from_result(result)
                citations.append(citation)
            else:
                logger.warning(f"Invalid source reference: [Source {source_num}]")

        return citations

    def _clean_answer(self, answer: str) -> str:
        """Clean the answer text for final output.

        Args:
            answer: The raw answer with citation markers.

        Returns:
            Cleaned answer text.
        """
        # Keep the [Source N] markers in the answer for transparency
        # Just clean up any extra whitespace
        return " ".join(answer.split())


_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get or create the RAG service singleton."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
