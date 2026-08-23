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


def write_session(
    directory: str,
    *,
    session_id: str,
    card_ids: tuple[int, ...] = (123,),
) -> StudySessionStore:
    store = StudySessionStore(directory)
    store.sessions_directory.mkdir(parents=True)
    cards = []
    for index, card_id in enumerate(card_ids):
        snapshot = ReviewToolBoundaryTests.scheduler_snapshot()
        snapshot["modified"] += index
        cards.append(
            {
                "card_id": card_id,
                "note_id": card_id + 333,
                "deck": "000-WuCai Inbox",
                "model": "Basic",
                "fields": {
                    "Prompt": f"Q{card_id}",
                    "Response": f"A{card_id}",
                },
                "scheduler_snapshot": snapshot,
                "retrievability": 0.4 + index / 10,
            }
        )
    manifest = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at": "2026-08-17T12:00:00+00:00",
        "status": "active",
        "decks": ["000-WuCai Inbox"],
        "requested_count": len(cards),
        "include_new": False,
        "selection_method": "anki-native-fsrs-retrievability",
        "cards": cards,
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
        self.assertEqual(
            tools["get_study_session"].inputSchema["properties"]["mode"]["enum"],
            ["full", "triage"],
        )

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
                server.record_triage_results(
                    session_id=session_id,
                    results=[
                        {
                            "card_id": 123,
                            "treatment": "remember",
                            "source": "teacher",
                            "reason": "worth retaining",
                        }
                    ],
                )
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


