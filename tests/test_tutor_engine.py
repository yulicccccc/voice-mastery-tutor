from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from learner_store import JsonlLearnerStore, default_store_path
from models import (
    AnswerAssessment,
    LearnerState,
    QuestionType,
    TeachingDepth,
    TeachingMethod,
    TutorAction,
    TutorContext,
)
from tutor_engine import TutorEngine


class TutorEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.store = JsonlLearnerStore(
            Path(self.temp_directory.name) / "tutor-events.jsonl"
        )
        self.engine = TutorEngine(self.store)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def decide(
        self,
        learner_answer: str,
        assessment: AnswerAssessment = AnswerAssessment.UNKNOWN,
        **overrides,
    ):
        return self.engine.decide(
            TutorContext(
                card_id=123,
                learner_answer=learner_answer,
                assessment=assessment,
                **overrides,
            )
        )

    def test_i_dont_know_gets_small_hint_and_is_persisted(self) -> None:
        decision = self.decide("I don't know")

        self.assertEqual(decision.state, LearnerState.RETRIEVAL_GAP)
        self.assertEqual(decision.action, TutorAction.GIVE_HINT)
        self.assertEqual(decision.depth, TeachingDepth.LIGHTWEIGHT)
        self.assertIn("smallest useful hint", decision.guidance)
        events = self.store.read_all()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["state"], "retrieval_gap")

    def test_known_but_cannot_apply_is_not_mastered(self) -> None:
        decision = self.decide(
            "I know the concept but can't apply it",
            assessment=AnswerAssessment.CORRECT,
            question_type=QuestionType.APPLICATION,
        )

        self.assertEqual(
            decision.state, LearnerState.KNOWN_BUT_NOT_TRANSFERABLE
        )
        self.assertEqual(decision.action, TutorAction.DEEPEN)
        self.assertEqual(decision.teaching_method, TeachingMethod.NEAR_TRANSFER)
        self.assertFalse(decision.mastered_candidate)

    def test_low_value_card_is_skipped_without_stopping_session(self) -> None:
        decision = self.decide("I don't want to learn this card")

        self.assertEqual(decision.state, LearnerState.SKIPPED_LOW_VALUE)
        self.assertEqual(decision.action, TutorAction.SKIP_AND_NEXT)
        self.assertIsNone(decision.teaching_method)
        self.assertTrue(decision.continue_session)
        self.assertIn("Do not persuade", decision.guidance)

    def test_successful_independent_recall_is_mastered_candidate(self) -> None:
        decision = self.decide(
            "A correct explanation",
            assessment=AnswerAssessment.CORRECT,
        )

        self.assertEqual(decision.state, LearnerState.INDEPENDENT_RECALL)
        self.assertEqual(decision.action, TutorAction.CONFIRM_AND_NEXT)
        self.assertTrue(decision.mastered_candidate)
        self.assertNotEqual(decision.state, LearnerState.MASTERED)
        self.assertIsNone(decision.teaching_method)

    def test_partial_answer_gets_lightweight_hint_not_mastery(self) -> None:
        decision = self.decide(
            "Part of the answer",
            assessment=AnswerAssessment.PARTIAL,
        )

        self.assertEqual(decision.state, LearnerState.RETRIEVAL_GAP)
        self.assertEqual(decision.action, TutorAction.GIVE_HINT)
        self.assertEqual(decision.depth, TeachingDepth.LIGHTWEIGHT)
        self.assertFalse(decision.mastered_candidate)

    def test_prompted_success_remains_prompted_recall(self) -> None:
        decision = self.decide(
            "The answer after a hint",
            assessment=AnswerAssessment.CORRECT,
            was_prompted=True,
        )

        self.assertEqual(decision.state, LearnerState.PROMPTED_RECALL)
        self.assertFalse(decision.mastered_candidate)

    def test_stable_independent_evidence_can_be_mastered(self) -> None:
        first_recall = self.decide(
            "A first correct explanation",
            assessment=AnswerAssessment.CORRECT,
        )
        decision = self.decide(
            "A later correct explanation",
            assessment=AnswerAssessment.CORRECT,
            stable_mastery_evidence=True,
        )

        self.assertEqual(first_recall.state, LearnerState.INDEPENDENT_RECALL)
        self.assertEqual(decision.state, LearnerState.MASTERED)
        self.assertFalse(decision.mastered_candidate)

    def test_stable_flag_cannot_make_first_recall_mastered(self) -> None:
        decision = self.decide(
            "A first correct explanation",
            assessment=AnswerAssessment.CORRECT,
            stable_mastery_evidence=True,
        )

        self.assertEqual(decision.state, LearnerState.INDEPENDENT_RECALL)
        self.assertTrue(decision.mastered_candidate)

    def test_learner_can_correct_an_incorrect_mastery_judgment(self) -> None:
        decision = self.decide(
            "That answer is right, but don't mark this mastered",
            assessment=AnswerAssessment.CORRECT,
            stable_mastery_evidence=True,
        )

        self.assertEqual(decision.state, LearnerState.INDEPENDENT_RECALL)
        self.assertFalse(decision.mastered_candidate)
        self.assertIn("learner overrode", decision.reason)

    def test_prompted_recall_can_later_become_independent_recall(self) -> None:
        prompted = self.decide(
            "The answer after a hint",
            assessment=AnswerAssessment.CORRECT,
            was_prompted=True,
        )
        independent = self.decide(
            "The answer without a hint",
            assessment=AnswerAssessment.CORRECT,
        )

        self.assertEqual(prompted.state, LearnerState.PROMPTED_RECALL)
        self.assertEqual(independent.state, LearnerState.INDEPENDENT_RECALL)
        self.assertEqual(
            self.engine.latest_state(123), LearnerState.INDEPENDENT_RECALL
        )

    def test_repeated_failure_chooses_exactly_one_contextual_method(self) -> None:
        decision = self.decide(
            "Still wrong",
            assessment=AnswerAssessment.INCORRECT,
            consecutive_incorrect=2,
            question_type=QuestionType.CAUSAL,
        )

        self.assertEqual(decision.state, LearnerState.UNDERSTANDING_GAP)
        self.assertEqual(decision.depth, TeachingDepth.DEEP)
        self.assertEqual(
            decision.teaching_method, TeachingMethod.COUNTERFACTUAL_THINKING
        )

    def test_default_flow_never_asks_whether_to_continue(self) -> None:
        decisions = [
            self.decide(
                f"Correct explanation {index}",
                assessment=AnswerAssessment.CORRECT,
            )
            for index in range(2)
        ]

        self.assertTrue(all(decision.continue_session for decision in decisions))
        self.assertFalse(any(decision.ask_to_continue for decision in decisions))
        self.assertTrue(
            all(
                decision.action == TutorAction.CONFIRM_AND_NEXT
                for decision in decisions
            )
        )

    def test_stop_has_priority_over_other_teaching_signals(self) -> None:
        decision = self.decide(
            "Please stop the session; I don't understand this card",
            assessment=AnswerAssessment.INCORRECT,
            consecutive_incorrect=2,
        )

        self.assertEqual(decision.state, LearnerState.PAUSED)
        self.assertEqual(decision.action, TutorAction.PAUSE)
        self.assertFalse(decision.continue_session)
        self.assertIsNone(decision.teaching_method)

    def test_low_value_skip_has_priority_over_understanding_language(self) -> None:
        decision = self.decide(
            "I understand it, but I don't want to spend time on this"
        )

        self.assertEqual(decision.state, LearnerState.SKIPPED_LOW_VALUE)
        self.assertEqual(decision.action, TutorAction.SKIP_AND_NEXT)
        self.assertEqual(decision.depth, TeachingDepth.NONE)


