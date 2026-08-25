from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import anki_mcp_server as server
from learner_store import JsonlLearnerStore, SqliteReviewStore
from models import ReviewEvent, ReviewSyncStatus, SchedulerSnapshot
from review_sync import ReviewSyncService
from study_session import StudySessionStore
from tutor_engine import TutorEngine


def write_session(
    directory: str, session_id: str, card_ids: tuple[int, ...]
) -> StudySessionStore:
    store = StudySessionStore(directory)
    store.sessions_directory.mkdir(parents=True)
    cards = []
    for offset, card_id in enumerate(card_ids):
        cards.append(
            {
                "card_id": card_id,
                "note_id": card_id + 1_000,
                "deck": "Test Deck",
                "model": "Basic",
                "fields": {"Prompt": f"Q{card_id}", "Answer": f"A{card_id}"},
                "scheduler_snapshot": {
                    "modified": 100 + offset,
                    "reps": 0,
                    "lapses": 0,
                    "queue": 0,
                    "card_type": 0,
                    "due": offset + 1,
                    "interval": 0,
                    "factor": 0,
                    "left": 0,
                },
                "retrievability": None,
            }
        )
    manifest = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at": "2026-08-24T12:00:00+00:00",
        "status": "active",
        "decks": ["Test Deck"],
        "requested_count": len(cards),
        "include_new": False,
        "selection_method": "test",
        "cards": cards,
    }
    (store.sessions_directory / f"{session_id}.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    store.active_path.write_text(
        json.dumps({"session_id": session_id}), encoding="utf-8"
    )
    return store


class ConfirmingReviewAdapter:
    def __init__(self, snapshots: dict[int, SchedulerSnapshot]) -> None:
        self.snapshots = snapshots
        self.apply_calls: list[int] = []

    def get_scheduler_snapshot(self, card_id: int) -> SchedulerSnapshot | None:
        return self.snapshots.get(card_id)

    def apply_review(self, event: ReviewEvent) -> bool:
        self.apply_calls.append(event.card_id)
        return True


