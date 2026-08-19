import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Metric, Submission

_DEGENERATE_METADATA_TOKENS: set[str] = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "undefined",
}


def compute_image_hash(image_payload: str | bytes) -> str:
    """Compute deterministic SHA-256 hex digest of an image payload.

    Accepts raw image bytes or base64-encoded string (with or without data URI prefix).
    Decodes base64 strings to raw bytes before hashing to ensure exact hash parity
    between raw byte streams and base64-encoded transmissions.
    """
    if isinstance(image_payload, bytes):
        raw_bytes = image_payload
    elif isinstance(image_payload, str):
        cleaned = image_payload.strip()
        if cleaned.startswith("data:") and "," in cleaned:
            cleaned = cleaned.split(",", 1)[1].strip()

        # Fix base64 padding if needed
        missing_padding = len(cleaned) % 4
        if missing_padding:
            cleaned += "=" * (4 - missing_padding)

        try:
            raw_bytes = base64.b64decode(cleaned, validate=True)
        except Exception:
            raw_bytes = image_payload.encode("utf-8")
    else:
        raise TypeError(
            f"Expected str or bytes for image_payload, got "
            f"{type(image_payload).__name__}"
        )

    return hashlib.sha256(raw_bytes).hexdigest()


def _normalize_value(val: Any) -> Any:
    """Recursively normalize values for canonical signature generation."""
    if val is None:
        return None
    if isinstance(val, Enum):
        return str(val.value).strip().lower()
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return round(float(val), 2)
    if isinstance(val, str):
        val_str = val.strip()
        if (val_str.startswith("{") and val_str.endswith("}")) or (
            val_str.startswith("[") and val_str.endswith("]")
        ):
            try:
                parsed = json.loads(val_str)
                return _normalize_value(parsed)
            except Exception:
                pass
        return val_str.lower()
    if hasattr(val, "model_dump"):
        return _normalize_value(val.model_dump())
    if hasattr(val, "dict") and callable(getattr(val, "dict")):
        return _normalize_value(val.dict())
    if isinstance(val, dict):
        if not val:
            return []
        return {
            str(k).strip().lower(): _normalize_value(v)
            for k, v in sorted(val.items(), key=lambda item: str(item[0]))
        }
    if isinstance(val, list | tuple | set):
        if not val:
            return []
        norm_list = [_normalize_value(item) for item in val if item is not None]
        return sorted(
            norm_list,
            key=lambda x: json.dumps(
                x, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ),
        )
    return str(val).strip().lower()


def compute_canonical_content_signature(
    exercise_type: str | Enum,
    total_questions: int | str | float,
    total_correct: int | str | float,
    overall_score_percentage: float | int | str,
    granular_details: dict | list | str | None = None,
) -> str:
    """Generate a deterministic canonical SHA-256 signature for test metrics.

    Guarantees that genuine submissions with differing exercise types,
    question counts, or scores yield distinct signatures, while identical
    test results produce identical signatures.
    """
    if isinstance(exercise_type, Enum):
        norm_exercise_type = str(exercise_type.value).strip().lower()
    else:
        norm_exercise_type = str(exercise_type or "").strip().lower()

    norm_total_questions = int(total_questions)
    norm_total_correct = int(total_correct)
    norm_overall_score = round(float(overall_score_percentage), 2)

    # Unwrap container dictionary if present
    if isinstance(granular_details, dict):
        if len(granular_details) == 1 and (
            "details" in granular_details or "granular_details" in granular_details
        ):
            granular_details = granular_details.get(
                "details", granular_details.get("granular_details")
            )

    if not granular_details:
        norm_granular_details: Any = []
    else:
        norm_granular_details = _normalize_value(granular_details)
        if not norm_granular_details:
            norm_granular_details = []

    canonical_payload = {
        "exercise_type": norm_exercise_type,
        "granular_details": norm_granular_details,
        "overall_score_percentage": norm_overall_score,
        "total_correct": norm_total_correct,
        "total_questions": norm_total_questions,
    }

    canonical_json = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def is_valid_device_metadata(device_metadata: str | None) -> bool:
    """Validate whether device metadata represents a usable status bar nonce.

    Returns False if device_metadata is None, empty/whitespace, non-string, or matches
    degenerate placeholders (e.g. 'N/A', 'na', 'none', 'unknown', 'null', 'undefined')
    either individually or as compound fields (e.g. 'N/A | 85% battery', 'N/A | N/A').
    Returns True for valid status bar nonces.
    """
    if device_metadata is None or not isinstance(device_metadata, str):
        return False

    cleaned = device_metadata.strip()
    if not cleaned:
        return False

    lowered = cleaned.lower()
    if lowered in _DEGENERATE_METADATA_TOKENS:
        return False

    # Check composite status bars separated by |, commas, or semicolons
    tokens = [t.strip() for t in re.split(r"[|,;]", lowered)]
    if not tokens:
        return False

    for t in tokens:
        cleaned_token = t.replace("%", "").replace("battery", "").strip()
        if cleaned_token in _DEGENERATE_METADATA_TOKENS:
            return False
        if re.search(r"\b(n/a|na|none|null|unknown|undefined)\b", t):
            return False

    return True