class JsonlLearnerStoreTests(unittest.TestCase):
    def test_corrupt_line_does_not_hide_valid_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tutor-events.jsonl"
            store = JsonlLearnerStore(path)
            store.append({"card_id": 1, "state": "prompted_recall"})
            with path.open("ab") as handle:
                handle.write(b"{not valid json}\n")
            store.append({"card_id": 1, "state": "independent_recall"})

            self.assertEqual(
                store.read_all(),
                [
                    {"card_id": 1, "state": "prompted_recall"},
                    {"card_id": 1, "state": "independent_recall"},
                ],
            )

    def test_restart_restores_latest_learner_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tutor-events.jsonl"
            first_engine = TutorEngine(JsonlLearnerStore(path))
            first_engine.decide(
                TutorContext(
                    card_id=321,
                    learner_answer="The answer after a hint",
                    assessment=AnswerAssessment.CORRECT,
                    was_prompted=True,
                )
            )

            restarted_engine = TutorEngine(JsonlLearnerStore(path))

            self.assertEqual(
                restarted_engine.latest_state(321), LearnerState.PROMPTED_RECALL
            )

    def test_configured_store_creates_private_file_and_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "tutor-events.jsonl"
            with patch.dict(os.environ, {"TUTOR_STORE_PATH": str(path)}):
                configured_path = default_store_path()
                store = JsonlLearnerStore()
                store.append({"card_id": 1, "state": "retrieval_gap"})

            self.assertEqual(configured_path, path)
            self.assertEqual(store.path, path)
            self.assertTrue(path.parent.is_dir())
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_append_only_store_keeps_each_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tutor-events.jsonl"
            store = JsonlLearnerStore(path)
            first = {"card_id": 1, "state": "retrieval_gap"}
            second = {"card_id": 1, "state": "independent_recall"}

            store.append(first)
            store.append(second)

            lines = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(lines, [first, second])


if __name__ == "__main__":
    unittest.main()
