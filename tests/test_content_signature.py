"""Unit tests for content signature, image hashing, and device metadata validation."""

import hashlib

import pytest

from app.schemas.schemas import ExerciseDetail, ExerciseType
from app.services.fraud_service import (
    compute_canonical_content_signature,
    compute_image_hash,
    is_valid_device_metadata,
)


class TestComputeImageHash:
    def test_compute_image_hash_raw_bytes_deterministic(self, sample_png_bytes: bytes):
        """Test hashing raw bytes produces exact deterministic SHA-256 hex digest."""
        expected_hash = hashlib.sha256(sample_png_bytes).hexdigest()
        result1 = compute_image_hash(sample_png_bytes)
        result2 = compute_image_hash(sample_png_bytes)

        assert result1 == expected_hash
        assert result2 == expected_hash
        assert len(result1) == 64
        assert isinstance(result1, str)

    def test_compute_image_hash_base64_string(
        self, sample_png_bytes: bytes, sample_png_b64: str
    ):
        """Test base64 string is decoded to raw bytes before hashing (byte parity)."""
        expected_hash = hashlib.sha256(sample_png_bytes).hexdigest()
        result = compute_image_hash(sample_png_b64)

        assert result == expected_hash

    def test_compute_image_hash_data_uri_prefix(
        self, sample_png_bytes: bytes, sample_data_uri_png_b64: str
    ):
        """Test data URI prefix ('data:image/png;base64,...') is stripped safely."""
        expected_hash = hashlib.sha256(sample_png_bytes).hexdigest()
        result = compute_image_hash(sample_data_uri_png_b64)

        assert result == expected_hash

    def test_compute_image_hash_raw_vs_base64_equivalence(
        self,
        sample_png_bytes: bytes,
        sample_png_b64: str,
        sample_jpg_bytes: bytes,
        sample_jpg_b64: str,
    ):
        """Test that raw bytes and base64 strings yield identical hashes."""
        assert compute_image_hash(sample_png_bytes) == compute_image_hash(
            sample_png_b64
        )
        assert compute_image_hash(sample_jpg_bytes) == compute_image_hash(
            sample_jpg_b64
        )

    def test_compute_image_hash_differing_payloads(
        self, sample_png_bytes: bytes, sample_jpg_bytes: bytes
    ):
        """Test that differing image payloads produce completely distinct hashes."""
        hash_png = compute_image_hash(sample_png_bytes)
        hash_jpg = compute_image_hash(sample_jpg_bytes)

        assert hash_png != hash_jpg

    def test_compute_image_hash_empty_payload(self):
        """Test hashing empty bytes and empty string returns empty SHA-256 digest."""
        empty_sha256 = hashlib.sha256(b"").hexdigest()
        assert compute_image_hash(b"") == empty_sha256
        assert compute_image_hash("") == empty_sha256

    def test_compute_image_hash_invalid_base64_fallback(self):
        """Test that non-base64 text falls back gracefully without unhandled crashes."""
        text_payload = "not_a_valid_base64_payload!#$*&^%"
        expected_fallback = hashlib.sha256(text_payload.encode("utf-8")).hexdigest()
        result = compute_image_hash(text_payload)

        assert result == expected_fallback
        assert len(result) == 64

    def test_compute_image_hash_invalid_type_raises_type_error(self):
        """Test that passing non-bytes/non-string types raises TypeError."""
        with pytest.raises(TypeError):
            compute_image_hash(12345)  # type: ignore

        with pytest.raises(TypeError):
            compute_image_hash(None)  # type: ignore


