"""Tests for citation extraction and integrity."""

import pytest

from app.clients.search_client import SearchResult
from app.models import Citation, ChatRequest, ChatResponse
from app.services.grounding import GroundingService


class TestCitationExtraction:
    """Test suite for citation extraction functionality."""

    @pytest.fixture
    def grounding_service(self):
        """Create a grounding service instance."""
        return GroundingService()

    @pytest.fixture
    def sample_results(self):
        """Create sample search results for testing."""
        return [
            SearchResult(
                id="safety_manual_p12_c1",
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_manual_p12_c1",
                content="In case of fire, immediately evacuate using the nearest exit. Do not use elevators during a fire emergency. Proceed to the assembly point.",
                section_title="Fire Emergency Procedures",
                image_caption=None,
                score=0.92,
            ),
            SearchResult(
                id="safety_manual_p15_c1",
                manual_name="Safety_Manual.pdf",
                page=15,
                chunk_id="safety_manual_p15_c1",
                content="Chemical spill response requires immediate action. First, alert nearby personnel and evacuate the immediate area. Contact the safety coordinator.",
                section_title="Chemical Spill Response",
                image_caption=None,
                score=0.85,
            ),
            SearchResult(
                id="operations_guide_p8_c1",
                manual_name="Operations_Guide.pdf",
                page=8,
                chunk_id="operations_guide_p8_c1",
                content="Daily startup procedures must be followed in the correct sequence. Begin by verifying all safety interlocks are engaged.",
                section_title="Daily Startup Procedures",
                image_caption=None,
                score=0.78,
            ),
        ]

    def test_create_citation_includes_all_required_fields(
        self, grounding_service, sample_results
    ):
        """Test that created citations include all required fields."""
        result = sample_results[0]
        citation = grounding_service.create_citation_from_result(result)

        # Verify all required fields are present
        assert citation.manual_name is not None
        assert citation.page is not None
        assert citation.chunk_id is not None
        assert citation.quote is not None

        # Verify values match the source
        assert citation.manual_name == "Safety_Manual.pdf"
        assert citation.page == 12
        assert citation.chunk_id == "safety_manual_p12_c1"

    def test_citation_quote_is_from_content(self, grounding_service, sample_results):
        """Test that citation quote is extracted from actual content."""
        result = sample_results[0]
        citation = grounding_service.create_citation_from_result(result)

        # Quote should be a substring or summary of the content
        # At minimum, it should contain words from the original content
        content_words = set(result.content.lower().split())
        quote_words = set(citation.quote.lower().split())

        # There should be significant overlap
        overlap = content_words & quote_words
        assert len(overlap) > 0, "Quote should contain words from the original content"

    def test_citation_quote_length_is_reasonable(self, grounding_service, sample_results):
        """Test that citation quotes are not too long."""
        for result in sample_results:
            citation = grounding_service.create_citation_from_result(result)

            # Quote should be reasonably short (1-2 lines)
            assert len(citation.quote) <= 500, "Quote should be concise"
            assert len(citation.quote) > 0, "Quote should not be empty"

    def test_validate_citations_preserves_order(self, grounding_service, sample_results):
        """Test that citation validation preserves the order of valid citations."""
        citations = [
            Citation(
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_manual_p12_c1",
                quote="First citation",
            ),
            Citation(
                manual_name="Safety_Manual.pdf",
                page=15,
                chunk_id="safety_manual_p15_c1",
                quote="Second citation",
            ),
            Citation(
                manual_name="Operations_Guide.pdf",
                page=8,
                chunk_id="operations_guide_p8_c1",
                quote="Third citation",
            ),
        ]

        validated = grounding_service.validate_citations(citations, sample_results)

        assert len(validated) == 3
        assert validated[0].chunk_id == "safety_manual_p12_c1"
        assert validated[1].chunk_id == "safety_manual_p15_c1"
        assert validated[2].chunk_id == "operations_guide_p8_c1"

    def test_validate_citations_handles_empty_input(self, grounding_service, sample_results):
        """Test that validation handles empty citation list."""
        validated = grounding_service.validate_citations([], sample_results)
        assert validated == []

    def test_validate_citations_handles_empty_results(self, grounding_service):
        """Test that validation handles empty results list."""
        citations = [
            Citation(
                manual_name="Test.pdf",
                page=1,
                chunk_id="test_c1",
                quote="Test quote",
            ),
        ]

        validated = grounding_service.validate_citations(citations, [])
        assert validated == []


