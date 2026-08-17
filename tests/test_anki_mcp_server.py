from __future__ import annotations

import asyncio
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import anki_mcp_server as server
from learner_store import JsonlLearnerStore, SqliteReviewStore
from tutor_engine import TutorEngine


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


if __name__ == "__main__":
    unittest.main()
