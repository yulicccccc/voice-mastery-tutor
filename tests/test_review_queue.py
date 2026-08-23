from __future__ import annotations

import stat
import sqlite3
import tempfile
import unittest
from pathlib import Path

from learner_store import SqliteReviewStore
from models import (
    AnkiRating,
    FirstAttemptResult,
    LearnerState,
    ReviewSyncStatus,
    SchedulerSnapshot,
)
from review_sync import ReviewSyncService, build_review_event


def snapshot(*, modified: int = 100, reps: int = 4) -> SchedulerSnapshot:
    return SchedulerSnapshot(
        modified=modified,
        reps=reps,
        lapses=1,
        queue=2,
        card_type=2,
        due=1234,
        interval=7,
        factor=2500,
        left=0,
    )


class FakeReviewAdapter:
    def __init__(
        self,
        current_snapshot: SchedulerSnapshot | None,
        *,
        apply_result: bool = True,
        snapshot_error: Exception | None = None,
        apply_error: Exception | None = None,
    ) -> None:
        self.current_snapshot = current_snapshot
        self.apply_result = apply_result
        self.snapshot_error = snapshot_error
        self.apply_error = apply_error
        self.apply_calls = 0

    def get_scheduler_snapshot(self, card_id: int) -> SchedulerSnapshot | None:
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return self.current_snapshot

    def apply_review(self, event) -> bool:
        self.apply_calls += 1
        if self.apply_error is not None:
            raise self.apply_error
        return self.apply_result


class ReviewQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_directory.name) / "review-events.sqlite3"
        self.store = SqliteReviewStore(self.path)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def record(
        self,
        *,
        first_attempt: FirstAttemptResult,
        session_id: str | None = None,
        card_id: int = 123,
        tutor_state: LearnerState = LearnerState.INDEPENDENT_RECALL,
        hints_used: int = 0,
        scheduler_snapshot: SchedulerSnapshot | None = None,
    ):
        event = build_review_event(
            session_id=session_id,
            card_id=card_id,
            note_id=456,
            first_attempt_result=first_attempt,
            tutor_state=tutor_state,
            hints_used=hints_used,
            scheduler_snapshot=scheduler_snapshot or snapshot(),
        )
        if event is None:
            return None, False
        return self.store.create_or_get(event)

    def test_independent_correct_creates_one_pending_good_event(self) -> None:
        event, created = self.record(
            first_attempt=FirstAttemptResult.SUCCEEDED
        )

        self.assertTrue(created)
        self.assertEqual(event.mapped_anki_rating, AnkiRating.GOOD)
        self.assertEqual(event.sync_status, ReviewSyncStatus.PENDING)
        self.assertEqual(
            len(self.store.list_by_status(ReviewSyncStatus.PENDING)), 1
        )

    def test_failed_first_attempt_stays_again_after_repair(self) -> None:
        event, created = self.record(
            first_attempt=FirstAttemptResult.FAILED,
            tutor_state=LearnerState.PROMPTED_RECALL,
            hints_used=1,
        )

        self.assertTrue(created)
        self.assertEqual(event.mapped_anki_rating, AnkiRating.AGAIN)
        self.assertEqual(event.tutor_state, LearnerState.PROMPTED_RECALL)
        self.assertEqual(event.hints_used, 1)

    def test_repeated_retry_does_not_create_second_review_event(self) -> None:
        first, first_created = self.record(
            first_attempt=FirstAttemptResult.FAILED,
            tutor_state=LearnerState.PROMPTED_RECALL,
            hints_used=1,
        )
        duplicate, duplicate_created = self.record(
            first_attempt=FirstAttemptResult.FAILED,
            tutor_state=LearnerState.PROMPTED_RECALL,
            hints_used=1,
        )

        self.assertTrue(first_created)
        self.assertFalse(duplicate_created)
        self.assertEqual(first.event_id, duplicate.event_id)
        self.assertEqual(
            len(self.store.list_by_status(ReviewSyncStatus.PENDING)), 1
        )

    def test_low_value_skip_without_attempt_creates_no_review_event(self) -> None:
        event, created = self.record(
            first_attempt=FirstAttemptResult.NOT_ATTEMPTED,
            tutor_state=LearnerState.SKIPPED_LOW_VALUE,
        )

        self.assertIsNone(event)
        self.assertFalse(created)
        self.assertEqual(
            self.store.list_by_status(ReviewSyncStatus.PENDING), []
        )

    def test_process_restart_recovers_pending_event(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)

        restarted_store = SqliteReviewStore(self.path)
        recovered = restarted_store.list_by_status(ReviewSyncStatus.PENDING)

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].event_id, event.event_id)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_process_restart_recovers_session_bound_pending_event(self) -> None:
        session_id = "study_" + "c" * 32
        event, _ = self.record(
            first_attempt=FirstAttemptResult.FAILED,
            session_id=session_id,
        )

        restarted = SqliteReviewStore(self.path)
        recovered = restarted.list_by_status(
            ReviewSyncStatus.PENDING, session_id=session_id
        )

        self.assertEqual([item.event_id for item in recovered], [event.event_id])
        self.assertEqual(recovered[0].session_id, session_id)

    def test_existing_review_database_is_migrated_for_session_ids(self) -> None:
        old_schema = SqliteReviewStore._SCHEMA.replace(
            "            session_id text,\n", ""
        )
        with sqlite3.connect(self.path) as connection:
            connection.execute(old_schema)

        migrated = SqliteReviewStore(self.path)
        migrated.list_by_status(ReviewSyncStatus.PENDING)

        with sqlite3.connect(self.path) as connection:
            columns = {
                row[1]
                for row in connection.execute("pragma table_info(review_events)")
            }
        self.assertIn("session_id", columns)

    def test_session_filtered_sync_does_not_touch_another_batch(self) -> None:
        session_a = "study_" + "a" * 32
        session_b = "study_" + "b" * 32
        event_a, _ = self.record(
            first_attempt=FirstAttemptResult.SUCCEEDED,
            session_id=session_a,
            card_id=123,
        )
        event_b, _ = self.record(
            first_attempt=FirstAttemptResult.FAILED,
            session_id=session_b,
            card_id=124,
        )
        adapter = FakeReviewAdapter(snapshot())
        service = ReviewSyncService(self.store, adapter, writeback_enabled=True)

        result = service.sync_pending(dry_run=False, session_id=session_a)

        self.assertEqual(result["session_id"], session_a)
        self.assertEqual(result["pending_found"], 1)
        self.assertEqual(result["applied"], 1)
        self.assertEqual(adapter.apply_calls, 1)
        self.assertEqual(
            self.store.get(event_a.event_id).sync_status,
            ReviewSyncStatus.APPLIED,
        )
        self.assertEqual(
            self.store.get(event_b.event_id).sync_status,
            ReviewSyncStatus.PENDING,
        )
        self.assertEqual(
            [event.event_id for event in self.store.list_for_session(session_b)],
            [event_b.event_id],
        )

    def test_anki_unavailable_keeps_event_pending(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        adapter = FakeReviewAdapter(
            snapshot(), snapshot_error=RuntimeError("offline")
        )
        service = ReviewSyncService(
            self.store, adapter, writeback_enabled=True
        )

        result = service.sync_pending(dry_run=False)
        stored = self.store.get(event.event_id)

        self.assertEqual(result["still_pending"], 1)
        self.assertEqual(stored.sync_status, ReviewSyncStatus.PENDING)
        self.assertEqual(stored.sync_attempts, 1)
        self.assertIn("offline", stored.last_error)
        self.assertEqual(adapter.apply_calls, 0)

    def test_repeated_sync_never_double_reviews(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        adapter = FakeReviewAdapter(snapshot())
        service = ReviewSyncService(
            self.store, adapter, writeback_enabled=True
        )

        first = service.sync_pending(dry_run=False)
        second = service.sync_pending(dry_run=False)

        self.assertEqual(first["applied"], 1)
        self.assertEqual(second["pending_found"], 0)
        self.assertEqual(adapter.apply_calls, 1)
        self.assertEqual(
            self.store.get(event.event_id).sync_status,
            ReviewSyncStatus.APPLIED,
        )

    def test_lost_write_response_then_retry_does_not_double_review(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        first_adapter = FakeReviewAdapter(
            snapshot(), apply_error=TimeoutError("response lost")
        )
        first_service = ReviewSyncService(
            self.store, first_adapter, writeback_enabled=True
        )

        first_result = first_service.sync_pending(dry_run=False)

        self.assertEqual(first_result["still_pending"], 1)
        self.assertEqual(first_adapter.apply_calls, 1)

        changed_snapshot = snapshot(modified=101, reps=5)
        retry_adapter = FakeReviewAdapter(changed_snapshot)
        retry_service = ReviewSyncService(
            self.store, retry_adapter, writeback_enabled=True
        )
        retry_result = retry_service.sync_pending(dry_run=False)

        self.assertEqual(retry_result["conflicted"], 1)
        self.assertEqual(retry_adapter.apply_calls, 0)
        self.assertEqual(
            self.store.get(event.event_id).sync_status,
            ReviewSyncStatus.CONFLICTED,
        )

    def test_external_scheduler_change_marks_conflicted(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        adapter = FakeReviewAdapter(snapshot(modified=101, reps=5))
        service = ReviewSyncService(
            self.store, adapter, writeback_enabled=True
        )

        result = service.sync_pending(dry_run=False)
        stored = self.store.get(event.event_id)

        self.assertEqual(result["conflicted"], 1)
        self.assertEqual(stored.sync_status, ReviewSyncStatus.CONFLICTED)
        self.assertEqual(adapter.apply_calls, 0)

    def test_dry_run_reports_conflict_without_changing_queue_state(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        adapter = FakeReviewAdapter(snapshot(modified=101, reps=5))
        service = ReviewSyncService(
            self.store, adapter, writeback_enabled=True
        )

        result = service.sync_pending(dry_run=True)
        stored = self.store.get(event.event_id)

        self.assertEqual(result["still_pending"], 1)
        self.assertEqual(result["results"][0]["action"], "would_conflict")
        self.assertEqual(stored.sync_status, ReviewSyncStatus.PENDING)
        self.assertEqual(stored.sync_attempts, 0)
        self.assertEqual(adapter.apply_calls, 0)

    def test_success_is_applied_only_after_confirmed_adapter_result(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        adapter = FakeReviewAdapter(snapshot(), apply_result=True)
        service = ReviewSyncService(
            self.store, adapter, writeback_enabled=True
        )

        result = service.sync_pending(dry_run=False)

        self.assertEqual(result["applied"], 1)
        self.assertEqual(
            self.store.get(event.event_id).sync_status,
            ReviewSyncStatus.APPLIED,
        )

    def test_unconfirmed_sync_is_failed_not_applied(self) -> None:
        event, _ = self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        adapter = FakeReviewAdapter(snapshot(), apply_result=False)
        service = ReviewSyncService(
            self.store, adapter, writeback_enabled=True
        )

        result = service.sync_pending(dry_run=False)
        stored = self.store.get(event.event_id)

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["applied"], 0)
        self.assertEqual(stored.sync_status, ReviewSyncStatus.FAILED)

    def test_dry_run_and_disabled_flag_call_zero_write_operations(self) -> None:
        self.record(first_attempt=FirstAttemptResult.SUCCEEDED)
        enabled_adapter = FakeReviewAdapter(snapshot())
        enabled_service = ReviewSyncService(
            self.store, enabled_adapter, writeback_enabled=True
        )

        dry_result = enabled_service.sync_pending(dry_run=True)

        self.assertTrue(dry_result["dry_run"])
        self.assertEqual(enabled_adapter.apply_calls, 0)

        disabled_adapter = FakeReviewAdapter(snapshot())
        disabled_service = ReviewSyncService(
            self.store, disabled_adapter, writeback_enabled=False
        )
        disabled_result = disabled_service.sync_pending(dry_run=False)

        self.assertTrue(disabled_result["dry_run"])
        self.assertFalse(disabled_result["writeback_enabled"])
        self.assertEqual(disabled_adapter.apply_calls, 0)


if __name__ == "__main__":
    unittest.main()
