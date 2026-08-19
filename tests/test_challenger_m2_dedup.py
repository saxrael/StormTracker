"""Adversarial dynamic verification harness by Challenger 2 for Milestone 2.

Empirically tests false-positive immunity guarantees, user progression safety,
cross-exercise UI isolation, degenerate nonce filtering, and type robustness in
`app/services/fraud_service.py`.
"""

import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.schemas import ExerciseDetail, ExerciseType
from app.services.fraud_service import (
    check_exact_image_duplicate,
    check_metadata_duplicate,
    check_visual_duplicate,
    compute_canonical_content_signature,
    compute_image_hash,
    is_valid_device_metadata,
)


class TestUserProgressionImmunity:
    """Verify that a user improving their score on the same exercise/app UI

    never flags as a duplicate across exact hash, metadata, or visual vector.
    """

    @pytest.mark.asyncio
    async def test_progression_over_time_different_scores_distinct_signatures(
        self,
    ):
        """Simulate a user's multi-day learning curve on 'Intervals'.

        Scores: Day 1 (50%), Day 2 (65%), Day 3 (80%), Day 4 (90%), Day 5
        (100%).
        Verify that all signatures are completely distinct.
        """
        progression_data = [
            {"questions": 20, "correct": 10, "score": 50.0},
            {"questions": 20, "correct": 13, "score": 65.0},
            {"questions": 20, "correct": 16, "score": 80.0},
            {"questions": 20, "correct": 18, "score": 90.0},
            {"questions": 20, "correct": 20, "score": 100.0},
        ]

        signatures = [
            compute_canonical_content_signature(
                exercise_type=ExerciseType.INTERVALS,
                total_questions=p["questions"],
                total_correct=p["correct"],
                overall_score_percentage=p["score"],
            )
            for p in progression_data
        ]

        # All signatures must be mutually unique (collision-free)
        assert len(set(signatures)) == len(progression_data)

    @pytest.mark.asyncio
    async def test_progression_visual_vector_immunity_under_near_identical_ui(
        self, mock_async_session: AsyncMock
    ):
        """Simulate progressive submissions on the exact same UI layout.

        Visual vector similarity is 0.9999 (near identical UI frame), but
        scores differ. Verify that check_visual_duplicate strictly returns
        0.0 because candidates are scoped by exercise_type, total_questions,
        total_correct, and overall_score.
        """
        # Session query returns None because DB query filters on
        # (score=100.0, correct=20) and previous submissions in DB only
        # had (score=50.0, correct=10)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        high_sim_vector = [0.9999] + [0.0] * 2047

        # Candidate is new attempt: 100% (20/20)
        similarity = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_progression",
            new_vector=high_sim_vector,
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=20,
            overall_score_percentage=100.0,
        )

        assert similarity == 0.0
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_progression_metadata_immunity_with_same_practice_time(
        self, mock_async_session: AsyncMock
    ):
        """A dedicated student practices daily at the exact same routine time

        (e.g., "07:30 | 95% battery").
        Since the score and content differ on each day, check_metadata_duplicate
        must return False.
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_routine",
            new_metadata="07:30 | 95% battery",
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=19,
            overall_score_percentage=95.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_same_score_different_mistakes_distribution_distinct_signatures(
        self,
    ):
        """Two attempts both achieve 90% (18/20) on Intervals, but on attempt 1

        the user missed 'Minor 2nd' twice, while on attempt 2 the user missed
        'Major 7th' twice. Verify that canonical content signatures are
        completely distinct.
        """
        attempt_1_details = [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 0,
                "accuracy_percentage": 100.0,
            },
            {
                "item_name": "Minor 2nd",
                "times_heard": 10,
                "times_wrong": 2,
                "accuracy_percentage": 80.0,
            },
        ]
        attempt_2_details = [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 0,
                "accuracy_percentage": 100.0,
            },
            {
                "item_name": "Major 7th",
                "times_heard": 10,
                "times_wrong": 2,
                "accuracy_percentage": 80.0,
            },
        ]

        sig1 = compute_canonical_content_signature(
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
            granular_details=attempt_1_details,
        )
        sig2 = compute_canonical_content_signature(
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
            granular_details=attempt_2_details,
        )

        assert sig1 != sig2
        assert len(sig1) == 64
        assert len(sig2) == 64

    def test_progression_screenshot_bytes_exact_hash_distinct(self):
        """Simulated screenshot bytes produce distinct SHA-256 hashes."""
        screenshot_attempt_1 = b"PNG_HEADER_TONEDEAR_INTERVALS_SCORE_50_ATTEMPT_1"
        screenshot_attempt_2 = b"PNG_HEADER_TONEDEAR_INTERVALS_SCORE_90_ATTEMPT_2"

        hash1 = compute_image_hash(screenshot_attempt_1)
        hash2 = compute_image_hash(screenshot_attempt_2)

        assert hash1 != hash2
        assert hash1 == hashlib.sha256(screenshot_attempt_1).hexdigest()
        assert hash2 == hashlib.sha256(screenshot_attempt_2).hexdigest()


class TestCrossExerciseUIIsolation:
    """Verify that different ear-training exercises on the same mobile UI

    never flag as visual duplicates or metadata duplicates even with high
    visual cosine similarity (e.g. 0.9999).
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tested_exercise",
        [
            ExerciseType.CHORDS,
            ExerciseType.SCALES,
            ExerciseType.CHORD_PROGRESSIONS,
            ExerciseType.PERFECT_PITCH,
            ExerciseType.SCALE_DEGREES,
            ExerciseType.INTERVALS_IN_CONTEXT,
            ExerciseType.MELODIC_DICTATION,
            ExerciseType.UNKNOWN_CUSTOM,
        ],
    )
    async def test_cross_exercise_visual_duplicate_returns_zero(
        self, mock_async_session: AsyncMock, tested_exercise: ExerciseType
    ):
        """When checking a new exercise against a DB with other exercise records

        sharing the same UI frame, check_visual_duplicate MUST return 0.0.
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        high_sim_vector = [0.9995] + [0.0] * 2047

        similarity = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_multi_exercise",
            new_vector=high_sim_vector,
            exercise_type=tested_exercise,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert similarity == 0.0

    @pytest.mark.asyncio
    async def test_cross_exercise_metadata_duplicate_returns_false(
        self, mock_async_session: AsyncMock
    ):
        """User finishes an Intervals exercise at 09:41, switches to Chords

        at 09:41 (same status bar nonce). Metadata duplicate check must
        return False.
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_switching_exercises",
            new_metadata="09:41 | 85% battery",
            exercise_type=ExerciseType.CHORDS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    def test_all_standard_exercise_types_produce_orthogonal_signatures(self):
        """Ensure all 9 standard exercise types produce disjoint signatures

        under identical score/question metrics (20 Q, 18 C, 90.0%).
        """
        all_exercises = list(ExerciseType)
        signatures = {
            ex: compute_canonical_content_signature(
                exercise_type=ex,
                total_questions=20,
                total_correct=18,
                overall_score_percentage=90.0,
            )
            for ex in all_exercises
        }

        assert len(set(signatures.values())) == len(all_exercises)