class TestCanonicalContentSignatureInvariance:
    def test_signature_key_reordering_invariance(self):
        """Test that dictionaries with different key orders match."""
        dict_order_1 = [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
        ]
        dict_order_2 = [
            {
                "accuracy_percentage": 90.0,
                "item_name": "Major 3rd",
                "times_wrong": 1,
                "times_heard": 10,
            },
        ]
        dict_order_3 = [
            {
                "times_wrong": 1,
                "times_heard": 10,
                "accuracy_percentage": 90.0,
                "item_name": "Major 3rd",
            },
        ]

        sig1 = compute_canonical_content_signature(
            "Intervals", 10, 9, 90.0, dict_order_1
        )
        sig2 = compute_canonical_content_signature(
            "Intervals", 10, 9, 90.0, dict_order_2
        )
        sig3 = compute_canonical_content_signature(
            "Intervals", 10, 9, 90.0, dict_order_3
        )

        assert sig1 == sig2 == sig3
        assert len(sig1) == 64

    def test_signature_details_list_ordering_invariance(self):
        """Test that permuting list order in granular details preserves signature."""
        item_a = {
            "item_name": "Major 3rd",
            "times_heard": 10,
            "times_wrong": 1,
            "accuracy_percentage": 90.0,
        }
        item_b = {
            "item_name": "Minor 2nd",
            "times_heard": 10,
            "times_wrong": 1,
            "accuracy_percentage": 90.0,
        }
        item_c = {
            "item_name": "Perfect 5th",
            "times_heard": 10,
            "times_wrong": 0,
            "accuracy_percentage": 100.0,
        }

        list_abc = [item_a, item_b, item_c]
        list_cba = [item_c, item_b, item_a]
        list_bac = [item_b, item_a, item_c]

        sig_abc = compute_canonical_content_signature(
            "Intervals", 30, 28, 93.33, list_abc
        )
        sig_cba = compute_canonical_content_signature(
            "Intervals", 30, 28, 93.33, list_cba
        )
        sig_bac = compute_canonical_content_signature(
            "Intervals", 30, 28, 93.33, list_bac
        )

        assert sig_abc == sig_cba == sig_bac

    def test_signature_whitespace_invariance(self):
        """Test that leading and trailing whitespace in fields is normalized."""
        sig_clean = compute_canonical_content_signature(
            "Intervals",
            20,
            18,
            90.0,
            [
                {
                    "item_name": "Major 3rd",
                    "times_heard": 10,
                    "times_wrong": 1,
                    "accuracy_percentage": 90.0,
                }
            ],
        )
        sig_padded = compute_canonical_content_signature(
            "  Intervals  \t",
            20,
            18,
            90.0,
            [
                {
                    "item_name": "  Major 3rd  ",
                    "times_heard": 10,
                    "times_wrong": 1,
                    "accuracy_percentage": 90.0,
                }
            ],
        )

        assert sig_clean == sig_padded

    def test_signature_case_normalization_invariance(self):
        """Test that exercise type case variations produce identical signatures."""
        sig_title = compute_canonical_content_signature("Intervals", 20, 18, 90.0)
        sig_lower = compute_canonical_content_signature("intervals", 20, 18, 90.0)
        sig_upper = compute_canonical_content_signature("INTERVALS", 20, 18, 90.0)
        sig_enum = compute_canonical_content_signature(
            ExerciseType.INTERVALS, 20, 18, 90.0
        )

        assert sig_title == sig_lower == sig_upper == sig_enum

    def test_signature_float_format_invariance(self):
        """Test that float representations (90.0 vs 90) yield identical signatures."""
        sig_float1 = compute_canonical_content_signature("Intervals", 20, 18, 90.0)
        sig_float2 = compute_canonical_content_signature("Intervals", 20, 18, 90.00)
        sig_int = compute_canonical_content_signature("Intervals", 20, 18, 90)

        assert sig_float1 == sig_float2 == sig_int

    def test_signature_pydantic_model_vs_dict_invariance(self):
        """Test interoperability between Pydantic models and plain dictionaries."""
        pydantic_details = [
            ExerciseDetail(
                item_name="Major 3rd",
                times_heard=10,
                times_wrong=1,
                accuracy_percentage=90.0,
            ),
            ExerciseDetail(
                item_name="Minor 2nd",
                times_heard=10,
                times_wrong=1,
                accuracy_percentage=90.0,
            ),
        ]
        dict_details = [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
            {
                "item_name": "Minor 2nd",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
        ]
        wrapped_dict = {"details": dict_details}

        sig_pydantic = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, [d.model_dump() for d in pydantic_details]
        )
        sig_dict = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, dict_details
        )
        sig_wrapped = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, wrapped_dict
        )

        assert sig_pydantic == sig_dict == sig_wrapped