class TestCitationIntegrity:
    """Test suite for citation integrity - ensuring citations match retrieved content."""

    @pytest.fixture
    def grounding_service(self):
        """Create a grounding service instance."""
        return GroundingService()

    @pytest.fixture
    def retrieved_results(self):
        """Create a set of retrieved results to validate against."""
        return [
            SearchResult(
                id="manual_a_p1_c1",
                manual_name="Manual_A.pdf",
                page=1,
                chunk_id="manual_a_p1_c1",
                content="Content from Manual A page 1.",
                section_title="Section A1",
                image_caption=None,
                score=0.9,
            ),
            SearchResult(
                id="manual_b_p5_c2",
                manual_name="Manual_B.pdf",
                page=5,
                chunk_id="manual_b_p5_c2",
                content="Content from Manual B page 5.",
                section_title="Section B5",
                image_caption=None,
                score=0.85,
            ),
        ]

    def test_citation_must_match_retrieved_chunk_id(
        self, grounding_service, retrieved_results
    ):
        """Test that citations must have chunk_id matching retrieved results."""
        # Valid citation - chunk_id exists in retrieved results
        valid_citation = Citation(
            manual_name="Manual_A.pdf",
            page=1,
            chunk_id="manual_a_p1_c1",
            quote="Content from Manual A",
        )

        # Invalid citation - chunk_id does not exist
        invalid_citation = Citation(
            manual_name="Manual_A.pdf",
            page=1,
            chunk_id="nonexistent_chunk",
            quote="Made up content",
        )

        validated = grounding_service.validate_citations(
            [valid_citation, invalid_citation], retrieved_results
        )

        assert len(validated) == 1
        assert validated[0].chunk_id == "manual_a_p1_c1"

    def test_citation_with_wrong_manual_name_but_valid_chunk_id(
        self, grounding_service, retrieved_results
    ):
        """Test that chunk_id is the primary validation key, not manual_name."""
        # Citation with mismatched manual_name but valid chunk_id
        # This tests that we validate by chunk_id, not by manual_name
        citation = Citation(
            manual_name="Wrong_Manual.pdf",  # Wrong name
            page=999,  # Wrong page
            chunk_id="manual_a_p1_c1",  # But valid chunk_id
            quote="Some quote",
        )

        validated = grounding_service.validate_citations([citation], retrieved_results)

        # Should still be valid because chunk_id matches
        assert len(validated) == 1

    def test_all_citations_must_be_from_retrieval(
        self, grounding_service, retrieved_results
    ):
        """Test that every citation must correspond to a retrieved chunk."""
        citations = [
            Citation(
                manual_name="Manual_A.pdf",
                page=1,
                chunk_id="manual_a_p1_c1",
                quote="Valid",
            ),
            Citation(
                manual_name="Manual_B.pdf",
                page=5,
                chunk_id="manual_b_p5_c2",
                quote="Valid",
            ),
            Citation(
                manual_name="Manual_C.pdf",
                page=10,
                chunk_id="manual_c_p10_c1",  # Not in retrieved results
                quote="Invalid - not retrieved",
            ),
        ]

        validated = grounding_service.validate_citations(citations, retrieved_results)

        assert len(validated) == 2
        valid_chunk_ids = {c.chunk_id for c in validated}
        assert "manual_a_p1_c1" in valid_chunk_ids
        assert "manual_b_p5_c2" in valid_chunk_ids
        assert "manual_c_p10_c1" not in valid_chunk_ids