class TestDegenerateNonceStressMatrix:
    """Exhaustive stress tests verifying that unreadable, missing, or degenerate

    status bar nonces NEVER trigger database queries and NEVER cause false
    rejections.
    """

    DEGENERATE_VARIANTS = [
        None,
        "",
        " ",
        "   ",
        "\t",
        "\n",
        "\r\n",
        " \t \n ",
        # Standard keywords
        "n/a",
        "N/A",
        "na",
        "NA",
        "Na",
        "n/A",
        "none",
        "NONE",
        "None",
        "null",
        "NULL",
        "Null",
        "unknown",
        "UNKNOWN",
        "Unknown",
        "undefined",
        "UNDEFINED",
        "Undefined",
        # Compound formats
        "N/A | 85% battery",
        "10:15 | N/A",
        "N/A | N/A",
        "n/a | 50%",
        "12:00 | na",
        "N/A |",
        "| N/A",
        "N/A|N/A",
        "  N/A | N/A  ",
        "na | na",
        "NONE | NONE",
        "unknown | 100% battery",
        "10:00 | undefined",
        "N/A; 80% battery",
        "unknown, 75% battery",
        # Non-string data types
        12345,
        0,
        -1,
        99.9,
        True,
        False,
        [],
        ["N/A"],
        {},
        {"metadata": "N/A"},
        object(),
    ]

    @pytest.mark.parametrize("nonce", DEGENERATE_VARIANTS)
    def test_is_valid_device_metadata_rejects_all_degenerate_variants(self, nonce):
        """Verify is_valid_device_metadata returns False for degenerate nonces."""
        assert is_valid_device_metadata(nonce) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("nonce", DEGENERATE_VARIANTS)
    async def test_check_metadata_duplicate_short_circuits_with_zero_db_queries(
        self, mock_async_session: AsyncMock, nonce
    ):
        """Verify check_metadata_duplicate returns False immediately with 0 DB queries

        when given any degenerate nonce.
        """
        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_nonce_test",
            new_metadata=nonce,  # type: ignore
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.parametrize(
        "valid_nonce",
        [
            "09:41 | 85% battery",
            "10:15",
            "9:41 AM 100%",
            "14:20 | 100%",
            "8:00 AM | 50% battery",
            "12:30 PM | 99%",
            "23:59 | 1% battery",
            "11:11 | 45%",
            "  10:15 | 85% battery  ",
            "7:05 PM",
            "00:00 | 100% battery",
        ],
    )
    def test_is_valid_device_metadata_accepts_valid_nonces(self, valid_nonce: str):
        """Ensure genuine status bar nonces are correctly recognized as valid."""
        assert is_valid_device_metadata(valid_nonce) is True