async def check_exact_image_duplicate(
    session: AsyncSession,
    image_hash: str | None,
) -> bool:
    """Check if an exact duplicate screenshot has already been recorded.

    Performs an indexed lookup on `Metric.image_hash`.
    Returns True if an identical image hash already exists, False otherwise.
    If image_hash is empty or None, returns False immediately without executing
    a database query.
    """
    if not image_hash or not isinstance(image_hash, str):
        return False

    cleaned_hash = image_hash.strip()
    if not cleaned_hash:
        return False

    stmt = select(Metric.id).where(Metric.image_hash == cleaned_hash).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def check_metadata_duplicate(
    session: AsyncSession,
    db_user_id: str,
    new_metadata: str | None,
    exercise_type: str | Enum,
    total_questions: int | str | float,
    total_correct: int | str | float,
    overall_score_percentage: float | int | str,
    granular_details: dict | list | str | None = None,
    breakdown_signature: str | None = None,
) -> bool:
    """Check if a duplicate submission occurred within rolling 24 hours.

    Evaluates `is_valid_device_metadata(new_metadata)` first. If invalid, degenerate,
    or None (e.g. 'N/A', 'none', 'unknown'), returns False immediately without
    executing a database query (guaranteeing 0 false positives on missing nonces).

    If valid, matches submissions within a rolling 24-hour window where the device
    metadata matches AND the test content breakdown signature matches (or individual
    exercise metrics match for legacy records).
    """
    if not is_valid_device_metadata(new_metadata):
        return False

    if not breakdown_signature:
        breakdown_signature = compute_canonical_content_signature(
            exercise_type=exercise_type,
            total_questions=total_questions,
            total_correct=total_correct,
            overall_score_percentage=overall_score_percentage,
            granular_details=granular_details,
        )

    cutoff = datetime.now(UTC) - timedelta(hours=24)

    if isinstance(exercise_type, Enum):
        norm_exercise = str(exercise_type.value).strip()
    else:
        norm_exercise = str(exercise_type or "").strip()

    norm_questions = int(total_questions)
    norm_correct = int(total_correct)
    norm_score = float(overall_score_percentage)

    content_match = or_(
        Metric.breakdown_signature == breakdown_signature,
        and_(
            Metric.exercise_type == norm_exercise,
            Metric.total_questions == norm_questions,
            Metric.total_correct == norm_correct,
            Metric.overall_score_percentage == norm_score,
        ),
    )

    stmt = (
        select(Metric.id)
        .join(Metric.submission)
        .where(
            Metric.device_metadata == new_metadata.strip(),  # type: ignore[union-attr]
            Submission.created_at >= cutoff,
            content_match,
        )
        .limit(1)
    )

    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def check_visual_duplicate(
    session: AsyncSession,
    db_user_id: str,
    new_vector: list[float],
    exercise_type: str | Enum,
    total_questions: int | str | float,
    total_correct: int | str | float,
    overall_score_percentage: float | int | str,
) -> float:
    """Compute maximum visual cosine similarity scoped to matching exercise/scores.

    Eliminates unscoped global MAX() cosine distance false positives by scoping vector
    distance comparison strictly to candidate submissions with identical
    exercise_type, total_questions, total_correct, and overall_score_percentage.
    """
    if not new_vector:
        return 0.0

    if isinstance(exercise_type, Enum):
        norm_exercise = str(exercise_type.value).strip()
    else:
        norm_exercise = str(exercise_type or "").strip()

    norm_questions = int(total_questions)
    norm_correct = int(total_correct)
    norm_score = float(overall_score_percentage)

    similarity_expr = 1 - Metric.image_vector.cosine_distance(new_vector)

    stmt = select(func.max(similarity_expr)).where(
        Metric.image_vector.isnot(None),
        Metric.exercise_type == norm_exercise,
        Metric.total_questions == norm_questions,
        Metric.total_correct == norm_correct,
        Metric.overall_score_percentage == norm_score,
    )

    result = await session.execute(stmt)
    max_similarity = result.scalar_one_or_none()

    return float(max_similarity) if max_similarity is not None else 0.0
