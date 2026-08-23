"""Deterministic, lightweight-first teaching policy for ChatGPT tutoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from learner_store import JsonlLearnerStore
from models import (
    AnswerAssessment,
    LearnerState,
    QuestionType,
    TeachingDepth,
    TeachingMethod,
    TriageEvent,
    TriageTreatment,
    TutorAction,
    TutorContext,
    TutorDecision,
)


SKIP_PHRASES = (
    "don't want to learn this",
    "do not want to learn this",
    "don't want to spend time on this",
    "do not want to spend time on this",
    "not worth learning",
    "not worth my time",
    "no value",
    "low value",
    "skip this card",
    "不想学这张",
    "不想在这张上花时间",
    "这张没价值",
    "跳过这张",
)
TRANSFER_GAP_PHRASES = (
    "know the concept but can't apply",
    "know the concept but cannot apply",
    "know it but can't apply",
    "know it but cannot apply",
    "understand it but can't use",
    "understand it but cannot use",
    "会这个但不会应用",
    "懂但不会用",
)
UNDERSTANDING_GAP_PHRASES = (
    "don't understand",
    "do not understand",
    "doesn't make sense",
    "cannot understand",
    "不懂",
    "没理解",
)
MORE_PRACTICE_PHRASES = (
    "need more practice",
    "need to practice more",
    "still need practice",
    "还需要练",
    "还要练",
)
STOP_EXACT_PHRASES = (
    "stop",
    "pause",
    "停止",
    "暂停",
)
STOP_REQUEST_PHRASES = (
    "stop the session",
    "pause the session",
    "let's stop",
    "let's pause",
    "let us stop",
    "let us pause",
    "please stop",
    "please pause",
    "stop now",
    "pause now",
    "i want to stop",
    "i want to pause",
    "i need to stop",
    "i need a pause",
    "take a break",
    "请停止",
    "请暂停",
    "先暂停",
    "停一下",
    "暂停一下",
)
NEGATED_STOP_PHRASES = (
    "don't stop",
    "do not stop",
    "don't pause",
    "do not pause",
    "don't want to stop",
    "do not want to stop",
    "don't want to pause",
    "do not want to pause",
)
MASTERY_CORRECTION_PHRASES = (
    "i'm not mastered",
    "i am not mastered",
    "you marked me mastered",
    "don't mark this mastered",
    "do not mark this mastered",
    "i haven't mastered this",
    "i have not mastered this",
    "我还没有掌握",
    "别标记为掌握",
    "不要标记为掌握",
)

RECENT_TUTOR_CONTEXT_LIMIT = 5
RESUME_TARGET_BY_STATE = {
    LearnerState.RETRIEVAL_GAP: "independent_retrieval",
    LearnerState.PROMPTED_RECALL: "independent_retrieval",
    LearnerState.UNDERSTANDING_GAP: "understanding_repair",
    LearnerState.KNOWN_BUT_NOT_TRANSFERABLE: "application_transfer",
    LearnerState.INDEPENDENT_RECALL: "normal_spaced_retrieval",
    LearnerState.MASTERED: "normal_spaced_retrieval",
    LearnerState.SKIPPED_LOW_VALUE: "deprioritized_or_skip",
    LearnerState.PAUSED: "resume_when_ready",
}
ACTIVE_TRIAGE_TREATMENTS = {
    TriageTreatment.UNDERSTAND,
    TriageTreatment.REMEMBER,
    TriageTreatment.APPLY,
    TriageTreatment.PRACTICE,
}


class TutorEngine:
    def __init__(self, store: JsonlLearnerStore | None = None) -> None:
        self.store = store

    def decide(self, context: TutorContext) -> TutorDecision:
        text = self._normalize(context.learner_answer)

        if self._is_stop(text):
            decision = TutorDecision(
                state=LearnerState.PAUSED,
                action=TutorAction.PAUSE,
                depth=TeachingDepth.NONE,
                guidance="Pause the session without advancing to another card.",
                reason="learner explicitly paused or stopped the session",
                continue_session=False,
            )
        elif self._contains(text, SKIP_PHRASES):
            decision = TutorDecision(
                state=LearnerState.SKIPPED_LOW_VALUE,
                action=TutorAction.SKIP_AND_NEXT,
                depth=TeachingDepth.NONE,
                guidance=(
                    "Acknowledge the value judgment briefly, deprioritize this card, "
                    "and ask the next card. Do not persuade the learner to continue "
                    "with this card."
                ),
                reason="learner explicitly marked the card as low-value",
            )
        elif self._contains(text, TRANSFER_GAP_PHRASES):
            decision = self._deep_decision(
                context,
                state=LearnerState.KNOWN_BUT_NOT_TRANSFERABLE,
                reason="learner can recall the concept but cannot apply it",
            )
        elif self._contains(text, UNDERSTANDING_GAP_PHRASES):
            decision = self._deep_decision(
                context,
                state=LearnerState.UNDERSTANDING_GAP,
                reason="learner explicitly reported an understanding gap",
            )
        elif self._contains(text, MORE_PRACTICE_PHRASES):
            decision = self._deep_decision(
                context,
                state=LearnerState.UNDERSTANDING_GAP,
                reason="learner explicitly requested deeper practice",
            )
        elif context.learner_rejects_mastery or self._contains(
            text, MASTERY_CORRECTION_PHRASES
        ):
            decision = self._mastery_correction_decision(context)
        elif context.assessment == AnswerAssessment.CORRECT:
            decision = self._correct_decision(context)
        elif context.consecutive_incorrect >= 2:
            decision = self._deep_decision(
                context,
                state=LearnerState.UNDERSTANDING_GAP,
                reason="repeated incorrect answers indicate a deeper gap",
            )
        else:
            decision = TutorDecision(
                state=LearnerState.RETRIEVAL_GAP,
                action=TutorAction.GIVE_HINT,
                depth=TeachingDepth.LIGHTWEIGHT,
                guidance=(
                    "Give the smallest useful hint without revealing the full answer, "
                    "then wait for one retry."
                ),
                reason="first failed or unknown retrieval attempt",
            )

        self._persist(context, decision)
        return decision

    def latest_state(self, card_id: int) -> LearnerState | None:
        if self.store is None:
            return None
        for event in reversed(self.store.read_card_events(card_id)):
            try:
                return LearnerState(event["state"])
            except (KeyError, ValueError):
                continue
        return None

    def record_triage_events(self, events: list[TriageEvent]) -> None:
        if self.store is None:
            raise RuntimeError("Tutor learner store is not configured")
        self.store.append_many([event.to_dict() for event in events])

    def build_triage_view(self, cards: list[dict[str, Any]]) -> dict[str, Any]:
        """Derive learning queues without changing the candidate manifest."""
        card_ids = [int(card["card_id"]) for card in cards]
        effective = (
            self.store.effective_triage_for_cards(card_ids)
            if self.store is not None
            else {}
        )
        untriaged: list[dict[str, Any]] = []
        active: list[dict[str, Any]] = []
        reference: list[dict[str, Any]] = []
        ignored: list[dict[str, Any]] = []

        for card in cards:
            card_id = int(card["card_id"])
            event = effective.get(card_id)
            if event is None:
                untriaged.append(dict(card))
                continue
            derived = {
                **card,
                "triage": {
                    "event_id": event.event_id,
                    "treatment": event.treatment.value,
                    "source": event.source.value,
                    "reason": event.reason,
                    "created_at": event.created_at,
                },
            }
            if event.treatment in ACTIVE_TRIAGE_TREATMENTS:
                active.append(derived)
            elif event.treatment == TriageTreatment.REFERENCE:
                reference.append(derived)
            else:
                ignored.append(derived)

        return {
            "triage_complete": not untriaged,
            "effective_results": {
                str(card_id): effective[card_id].to_dict()
                for card_id in card_ids
                if card_id in effective
            },
            "untriaged_cards": untriaged,
            "active_learning_cards": active,
            "reference_cards": reference,
            "ignored_cards": ignored,
        }

    def build_tutor_context(self, card_id: int) -> dict[str, Any]:
        """Reconstruct compact teaching context from durable events for one card."""
        if card_id < 1:
            raise ValueError("card_id must be a positive integer")

        stored_events = (
            self.store.read_card_events(card_id) if self.store is not None else []
        )
        relevant_events: list[tuple[dict[str, Any], LearnerState]] = []
        for event in stored_events:
            try:
                state = LearnerState(event["state"])
            except (KeyError, ValueError):
                continue
            relevant_events.append((event, state))

        independent_results: list[str] = []
        prompted_success_seen = False
        hints_used = False
        states: list[LearnerState] = []

        for event, state in relevant_events:
            states.append(state)
            assessment = event.get("assessment")
            was_prompted = event.get("was_prompted") is True
            if was_prompted and assessment == AnswerAssessment.CORRECT.value:
                prompted_success_seen = True
            elif not was_prompted and state not in {
                LearnerState.SKIPPED_LOW_VALUE,
                LearnerState.PAUSED,
            }:
                if assessment == AnswerAssessment.CORRECT.value:
                    independent_results.append("succeeded")
                elif assessment in {
                    AnswerAssessment.INCORRECT.value,
                    AnswerAssessment.PARTIAL.value,
                } or (
                    assessment == AnswerAssessment.UNKNOWN.value
                    and state == LearnerState.RETRIEVAL_GAP
                ):
                    independent_results.append("failed")
            if was_prompted or event.get("action") == TutorAction.GIVE_HINT.value:
                hints_used = True

        latest_state = states[-1] if states else None
        recent_events = [
            self._compact_context_event(event)
            for event, _ in relevant_events[-RECENT_TUTOR_CONTEXT_LIMIT:]
        ]

        return {
            "card_id": card_id,
            "has_history": bool(relevant_events),
            "latest_state": latest_state.value if latest_state else None,
            "retrieval": {
                "independent_attempt_seen": bool(independent_results),
                "independent_failure_seen": "failed" in independent_results,
                "latest_independent_result": (
                    independent_results[-1] if independent_results else None
                ),
                "prompted_success_seen": prompted_success_seen,
            },
            "teaching_evidence": {
                "hints_used": hints_used,
                "understanding_gap_seen": (
                    LearnerState.UNDERSTANDING_GAP in states
                ),
                "application_gap_seen": (
                    LearnerState.KNOWN_BUT_NOT_TRANSFERABLE in states
                ),
            },
            "recommended_resume_target": (
                RESUME_TARGET_BY_STATE[latest_state]
                if latest_state
                else "first_retrieval"
            ),
            "recent_relevant_events": recent_events,
        }

    def build_session_progress(
        self, session_id: str, card_ids: list[int]
    ) -> dict[str, Any]:
        """Reconstruct one study batch's progress from durable Tutor events."""
        if not session_id.strip():
            raise ValueError("session_id must not be empty")
        allowed = set(card_ids)
        events = (
            self.store.read_session_events(session_id)
            if self.store is not None
            else []
        )
        latest_states: dict[int, str] = {}
        completed: set[int] = set()
        skipped: set[int] = set()
        for event in events:
            card_id = event.get("card_id")
            if card_id not in allowed:
                continue
            state = event.get("state")
            if isinstance(state, str):
                latest_states[int(card_id)] = state
            action = event.get("action")
            if action in {
                TutorAction.CONFIRM_AND_NEXT.value,
                TutorAction.SKIP_AND_NEXT.value,
            }:
                completed.add(int(card_id))
            if action == TutorAction.SKIP_AND_NEXT.value:
                skipped.add(int(card_id))

        completed_in_order = [card_id for card_id in card_ids if card_id in completed]
        return {
            "completed_card_ids": completed_in_order,
            "skipped_card_ids": [card_id for card_id in card_ids if card_id in skipped],
            "remaining_card_ids": [
                card_id for card_id in card_ids if card_id not in completed
            ],
            "latest_states": {
                str(card_id): latest_states[card_id]
                for card_id in card_ids
                if card_id in latest_states
            },
        }

    @staticmethod
    def _compact_context_event(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": event.get("event_id"),
            "created_at": event.get("created_at"),
            "session_id": event.get("session_id"),
            "card_id": event.get("card_id"),
            "state": event.get("state"),
            "assessment": event.get("assessment"),
            "was_prompted": event.get("was_prompted") is True,
            "action": event.get("action"),
            "teaching_method": event.get("teaching_method"),
            "mastered_candidate": event.get("mastered_candidate") is True,
        }

    def _correct_decision(self, context: TutorContext) -> TutorDecision:
        if context.was_prompted:
            state = LearnerState.PROMPTED_RECALL
            reason = "correct recall required a prompt"
            mastered_candidate = False
        elif (
            context.stable_mastery_evidence
            and self._has_prior_independent_evidence(context.card_id)
        ):
            state = LearnerState.MASTERED
            reason = (
                "independent recall is backed by prior independent retrieval and "
                "stable mastery evidence"
            )
            mastered_candidate = False
        else:
            state = LearnerState.INDEPENDENT_RECALL
            reason = "successful unaided retrieval is a mastery candidate"
            mastered_candidate = True

        return TutorDecision(
            state=state,
            action=TutorAction.CONFIRM_AND_NEXT,
            depth=TeachingDepth.LIGHTWEIGHT,
            guidance=(
                "Confirm briefly and immediately ask the next card. Do not ask "
                "whether the learner wants to continue."
            ),
            reason=reason,
            mastered_candidate=mastered_candidate,
        )

    def _has_prior_independent_evidence(self, card_id: int) -> bool:
        if self.store is None:
            return False
        return self.store.has_state_for_card(
            card_id,
            {
                LearnerState.INDEPENDENT_RECALL.value,
                LearnerState.MASTERED.value,
            },
        )

    def _mastery_correction_decision(
        self, context: TutorContext
    ) -> TutorDecision:
        if context.assessment == AnswerAssessment.CORRECT:
            state = (
                LearnerState.PROMPTED_RECALL
                if context.was_prompted
                else LearnerState.INDEPENDENT_RECALL
            )
            return TutorDecision(
                state=state,
                action=TutorAction.CONFIRM_AND_NEXT,
                depth=TeachingDepth.LIGHTWEIGHT,
                guidance=(
                    "Accept the learner's correction, do not mark mastery, and move "
                    "to the next card without asking whether to continue."
                ),
                reason="learner overrode the Tutor's mastery judgment",
                mastered_candidate=False,
            )
        if context.consecutive_incorrect >= 2:
            return self._deep_decision(
                context,
                state=LearnerState.UNDERSTANDING_GAP,
                reason="learner correction plus repeated misses indicates a deeper gap",
            )
        return TutorDecision(
            state=LearnerState.RETRIEVAL_GAP,
            action=TutorAction.GIVE_HINT,
            depth=TeachingDepth.LIGHTWEIGHT,
            guidance=(
                "Accept the correction, give the smallest useful hint, and wait "
                "for one retry."
            ),
            reason="learner rejected the Tutor's mastery judgment",
        )

    def _deep_decision(
        self,
        context: TutorContext,
        *,
        state: LearnerState,
        reason: str,
    ) -> TutorDecision:
        method = self._choose_method(context, state)
        readable_method = method.value.replace("_", " ")
        return TutorDecision(
            state=state,
            action=TutorAction.DEEPEN,
            depth=TeachingDepth.DEEP,
            teaching_method=method,
            guidance=(
                f"Use one {readable_method} to address the current gap, then ask "
                "the learner to retry. Do not stack multiple teaching methods."
            ),
            reason=reason,
        )

    @staticmethod
    def _choose_method(
        context: TutorContext, state: LearnerState
    ) -> TeachingMethod:
        if state == LearnerState.KNOWN_BUT_NOT_TRANSFERABLE:
            return (
                TeachingMethod.OWN_WORK_EXAMPLE
                if context.has_personal_context
                else TeachingMethod.NEAR_TRANSFER
            )
        return {
            QuestionType.ABSTRACT: TeachingMethod.ANALOGY,
            QuestionType.PROCESS: TeachingMethod.NEAR_TRANSFER,
            QuestionType.APPLICATION: (
                TeachingMethod.OWN_WORK_EXAMPLE
                if context.has_personal_context
                else TeachingMethod.NEAR_TRANSFER
            ),
            QuestionType.DECISION: TeachingMethod.CASE_STUDY,
            QuestionType.CAUSAL: TeachingMethod.COUNTERFACTUAL_THINKING,
        }.get(context.question_type, TeachingMethod.CONCRETE_EXAMPLE)

    def _persist(self, context: TutorContext, decision: TutorDecision) -> None:
        if self.store is None:
            return
        self.store.append(
            {
                "event_id": str(uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "session_id": context.session_id,
                "card_id": context.card_id,
                "note_id": context.note_id,
                "learner_answer": context.learner_answer,
                "assessment": context.assessment.value,
                "was_prompted": context.was_prompted,
                "consecutive_incorrect": context.consecutive_incorrect,
                "question_type": context.question_type.value,
                "learner_rejects_mastery": context.learner_rejects_mastery,
                **decision.to_dict(),
            }
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().replace("’", "'").strip().split())

    @staticmethod
    def _contains(text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in text for phrase in phrases)

    @classmethod
    def _is_stop(cls, text: str) -> bool:
        if cls._contains(text, NEGATED_STOP_PHRASES):
            return False
        stripped = text.rstrip(".!?。！")
        return stripped in STOP_EXACT_PHRASES or cls._contains(
            stripped, STOP_REQUEST_PHRASES
        )
