from __future__ import annotations

import asyncio
import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import anki_mcp_server as server
from learner_store import JsonlLearnerStore, SqliteReviewStore
from study_session import StudySessionStore
from tutor_engine import TutorEngine


def write_session(directory: str, *, session_id: str) -> StudySessionStore:
    store = StudySessionStore(directory)
    store.sessions_directory.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at": "2026-08-17T12:00:00+00:00",
        "status": "active",
        "decks": ["000-WuCai Inbox"],
        "requested_count": 1,
        "include_new": False,
        "selection_method": "anki-native-fsrs-retrievability",
        "cards": [
            {
                "card_id": 123,
                "note_id": 456,
                "deck": "000-WuCai Inbox",
                "model": "Basic",
                "fields": {"Prompt": "Q", "Response": "A"},
                "scheduler_snapshot": ReviewToolBoundaryTests.scheduler_snapshot(),
                "retrievability": 0.4,
            }
        ],
    }
    (store.sessions_directory / f"{session_id}.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    store.active_path.write_text(
        json.dumps({"session_id": session_id}), encoding="utf-8"
    )
    return store


class TutorToolBoundaryTests(unittest.TestCase):
    def test_tutor_decision_persists_locally_without_calling_anki(self) -> None:
        with TemporaryDirectory() as directory:
            engine = TutorEngine(
                JsonlLearnerStore(Path(directory) / "tutor-events.jsonl")
            )
            with (
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_anki_call") as anki_call,
            ):
                result = server.decide_tutor_next_step(
                    card_id=123,
                    learner_answer="I don't know",
                    assessment="unknown",
                )

            anki_call.assert_not_called()
            self.assertTrue(result["event_saved_locally"])
            self.assertFalse(result["anki_mutated"])

    def test_low_value_skip_only_writes_tutor_event_not_anki(self) -> None:
        with TemporaryDirectory() as directory:
            store = JsonlLearnerStore(Path(directory) / "tutor-events.jsonl")
            engine = TutorEngine(store)
            with (
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_anki_call") as anki_call,
            ):
                result = server.decide_tutor_next_step(
                    card_id=123,
                    learner_answer="I don't want to learn this card",
                    assessment="unknown",
                )

            anki_call.assert_not_called()
            self.assertEqual(result["state"], "skipped_low_value")
            self.assertFalse(result["anki_mutated"])
            self.assertEqual(store.read_all()[0]["state"], "skipped_low_value")

    def test_mastery_candidate_does_not_change_or_stop_anki_review(self) -> None:
        with TemporaryDirectory() as directory:
            engine = TutorEngine(
                JsonlLearnerStore(Path(directory) / "tutor-events.jsonl")
            )
            with (
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_anki_call") as anki_call,
            ):
                result = server.decide_tutor_next_step(
                    card_id=123,
                    learner_answer="A correct explanation",
                    assessment="correct",
                )

            anki_call.assert_not_called()
            self.assertEqual(result["state"], "independent_recall")
            self.assertTrue(result["mastered_candidate"])
            self.assertTrue(result["continue_session"])
            self.assertFalse(result["anki_mutated"])

    def test_tool_annotations_describe_local_non_destructive_append(self) -> None:
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
        annotations = tools["decide_tutor_next_step"].annotations

        self.assertFalse(annotations.readOnlyHint)
        self.assertFalse(annotations.destructiveHint)
        self.assertFalse(annotations.idempotentHint)
        self.assertFalse(annotations.openWorldHint)
        self.assertIn(
            "learner_rejects_mastery",
            tools["decide_tutor_next_step"].inputSchema["properties"],
        )


