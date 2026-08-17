"""Small data contract for the local Tutor policy layer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class StringEnum(str, Enum):
    pass


class AnswerAssessment(StringEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class LearnerState(StringEnum):
    RETRIEVAL_GAP = "retrieval_gap"
    INDEPENDENT_RECALL = "independent_recall"
    PROMPTED_RECALL = "prompted_recall"
    UNDERSTANDING_GAP = "understanding_gap"
    KNOWN_BUT_NOT_TRANSFERABLE = "known_but_not_transferable"
    MASTERED = "mastered"
    SKIPPED_LOW_VALUE = "skipped_low_value"
    PAUSED = "paused"


class TutorAction(StringEnum):
    GIVE_HINT = "give_hint"
    DEEPEN = "deepen"
    CONFIRM_AND_NEXT = "confirm_and_next"
    SKIP_AND_NEXT = "skip_and_next"
    PAUSE = "pause"


class TeachingDepth(StringEnum):
    NONE = "none"
    LIGHTWEIGHT = "lightweight"
    DEEP = "deep"


class TeachingMethod(StringEnum):
    CONCRETE_EXAMPLE = "concrete_example"
    ANALOGY = "analogy"
    CASE_STUDY = "case_study"
    COUNTERFACTUAL_THINKING = "counterfactual_thinking"
    OWN_WORK_EXAMPLE = "own_work_example"
    NEAR_TRANSFER = "near_transfer"


class QuestionType(StringEnum):
    FACT = "fact"
    CONCEPT = "concept"
    ABSTRACT = "abstract"
    PROCESS = "process"
    APPLICATION = "application"
    DECISION = "decision"
    CAUSAL = "causal"


class FirstAttemptResult(StringEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


class AnkiRating(StringEnum):
    AGAIN = "Again"
    GOOD = "Good"

    @property
    def ease(self) -> int:
        return 1 if self == AnkiRating.AGAIN else 3


class ReviewSyncStatus(StringEnum):
    PENDING = "pending"
    APPLIED = "applied"
    CONFLICTED = "conflicted"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SchedulerSnapshot:
    modified: int
    reps: int
    lapses: int
    queue: int
    card_type: int
    due: int
    interval: int
    factor: int
    left: int

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> SchedulerSnapshot:
        aliases = {
            "modified": ("modified", "mod"),
            "reps": ("reps",),
            "lapses": ("lapses",),
            "queue": ("queue",),
            "card_type": ("card_type", "type"),
            "due": ("due",),
            "interval": ("interval", "ivl"),
            "factor": ("factor",),
            "left": ("left",),
        }
        values: dict[str, int] = {}
        for field_name, possible_names in aliases.items():
            value = next(
                (data[name] for name in possible_names if name in data),
                None,
            )
            if value is None or isinstance(value, bool):
                raise ValueError(
                    f"scheduler_snapshot requires integer field {field_name!r}"
                )
            try:
                values[field_name] = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"scheduler_snapshot field {field_name!r} must be an integer"
                ) from exc
        return cls(**values)

    def to_dict(self) -> dict[str, int]:
        return {
            "modified": self.modified,
            "reps": self.reps,
            "lapses": self.lapses,
            "queue": self.queue,
            "card_type": self.card_type,
            "due": self.due,
            "interval": self.interval,
            "factor": self.factor,
            "left": self.left,
        }


@dataclass(frozen=True)
class ReviewEvent:
    event_id: str
    card_id: int
    note_id: int | None
    first_attempt_result: FirstAttemptResult
    mapped_anki_rating: AnkiRating
    tutor_state: LearnerState
    hints_used: int
    scheduler_snapshot: SchedulerSnapshot
    created_at: str
    sync_status: ReviewSyncStatus = ReviewSyncStatus.PENDING
    sync_attempts: int = 0
    last_error: str | None = None

    @staticmethod
    def stable_event_id(card_id: int, snapshot: SchedulerSnapshot) -> str:
        identity = json.dumps(
            {
                "card_id": card_id,
                "scheduler_snapshot": snapshot.to_dict(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"review_{hashlib.sha256(identity).hexdigest()[:32]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "card_id": self.card_id,
            "note_id": self.note_id,
            "first_attempt_result": self.first_attempt_result.value,
            "mapped_anki_rating": self.mapped_anki_rating.value,
            "tutor_state": self.tutor_state.value,
            "hints_used": self.hints_used,
            "scheduler_snapshot": self.scheduler_snapshot.to_dict(),
            "created_at": self.created_at,
            "sync_status": self.sync_status.value,
            "sync_attempts": self.sync_attempts,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class TutorContext:
    card_id: int
    learner_answer: str
    assessment: AnswerAssessment
    note_id: int | None = None
    was_prompted: bool = False
    consecutive_incorrect: int = 0
    question_type: QuestionType = QuestionType.CONCEPT
    has_personal_context: bool = False
    stable_mastery_evidence: bool = False
    learner_rejects_mastery: bool = False

    def __post_init__(self) -> None:
        if self.card_id < 1:
            raise ValueError("card_id must be a positive integer")
        if not self.learner_answer.strip():
            raise ValueError("learner_answer must not be empty")
        if self.consecutive_incorrect < 0:
            raise ValueError("consecutive_incorrect must not be negative")


@dataclass(frozen=True)
class TutorDecision:
    state: LearnerState
    action: TutorAction
    depth: TeachingDepth
    guidance: str
    reason: str
    teaching_method: TeachingMethod | None = None
    continue_session: bool = True
    ask_to_continue: bool = False
    mastered_candidate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "action": self.action.value,
            "depth": self.depth.value,
            "guidance": self.guidance,
            "reason": self.reason,
            "teaching_method": (
                self.teaching_method.value if self.teaching_method else None
            ),
            "continue_session": self.continue_session,
            "ask_to_continue": self.ask_to_continue,
            "mastered_candidate": self.mastered_candidate,
        }
