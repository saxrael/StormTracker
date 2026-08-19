"""Comprehensive unit tests for conjunctive fraud service queries."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.schemas import ExerciseType
from app.services.fraud_service import (
    check_exact_image_duplicate,
    check_metadata_duplicate,
    check_visual_duplicate,
    compute_canonical_content_signature,
)


class TestCheckExactImageDuplicate:
    """Tests for Layer 1 exact image SHA-256 hash deduplication query."""

    @pytest.mark.asyncio
    async def test_exact_image_duplicate_found(self, mock_async_session: AsyncMock):
        """Test returns True when an identical image hash already exists in DB."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        test_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        result = await check_exact_image_duplicate(mock_async_session, test_hash)

        assert result is True
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exact_image_duplicate_not_found(self, mock_async_session: AsyncMock):
        """Test returns False when the image hash does not exist in DB."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        test_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        result = await check_exact_image_duplicate(mock_async_session, test_hash)

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("empty_hash", ["", "   ", None, 12345, [], {}])
    async def test_exact_image_duplicate_empty_or_none_hash(
        self, mock_async_session: AsyncMock, empty_hash
    ):
        """Test empty, None, or non-string hash returns False without DB query."""
        result = await check_exact_image_duplicate(mock_async_session, empty_hash)
        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_exact_image_duplicate_query_ast(self, mock_async_session: AsyncMock):
        """Test that query selects Metric.id and filters on Metric.image_hash."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        test_hash = "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff"
        await check_exact_image_duplicate(mock_async_session, test_hash)

        call_args = mock_async_session.execute.call_args
        assert call_args is not None
        stmt = call_args[0][0]
        assert stmt is not None


class TestCheckMetadataDuplicateShortCircuit:
    """Tests for Layer 2 metadata guard phase (short-circuit with 0 DB queries)."""

    @pytest.mark.asyncio
    async def test_metadata_duplicate_none_short_circuits(
        self, mock_async_session: AsyncMock
    ):
        """Test None device metadata returns False immediately without DB query."""
        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata=None,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "empty_metadata",
        [
            "",
            "   ",
            "\t\n  ",
            "\r\n",
        ],
    )
    async def test_metadata_duplicate_empty_string_short_circuits(
        self, mock_async_session: AsyncMock, empty_metadata: str
    ):
        """Test empty/whitespace metadata returns False immediately without DB query."""
        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata=empty_metadata,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "degenerate_token",
        [
            "N/A",
            "n/a",
            "Na",
            "na",
            "none",
            "NONE",
            "null",
            "NULL",
            "unknown",
            "UNKNOWN",
            "undefined",
            "UNDEFINED",
            "  N/A  ",
            "  none  ",
        ],
    )
    async def test_metadata_duplicate_degenerate_tokens_short_circuits(
        self, mock_async_session: AsyncMock, degenerate_token: str
    ):
        """Test degenerate metadata tokens return False with 0 DB queries."""
        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata=degenerate_token,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "compound_degenerate",
        [
            "N/A | 85% battery",
            "10:15 | N/A",
            "N/A | N/A",
            "n/a | 50%",
            "12:00 | na",
            "N/A |",
            "| N/A",
            "N/A|N/A",
            "  N/A | N/A  ",
        ],
    )
    async def test_metadata_duplicate_compound_degenerate_short_circuits(
        self, mock_async_session: AsyncMock, compound_degenerate: str
    ):
        """Test compound status bars containing 'N/A' return False with 0 DB queries."""
        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata=compound_degenerate,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("non_string", [12345, 99.9, [], {}, object()])
    async def test_metadata_duplicate_non_string_short_circuits(
        self, mock_async_session: AsyncMock, non_string
    ):
        """Test non-string inputs safely return False without DB queries."""
        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata=non_string,  # type: ignore
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_not_called()