class TeacherTriageToolTests(unittest.TestCase):
    def test_compact_triage_mode_bounds_oversized_dictionary_cards(self) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "e" * 32
            card_ids = (201, 202, 203, 204, 205)
            session_store = write_session(
                directory,
                session_id=session_id,
                card_ids=card_ids,
            )
            manifest_path = session_store.sessions_directory / f"{session_id}.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            semantic_fields = (
                {
                    "Expression": "Reduce friction in an existing behavior",
                    "Meaning": "Remember this transferable product principle",
                },
                {
                    "Title": "Quarterly market-size statistic",
                    "Usage": "Reference data for lookup, not durable recall",
                },
                {
                    "Skill": "Dance transition timing",
                    "Task": "Practice the movement until it is reliable",
                },
                {"Question": "Why did the assay fail?", "Answer": "Understand cause"},
                {"Prompt": "Apply the framework", "Context": "Own-work example"},
            )
            giant_dictionary = (
                "<div><b>dictionary detail</b> " + "example " * 10_000 + "</div>"
            )
            for card, semantic in zip(manifest["cards"], semantic_fields):
                card["fields"] = {
                    **semantic,
                    "Style": "<style>body { color: red; }</style>" + "x" * 20_000,
                    "Audio": "[sound:dictionary-entry.mp3]",
                    "URL": "https://example.invalid/dictionary-entry",
                    "DictionaryHTML": giant_dictionary,
                    "Glossary": giant_dictionary,
                }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            before_manifest = session_store.load(session_id)
            engine = TutorEngine(
                JsonlLearnerStore(Path(directory) / "tutor.jsonl")
            )
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")

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
                            "card_id": 202,
                            "treatment": "reference",
                            "source": "teacher",
                            "reason": "lookup material",
                        }
                    ],
                )
                full = server.get_study_session(session_id)
                compact = server.get_study_session(session_id, mode="triage")

            full_bytes = len(json.dumps(full, ensure_ascii=False).encode("utf-8"))
            compact_json = json.dumps(compact, ensure_ascii=False)
            compact_bytes = len(compact_json.encode("utf-8"))
            anki_call.assert_not_called()
            self.assertGreater(full_bytes, 100_000)
            self.assertLess(compact_bytes, 20_000)
            self.assertEqual(
                [card["card_id"] for card in compact["cards"]], list(card_ids)
            )
            self.assertEqual(compact["candidate_count"], 5)
            self.assertEqual(compact["cards"][1]["triage"]["treatment"], "reference")
            self.assertEqual(compact["reference_card_ids"], [202])
            compact_text = [
                " ".join(card["content_fields"].values()).casefold()
                for card in compact["cards"]
            ]
            self.assertIn("transferable product principle", compact_text[0])
            self.assertIn("reference data for lookup", compact_text[1])
            self.assertIn("practice the movement", compact_text[2])
            self.assertNotIn("body { color: red; }", compact_json)
            self.assertNotIn("[sound:", compact_json)
            self.assertNotIn("https://example.invalid", compact_json)
            self.assertNotIn("<div>", compact_json)
            self.assertIn("DictionaryHTML", compact["cards"][0]["content_fields"])
            self.assertNotIn("Glossary", compact["cards"][0]["content_fields"])
            self.assertEqual(session_store.load(session_id), before_manifest)
            self.assertEqual(review_store.list_for_session(session_id), [])

    def test_batch_triage_derives_queues_without_touching_manifest_anki_or_reviews(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "c" * 32
            session_store = write_session(
                directory,
                session_id=session_id,
                card_ids=(123, 124, 125, 126, 127),
            )
            before_manifest = session_store.load(session_id)
            learner_path = Path(directory) / "tutor.jsonl"
            engine = TutorEngine(JsonlLearnerStore(learner_path))
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_anki_call") as anki_call,
            ):
                recorded = server.record_triage_results(
                    session_id=session_id,
                    results=[
                        {
                            "card_id": 123,
                            "treatment": "reference",
                            "source": "teacher",
                            "reason": "lookup material",
                        },
                        {
                            "card_id": 124,
                            "treatment": "remember",
                            "source": "teacher",
                            "reason": "durable recall matters",
                        },
                        {
                            "card_id": 125,
                            "treatment": "ignore",
                            "source": "teacher",
                            "reason": "low value",
                        },
                        {
                            "card_id": 126,
                            "treatment": "apply",
                            "source": "teacher",
                            "reason": "work transfer matters",
                        },
                    ],
                )
                derived = server.get_study_session(session_id)

            anki_call.assert_not_called()
            self.assertEqual(recorded["recorded_count"], 4)
            self.assertEqual(recorded["review_events_created"], 0)
            self.assertFalse(recorded["candidate_manifest_mutated"])
            self.assertEqual(session_store.load(session_id), before_manifest)
            self.assertEqual(
                [card["card_id"] for card in derived["active_learning_cards"]],
                [124, 126],
            )
            self.assertEqual(
                [card["card_id"] for card in derived["reference_cards"]], [123]
            )
            self.assertEqual(
                [card["card_id"] for card in derived["ignored_cards"]], [125]
            )
            self.assertEqual(
                [card["card_id"] for card in derived["untriaged_cards"]], [127]
            )
            self.assertFalse(derived["triage_complete"])
            self.assertEqual(derived["voice_handoff"]["card_count"], 2)
            self.assertEqual(review_store.list_for_session(session_id), [])

    def test_restart_recovers_triage_and_latest_learner_override_wins(self) -> None:
        with TemporaryDirectory() as directory:
            session_id = "study_" + "d" * 32
            session_store = write_session(directory, session_id=session_id)
            learner_path = Path(directory) / "tutor.jsonl"
            review_store = SqliteReviewStore(Path(directory) / "reviews.sqlite3")
            first_engine = TutorEngine(JsonlLearnerStore(learner_path))
            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", first_engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_anki_call") as anki_call,
            ):
                for index, (treatment, source) in enumerate((
                    ("remember", "teacher"),
                    ("practice", "teacher"),
                    ("ignore", "learner_override"),
                    ("apply", "teacher"),
                    ("understand", "learner_override"),
                )):
                    server.record_triage_results(
                        session_id=session_id,
                        results=[
                            {
                                "card_id": 123,
                                "treatment": treatment,
                                "source": source,
                                "reason": f"choose {treatment}",
                            }
                        ],
                    )
                    if index == 1:
                        teacher_retriage = server.get_study_session(session_id)

            self.assertEqual(
                teacher_retriage["triage_results"]["123"]["treatment"],
                "practice",
            )

            restarted_engine = TutorEngine(JsonlLearnerStore(learner_path))
            with (
                patch.object(server, "_study_session_store", session_store),
                patch.object(server, "_tutor_engine", restarted_engine),
                patch.object(server, "_review_store", review_store),
                patch.object(server, "_anki_call") as restarted_anki_call,
            ):
                recovered = server.get_study_session(session_id)

            anki_call.assert_not_called()
            restarted_anki_call.assert_not_called()
            self.assertTrue(recovered["triage_complete"])
            self.assertEqual(
                recovered["triage_results"]["123"]["treatment"], "understand"
            )
            self.assertEqual(
                recovered["triage_results"]["123"]["source"],
                "learner_override",
            )
            self.assertEqual(
                [card["card_id"] for card in recovered["active_learning_cards"]],
                [123],
            )
            self.assertEqual(len(JsonlLearnerStore(learner_path).read_all()), 5)

    def test_triage_tool_annotations_match_local_append_only_write(self) -> None:
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
        annotations = tools["record_triage_results"].annotations

        self.assertFalse(annotations.readOnlyHint)
        self.assertFalse(annotations.destructiveHint)
        self.assertFalse(annotations.idempotentHint)
        self.assertFalse(annotations.openWorldHint)


if __name__ == "__main__":
    unittest.main()
