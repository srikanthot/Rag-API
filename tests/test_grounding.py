"""Tests for grounding and anti-hallucination guardrails."""

import pytest

from app.clients.search_client import SearchResult
from app.models import Citation
from app.services.grounding import GroundingService


class TestGroundingService:
    """Test suite for GroundingService."""

    @pytest.fixture
    def grounding_service(self):
        """Create a grounding service instance for testing."""
        service = GroundingService()
        # Set a known threshold for testing
        service.min_grounded_score = 0.7
        return service

    @pytest.fixture
    def sample_results(self):
        """Create sample search results for testing."""
        return [
            SearchResult(
                id="safety_manual_p12_c1",
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_manual_p12_c1",
                content="In case of fire, immediately evacuate using the nearest exit. Do not use elevators.",
                section_title="Fire Emergency",
                image_caption=None,
                score=0.85,
            ),
            SearchResult(
                id="safety_manual_p15_c1",
                manual_name="Safety_Manual.pdf",
                page=15,
                chunk_id="safety_manual_p15_c1",
                content="Chemical spill response requires immediate action. Alert nearby personnel.",
                section_title="Chemical Spills",
                image_caption=None,
                score=0.75,
            ),
            SearchResult(
                id="operations_guide_p3_c1",
                manual_name="Operations_Guide.pdf",
                page=3,
                chunk_id="operations_guide_p3_c1",
                content="The main control panel is located in the operations center.",
                section_title="Control Panel",
                image_caption="Control panel layout diagram",
                score=0.65,
            ),
        ]

    @pytest.fixture
    def low_score_results(self):
        """Create search results with low scores."""
        return [
            SearchResult(
                id="test_p1_c1",
                manual_name="Test_Manual.pdf",
                page=1,
                chunk_id="test_p1_c1",
                content="Some unrelated content.",
                section_title="Test",
                image_caption=None,
                score=0.45,
            ),
        ]

    def test_check_retrieval_quality_with_good_results(
        self, grounding_service, sample_results
    ):
        """Test that good retrieval results pass grounding check."""
        is_grounded, reason, follow_up = grounding_service.check_retrieval_quality(
            sample_results
        )

        assert is_grounded is True
        assert "relevant chunks found" in reason
        assert follow_up is None

    def test_check_retrieval_quality_with_no_results(self, grounding_service):
        """Test that empty results fail grounding check."""
        is_grounded, reason, follow_up = grounding_service.check_retrieval_quality([])

        assert is_grounded is False
        assert "No relevant content" in reason
        assert follow_up is not None
        assert "manual name" in follow_up.lower() or "details" in follow_up.lower()

    def test_check_retrieval_quality_with_low_scores(
        self, grounding_service, low_score_results
    ):
        """Test that low-score results fail grounding check."""
        is_grounded, reason, follow_up = grounding_service.check_retrieval_quality(
            low_score_results
        )

        assert is_grounded is False
        assert "below threshold" in reason
        assert follow_up is not None

    def test_extract_quote_short_content(self, grounding_service):
        """Test quote extraction for short content."""
        content = "This is a short sentence."
        quote = grounding_service.extract_quote(content)

        assert quote == content

    def test_extract_quote_long_content(self, grounding_service):
        """Test quote extraction truncates long content."""
        content = (
            "This is a very long piece of content that goes on and on. "
            "It contains multiple sentences. Each sentence adds more text. "
            "Eventually it exceeds the maximum quote length. "
            "This part should not appear in the quote."
        )
        quote = grounding_service.extract_quote(content, max_length=100)

        assert len(quote) <= 100
        assert quote.startswith("This is a very long")

    def test_create_citation_from_result(self, grounding_service, sample_results):
        """Test creating a citation from a search result."""
        result = sample_results[0]
        citation = grounding_service.create_citation_from_result(result)

        assert citation.manual_name == "Safety_Manual.pdf"
        assert citation.page == 12
        assert citation.chunk_id == "safety_manual_p12_c1"
        assert len(citation.quote) > 0
        assert "fire" in citation.quote.lower() or "evacuate" in citation.quote.lower()

    def test_validate_citations_all_valid(self, grounding_service, sample_results):
        """Test that valid citations pass validation."""
        citations = [
            Citation(
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_manual_p12_c1",
                quote="In case of fire...",
            ),
            Citation(
                manual_name="Safety_Manual.pdf",
                page=15,
                chunk_id="safety_manual_p15_c1",
                quote="Chemical spill response...",
            ),
        ]

        validated = grounding_service.validate_citations(citations, sample_results)

        assert len(validated) == 2

    def test_validate_citations_removes_invalid(self, grounding_service, sample_results):
        """Test that invalid citations are removed."""
        citations = [
            Citation(
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_manual_p12_c1",
                quote="Valid citation",
            ),
            Citation(
                manual_name="Fake_Manual.pdf",
                page=99,
                chunk_id="fake_chunk_id",
                quote="This citation does not exist in results",
            ),
        ]

        validated = grounding_service.validate_citations(citations, sample_results)

        assert len(validated) == 1
        assert validated[0].chunk_id == "safety_manual_p12_c1"

    def test_determine_confidence_high(self, grounding_service, sample_results):
        """Test high confidence determination."""
        citations = [
            Citation(
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_manual_p12_c1",
                quote="Quote 1",
            ),
            Citation(
                manual_name="Safety_Manual.pdf",
                page=15,
                chunk_id="safety_manual_p15_c1",
                quote="Quote 2",
            ),
        ]

        confidence = grounding_service.determine_confidence(sample_results, citations)

        assert confidence == "high"

    def test_determine_confidence_medium(self, grounding_service, sample_results):
        """Test medium confidence determination."""
        citations = [
            Citation(
                manual_name="Safety_Manual.pdf",
                page=12,
                chunk_id="safety_manual_p12_c1",
                quote="Single citation",
            ),
        ]

        confidence = grounding_service.determine_confidence(sample_results, citations)

        assert confidence == "medium"

    def test_determine_confidence_low_no_citations(self, grounding_service, sample_results):
        """Test low confidence when no citations."""
        confidence = grounding_service.determine_confidence(sample_results, [])

        assert confidence == "low"

    def test_determine_confidence_low_no_results(self, grounding_service):
        """Test low confidence when no results."""
        citations = [
            Citation(
                manual_name="Test.pdf",
                page=1,
                chunk_id="test_c1",
                quote="Test",
            ),
        ]

        confidence = grounding_service.determine_confidence([], citations)

        assert confidence == "low"

    def test_build_no_answer_response(self, grounding_service):
        """Test building a standardized no-answer response."""
        response = grounding_service.build_no_answer_response(
            reason="No relevant content",
            follow_up="Please specify the manual name.",
        )

        assert response["answer"] == GroundingService.NO_ANSWER_RESPONSE
        assert response["citations"] == []
        assert response["confidence"] == "low"
        assert response["follow_up_question"] == "Please specify the manual name."

    def test_no_answer_response_contains_dont_know(self, grounding_service):
        """Test that the no-answer response contains 'I don't know'."""
        response = grounding_service.build_no_answer_response(
            reason="Test reason",
        )

        assert "don't know" in response["answer"].lower()
        assert "manuals" in response["answer"].lower()