class StudySessionCompletionTests(unittest.TestCase):
    def _record_review(
        self,
        session: dict,
        card_id: int,
        *,
        tutor_state: str = "independent_recall",
    ) -> dict:
        card = next(card for card in session["cards"] if card["card_id"] == card_id)
        return server.record_review_result(
            session_id=session["session_id"],
            card_id=card_id,
            note_id=card["note_id"],
            first_attempt_result="succeeded",
            tutor_state=tutor_state,
            hints_used=0,
            scheduler_snapshot=card["scheduler_snapshot"],
        )

    def test_partial_then_pending_then_applied_completion_survives_restart(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "a" * 32
            session_store = write_session(directory, session_id, (101, 102, 103))
            session = session_store.load(session_id)
            assert session is not None
            learner_store = JsonlLearnerStore(Path(directory) / "tutor.jsonl")
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            engine = TutorEngine(learner_store)
            snapshots = {
                card["card_id"]: SchedulerSnapshot.from_mapping(
                    card["scheduler_snapshot"]
                )
                for card in session["cards"]
            }
            adapter = ConfirmingReviewAdapter(snapshots)
            sync_service = ReviewSyncService(
                review_store, adapter, writeback_enabled=True
            )

            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_review_sync_service", sync_service),
                patch.object(server, "_anki_call") as anki_call,
            ):
                server.record_triage_results(
                    session_id=session_id,
                    results=[
                        {
                            "card_id": 101,
                            "treatment": "remember",
                            "source": "teacher",
                            "reason": "recall matters",
                        },
                        {
                            "card_id": 102,
                            "treatment": "apply",
                            "source": "teacher",
                            "reason": "transfer matters",
                        },
                        {
                            "card_id": 103,
                            "treatment": "reference",
                            "source": "teacher",
                            "reason": "lookup only",
                        },
                    ],
                )

                first = self._record_review(session, 101)
                self.assertFalse(first["completion"]["learning_complete"])
                self.assertFalse(first["completion"]["sync_complete"])

                second = self._record_review(session, 102)
                self.assertTrue(second["completion"]["learning_complete"])
                self.assertFalse(second["completion"]["sync_complete"])
                self.assertEqual(second["completion"]["status"], "active")

                restarted = StudySessionStore(directory)
                self.assertEqual(
                    restarted.load_completion(session_id), second["completion"]
                )

                first_sync = server.sync_pending_reviews(
                    dry_run=False, session_id=session_id
                )
                completed = first_sync["session_completions"][session_id]
                self.assertTrue(completed["learning_complete"])
                self.assertTrue(completed["sync_complete"])
                self.assertEqual(completed["status"], "completed")

                duplicate = self._record_review(session, 102)
                second_sync = server.sync_pending_reviews(
                    dry_run=False, session_id=session_id
                )

            anki_call.assert_not_called()
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(duplicate["completion"], completed)
            self.assertEqual(second_sync["pending_found"], 0)
            self.assertEqual(
                second_sync["session_completions"][session_id], completed
            )
            self.assertEqual(adapter.apply_calls, [101, 102])
            self.assertEqual(
                StudySessionStore(directory).load_completion(session_id), completed
            )

    def test_missing_sidecar_reconciles_historical_durable_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "d" * 32
            card_ids = (401, 402, 403, 404, 405)
            session_store = write_session(directory, session_id, card_ids)
            session = session_store.load(session_id)
            assert session is not None
            learner_store = JsonlLearnerStore(Path(directory) / "tutor.jsonl")
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            engine = TutorEngine(learner_store)

            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_anki_call") as anki_call,
            ):
                server.record_triage_results(
                    session_id=session_id,
                    results=[
                        {
                            "card_id": card_id,
                            "treatment": "remember",
                            "source": "teacher",
                            "reason": "durable recall matters",
                        }
                        for card_id in card_ids
                    ],
                )
                recorded = [
                    self._record_review(session, card_id)
                    for card_id in card_ids
                ]
                for result in recorded[:4]:
                    review_store.record_sync_attempt(
                        result["event_id"],
                        status=ReviewSyncStatus.APPLIED,
                        last_error=None,
                    )

                completion_path = (
                    session_store.completion_directory / f"{session_id}.json"
                )
                completion_path.unlink()
                incomplete = server.reconcile_session_completion(session_id)

                review_store.record_sync_attempt(
                    recorded[4]["event_id"],
                    status=ReviewSyncStatus.APPLIED,
                    last_error=None,
                )
                completion_path.unlink()
                recovered = server.reconcile_session_completion(session_id)
                repeated = server.reconcile_session_completion(session_id)

            anki_call.assert_not_called()
            self.assertTrue(incomplete["learning_complete"])
            self.assertFalse(incomplete["sync_complete"])
            self.assertEqual(incomplete["status"], "active")
            self.assertTrue(recovered["learning_complete"])
            self.assertTrue(recovered["sync_complete"])
            self.assertEqual(recovered["status"], "completed")
            self.assertEqual(repeated, recovered)
            self.assertEqual(
                StudySessionStore(directory).load_completion(session_id), recovered
            )

    def test_reference_and_ignore_only_session_completes_without_reviews(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "b" * 32
            session_store = write_session(directory, session_id, (201, 202))
            learner_store = JsonlLearnerStore(Path(directory) / "tutor.jsonl")
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            engine = TutorEngine(learner_store)

            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_anki_call") as anki_call,
            ):
                result = server.record_triage_results(
                    session_id=session_id,
                    results=[
                        {
                            "card_id": 201,
                            "treatment": "reference",
                            "source": "teacher",
                            "reason": "lookup only",
                        },
                        {
                            "card_id": 202,
                            "treatment": "ignore",
                            "source": "teacher",
                            "reason": "no learning value",
                        },
                    ],
                )
                completion_path = (
                    session_store.completion_directory / f"{session_id}.json"
                )
                completion_path.unlink()
                reconciled = server.reconcile_session_completion(session_id)

            anki_call.assert_not_called()
            self.assertEqual(review_store.list_for_session(session_id), [])
            self.assertTrue(result["completion"]["learning_complete"])
            self.assertTrue(result["completion"]["sync_complete"])
            self.assertEqual(result["completion"]["status"], "completed")
            self.assertEqual(reconciled["status"], "completed")

    def test_paused_card_does_not_complete_after_review_sync(self) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "c" * 32
            session_store = write_session(directory, session_id, (301,))
            session = session_store.load(session_id)
            assert session is not None
            learner_store = JsonlLearnerStore(Path(directory) / "tutor.jsonl")
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            engine = TutorEngine(learner_store)
            snapshot = SchedulerSnapshot.from_mapping(
                session["cards"][0]["scheduler_snapshot"]
            )
            adapter = ConfirmingReviewAdapter({301: snapshot})
            sync_service = ReviewSyncService(
                review_store, adapter, writeback_enabled=True
            )

            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_review_sync_service", sync_service),
            ):
                server.record_triage_results(
                    session_id=session_id,
                    results=[
                        {
                            "card_id": 301,
                            "treatment": "remember",
                            "source": "teacher",
                            "reason": "recall matters",
                        }
                    ],
                )
                recorded = self._record_review(
                    session, 301, tutor_state="paused"
                )
                synced = server.sync_pending_reviews(
                    dry_run=False, session_id=session_id
                )

            self.assertFalse(recorded["completion"]["learning_complete"])
            completion = synced["session_completions"][session_id]
            self.assertFalse(completion["learning_complete"])
            self.assertFalse(completion["sync_complete"])
            self.assertEqual(completion["status"], "active")


if __name__ == "__main__":
    unittest.main()
