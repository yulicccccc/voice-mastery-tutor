from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import anki_mcp_server as server
from learner_store import JsonlLearnerStore
from models import AnswerAssessment, TutorContext
from tutor_engine import RECENT_TUTOR_CONTEXT_LIMIT, TutorEngine


class TutorContextReconstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_directory.name) / "tutor-events.jsonl"
        self.store = JsonlLearnerStore(self.path)
        self.engine = TutorEngine(self.store)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def decide(
        self,
        card_id: int,
        learner_answer: str,
        assessment: AnswerAssessment = AnswerAssessment.UNKNOWN,
        **overrides,
    ) -> None:
        self.engine.decide(
            TutorContext(
                card_id=card_id,
                learner_answer=learner_answer,
                assessment=assessment,
                **overrides,
            )
        )

    def add_prompted_recall_history(self, card_id: int) -> None:
        self.decide(card_id, "I don't know")
        self.decide(
            card_id,
            "The answer after a hint",
            AnswerAssessment.CORRECT,
            was_prompted=True,
        )

    def test_prompted_recall_reconstructs_failure_and_prompted_success(self) -> None:
        self.add_prompted_recall_history(123)

        context = self.engine.build_tutor_context(123)

        self.assertTrue(context["has_history"])
        self.assertEqual(context["latest_state"], "prompted_recall")
        self.assertEqual(
            context["retrieval"],
            {
                "independent_attempt_seen": True,
                "independent_failure_seen": True,
                "latest_independent_result": "failed",
                "prompted_success_seen": True,
            },
        )
        self.assertEqual(
            context["teaching_evidence"],
            {
                "hints_used": True,
                "understanding_gap_seen": False,
                "application_gap_seen": False,
            },
        )
        self.assertEqual(
            context["recommended_resume_target"], "independent_retrieval"
        )
        self.assertEqual(len(context["recent_relevant_events"]), 2)
        self.assertEqual(
            set(context["recent_relevant_events"][-1]),
            {
                "event_id",
                "created_at",
                "session_id",
                "card_id",
                "state",
                "assessment",
                "was_prompted",
                "action",
                "teaching_method",
                "mastered_candidate",
            },
        )
        self.assertNotIn(
            "learner_answer", context["recent_relevant_events"][-1]
        )

    def test_restart_reconstructs_context_from_disk_only(self) -> None:
        self.add_prompted_recall_history(321)
        del self.engine
        del self.store

        restarted_store = JsonlLearnerStore(self.path)
        restarted_engine = TutorEngine(restarted_store)
        context = restarted_engine.build_tutor_context(321)

        self.assertEqual(context["latest_state"], "prompted_recall")
        self.assertTrue(context["retrieval"]["independent_failure_seen"])
        self.assertTrue(context["retrieval"]["prompted_success_seen"])
        self.assertEqual(
            context["recommended_resume_target"], "independent_retrieval"
        )

    def test_no_history_returns_clean_first_retrieval_context(self) -> None:
        self.assertEqual(
            self.engine.build_tutor_context(999),
            {
                "card_id": 999,
                "has_history": False,
                "latest_state": None,
                "retrieval": {
                    "independent_attempt_seen": False,
                    "independent_failure_seen": False,
                    "latest_independent_result": None,
                    "prompted_success_seen": False,
                },
                "teaching_evidence": {
                    "hints_used": False,
                    "understanding_gap_seen": False,
                    "application_gap_seen": False,
                },
                "recommended_resume_target": "first_retrieval",
                "recent_relevant_events": [],
            },
        )

    def test_card_context_isolated_from_other_cards(self) -> None:
        self.add_prompted_recall_history(100)
        self.decide(
            200,
            "I know the concept but can't apply it",
            AnswerAssessment.CORRECT,
        )

        context = self.engine.build_tutor_context(100)

        self.assertEqual(context["latest_state"], "prompted_recall")
        self.assertFalse(context["teaching_evidence"]["application_gap_seen"])
        self.assertTrue(
            all(
                event["card_id"] == 100
                for event in context["recent_relevant_events"]
            )
        )

    def test_context_limits_recent_events_to_five(self) -> None:
        for index in range(8):
            self.decide(
                123,
                f"Correct answer {index}",
                AnswerAssessment.CORRECT,
            )
        all_events = self.store.read_card_events(123)

        context = self.engine.build_tutor_context(123)

        self.assertEqual(
            len(context["recent_relevant_events"]),
            RECENT_TUTOR_CONTEXT_LIMIT,
        )
        self.assertEqual(
            [
                event["event_id"]
                for event in context["recent_relevant_events"]
            ],
            [
                event["event_id"]
                for event in all_events[-RECENT_TUTOR_CONTEXT_LIMIT:]
            ],
        )

    def test_understanding_gap_resumes_with_understanding_repair(self) -> None:
        self.decide(123, "I don't understand this")

        context = self.engine.build_tutor_context(123)

        self.assertEqual(context["latest_state"], "understanding_gap")
        self.assertTrue(context["teaching_evidence"]["understanding_gap_seen"])
        self.assertEqual(
            context["recommended_resume_target"], "understanding_repair"
        )

    def test_retrieval_gap_resumes_with_independent_retrieval(self) -> None:
        self.decide(123, "I don't know")

        context = self.engine.build_tutor_context(123)

        self.assertEqual(context["latest_state"], "retrieval_gap")
        self.assertTrue(context["retrieval"]["independent_failure_seen"])
        self.assertEqual(
            context["recommended_resume_target"], "independent_retrieval"
        )

    def test_transfer_gap_resumes_with_application_transfer(self) -> None:
        self.decide(
            123,
            "I know the concept but can't apply it",
            AnswerAssessment.CORRECT,
        )

        context = self.engine.build_tutor_context(123)

        self.assertEqual(
            context["latest_state"], "known_but_not_transferable"
        )
        self.assertTrue(context["teaching_evidence"]["application_gap_seen"])
        self.assertEqual(
            context["recommended_resume_target"], "application_transfer"
        )

    def test_low_value_card_remains_deprioritized(self) -> None:
        self.decide(123, "I don't want to learn this card")

        context = self.engine.build_tutor_context(123)

        self.assertEqual(context["latest_state"], "skipped_low_value")
        self.assertFalse(context["retrieval"]["independent_attempt_seen"])
        self.assertEqual(
            context["recommended_resume_target"], "deprioritized_or_skip"
        )

    def test_independent_and_mastered_states_resume_spaced_retrieval(self) -> None:
        self.decide(123, "Correct answer", AnswerAssessment.CORRECT)
        independent_context = self.engine.build_tutor_context(123)
        self.decide(
            123,
            "Correct answer again",
            AnswerAssessment.CORRECT,
            stable_mastery_evidence=True,
        )
        mastered_context = self.engine.build_tutor_context(123)

        self.assertEqual(
            independent_context["recommended_resume_target"],
            "normal_spaced_retrieval",
        )
        self.assertEqual(mastered_context["latest_state"], "mastered")
        self.assertEqual(
            mastered_context["recommended_resume_target"],
            "normal_spaced_retrieval",
        )


class TutorContextMcpTests(unittest.TestCase):
    def test_context_tool_is_repeatable_and_never_calls_anki(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tutor-events.jsonl"
            engine = TutorEngine(JsonlLearnerStore(path))
            engine.decide(
                TutorContext(
                    card_id=123,
                    learner_answer="The answer after a hint",
                    assessment=AnswerAssessment.CORRECT,
                    was_prompted=True,
                )
            )
            before = path.read_bytes()

            with (
                patch.object(server, "_tutor_engine", engine),
                patch.object(server, "_anki_call") as anki_call,
            ):
                results = [server.get_tutor_context(123) for _ in range(3)]

            anki_call.assert_not_called()
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[1], results[2])
            self.assertEqual(path.read_bytes(), before)

    def test_context_tool_annotations_are_read_only(self) -> None:
        tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
        annotations = tools["get_tutor_context"].annotations

        self.assertTrue(annotations.readOnlyHint)
        self.assertFalse(annotations.destructiveHint)
        self.assertTrue(annotations.idempotentHint)
        self.assertFalse(annotations.openWorldHint)
        self.assertIn(
            "card_id", tools["get_tutor_context"].inputSchema["properties"]
        )


if __name__ == "__main__":
    unittest.main()
