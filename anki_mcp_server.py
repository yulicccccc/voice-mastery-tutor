"""Anki read bridge, local Tutor policy, and guarded ReviewEvent sync tools."""

from __future__ import annotations

import json
import os
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from learner_store import JsonlLearnerStore, SqliteReviewStore
from models import (
    AnswerAssessment,
    FirstAttemptResult,
    LearnerState,
    QuestionType,
    ReviewSyncStatus,
    SchedulerSnapshot,
    TutorContext,
)
from review_sync import (
    AnkiConnectReviewAdapter,
    ReviewSyncService,
    build_review_event,
)
from tutor_engine import TutorEngine

ANKICONNECT_URL = os.environ.get("ANKICONNECT_URL", "http://127.0.0.1:8765")
DEFAULT_DECK = os.environ.get("ANKI_DEFAULT_DECK", "000-WuCai Inbox")
ANKICONNECT_VERSION = 6
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("ANKICONNECT_TIMEOUT", "8"))
MAX_CARDS_PER_CALL = 100
ANKI_REVIEW_WRITEBACK_ENABLED = os.environ.get(
    "ANKI_REVIEW_WRITEBACK_ENABLED", "false"
).lower() in {"1", "true", "yes"}

mcp = FastMCP("voice-mastery-tutor")
_tutor_engine = TutorEngine(JsonlLearnerStore())


