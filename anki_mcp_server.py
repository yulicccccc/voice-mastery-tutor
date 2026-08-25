"""Anki read bridge, local Tutor policy, and guarded ReviewEvent sync tools."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Literal, TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

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
    TriageEvent,
    TriageSource,
    TriageTreatment,
    TutorContext,
)
from review_sync import (
    AnkiConnectReviewAdapter,
    ReviewSyncService,
    build_review_event,
)
from study_session import StudySessionStore, build_voice_handoff
from tutor_engine import TutorEngine

ANKICONNECT_URL = os.environ.get("ANKICONNECT_URL", "http://127.0.0.1:8765")
DEFAULT_DECK = os.environ.get("ANKI_DEFAULT_DECK", "000-WuCai Inbox")
ANKICONNECT_VERSION = 6
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("ANKICONNECT_TIMEOUT", "8"))
MAX_CARDS_PER_CALL = 100
MAX_TRIAGE_FIELDS_PER_CARD = 5
MAX_TRIAGE_FIELD_CHARS = 400
MAX_TRIAGE_CONTENT_CHARS_PER_CARD = 1200
ANKI_REVIEW_WRITEBACK_ENABLED = os.environ.get(
    "ANKI_REVIEW_WRITEBACK_ENABLED", "false"
).lower() in {"1", "true", "yes"}


class TriageResultInput(TypedDict):
    card_id: int
    treatment: Literal[
        "reference", "understand", "remember", "apply", "practice", "ignore"
    ]
    source: Literal["teacher", "learner_override"]
    reason: str


class _CompactTextExtractor(HTMLParser):
    """Extract visible text while discarding style and media bodies."""

    _ignored_tags = {"audio", "script", "style", "svg", "video"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self._ignored_depth or tag.casefold() in self._ignored_tags:
            self._ignored_depth += 1
        elif tag.casefold() in {"br", "div", "li", "p", "tr"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_depth:
            self._ignored_depth -= 1
        elif tag.casefold() in {"div", "li", "p", "tr"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

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
_study_session_store = StudySessionStore()
_review_sync_service = ReviewSyncService(
    _review_store,
    AnkiConnectReviewAdapter(_anki_call),
    writeback_enabled=ANKI_REVIEW_WRITEBACK_ENABLED,
)


def _load_session_card(session_id: str, card_id: int) -> dict[str, Any]:
    session = _study_session_store.load(session_id)
    if session is None:
        raise ValueError("study session does not exist")
    for card in session["cards"]:
        if card["card_id"] == card_id:
            return card
    raise ValueError("card is not part of this study session")


def reconcile_session_completion(session_id: str) -> dict[str, Any]:
    """Rebuild lifecycle from durable evidence without contacting Anki."""
    session = _study_session_store.load(session_id)
    if session is None:
        raise ValueError("study session does not exist")
    triage = _tutor_engine.build_triage_view(session["cards"])
    active_card_ids = [
        int(card["card_id"]) for card in triage["active_learning_cards"]
    ]
    return _study_session_store.refresh_completion(
        session_id,
        triage_complete=bool(triage["triage_complete"]),
        active_card_ids=active_card_ids,
        review_events=_review_store.list_for_session(session_id),
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


def _plain_triage_text(value: Any) -> str:
    extractor = _CompactTextExtractor()
    extractor.feed("" if value is None else str(value))
    extractor.close()
    text = "".join(extractor.parts)
    text = re.sub(r"\[sound:[^\]]+\]", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _compact_triage_fields(fields: Any) -> dict[str, str]:
    """Keep bounded semantic snippets rather than raw note/card payloads."""
    if not isinstance(fields, dict):
        return {}

    noise_markers = {
        "audio",
        "css",
        "link",
        "media",
        "sound",
        "source",
        "style",
        "uri",
        "url",
    }
    dictionary_markers = {"add dw", "collins", "dictionary", "glossary"}
    primary: list[tuple[str, str]] = []
    fallback: list[tuple[str, str]] = []
    seen_text: set[str] = set()

    for raw_name, raw_value in fields.items():
        name = str(raw_name).strip()
        normalized_name = " ".join(
            name.casefold().replace("_", " ").replace("-", " ").split()
        )
        if not name or any(marker in normalized_name for marker in noise_markers):
            continue
        text = _plain_triage_text(raw_value)
        fingerprint = text.casefold()
        if not text or fingerprint in seen_text:
            continue
        seen_text.add(fingerprint)
        target = (
            fallback
            if any(marker in normalized_name for marker in dictionary_markers)
            else primary
        )
        target.append((name[:80], text))

    result: dict[str, str] = {}
    remaining = MAX_TRIAGE_CONTENT_CHARS_PER_CARD
    for name, text in primary + fallback:
        if len(result) >= MAX_TRIAGE_FIELDS_PER_CARD or remaining <= 0:
            break
        limit = min(MAX_TRIAGE_FIELD_CHARS, remaining)
        if len(text) > limit:
            text = text[: max(1, limit - 1)].rstrip() + "…"
        result[name] = text
        remaining -= len(text)
    return result


def _compact_triage_response(
    session: dict[str, Any], triage: dict[str, Any]
) -> dict[str, Any]:
    effective = triage["effective_results"]
    cards = []
    for position, card in enumerate(session["cards"], start=1):
        card_id = int(card["card_id"])
        event = effective.get(str(card_id))
        triage_state = None
        if event is not None:
            triage_state = {
                "treatment": event["treatment"],
                "source": event["source"],
                "reason": _plain_triage_text(event.get("reason", ""))[:400],
            }
        cards.append(
            {
                "position": position,
                "card_id": card_id,
                "note_id": int(card["note_id"]),
                "deck": str(card.get("deck", "")),
                "model": str(card.get("model", "")),
                "content_fields": _compact_triage_fields(card.get("fields")),
                "triage": triage_state,
            }
        )

    def card_ids(key: str) -> list[int]:
        return [int(card["card_id"]) for card in triage[key]]

    return {
        "has_study_session": True,
        "mode": "triage",
        "session_id": str(session["session_id"]),
        "candidate_count": len(cards),
        "triage_complete": triage["triage_complete"],
        "cards": cards,
        "untriaged_card_ids": card_ids("untriaged_cards"),
        "active_card_ids": card_ids("active_learning_cards"),
        "reference_card_ids": card_ids("reference_cards"),
        "ignored_card_ids": card_ids("ignored_cards"),
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
        title="Read the active durable study session",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def get_study_session(
    session_id: str | None = None,
    mode: Literal["full", "triage"] = "full",
) -> dict[str, Any]:
    """Load an Anki-created card batch and its durable local progress.

    With no ID, this returns the latest immutable candidate batch plus durable
    triage-derived queues. Untriaged cards must be classified before teaching;
    only the active learning cards are included in the Voice handoff. Use triage
    mode to read bounded semantic snippets without the full Voice payload. This
    operation never modifies Anki or local learner state.
    """
    if mode not in {"full", "triage"}:
        raise ValueError("mode must be full or triage")
    session = _study_session_store.load(session_id)
    if session is None:
        missing = {
            "has_study_session": False,
            "session_id": session_id,
            "cards": [],
        }
        if mode == "triage":
            missing["mode"] = "triage"
        return missing

    triage = _tutor_engine.build_triage_view(session["cards"])
    completion = _study_session_store.load_completion(str(session["session_id"]))
    if mode == "triage":
        return {**_compact_triage_response(session, triage), "completion": completion}

    active_cards = triage["active_learning_cards"]
    card_ids = [int(card["card_id"]) for card in active_cards]
    progress = _tutor_engine.build_session_progress(
        str(session["session_id"]), card_ids
    )
    reviews = _review_store.list_for_session(str(session["session_id"]))
    active_card_ids = set(card_ids)
    reviewed_card_ids = {
        event.card_id for event in reviews if event.card_id in active_card_ids
    }
    durable_completed = reviewed_card_ids | set(progress["skipped_card_ids"])
    teaching_complete = progress["completed_card_ids"]
    active_session = {**session, "cards": active_cards}
    return {
        **session,
        "has_study_session": True,
        "triage_complete": triage["triage_complete"],
        "triage_results": triage["effective_results"],
        "untriaged_cards": triage["untriaged_cards"],
        "active_learning_cards": active_cards,
        "reference_cards": triage["reference_cards"],
        "ignored_cards": triage["ignored_cards"],
        "completion": completion,
        "voice_handoff": build_voice_handoff(active_session),
        "progress": {
            **progress,
            "candidate_card_ids": [
                int(card["card_id"]) for card in session["cards"]
            ],
            "active_card_ids": card_ids,
            "teaching_complete_card_ids": teaching_complete,
            "completed_card_ids": [
                card_id for card_id in card_ids if card_id in durable_completed
            ],
            "remaining_card_ids": [
                card_id for card_id in card_ids if card_id not in durable_completed
            ],
            "complete": triage["triage_complete"]
            and all(card_id in durable_completed for card_id in card_ids),
            "review_events": [
                {
                    "event_id": event.event_id,
                    "card_id": event.card_id,
                    "mapped_anki_rating": event.mapped_anki_rating.value,
                    "sync_status": event.sync_status.value,
                }
                for event in reviews
            ],
        },
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Record Teacher Triage results for a candidate batch",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )
)
def record_triage_results(
    session_id: str,
    results: list[TriageResultInput],
) -> dict[str, Any]:
    """Append a batch of local triage decisions without changing Anki.

    Each result requires `card_id`, `treatment`, `source`, and `reason`.
    Treatment is reference, understand, remember, apply, practice, or ignore;
    source is teacher or learner_override. The candidate StudySession stays
    immutable, and this operation creates no ReviewEvent.
    """
    session = _study_session_store.load(session_id)
    if session is None:
        raise ValueError("study session does not exist")
    if not isinstance(results, list) or not 1 <= len(results) <= MAX_CARDS_PER_CALL:
        raise ValueError(
            f"results must contain between 1 and {MAX_CARDS_PER_CALL} items"
        )

    cards_by_id = {int(card["card_id"]): card for card in session["cards"]}
    seen: set[int] = set()
    events: list[TriageEvent] = []
    created_at = datetime.now(timezone.utc).isoformat()
    required = {"card_id", "treatment", "source", "reason"}
    for result in results:
        if not isinstance(result, dict) or set(result) != required:
            raise ValueError(
                "each result must contain only card_id, treatment, source, and reason"
            )
        raw_card_id = result["card_id"]
        if isinstance(raw_card_id, bool) or not isinstance(raw_card_id, int):
            raise ValueError("card_id must be a positive integer")
        card_id = raw_card_id
        if card_id not in cards_by_id:
            raise ValueError("card is not part of this study session")
        if card_id in seen:
            raise ValueError("a triage batch cannot contain duplicate card ids")
        seen.add(card_id)
        reason = str(result["reason"]).strip()
        events.append(
            TriageEvent(
                event_id=f"triage_{uuid4().hex}",
                session_id=session_id,
                card_id=card_id,
                note_id=int(cards_by_id[card_id]["note_id"]),
                treatment=TriageTreatment(result["treatment"]),
                source=TriageSource(result["source"]),
                reason=reason,
                created_at=created_at,
            )
        )

    _tutor_engine.record_triage_events(events)
    completion = reconcile_session_completion(session_id)
    return {
        "session_id": session_id,
        "recorded_count": len(events),
        "results": [event.to_dict() for event in events],
        "completion": completion,
        "candidate_manifest_mutated": False,
        "review_events_created": 0,
        "anki_mutated": False,
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Read compact durable Tutor context for one card",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def get_tutor_context(card_id: int) -> dict[str, Any]:
    """Resume teaching context for one card without ChatGPT history or Anki.

    The result is reconstructed only from local durable Tutor events, includes at
    most five recent events for this card, and never reads or mutates Anki.
    """
    return _tutor_engine.build_tutor_context(card_id)


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
    session_id: str | None = None,
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
    if session_id is not None:
        _load_session_card(session_id, card_id)
    context = TutorContext(
        card_id=card_id,
        session_id=session_id,
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
        "session_id": session_id,
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
    session_id: str | None = None,
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
    if session_id is not None:
        session_card = _load_session_card(session_id, card_id)
        expected_snapshot = SchedulerSnapshot.from_mapping(
            session_card["scheduler_snapshot"]
        )
        if snapshot != expected_snapshot:
            raise ValueError(
                "scheduler_snapshot does not match the durable study session"
            )
        expected_note_id = session_card.get("note_id")
        if note_id is not None and note_id != expected_note_id:
            raise ValueError("note_id does not match the durable study session")
        note_id = expected_note_id
    event = build_review_event(
        session_id=session_id,
        card_id=card_id,
        note_id=note_id,
        first_attempt_result=FirstAttemptResult(first_attempt_result),
        tutor_state=LearnerState(tutor_state),
        hints_used=hints_used,
        scheduler_snapshot=snapshot,
    )
    if event is None:
        completion = (
            reconcile_session_completion(session_id)
            if session_id is not None
            else None
        )
        return {
            "recorded": False,
            "duplicate": False,
            "event_id": None,
            "sync_status": ReviewSyncStatus.NOT_APPLICABLE.value,
            "reason": "no genuine first unaided retrieval attempt",
            "completion": completion,
            "anki_mutated": False,
        }

    stored, created = _review_store.create_or_get(event)
    completion = (
        reconcile_session_completion(session_id)
        if session_id is not None
        else None
    )
    return {
        "recorded": True,
        "duplicate": not created,
        "anki_mutated": False,
        "completion": completion,
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
    session_id: str | None = None,
) -> dict[str, Any]:
    """Inspect or synchronize durable pending ReviewEvents one card at a time.

    `dry_run` defaults to true. Real scheduler writes also require the process-level
    `ANKI_REVIEW_WRITEBACK_ENABLED=true` feature flag. Before any enabled write,
    the current Anki card snapshot must exactly match the event snapshot. The
    adapter uses AnkiConnect's scheduler-backed `answerCards` action; it never
    edits Anki DB rows or FSRS fields directly. Only a confirmed `[true]` response
    marks an event applied.
    """
    if session_id is not None and _study_session_store.load(session_id) is None:
        raise ValueError("study session does not exist")
    result = _review_sync_service.sync_pending(
        dry_run=dry_run,
        limit=limit,
        session_id=session_id,
    )
    completions: dict[str, dict[str, Any]] = {}
    if not result["dry_run"]:
        affected_session_ids = {session_id} if session_id is not None else set()
        for item in result["results"]:
            event = _review_store.get(item["event_id"])
            if event is not None and event.session_id is not None:
                affected_session_ids.add(event.session_id)
        for affected_session_id in sorted(affected_session_ids):
            completions[affected_session_id] = reconcile_session_completion(
                affected_session_id
            )
    return {**result, "session_completions": completions}



if __name__ == "__main__":
    # stdio is the MCP SDK default and is supported by OpenAI Secure MCP Tunnel.
    mcp.run()