class TestCanonicalContentSignatureCollisionResistance:
    def test_distinct_exercise_types_collision_resistance(self):
        """Test that different exercise types yield distinct signatures."""
        exercise_types = [
            "Intervals",
            "Chords",
            "Scales",
            "Chord Progressions",
            "Perfect Pitch",
            "Scale Degrees",
            "Intervals in Context",
            "Melodic Dictation",
            "Unknown/Custom",
        ]
        signatures = {
            ex: compute_canonical_content_signature(ex, 20, 18, 90.0)
            for ex in exercise_types
        }

        # Mathematical collision resistance: all generated signatures must be unique
        assert len(set(signatures.values())) == len(exercise_types)

    def test_distinct_question_counts_collision_resistance(self):
        """Test that different question counts yield distinct signatures."""
        sig_20 = compute_canonical_content_signature("Intervals", 20, 18, 90.0)
        sig_30 = compute_canonical_content_signature("Intervals", 30, 27, 90.0)
        sig_40 = compute_canonical_content_signature("Intervals", 40, 36, 90.0)
        sig_100 = compute_canonical_content_signature("Intervals", 100, 90, 90.0)

        assert len({sig_20, sig_30, sig_40, sig_100}) == 4

    def test_distinct_scores_collision_resistance(self):
        """Test that different correct counts and scores yield distinct signatures."""
        sig_100 = compute_canonical_content_signature("Intervals", 20, 20, 100.0)
        sig_95 = compute_canonical_content_signature("Intervals", 20, 19, 95.0)
        sig_90 = compute_canonical_content_signature("Intervals", 20, 18, 90.0)
        sig_85 = compute_canonical_content_signature("Intervals", 20, 17, 85.0)
        sig_0 = compute_canonical_content_signature("Intervals", 20, 0, 0.0)

        assert len({sig_100, sig_95, sig_90, sig_85, sig_0}) == 5

    def test_distinct_granular_mistakes_collision_resistance(self):
        """Test that distinct error distributions yield distinct signatures."""
        # Attempt A: 2 mistakes on Minor 2nd, 0 on Major 3rd
        details_a = [
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
        # Attempt B: 0 mistakes on Minor 2nd, 2 on Major 3rd
        details_b = [
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
        # Attempt C: 1 mistake on each
        details_c = [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
            {
                "item_name": "Minor 2nd",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
        ]

        sig_a = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, details_a
        )
        sig_b = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, details_b
        )
        sig_c = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, details_c
        )

        assert sig_a != sig_b
        assert sig_b != sig_c
        assert sig_a != sig_c

    def test_distinct_granular_heard_counts_collision_resistance(self):
        """Test that differing item exposure counts yield distinct signatures."""
        details_1 = [
            {
                "item_name": "Major 3rd",
                "times_heard": 15,
                "times_wrong": 1,
                "accuracy_percentage": 93.33,
            },
            {
                "item_name": "Minor 2nd",
                "times_heard": 5,
                "times_wrong": 1,
                "accuracy_percentage": 80.0,
            },
        ]
        details_2 = [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
            {
                "item_name": "Minor 2nd",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
        ]

        sig_1 = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, details_1
        )
        sig_2 = compute_canonical_content_signature(
            "Intervals", 20, 18, 90.0, details_2
        )

        assert sig_1 != sig_2

    def test_empty_and_none_granular_details_safety(self):
        """Test that None, empty list, and empty dict are handled consistently."""
        sig_none = compute_canonical_content_signature("Intervals", 20, 18, 90.0, None)
        sig_list = compute_canonical_content_signature("Intervals", 20, 18, 90.0, [])
        sig_dict = compute_canonical_content_signature("Intervals", 20, 18, 90.0, {})

        assert sig_none == sig_list == sig_dict
        assert len(sig_none) == 64


class TestStatusBarNonceValidation:
    @pytest.mark.parametrize(
        "valid_nonce",
        [
            "10:15",
            "9:41 AM 100%",
            "09:41 | 85% battery",
            "14:20 | 100%",
            "8:00 AM | 50% battery",
            "12:30 PM | 99%",
            "23:59 | 1% battery",
            "11:11 | 45%",
            "  10:15 | 85% battery  ",
            "7:05 PM",
        ],
    )
    def test_is_valid_device_metadata_valid_formats(self, valid_nonce: str):
        """Test that authentic phone status bar nonces are validated as True."""
        assert is_valid_device_metadata(valid_nonce) is True

    @pytest.mark.parametrize(
        "empty_or_none",
        [
            None,
            "",
            "   ",
            "\t\n  ",
            "\r\n",
        ],
    )
    def test_is_valid_device_metadata_none_and_empty(self, empty_or_none):
        """Test that None, empty strings, and whitespace return False."""
        assert is_valid_device_metadata(empty_or_none) is False

    @pytest.mark.parametrize(
        "degenerate_keyword",
        [
            "N/A",
            "n/a",
            "Na",
            "na",
            "N/a",
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
            "  N/A  ",
            "  none  ",
        ],
    )
    def test_is_valid_device_metadata_degenerate_keywords(
        self, degenerate_keyword: str
    ):
        """Test that single-token degenerate keywords return False."""
        assert is_valid_device_metadata(degenerate_keyword) is False

    @pytest.mark.parametrize(
        "compound_na",
        [
            "N/A | N/A",
            "n/a | n/a",
            "NA | NA",
            "N/A | 80% battery",
            "10:15 | N/A",
            "N/A | N/A battery",
            "N/A |",
            "| N/A",
            "N/A|N/A",
            "n/a | 50%",
            "12:00 | na",
            "  N/A | N/A  ",
        ],
    )
    def test_is_valid_device_metadata_compound_degenerate_nonces(
        self, compound_na: str
    ):
        """Test that compound status bars containing 'N/A' return False."""
        assert is_valid_device_metadata(compound_na) is False

    def test_is_valid_device_metadata_non_string_types(self):
        """Test that non-string inputs safely return False."""
        assert is_valid_device_metadata(12345) is False  # type: ignore
        assert is_valid_device_metadata([]) is False  # type: ignore
        assert is_valid_device_metadata({}) is False  # type: ignore