class TestTypeRobustnessAndFloatResilience:
    """Verify that type coercions (int, float, str, Enum, Pydantic) and floating-point

    precision quirks are handled robustly without runtime exceptions.
    """

    def test_float_precision_jitter_canonical_signature(self):
        """Floating point inaccuracies (e.g. 90.00000000000001 vs 90.0)

        must produce identical canonical content signatures via round(val, 2).
        """
        sig_exact = compute_canonical_content_signature("Intervals", 20, 18, 90.0)
        sig_jitter1 = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.00000000000001
        )
        sig_jitter2 = compute_canonical_content_signature(
            "Intervals", 20, 18, 89.99999999999999
        )
        sig_str_float = compute_canonical_content_signature(
            "Intervals", 20, 18, "90.00"
        )

        assert sig_exact == sig_jitter1 == sig_jitter2 == sig_str_float

    def test_int_and_float_coercion_for_counts(self):
        """Question counts and correct counts passed as int, float, or string."""
        sig_int = compute_canonical_content_signature("Intervals", 20, 18, 90.0)
        sig_float = compute_canonical_content_signature("Intervals", 20.0, 18.0, 90.0)
        sig_str = compute_canonical_content_signature("Intervals", "20", "18", 90.0)

        assert sig_int == sig_float == sig_str

    @pytest.mark.asyncio
    async def test_check_visual_duplicate_type_flexibility(
        self, mock_async_session: AsyncMock
    ):
        """Verify check_visual_duplicate accepts float, int, str, and Enum types

        without crashing.
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 0.95
        mock_async_session.execute.return_value = mock_result

        test_vector = [0.5] * 2048

        # Test with string numbers and Enum
        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_type_flex",
            new_vector=test_vector,
            exercise_type=ExerciseType.INTERVALS,
            total_questions="20",
            total_correct="18",
            overall_score_percentage="90.0",
        )

        assert result == 0.95
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_metadata_duplicate_type_flexibility(
        self, mock_async_session: AsyncMock
    ):
        """Verify check_metadata_duplicate accepts various types for metrics."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_type_flex",
            new_metadata="10:15 | 80% battery",
            exercise_type="Intervals",
            total_questions=20.0,
            total_correct=18.0,
            overall_score_percentage=90,
        )

        assert result is True
        mock_async_session.execute.assert_awaited_once()

    def test_granular_details_nested_structure_resilience(self):
        """Verify handling of deeply nested, JSON string, Pydantic objects,

        and empty variations in granular details.
        """
        # Pydantic detail
        pydantic_obj = ExerciseDetail(
            item_name="Major 3rd",
            times_heard=10,
            times_wrong=1,
            accuracy_percentage=90.0,
        )
        sig_pydantic = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, [pydantic_obj]
        )

        # Plain dict
        dict_obj = {
            "item_name": "Major 3rd",
            "times_heard": 10,
            "times_wrong": 1,
            "accuracy_percentage": 90.0,
        }
        sig_dict = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, [dict_obj]
        )

        # JSON encoded string of list of dict
        json_str = json.dumps([dict_obj])
        sig_json = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, json_str
        )

        assert sig_pydantic == sig_dict == sig_json

    def test_image_payload_base64_and_data_uri_robustness(self):
        """Verify byte hashing handles various base64 encodings, padding quirks,

        and data URI prefixes.
        """
        import base64

        raw_bytes = b"TEST_IMAGE_PAYLOAD_FOR_HASH_ROBUSTNESS"
        expected_hash = hashlib.sha256(raw_bytes).hexdigest()

        clean_b64 = base64.b64encode(raw_bytes).decode("ascii")
        data_uri_b64 = f"data:image/png;base64,{clean_b64}"
        unpadded_b64 = clean_b64.rstrip("=")

        assert compute_image_hash(raw_bytes) == expected_hash
        assert compute_image_hash(clean_b64) == expected_hash
        assert compute_image_hash(data_uri_b64) == expected_hash
        assert compute_image_hash(unpadded_b64) == expected_hash


class TestTruePositiveFraudDetection:
    """Verify that genuine duplicate submissions (re-uploads, identical retakes)

    are accurately caught across all 3 layers.
    """

    @pytest.mark.asyncio
    async def test_exact_duplicate_screenshot_caught_instantly(
        self, mock_async_session: AsyncMock
    ):
        """Layer 1: Identical image payload hash matches existing DB record -> True."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        test_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        is_dup = await check_exact_image_duplicate(mock_async_session, test_hash)

        assert is_dup is True
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_identical_metadata_and_signature_within_24h_caught(
        self, mock_async_session: AsyncMock
    ):
        """Layer 2: Valid metadata within 24h + identical signature -> True."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        is_dup = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_fraudster",
            new_metadata="09:41 | 85% battery",
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert is_dup is True
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_matching_visual_vector_and_metrics_caught(
        self, mock_async_session: AsyncMock
    ):
        """Layer 3: Visual similarity > 0.99 with matching metrics -> True."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 0.998
        mock_async_session.execute.return_value = mock_result

        vector = [0.999] + [0.0] * 2047

        similarity = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_fraudster",
            new_vector=vector,
            exercise_type=ExerciseType.INTERVALS,
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert similarity == 0.998
        assert similarity >= 0.99
