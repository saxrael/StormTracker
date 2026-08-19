"""Adversarial stress test suite for Milestone 2 fraud service.

Challenger 1 Empirical Stress Harness:
1. Exact image duplicate fuzzing & boundary tests (None, empty, malformed,
   valid hex, SQL injection payloads, fuzz inputs).
2. Metadata duplicate stress tests (degenerate nonces, compound tokens,
   24h boundary edge cases: 23h59m vs 24h01m, identical status bar with
   different vs identical exercises).
3. Visual duplicate scoping stress tests (exercise type matching/non-matching,
   score matching/non-matching, question count mismatch, vector edge cases).
4. Property-based randomized fuzzing across all 3 layers.
"""

import hashlib
import random
import string
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.sql.elements import BinaryExpression

from app.services.fraud_service import (
    check_exact_image_duplicate,
    check_metadata_duplicate,
    check_visual_duplicate,
    compute_canonical_content_signature,
    compute_image_hash,
    is_valid_device_metadata,
)


class TestExactImageDuplicateAdversarial:
    """Adversarial testing for exact image deduplication and SHA-256 hashing."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "falsy_or_malformed",
        [
            None,
            "",
            " ",
            "   ",
            "\t\n\r\n",
            12345,
            0,
            -1,
            3.14159,
            [],
            [1, 2, 3],
            {},
            {"hash": "abc"},
            object(),
            True,
            False,
        ],
    )
    async def test_exact_image_duplicate_non_strings_and_empty_short_circuits(
        self, mock_async_session: AsyncMock, falsy_or_malformed
    ):
        """Verify that any non-string or blank input returns False with 0 DB queries."""
        result = await check_exact_image_duplicate(
            mock_async_session, falsy_or_malformed
        )
        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "adversarial_string",
        [
            "'; DROP TABLE metrics; --",
            "' OR '1'='1",
            "SELECT * FROM users",
            "<script>alert('xss')</script>",
            "🚀🔥💥🎉",
            "日本語テスト",
            "A" * 10000,
            "\x00\x01\x02\x03\xff",
            "!@#$%^&*()_+=-~`[]{};:'\",.<>?/\\|",
            "not_a_valid_hex_digest_at_all",
        ],
    )
    async def test_exact_image_duplicate_malformed_strings_execute_safely(
        self, mock_async_session: AsyncMock, adversarial_string: str
    ):
        """Verify malformed or adversarial string queries execute safely via SQL."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_exact_image_duplicate(
            mock_async_session, adversarial_string
        )
        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exact_image_duplicate_valid_hex_with_whitespace_stripping(
        self, mock_async_session: AsyncMock
    ):
        """Verify whitespace around valid hex digest is properly trimmed."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        raw_hex = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        padded_hex = f"  \t\n  {raw_hex}  \r\n "

        result = await check_exact_image_duplicate(mock_async_session, padded_hex)
        assert result is True

        stmt = mock_async_session.execute.call_args[0][0]
        # Inspect compiled where clause
        where_clause = stmt._where_criteria[0]
        assert isinstance(where_clause, BinaryExpression)
        assert where_clause.right.value == raw_hex

    def test_compute_image_hash_property_and_fuzz(self):
        """Fuzz compute_image_hash with random byte streams and bad base64."""
        # 1. Byte hashing determinism
        for _ in range(50):
            payload_len = random.randint(1, 4096)
            data = random.randbytes(payload_len)
            expected = hashlib.sha256(data).hexdigest()
            assert compute_image_hash(data) == expected

        # 2. Corrupted base64 handling
        bad_base64_inputs = [
            "data:image/png;base64,invalid!!!base64===",
            "data:image/jpeg;base64,???",
            "not_valid_b64",
            "data:image/png;base64,",
        ]
        for b64 in bad_base64_inputs:
            h = compute_image_hash(b64)
            assert isinstance(h, str)
            assert len(h) == 64


class TestMetadataDuplicateAdversarial:
    """Adversarial testing for metadata deduplication and boundaries."""

    @pytest.mark.parametrize(
        "degenerate_input",
        [
            "N/A",
            "n/a",
            "Na",
            "na",
            "NA",
            "none",
            "None",
            "NONE",
            "  none  ",
            "null",
            "NULL",
            "Null",
            "unknown",
            "UNKNOWN",
            "Unknown",
            "undefined",
            "UNDEFINED",
            "  N/A  ",
            " \t n/a \n ",
            # Compound formats
            "N/A | 85% battery",
            "85% battery | N/A",
            "10:15 | N/A",
            "10:15 | na",
            "10:15 | none",
            "10:15 | unknown",
            "10:15 | undefined",
            "N/A | N/A",
            "na | na",
            "none | none",
            "n/a | 50% battery",
            "10:15; na; 90%",
            "10:15, na, 90%",
            "09:41 | na battery",
            "09:41 | NULL",
            "09:41 | Unknown",
            "N/A | 100%",
            "  na  |  80%  ",
        ],
    )
    def test_is_valid_device_metadata_catches_all_degenerate_variants(
        self, degenerate_input: str
    ):
        """Verify is_valid_device_metadata rejects every degenerate variant."""
        assert is_valid_device_metadata(degenerate_input) is False

    @pytest.mark.parametrize(
        "valid_input",
        [
            "09:41 | 85% battery",
            "10:15",
            "23:59 | 100% battery",
            "00:00",
            "12:30 PM",
            "9:41 AM | 42%",
            "14:20:05",
            "iPhone 15 Pro | 09:41",
            "Status: 11:11",
        ],
    )
    def test_is_valid_device_metadata_accepts_legitimate_nonces(self, valid_input: str):
        """Verify is_valid_device_metadata accepts genuine status bar nonces."""
        assert is_valid_device_metadata(valid_input) is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "degenerate_nonce",
        [
            "N/A",
            "na",
            "  none  ",
            "UNKNOWN",
            "n/a | 85% battery",
            "10:15 | N/A",
            "undefined",
            None,
            "",
            "   ",
        ],
    )
    async def test_check_metadata_duplicate_degenerate_nonces_zero_queries(
        self, mock_async_session: AsyncMock, degenerate_nonce
    ):
        """Verify degenerate nonces return False with 0 DB queries."""
        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_test",
            new_metadata=degenerate_nonce,
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )
        assert result is False
        mock_async_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_metadata_duplicate_identical_status_bar_different_exercises(
        self, mock_async_session: AsyncMock
    ):
        """Challenge: Identical status bar time with DIFFERENT exercise -> False.

        Simulates candidate in DB with 'Intervals' 20/18, user submits 'Chords'.
        """
        # When DB queries for 'Chords', no row matches
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_test",
            new_metadata="09:41 | 85% battery",
            exercise_type="Chords",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is False
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_metadata_duplicate_identical_status_bar_identical_exercise(
        self, mock_async_session: AsyncMock
    ):
        """Challenge: Identical status bar time with IDENTICAL exercise -> True."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_async_session.execute.return_value = mock_result

        result = await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_test",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )

        assert result is True
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_check_metadata_duplicate_24h_boundary_conditions(
        self, mock_async_session: AsyncMock
    ):
        """Challenge: 24h boundary edge cases (23h59m vs 24h01m).

        Verifies the constructed SQL query applies `Submission.created_at >= cutoff`
        where cutoff is exactly (now - 24 hours).
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        now_before = datetime.now(UTC)
        await check_metadata_duplicate(
            session=mock_async_session,
            db_user_id="user_test",
            new_metadata="09:41 | 85% battery",
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )
        now_after = datetime.now(UTC)

        stmt = mock_async_session.execute.call_args[0][0]
        where_clauses = stmt._where_criteria

        # Find the cutoff clause on Submission.created_at
        created_at_clause = None
        for clause in where_clauses:
            if (
                hasattr(clause, "left")
                and getattr(clause.left, "name", None) == "created_at"
            ):
                created_at_clause = clause
                break

        assert created_at_clause is not None
        # Check that the cutoff value is within 24h +/- 2 seconds
        cutoff_val = created_at_clause.right.value
        expected_cutoff_lower = now_before - timedelta(hours=24, seconds=2)
        expected_cutoff_upper = now_after - timedelta(hours=24, seconds=-2)
        assert expected_cutoff_lower <= cutoff_val <= expected_cutoff_upper

        # Dynamic simulation:
        # 23h59m ago submission created_at > cutoff (PASSES -> duplicate if matched)
        sub_23h59m = datetime.now(UTC) - timedelta(hours=23, minutes=59)
        assert sub_23h59m >= cutoff_val, "23h59m submission must be >= cutoff"

        # 24h01m ago submission created_at < cutoff (FAILS filter -> NOT duplicate)
        sub_24h01m = datetime.now(UTC) - timedelta(hours=24, minutes=1)
        assert sub_24h01m < cutoff_val, "24h01m submission must be < cutoff"


class TestVisualDuplicateAdversarial:
    """Adversarial testing for visual vector similarity scoping and edge cases."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "mismatched_field,candidate_val",
        [
            ("exercise_type", "Chords"),
            ("total_questions", 30),
            ("total_correct", 12),
            ("overall_score_percentage", 60.0),
        ],
    )
    async def test_check_visual_duplicate_scoped_filtering_rejects_unscoped(
        self, mock_async_session: AsyncMock, mismatched_field: str, candidate_val
    ):
        """Challenge: Scoped matching with matching vs non-matching metrics.

        When any metric attribute differs, query returns 0.0 (no match).
        """
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        params = {
            "exercise_type": "Intervals",
            "total_questions": 20,
            "total_correct": 18,
            "overall_score_percentage": 90.0,
        }
        params[mismatched_field] = candidate_val

        sim = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_test",
            new_vector=[1.0] + [0.0] * 2047,
            **params,
        )

        assert sim == 0.0
        assert isinstance(sim, float)

    @pytest.mark.asyncio
    async def test_check_visual_duplicate_verifies_all_predicates_in_sql_ast(
        self, mock_async_session: AsyncMock
    ):
        """Verify check_visual_duplicate SQL AST contains all 4 scoping filters."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 0.998
        mock_async_session.execute.return_value = mock_result

        test_vector = [0.5] * 2048
        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_test",
            new_vector=test_vector,
            exercise_type="Melodic Dictation",
            total_questions=15,
            total_correct=15,
            overall_score_percentage=100.0,
        )

        assert result == 0.998
        stmt = mock_async_session.execute.call_args[0][0]
        where_criteria = stmt._where_criteria

        clause_columns = {
            c.left.name: c.right.value
            for c in where_criteria
            if hasattr(c, "left")
            and hasattr(c.left, "name")
            and hasattr(c, "right")
            and hasattr(c.right, "value")
        }

        assert clause_columns.get("exercise_type") == "Melodic Dictation"
        assert clause_columns.get("total_questions") == 15
        assert clause_columns.get("total_correct") == 15
        assert clause_columns.get("overall_score_percentage") == 100.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "edge_vector",
        [
            [],
            None,
        ],
    )
    async def test_check_visual_duplicate_empty_or_none_vector_safe(
        self, mock_async_session: AsyncMock, edge_vector
    ):
        """Verify empty or None vector returns 0.0 without executing DB query."""
        result = await check_visual_duplicate(
            session=mock_async_session,
            db_user_id="user_test",
            new_vector=edge_vector,  # type: ignore
            exercise_type="Intervals",
            total_questions=20,
            total_correct=18,
            overall_score_percentage=90.0,
        )
        assert result == 0.0
        mock_async_session.execute.assert_not_called()


class TestPropertyBasedFuzzing:
    """Property-based randomized generators to discover latent runtime crashes."""

    def test_canonical_content_signature_fuzz_invariants(self):
        """Property: Identical normalized values ALWAYS yield identical signatures.

        Differing values MUST yield distinct signatures with zero collisions.
        """
        exercise_types = [
            "Intervals",
            "Chords",
            "Scales",
            "Melodic Dictation",
            "Harmonic Progression",
        ]
        signatures_seen: set[str] = set()

        for i in range(500):
            ex = random.choice(exercise_types)
            q = random.randint(1, 100)
            c = random.randint(0, q)
            pct = round((c / q) * 100.0, 2)
            details = [
                {
                    "item_name": f"Item_{j}",
                    "times_heard": random.randint(1, 10),
                    "times_wrong": random.randint(0, 5),
                    "accuracy_percentage": round(random.uniform(50.0, 100.0), 2),
                }
                for j in range(random.randint(1, 4))
            ]

            sig1 = compute_canonical_content_signature(ex, q, c, pct, details)
            # Permute details order to verify sorting invariance
            permuted_details = list(reversed(details))
            sig2 = compute_canonical_content_signature(
                ex.upper(),  # case-insensitive
                str(q),  # string type coercion
                float(c),  # float type coercion
                pct,
                permuted_details,
            )

            assert sig1 == sig2, f"Signature failed invariance on trial {i}"
            assert len(sig1) == 64
            assert all(ch in string.hexdigits for ch in sig1)
            signatures_seen.add(sig1)

        # Ensure healthy diversity (zero collisions across distinct runs)
        assert len(signatures_seen) >= 450

    def test_metadata_nonce_fuzzer(self):
        """Fuzz random text to ensure is_valid_device_metadata never raises."""
        printable = (
            string.ascii_letters + string.digits + string.punctuation + " \t\n\r"
        )

        for _ in range(500):
            length = random.randint(0, 100)
            rand_str = "".join(random.choice(printable) for _ in range(length))

            res = is_valid_device_metadata(rand_str)
            assert isinstance(res, bool)

    @pytest.mark.asyncio
    async def test_check_metadata_duplicate_fuzzer(self, mock_async_session: AsyncMock):
        """Fuzz check_metadata_duplicate with randomized mixed types and inputs."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        for _ in range(100):
            mock_async_session.reset_mock()
            rand_meta = random.choice(
                [
                    None,
                    "N/A",
                    "na",
                    "09:41 | 85% battery",
                    "  unknown  ",
                    f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}",
                ]
            )
            q = random.randint(1, 50)
            c = random.randint(0, q)
            pct = round((c / q) * 100.0, 2)

            res = await check_metadata_duplicate(
                session=mock_async_session,
                db_user_id="user_fuzz",
                new_metadata=rand_meta,
                exercise_type="Intervals",
                total_questions=q,
                total_correct=c,
                overall_score_percentage=pct,
            )
            assert isinstance(res, bool)