class ReviewToolBoundaryTests(unittest.TestCase):
    @staticmethod
    def scheduler_snapshot():
        return {
            "modified": 100,
            "reps": 4,
            "lapses": 1,
            "queue": 2,
            "card_type": 2,
            "due": 1234,
            "interval": 7,
            "factor": 2500,
            "left": 0,
        }

    def test_record_review_result_is_durable_and_never_calls_anki(self) -> None:
        with TemporaryDirectory() as directory:
            store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            with (
                patch.object(server, "_review_store", store),
                patch.object(server, "_anki_call") as anki_call,
            ):
                first = server.record_review_result(
                    card_id=123,
                    note_id=456,
                    first_attempt_result="succeeded",
                    tutor_state="independent_recall",
                    hints_used=0,
                    scheduler_snapshot=self.scheduler_snapshot(),
                )
                duplicate = server.record_review_result(
                    card_id=123,
                    note_id=456,
                    first_attempt_result="succeeded",
                    tutor_state="independent_recall",
                    hints_used=0,
                    scheduler_snapshot=self.scheduler_snapshot(),
                )

            anki_call.assert_not_called()
            self.assertTrue(first["recorded"])
            self.assertEqual(first["mapped_anki_rating"], "Good")
            self.assertEqual(first["sync_status"], "pending")
            self.assertFalse(first["duplicate"])
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(first["event_id"], duplicate["event_id"])

    def test_low_value_no_attempt_returns_not_applicable_without_event(self) -> None:
        with TemporaryDirectory() as directory:
            store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            with (
                patch.object(server, "_review_store", store),
                patch.object(server, "_anki_call") as anki_call,
            ):
                result = server.record_review_result(
                    card_id=123,
                    note_id=456,
                    first_attempt_result="not_attempted",
                    tutor_state="skipped_low_value",
                    hints_used=0,
                    scheduler_snapshot=self.scheduler_snapshot(),
                )

            anki_call.assert_not_called()
            self.assertFalse(result["recorded"])
            self.assertEqual(result["sync_status"], "not_applicable")
            self.assertEqual(store.list_by_status(server.ReviewSyncStatus.PENDING), [])

    def test_review_tool_annotations_match_durable_idempotent_writes(self) -> None:
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}

        for name in ("record_review_result", "sync_pending_reviews"):
            annotations = tools[name].annotations
            self.assertFalse(annotations.readOnlyHint)
            self.assertFalse(annotations.destructiveHint)
            self.assertTrue(annotations.idempotentHint)
            self.assertFalse(annotations.openWorldHint)

        dry_run_schema = tools["sync_pending_reviews"].inputSchema["properties"][
            "dry_run"
        ]
        self.assertTrue(dry_run_schema["default"])


class StudySessionToolTests(unittest.TestCase):
    def test_study_session_tool_is_read_only(self) -> None:
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
        annotations = tools["get_study_session"].annotations
        self.assertTrue(annotations.readOnlyHint)
        self.assertFalse(annotations.destructiveHint)
        self.assertTrue(annotations.idempotentHint)
        self.assertFalse(annotations.openWorldHint)

    def test_active_session_and_progress_are_recovered_without_anki(self) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "a" * 32
            session_store = write_session(directory, session_id=session_id)
            learner_store = JsonlLearnerStore(Path(directory) / "tutor.jsonl")
            engine = TutorEngine(learner_store)
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_anki_call") as anki_call,
            ):
                server.decide_tutor_next_step(
                    session_id=session_id,
                    card_id=123,
                    learner_answer="correct",
                    assessment="correct",
                )
                before_review_event = server.get_study_session()
                server.record_review_result(
                    session_id=session_id,
                    card_id=123,
                    note_id=456,
                    first_attempt_result="succeeded",
                    tutor_state="independent_recall",
                    hints_used=0,
                    scheduler_snapshot=ReviewToolBoundaryTests.scheduler_snapshot(),
                )
                result = server.get_study_session()

            anki_call.assert_not_called()
            self.assertEqual(
                before_review_event["progress"]["remaining_card_ids"], [123]
            )
            self.assertTrue(result["has_study_session"])
            self.assertEqual(result["session_id"], session_id)
            self.assertEqual(result["voice_handoff"]["card_count"], 1)
            self.assertIn("Q", result["voice_handoff"]["packet_markdown"])
            self.assertEqual(result["progress"]["completed_card_ids"], [123])
            self.assertEqual(result["progress"]["remaining_card_ids"], [])
            self.assertTrue(result["progress"]["complete"])

    def test_review_snapshot_must_match_selected_session_card(self) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "b" * 32
            session_store = write_session(directory, session_id=session_id)
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            wrong = {**ReviewToolBoundaryTests.scheduler_snapshot(), "reps": 99}
            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_anki_call") as anki_call,
                self.assertRaises(ValueError),
            ):
                server.record_review_result(
                    session_id=session_id,
                    card_id=123,
                    note_id=456,
                    first_attempt_result="failed",
                    tutor_state="prompted_recall",
                    hints_used=1,
                    scheduler_snapshot=wrong,
                )

            anki_call.assert_not_called()
            self.assertEqual(
                review_store.list_by_status(server.ReviewSyncStatus.PENDING), []
            )


if __name__ == "__main__":
    unittest.main()