def _anki_call(action: str, params: dict[str, Any] | None = None) -> Any:
    payload = json.dumps(
        {
            "action": action,
            "version": ANKICONNECT_VERSION,
            "params": params or {},
        }
    ).encode("utf-8")

    request = Request(
        ANKICONNECT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except (URLError, HTTPError, TimeoutError) as exc:
        raise RuntimeError(
            "Cannot reach AnkiConnect. Make sure desktop Anki is open and "
            f"AnkiConnect is listening at {ANKICONNECT_URL}."
        ) from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AnkiConnect returned invalid JSON.") from exc

    if not isinstance(decoded, dict) or "error" not in decoded or "result" not in decoded:
        raise RuntimeError("Unexpected AnkiConnect response shape.")

    if decoded["error"] is not None:
        raise RuntimeError(f"AnkiConnect error: {decoded['error']}")

    return decoded["result"]


_review_store = SqliteReviewStore()
_review_sync_service = ReviewSyncService(
    _review_store,
    AnkiConnectReviewAdapter(_anki_call),
    writeback_enabled=ANKI_REVIEW_WRITEBACK_ENABLED,
)


def _deck_due_query(deck: str) -> str:
    # Anki search syntax uses backslash escaping inside a quoted deck name.
    escaped = deck.replace("\\", "\\\\").replace('"', '\\"')
    return f'deck:"{escaped}" is:due'


def _field_values(fields: Any) -> dict[str, str]:
    """Convert AnkiConnect's {field: {value, order}} shape to plain strings."""
    if not isinstance(fields, dict):
        return {}

    values: dict[str, str] = {}
    for name, data in fields.items():
        if isinstance(data, dict):
            value = data.get("value", "")
        else:
            value = data
        values[str(name)] = "" if value is None else str(value)
    return values


def _teacher_card(card: dict[str, Any]) -> dict[str, Any]:
    """Keep teacher-relevant source + scheduling fields; omit rendered HTML noise."""
    return {
        "card_id": card.get("cardId"),
        "note_id": card.get("note"),
        "deck": card.get("deckName"),
        "model": card.get("modelName"),
        "fields": _field_values(card.get("fields")),
        "due": card.get("due"),
        "queue": card.get("queue"),
        "type": card.get("type"),
        "reps": card.get("reps"),
        "lapses": card.get("lapses"),
        "interval": card.get("interval"),
        "factor": card.get("factor"),
        "left": card.get("left"),
        "modified": card.get("mod"),
        "next_reviews": card.get("nextReviews"),
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Read due Anki cards",
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )
)
def get_due_cards(deck: str = DEFAULT_DECK, limit: int = 20) -> dict[str, Any]:
    """Get teacher-facing Anki material that is due in a deck.

    Use this before a tutoring/review session. The returned `fields` are the source
    note fields; do NOT assume Front/Back are necessarily question/answer. `is:due`
    can include cards in learning/relearning as well as review cards. This tool is
    read-only and never changes Anki or FSRS state.
    """
    deck = deck.strip()
    if not deck:
        raise ValueError("deck must not be empty")
    if limit < 1 or limit > MAX_CARDS_PER_CALL:
        raise ValueError(f"limit must be between 1 and {MAX_CARDS_PER_CALL}")

    query = _deck_due_query(deck)
    card_ids = _anki_call("findCards", {"query": query})
    if not isinstance(card_ids, list):
        raise RuntimeError("AnkiConnect findCards did not return a list.")

    selected_ids = card_ids[:limit]
    cards: list[dict[str, Any]] = []
    if selected_ids:
        raw_cards = _anki_call("cardsInfo", {"cards": selected_ids})
        if not isinstance(raw_cards, list):
            raise RuntimeError("AnkiConnect cardsInfo did not return a list.")
        cards = [_teacher_card(card) for card in raw_cards if isinstance(card, dict)]

    return {
        "deck": deck,
        "query": query,
        "total_due": len(card_ids),
        "returned": len(cards),
        "cards": cards,
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Choose the Tutor's next teaching step",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
)
def decide_tutor_next_step(
    card_id: int,
    learner_answer: str,
    assessment: Literal["correct", "incorrect", "partial", "unknown"],
    note_id: int | None = None,
    was_prompted: bool = False,
    consecutive_incorrect: int = 0,
    question_type: Literal[
        "fact", "concept", "abstract", "process", "application", "decision", "causal"
    ] = "concept",
    has_personal_context: bool = False,
    stable_mastery_evidence: bool = False,
    learner_rejects_mastery: bool = False,
) -> dict[str, Any]:
    """Apply the lightweight-first Tutor policy to one learner answer.

    ChatGPT should compare the answer with the card material and pass its semantic
    judgment in `assessment`. The policy handles explicit learner intent, state
    transitions, depth escalation, one-method teaching selection, and session
    continuity. It appends one local JSONL Tutor event, but never writes to Anki or
    changes FSRS, due dates, intervals, notes, or review history. Set
    `learner_rejects_mastery` when the learner corrects a prior mastery judgment;
    the learner's correction wins over Tutor-inferred mastery evidence. A true
    `mastered` state also requires previously persisted independent-recall
    evidence; one answer can only become a mastery candidate.
    """
    context = TutorContext(
        card_id=card_id,
        note_id=note_id,
        learner_answer=learner_answer,
        assessment=AnswerAssessment(assessment),
        was_prompted=was_prompted,
        consecutive_incorrect=consecutive_incorrect,
        question_type=QuestionType(question_type),
        has_personal_context=has_personal_context,
        stable_mastery_evidence=stable_mastery_evidence,
        learner_rejects_mastery=learner_rejects_mastery,
    )
    decision = _tutor_engine.decide(context)
    return {
        "card_id": card_id,
        "note_id": note_id,
        "event_saved_locally": True,
        "anki_mutated": False,
        **decision.to_dict(),
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Record one completed card ReviewEvent",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def record_review_result(
    card_id: int,
    first_attempt_result: Literal["succeeded", "failed", "not_attempted"],
    tutor_state: Literal[
        "retrieval_gap",
        "independent_recall",
        "prompted_recall",
        "understanding_gap",
        "known_but_not_transferable",
        "mastered",
        "skipped_low_value",
        "paused",
    ],
    scheduler_snapshot: dict[str, Any],
    note_id: int | None = None,
    hints_used: int = 0,
) -> dict[str, Any]:
    """Durably record the scheduling outcome of one completed card interaction.

    The Anki rating is fixed by the first unaided attempt: succeeded maps to Good,
    failed maps to Again, and later hints/retries do not change it. A
    `not_attempted` value creates no ReviewEvent. The stable event ID is derived
    from the card and scheduler snapshot, so an identical repeated completion is
    idempotent. This tool never calls AnkiConnect or modifies Anki.
    """
    snapshot = SchedulerSnapshot.from_mapping(scheduler_snapshot)
    event = build_review_event(
        card_id=card_id,
        note_id=note_id,
        first_attempt_result=FirstAttemptResult(first_attempt_result),
        tutor_state=LearnerState(tutor_state),
        hints_used=hints_used,
        scheduler_snapshot=snapshot,
    )
    if event is None:
        return {
            "recorded": False,
            "duplicate": False,
            "event_id": None,
            "sync_status": ReviewSyncStatus.NOT_APPLICABLE.value,
            "reason": "no genuine first unaided retrieval attempt",
            "anki_mutated": False,
        }

    stored, created = _review_store.create_or_get(event)
    return {
        "recorded": True,
        "duplicate": not created,
        "anki_mutated": False,
        **stored.to_dict(),
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Safely synchronize pending Anki ReviewEvents",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def sync_pending_reviews(
    dry_run: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    """Inspect or synchronize durable pending ReviewEvents one card at a time.

    `dry_run` defaults to true. Real scheduler writes also require the process-level
    `ANKI_REVIEW_WRITEBACK_ENABLED=true` feature flag. Before any enabled write,
    the current Anki card snapshot must exactly match the event snapshot. The
    adapter uses AnkiConnect's scheduler-backed `answerCards` action; it never
    edits Anki DB rows or FSRS fields directly. Only a confirmed `[true]` response
    marks an event applied.
    """
    return _review_sync_service.sync_pending(dry_run=dry_run, limit=limit)



if __name__ == "__main__":
    # stdio is the MCP SDK default and is supported by OpenAI Secure MCP Tunnel.
    mcp.run()