class TestChatResponseCitations:
    """Test suite for ChatResponse citation requirements."""

    def test_chat_response_requires_citations_list(self):
        """Test that ChatResponse has a citations field."""
        response = ChatResponse(
            answer="Test answer",
            citations=[],
            confidence="medium",
            follow_up_question=None,
        )

        assert hasattr(response, "citations")
        assert isinstance(response.citations, list)

    def test_chat_response_with_valid_citations(self):
        """Test creating a ChatResponse with valid citations."""
        citations = [
            Citation(
                manual_name="Test_Manual.pdf",
                page=1,
                chunk_id="test_p1_c1",
                quote="Test quote from the manual.",
            ),
        ]

        response = ChatResponse(
            answer="Based on the manual [Source 1], the answer is...",
            citations=citations,
            confidence="high",
            follow_up_question=None,
        )

        assert len(response.citations) == 1
        assert response.citations[0].manual_name == "Test_Manual.pdf"
        assert response.citations[0].page == 1

    def test_citation_model_validation(self):
        """Test that Citation model validates required fields."""
        # Valid citation
        citation = Citation(
            manual_name="Manual.pdf",
            page=5,
            chunk_id="manual_p5_c1",
            quote="A short quote.",
        )

        assert citation.manual_name == "Manual.pdf"
        assert citation.page == 5
        assert citation.chunk_id == "manual_p5_c1"
        assert citation.quote == "A short quote."

    def test_citation_quote_max_length(self):
        """Test that citation quote respects max length."""
        # The model should accept quotes up to 500 characters
        long_quote = "x" * 500

        citation = Citation(
            manual_name="Manual.pdf",
            page=1,
            chunk_id="test_c1",
            quote=long_quote,
        )

        assert len(citation.quote) == 500


class TestNoHallucinationPolicy:
    """Test suite verifying the no-hallucination policy for citations."""

    @pytest.fixture
    def grounding_service(self):
        """Create a grounding service instance."""
        service = GroundingService()
        service.min_grounded_score = 0.7
        return service

    def test_answerable_question_has_citations(self, grounding_service):
        """Test that answerable questions produce citations from retrieval."""
        # Simulate good retrieval results
        results = [
            SearchResult(
                id="safety_p12_c1",
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_p12_c1",
                content="Fire evacuation procedures require all employees to exit immediately.",
                section_title="Fire Safety",
                image_caption=None,
                score=0.92,
            ),
        ]

        # Check grounding passes
        is_grounded, _, _ = grounding_service.check_retrieval_quality(results)
        assert is_grounded is True

        # Create citation from result
        citation = grounding_service.create_citation_from_result(results[0])

        # Verify citation exists in retrieval
        validated = grounding_service.validate_citations([citation], results)
        assert len(validated) == 1
        assert validated[0].chunk_id == "safety_p12_c1"

    def test_unanswerable_question_has_no_citations(self, grounding_service):
        """Test that unanswerable questions return empty citations."""
        # No results = unanswerable
        is_grounded, reason, follow_up = grounding_service.check_retrieval_quality([])

        assert is_grounded is False

        response = grounding_service.build_no_answer_response(reason, follow_up)

        # Verify no citations
        assert response["citations"] == []
        assert "don't know" in response["answer"].lower()

    def test_citations_cannot_be_invented(self, grounding_service):
        """Test that invented citations are rejected."""
        # Real retrieval results
        real_results = [
            SearchResult(
                id="real_chunk",
                manual_name="Real_Manual.pdf",
                page=1,
                chunk_id="real_chunk",
                content="Real content",
                section_title="Real Section",
                image_caption=None,
                score=0.9,
            ),
        ]

        # Invented citations (not from retrieval)
        invented_citations = [
            Citation(
                manual_name="Invented_Manual.pdf",
                page=999,
                chunk_id="invented_chunk_1",
                quote="This manual doesn't exist",
            ),
            Citation(
                manual_name="Another_Fake.pdf",
                page=123,
                chunk_id="invented_chunk_2",
                quote="Also invented",
            ),
        ]

        # Validation should reject all invented citations
        validated = grounding_service.validate_citations(invented_citations, real_results)

        assert len(validated) == 0, "Invented citations must be rejected"
