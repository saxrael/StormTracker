"""Shared test fixtures for StormTracker test suite."""

import base64
import os
from unittest.mock import AsyncMock, MagicMock

# Ensure required environment variables exist during test execution
os.environ.setdefault("TELEGRAM_SECRET_TOKEN", "test_secret_token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
os.environ.setdefault("WEBHOOK_URL", "https://test.example.com/webhook")
os.environ.setdefault("DOMAIN_NAME", "test.example.com")
os.environ.setdefault("GOOGLE_AI_API_KEY", "test_google_key")
os.environ.setdefault("OPENROUTER_API_KEY", "test_openrouter_key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/testdb"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-test")
os.environ.setdefault("LANGFUSE_HOST", "https://cloud.langfuse.com")
os.environ.setdefault("CRON_SECRET", "test_cron_secret")

import pytest

from app.schemas.schemas import ExerciseDetail, ExerciseType, MetricExtractionSchema


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Deterministic 1x1 transparent PNG binary bytes."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


@pytest.fixture
def sample_png_b64(sample_png_bytes: bytes) -> str:
    """Standard base64 encoded string of sample PNG."""
    return base64.b64encode(sample_png_bytes).decode("utf-8")


@pytest.fixture
def sample_data_uri_png_b64(sample_png_b64: str) -> str:
    """Base64 PNG string formatted as a Data URI."""
    return f"data:image/png;base64,{sample_png_b64}"


@pytest.fixture
def sample_jpg_bytes() -> bytes:
    """Deterministic alternative binary image bytes."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"
        b"\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19"
    )


@pytest.fixture
def sample_jpg_b64(sample_jpg_bytes: bytes) -> str:
    """Standard base64 encoded string of sample JPG."""
    return base64.b64encode(sample_jpg_bytes).decode("utf-8")


@pytest.fixture
def sample_intervals_details() -> list[dict]:
    """Sample granular detail list for Intervals test."""
    return [
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


@pytest.fixture
def sample_intervals_metrics_90(sample_intervals_details: list[dict]) -> dict:
    """Standard 90% Intervals metric dictionary."""
    return {
        "exercise_type": "Intervals",
        "total_questions": 20,
        "total_correct": 18,
        "overall_score_percentage": 90.0,
        "device_metadata": "09:41 | 85% battery",
        "details": sample_intervals_details,
    }


@pytest.fixture
def sample_intervals_metrics_75() -> dict:
    """Standard 75% Intervals metric dictionary."""
    return {
        "exercise_type": "Intervals",
        "total_questions": 20,
        "total_correct": 15,
        "overall_score_percentage": 75.0,
        "device_metadata": "09:41 | 85% battery",
        "details": [
            {
                "item_name": "Major 3rd",
                "times_heard": 10,
                "times_wrong": 2,
                "accuracy_percentage": 80.0,
            },
            {
                "item_name": "Minor 2nd",
                "times_heard": 10,
                "times_wrong": 3,
                "accuracy_percentage": 70.0,
            },
        ],
    }


@pytest.fixture
def sample_chords_metrics_90() -> dict:
    """Standard 90% Chords metric dictionary.

    Uses same score and question count as Intervals, but with distinct exercise type.
    """
    return {
        "exercise_type": "Chords",
        "total_questions": 20,
        "total_correct": 18,
        "overall_score_percentage": 90.0,
        "device_metadata": "09:41 | 85% battery",
        "details": [
            {
                "item_name": "Major Triad",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
            {
                "item_name": "Minor Triad",
                "times_heard": 10,
                "times_wrong": 1,
                "accuracy_percentage": 90.0,
            },
        ],
    }


@pytest.fixture
def sample_scales_metrics_100() -> dict:
    """Standard 100% Scales metric dictionary."""
    return {
        "exercise_type": "Scales",
        "total_questions": 10,
        "total_correct": 10,
        "overall_score_percentage": 100.0,
        "device_metadata": "10:15 | 92% battery",
        "details": [
            {
                "item_name": "Major Scale",
                "times_heard": 5,
                "times_wrong": 0,
                "accuracy_percentage": 100.0,
            },
            {
                "item_name": "Natural Minor",
                "times_heard": 5,
                "times_wrong": 0,
                "accuracy_percentage": 100.0,
            },
        ],
    }


@pytest.fixture
def sample_na_metadata_metrics(sample_intervals_details: list[dict]) -> dict:
    """Metric dictionary with degenerate 'N/A' device metadata."""
    return {
        "exercise_type": "Intervals",
        "total_questions": 20,
        "total_correct": 18,
        "overall_score_percentage": 90.0,
        "device_metadata": "N/A",
        "details": sample_intervals_details,
    }


@pytest.fixture
def sample_pydantic_intervals_schema(
    sample_intervals_metrics_90: dict,
) -> MetricExtractionSchema:
    """Validated Pydantic MetricExtractionSchema instance."""
    return MetricExtractionSchema(
        exercise_type=ExerciseType.INTERVALS,
        total_questions=sample_intervals_metrics_90["total_questions"],
        total_correct=sample_intervals_metrics_90["total_correct"],
        overall_score_percentage=sample_intervals_metrics_90[
            "overall_score_percentage"
        ],
        device_metadata=sample_intervals_metrics_90["device_metadata"],
        details=[
            ExerciseDetail(**item) for item in sample_intervals_metrics_90["details"]
        ],
    )


@pytest.fixture
def sample_image_vector_a() -> list[float]:
    """Deterministic normalized 2048-dimensional unit vector A."""
    vec = [0.0] * 2048
    vec[0] = 1.0
    return vec


@pytest.fixture
def sample_image_vector_near() -> list[float]:
    """Deterministic 2048-dim vector with cosine similarity > 0.99 with vector A."""
    vec = [0.0] * 2048
    vec[0] = 0.999
    vec[1] = 0.04471
    return vec


@pytest.fixture
def sample_image_vector_far() -> list[float]:
    """Deterministic 2048-dim orthogonal vector (cosine similarity = 0.0)."""
    vec = [0.0] * 2048
    vec[100] = 1.0
    return vec


@pytest.fixture
def mock_async_session():
    """Mock AsyncSession for offline database testing."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_result.all.return_value = []
    session.execute.return_value = mock_result
    return session
