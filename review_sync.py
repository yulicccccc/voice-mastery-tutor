"""Durable per-card ReviewEvent creation and guarded Anki synchronization."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Protocol

from learner_store import SqliteReviewStore
from models import (
    AnkiRating,
    FirstAttemptResult,
    LearnerState,
    ReviewEvent,
    ReviewSyncStatus,
    SchedulerSnapshot,
)


class ReviewAdapter(Protocol):
    def get_scheduler_snapshot(self, card_id: int) -> SchedulerSnapshot | None: ...

    def apply_review(self, event: ReviewEvent) -> bool: ...


def build_review_event(
    *,
    card_id: int,
    note_id: int | None,
    first_attempt_result: FirstAttemptResult,
    tutor_state: LearnerState,
    hints_used: int,
    scheduler_snapshot: SchedulerSnapshot,
) -> ReviewEvent | None:
    if card_id < 1:
        raise ValueError("card_id must be a positive integer")
    if hints_used < 0:
        raise ValueError("hints_used must not be negative")
    if first_attempt_result == FirstAttemptResult.NOT_ATTEMPTED:
        return None

    rating = (
        AnkiRating.GOOD
        if first_attempt_result == FirstAttemptResult.SUCCEEDED
        else AnkiRating.AGAIN
    )
    return ReviewEvent(
        event_id=ReviewEvent.stable_event_id(card_id, scheduler_snapshot),
        card_id=card_id,
        note_id=note_id,
        first_attempt_result=first_attempt_result,
        mapped_anki_rating=rating,
        tutor_state=tutor_state,
        hints_used=hints_used,
        scheduler_snapshot=scheduler_snapshot,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class AnkiConnectReviewAdapter:
    """Use AnkiConnect's scheduler-backed answerCards action."""

    def __init__(
        self,
        anki_call: Callable[[str, dict[str, Any] | None], Any],
    ) -> None:
        self._anki_call = anki_call

    def get_scheduler_snapshot(self, card_id: int) -> SchedulerSnapshot | None:
        cards = self._anki_call("cardsInfo", {"cards": [card_id]})
        if not isinstance(cards, list) or len(cards) != 1:
            return None
        card = cards[0]
        if not isinstance(card, dict) or card.get("cardId") != card_id:
            return None
        return SchedulerSnapshot.from_mapping(card)

    def apply_review(self, event: ReviewEvent) -> bool:
        result = self._anki_call(
            "answerCards",
            {
                "answers": [
                    {
                        "cardId": event.card_id,
                        "ease": event.mapped_anki_rating.ease,
                    }
                ]
            },
        )
        return result == [True]


class ReviewSyncService:
    def __init__(
        self,
        store: SqliteReviewStore,
        adapter: ReviewAdapter,
        *,
        writeback_enabled: bool = False,
    ) -> None:
        self.store = store
        self.adapter = adapter
        self.writeback_enabled = writeback_enabled
        self._sync_lock = Lock()

    def sync_pending(
        self, *, dry_run: bool = True, limit: int = 100
    ) -> dict[str, Any]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")

        effective_dry_run = dry_run or not self.writeback_enabled
        with self._sync_lock:
            pending = self.store.list_by_status(ReviewSyncStatus.PENDING, limit)
            results = [
                self._sync_one(event, dry_run=effective_dry_run)
                for event in pending
            ]

        return {
            "dry_run": effective_dry_run,
            "writeback_enabled": self.writeback_enabled,
            "pending_found": len(pending),
            "applied": sum(item["status"] == "applied" for item in results),
            "conflicted": sum(
                item["status"] == "conflicted" for item in results
            ),
            "failed": sum(item["status"] == "failed" for item in results),
            "still_pending": sum(
                item["status"] == "pending" for item in results
            ),
            "results": results,
        }

    def _sync_one(
        self, event: ReviewEvent, *, dry_run: bool
    ) -> dict[str, Any]:
        try:
            current_snapshot = self.adapter.get_scheduler_snapshot(event.card_id)
        except Exception as exc:
            error = f"Anki unavailable: {exc}"
            if not dry_run:
                self.store.record_sync_attempt(
                    event.event_id,
                    status=ReviewSyncStatus.PENDING,
                    last_error=error,
                )
            return self._result(event, "pending", "retry_later", error)

        if current_snapshot is None:
            error = "card is unavailable in Anki"
            if dry_run:
                return self._result(event, "pending", "would_fail", error)
            self.store.record_sync_attempt(
                event.event_id,
                status=ReviewSyncStatus.FAILED,
                last_error=error,
            )
            return self._result(event, "failed", "card_unavailable", error)

        if current_snapshot != event.scheduler_snapshot:
            error = "scheduler snapshot changed after ReviewEvent creation"
            if dry_run:
                return self._result(
                    event, "pending", "would_conflict", error
                )
            self.store.record_sync_attempt(
                event.event_id,
                status=ReviewSyncStatus.CONFLICTED,
                last_error=error,
            )
            return self._result(event, "conflicted", "do_not_apply", error)

        if dry_run:
            action = (
                "would_apply"
                if self.writeback_enabled
                else "writeback_disabled"
            )
            return self._result(event, "pending", action, None)

        try:
            confirmed = self.adapter.apply_review(event)
        except Exception as exc:
            error = f"Anki review call failed: {exc}"
            self.store.record_sync_attempt(
                event.event_id,
                status=ReviewSyncStatus.PENDING,
                last_error=error,
            )
            return self._result(event, "pending", "retry_later", error)

        if not confirmed:
            error = "Anki review call did not confirm success"
            self.store.record_sync_attempt(
                event.event_id,
                status=ReviewSyncStatus.FAILED,
                last_error=error,
            )
            return self._result(event, "failed", "not_confirmed", error)

        self.store.record_sync_attempt(
            event.event_id,
            status=ReviewSyncStatus.APPLIED,
            last_error=None,
        )
        return self._result(event, "applied", "review_confirmed", None)

    @staticmethod
    def _result(
        event: ReviewEvent,
        status: str,
        action: str,
        error: str | None,
    ) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "card_id": event.card_id,
            "status": status,
            "action": action,
            "error": error,
        }