class TestAntiHallucination:
    """Test suite specifically for anti-hallucination behavior."""

    @pytest.fixture
    def grounding_service(self):
        """Create a grounding service instance."""
        service = GroundingService()
        service.min_grounded_score = 0.7
        return service

    def test_unanswerable_question_returns_dont_know(self, grounding_service):
        """Test that unanswerable questions return 'I don't know' response."""
        # Empty results simulate no relevant content found
        is_grounded, reason, follow_up = grounding_service.check_retrieval_quality([])

        assert is_grounded is False

        response = grounding_service.build_no_answer_response(reason, follow_up)

        # Verify the response follows the no-hallucination policy
        assert "don't know" in response["answer"].lower()
        assert "manuals" in response["answer"].lower()
        assert response["citations"] == []
        assert response["follow_up_question"] is not None

    def test_low_relevance_returns_dont_know(self, grounding_service):
        """Test that low relevance scores trigger 'I don't know' response."""
        low_score_results = [
            SearchResult(
                id="test_c1",
                manual_name="Test.pdf",
                page=1,
                chunk_id="test_c1",
                content="Unrelated content",
                section_title="Test",
                image_caption=None,
                score=0.3,  # Well below threshold
            ),
        ]

        is_grounded, reason, follow_up = grounding_service.check_retrieval_quality(
            low_score_results
        )

        assert is_grounded is False
        assert "below threshold" in reason

    def test_citation_integrity_prevents_hallucinated_citations(self, grounding_service):
        """Test that hallucinated citations are rejected."""
        # Real retrieved results
        real_results = [
            SearchResult(
                id="real_chunk_1",
                manual_name="Real_Manual.pdf",
                page=1,
                chunk_id="real_chunk_1",
                content="Real content",
                section_title="Real Section",
                image_caption=None,
                score=0.9,
            ),
        ]

        # Hallucinated citations (not in retrieved results)
        hallucinated_citations = [
            Citation(
                manual_name="Fake_Manual.pdf",
                page=999,
                chunk_id="hallucinated_chunk",
                quote="This was never retrieved",
            ),
            Citation(
                manual_name="Another_Fake.pdf",
                page=123,
                chunk_id="another_fake_chunk",
                quote="Also hallucinated",
            ),
        ]

        validated = grounding_service.validate_citations(
            hallucinated_citations, real_results
        )

        # All hallucinated citations should be removed
        assert len(validated) == 0

    def test_mixed_citations_keeps_only_valid(self, grounding_service):
        """Test that mixed valid/invalid citations keeps only valid ones."""
        real_results = [
            SearchResult(
                id="real_chunk_1",
                manual_name="Real_Manual.pdf",
                page=1,
                chunk_id="real_chunk_1",
                content="Real content",
                section_title="Real Section",
                image_caption=None,
                score=0.9,
            ),
        ]

        mixed_citations = [
            Citation(
                manual_name="Real_Manual.pdf",
                page=1,
                chunk_id="real_chunk_1",
                quote="Valid quote from real content",
            ),
            Citation(
                manual_name="Fake_Manual.pdf",
                page=999,
                chunk_id="hallucinated_chunk",
                quote="This was never retrieved",
            ),
        ]

        validated = grounding_service.validate_citations(mixed_citations, real_results)

        assert len(validated) == 1
        assert validated[0].chunk_id == "real_chunk_1"