class TestCheckMetadataDuplicateConjunctiveMatching:
    """Tests for Layer 2 conjunctive metadata and content breakdown DB queries."""

    @pytest.mark.asyncio
    async def test_metadata_duplicate_identical_valid_within_24h_matching_metrics(
        self, mock_async_session: AsyncMock, sample_intervals_details: list[dict]
    ):
        """Test returns True on valid metadata within 24h with matching metrics."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
            granular_details=sample_intervals_details,
        )

        assert result is True
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_matching_metadata_differing_exercise_type(
        self, mock_async_session: AsyncMock
    ):
        """Test returns False when metadata matches but exercise_type differs."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Chords",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_matching_metadata_differing_score(
        self, mock_async_session: AsyncMock
    ):
        """Test returns False when metadata matches but score differs."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=15,
            overall_score_percentage=75.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_matching_metadata_differing_question_counts(
        self, mock_async_session: AsyncMock
    ):
        """Test returns False when question counts differ (e.g. 10 vs 20)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=10,
            total_correct=9,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_matching_metadata_differing_total_correct(
        self, mock_async_session: AsyncMock
    ):
        """Test returns False when total_correct differs."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=17,
            overall_score_percentage=85.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_matching_metadata_differing_granular_details(
        self, mock_async_session: AsyncMock
    ):
        """Test returns False when mistake distribution in granular details differs."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        details_different_mistakes = [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 2,
                "accuracy_percentage": 80.0,
            },
            {
                "item_name": "Minor 2nd",
                "times_heard": 10,
                "times_wrong": 0,
                "accuracy_percentage": 100.0,
            },
        ]

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
            granular_details=details_different_mistakes,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_submission_older_than_24h(
        self, mock_async_session: AsyncMock
    ):
        """Test returns False when matching metadata/exercise submission is >24h old."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_with_explicit_breakdown_signature(
        self, mock_async_session: AsyncMock
    ):
        """Test passing explicit breakdown_signature executes successfully."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        sig = compute_canonical_content_signature("Intervals", 20, 18, 90.0)

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
            breakdown_signature=sig,
        )

        assert result is True
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_handles_enum_exercise_type(
        self, mock_async_session: AsyncMock
    ):
        """Test passing ExerciseType Enum is handled smoothly."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is True
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_duplicate_query_ast_verification(
        self, mock_async_session: AsyncMock
    ):
        """Test that query joins Submission and applies conjunctive predicates."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        call_args = mock_async_session.execute.call_args
        assert call_args is not None
        stmt = call_args[0][0]
        assert stmt is not None


class TestCheckVisualDuplicateConjunctiveScoping:
    """Tests for Layer 3 visual vector matching scoped by exercise and score."""

    @pytest.mark.asyncio
    async def test_visual_duplicate_matching_exercise_and_score(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns high similarity when candidate matches exercise and score."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 0.995
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result == 0.995
        assert isinstance(result, float)
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_visual_duplicate_differing_exercise_type_returns_zero(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns 0.0 when candidate records have different exercise_type."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result == 0.0
        assert isinstance(result, float)
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_visual_duplicate_differing_score_returns_zero(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns 0.0 when candidate records have different score."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=15,
            overall_score_percentage=75.0,
        )

        assert result == 0.0
        assert isinstance(result, float)
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_visual_duplicate_differing_question_counts_returns_zero(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns 0.0 when candidate records have different total_questions."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=10,
            total_correct=9,
            overall_score_percentage=90.0,
        )

        assert result == 0.0
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_visual_duplicate_differing_total_correct_returns_zero(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns 0.0 when candidate records have different total_correct."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=17,
            overall_score_percentage=85.0,
        )

        assert result == 0.0
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_visual_duplicate_empty_database_table_returns_zero(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns 0.0 when metrics table is empty."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result == 0.0
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_visual_duplicate_low_similarity_matching_metrics(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns moderate/low similarity when visual content differs."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 0.42
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result == 0.42
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_visual_duplicate_exact_1_0_similarity(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test returns 1.0 for identical visual vector embeddings."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 1.0
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result == 1.0
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_visual_duplicate_handles_enum_exercise_type(
        self, mock_async_session: AsyncMock, sample_image_vector_a: list[float]
    ):
        """Test handles ExerciseType Enum seamlessly."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 0.995
        mock_async_session.execute.return_value = mock_result

        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=sample_image_vector_a,
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result == 0.995
        assert isinstance(result, float)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("empty_vector", [[], None])
    async def test_visual_duplicate_empty_vector_returns_zero(
        self, mock_async_session: AsyncMock, empty_vector
    ):
        """Test empty or None vector immediately returns 0.0 without querying DB."""
        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_123",
            new_vector=empty_vector,  # type: ignore
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )
        assert result == 0.0
        mock_async_session.execute.assert_not_called()
