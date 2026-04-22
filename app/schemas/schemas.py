from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExerciseType(Enum):
    INTERVALS = "Intervals"
    CHORDS = "Chords"
    SCALES = "Scales"
    CHORD_PROGRESSIONS = "Chord Progressions"
    PERFECT_PITCH = "Perfect Pitch"
    SCALE_DEGREES = "Scale Degrees"
    INTERVALS_IN_CONTEXT = "Intervals in Context"
    MELODIC_DICTATION = "Melodic Dictation"
    UNKNOWN_CUSTOM = "Unknown/Custom"


class ExerciseDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(
        description=(
            "The specific name of the individual exercise item as displayed "
            "in the results breakdown. Examples: 'Minor 2nd', 'Major 3rd', "
            "'Perfect 5th', 'Cmaj7'. Extract the exact label shown on screen."
        )
    )
    times_heard: int = Field(
        description=(
            "The total number of times this specific item was presented to "
            "the user during the exercise session. Extract the integer count "
            "from the corresponding column in the results table."
        )
    )
    times_wrong: int = Field(
        description=(
            "The total number of incorrect answers the user gave for this "
            "specific item. Extract the integer count from the 'wrong' or "
            "'incorrect' column in the results table."
        )
    )
    accuracy_percentage: float = Field(
        description=(
            "The accuracy percentage for this specific item, expressed as a "
            "float between 0.0 and 100.0. If the percentage is not directly "
            "displayed, compute it as ((times_heard - times_wrong) / "
            "times_heard) * 100."
        )
    )


class MetricExtractionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_type: ExerciseType = Field(
        description=(
            "The category of ear-training exercise shown in the screenshot. "
            "Must be one of the predefined enum values: 'Intervals', "
            "'Chords', 'Scales', 'Chord Progressions', 'Perfect Pitch', "
            "'Scale Degrees', 'Intervals in Context', 'Melodic Dictation', "
            "or 'Unknown/Custom'. Identify this from the title or header "
            "area of the results screen."
        )
    )
    total_questions: int = Field(
        description=(
            "The total number of questions asked across the entire exercise "
            "session. Extract this from the summary statistics section of "
            "the results screen."
        )
    )
    total_correct: int = Field(
        description=(
            "The total number of questions answered correctly across the "
            "entire exercise session. Extract this from the summary "
            "statistics section of the results screen."
        )
    )
    overall_score_percentage: float = Field(
        description=(
            "The overall accuracy score for the session expressed as a "
            "float between 0.0 and 100.0. Extract the percentage from the "
            "prominent score display on the results screen. If not directly "
            "visible, compute it as (total_correct / total_questions) * 100."
        )
    )
    device_metadata: str = Field(
        description=(
            "Extract the exact time and battery percentage from the phone's "
            "status bar at the top edge of the screenshot. Look at the "
            "top-left corner for the current time and the top-right corner "
            "for the battery percentage indicator. Return a string in the "
            "format 'HH:MM | XX% battery'. If either value is unreadable, "
            "substitute 'N/A' for that field."
        )
    )
    details: list[ExerciseDetail] = Field(
        description=(
            "A list of individual item-level breakdowns extracted from the "
            "results table in the screenshot. Each entry corresponds to one "
            "row in the detailed results, capturing the item name, times "
            "heard, times wrong, and accuracy percentage. Preserve the "
            "order as displayed on screen."
        )
    )
