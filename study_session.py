"""Durable StudySession manifest reads and completion-state persistence."""

from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from models import LearnerState, ReviewEvent, ReviewSyncStatus, SchedulerSnapshot


SESSION_ID_PATTERN = re.compile(r"^study_[0-9a-f]{32}$")
VOICE_HANDOFF_PROTOCOL = "voice-study-batch-v1"


def default_data_directory() -> Path:
    configured = os.environ.get("VOICE_MASTERY_TUTOR_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "voice-mastery-tutor"


class StudySessionStore:
    """Keep immutable manifests and mutable completion state separate."""

    def __init__(self, data_directory: str | Path | None = None) -> None:
        selected = (
            Path(data_directory)
            if data_directory is not None
            else default_data_directory()
        )
        self.data_directory = Path(os.path.abspath(selected.expanduser()))
        self.sessions_directory = self.data_directory / "study-sessions"
        self.completion_directory = (
            self.data_directory / "study-session-completion"
        )
        self.active_path = self.data_directory / "active-study-session.json"
        self._completion_lock = Lock()

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("invalid study session id")
        return session_id

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise ValueError("study session path must be a regular file")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("study session path must be a regular file")
            with os.fdopen(descriptor, encoding="utf-8") as handle:
                descriptor = -1
                payload = json.load(handle)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if not isinstance(payload, dict):
            raise ValueError("study session JSON must be an object")
        return payload


    def load(self, session_id: str | None = None) -> dict[str, Any] | None:
        selected_id = session_id
        if selected_id is None:
            if not self.active_path.exists():
                return None
            pointer = self._read_json(self.active_path)
            selected_id = pointer.get("session_id")
            if not isinstance(selected_id, str):
                raise ValueError("active study session pointer is invalid")

        selected_id = self._validate_session_id(selected_id)
        path = self.sessions_directory / f"{selected_id}.json"
        if not path.exists():
            return None
        return self._validate_manifest(self._read_json(path), selected_id)

    @staticmethod
    def _initial_completion(session_id: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": session_id,
            "status": "active",
            "learning_complete": False,
            "sync_complete": False,
            "active_card_count": 0,
            "final_review_count": 0,
            "applied_review_count": 0,
            "updated_at": None,
            "completed_at": None,
        }

    def load_completion(self, session_id: str) -> dict[str, Any]:
        selected_id = self._validate_session_id(session_id)
        if self.load(selected_id) is None:
            raise ValueError("study session does not exist")
        path = self.completion_directory / f"{selected_id}.json"
        if not path.exists():
            return self._initial_completion(selected_id)
        payload = self._read_json(path)
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported study session completion schema")
        if payload.get("session_id") != selected_id:
            raise ValueError("study session completion id is invalid")
        if payload.get("status") not in {"active", "completed"}:
            raise ValueError("study session completion status is invalid")
        for field in (
            "learning_complete",
            "sync_complete",
        ):
            if not isinstance(payload.get(field), bool):
                raise ValueError(f"study session completion {field} is invalid")
        if payload["sync_complete"] and not payload["learning_complete"]:
            raise ValueError("sync_complete requires learning_complete")
        if payload["status"] == "completed" and not (
            payload["learning_complete"] and payload["sync_complete"]
        ):
            raise ValueError("completed study session has incomplete lifecycle")
        for field in (
            "active_card_count",
            "final_review_count",
            "applied_review_count",
        ):
            value = payload.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"study session completion {field} is invalid")
        return payload

    def refresh_completion(
        self,
        session_id: str,
        *,
        triage_complete: bool,
        active_card_ids: list[int],
        review_events: list[ReviewEvent],
    ) -> dict[str, Any]:
        """Atomically persist completion derived from durable session evidence."""
        selected_id = self._validate_session_id(session_id)
        if self.load(selected_id) is None:
            raise ValueError("study session does not exist")
        active_ids = set(active_card_ids)
        final_review_ids = {
            event.card_id
            for event in review_events
            if event.card_id in active_ids
            and event.tutor_state != LearnerState.PAUSED
        }
        applied_review_ids = {
            event.card_id
            for event in review_events
            if event.card_id in active_ids
            and event.tutor_state != LearnerState.PAUSED
            and event.sync_status == ReviewSyncStatus.APPLIED
        }
        learning_complete = triage_complete and active_ids <= final_review_ids
        sync_complete = (
            learning_complete
            and active_ids <= applied_review_ids
            and all(
                event.sync_status == ReviewSyncStatus.APPLIED
                for event in review_events
            )
        )
        status = "completed" if learning_complete and sync_complete else "active"

        with self._completion_lock:
            current = self.load_completion(selected_id)
            stable_fields = {
                "status": status,
                "learning_complete": learning_complete,
                "sync_complete": sync_complete,
                "active_card_count": len(active_ids),
                "final_review_count": len(final_review_ids),
                "applied_review_count": len(applied_review_ids),
            }
            if all(
                current.get(key) == value
                for key, value in stable_fields.items()
            ):
                return current

            now = datetime.now(timezone.utc).isoformat()
            payload = {
                "schema_version": 1,
                "session_id": selected_id,
                **stable_fields,
                "updated_at": now,
                "completed_at": (
                    current.get("completed_at")
                    if status == "completed" and current.get("completed_at")
                    else now if status == "completed" else None
                ),
            }
            self._atomic_private_json(
                self.completion_directory / f"{selected_id}.json", payload
            )
            return payload

    @staticmethod
    def _atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("study session completion path must be a regular file")
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            body = (
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            ).encode("utf-8")
            written = os.write(descriptor, body)
            if written != len(body):
                raise OSError("study session completion was not fully written")
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
            raise

    @classmethod
    def _validate_manifest(
        cls, payload: dict[str, Any], expected_session_id: str
    ) -> dict[str, Any]:
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported study session schema version")
        if payload.get("session_id") != expected_session_id:
            raise ValueError("study session id does not match its filename")
        if payload.get("status") not in {"active", "completed"}:
            raise ValueError("study session status is invalid")
        decks = payload.get("decks")
        if not isinstance(decks, list) or not decks or not all(
            isinstance(deck, str) and deck.strip() for deck in decks
        ):
            raise ValueError("study session requires at least one deck")
        requested_count = payload.get("requested_count")
        if (
            isinstance(requested_count, bool)
            or not isinstance(requested_count, int)
            or requested_count < 1
            or requested_count > 20
        ):
            raise ValueError("requested_count must be between 1 and 20")
        cards = payload.get("cards")
        if not isinstance(cards, list) or len(cards) > requested_count:
            raise ValueError("study session cards are invalid")

        seen: set[int] = set()
        for card in cards:
            if not isinstance(card, dict):
                raise ValueError("study session card must be an object")
            card_id = card.get("card_id")
            if (
                isinstance(card_id, bool)
                or not isinstance(card_id, int)
                or card_id < 1
                or card_id in seen
            ):
                raise ValueError("study session card ids must be unique integers")
            seen.add(card_id)
            fields = card.get("fields")
            if not isinstance(fields, dict) or not all(
                isinstance(name, str) and isinstance(value, str)
                for name, value in fields.items()
            ):
                raise ValueError("study session card fields are invalid")
            SchedulerSnapshot.from_mapping(card.get("scheduler_snapshot", {}))
        return payload


def build_voice_handoff(session: dict[str, Any]) -> dict[str, Any]:
    """Build a self-contained batch that can survive the switch to Voice Mode.

    ChatGPT Voice cannot call Custom Actions. The custom GPT must therefore place
    the returned collapsed packet in its visible pre-Voice reply so the voice
    conversation has every selected card in its ordinary conversation context.
    Scheduler snapshots intentionally stay server-side and are reloaded only when
    the learner exits Voice Mode and asks to save.
    """
    cards = [
        {
            "position": position,
            "card_id": int(card["card_id"]),
            "note_id": int(card["note_id"]),
            "deck": str(card.get("deck", "")),
            "model": str(card.get("model", "")),
            "teacher_fields": dict(card["fields"]),
        }
        for position, card in enumerate(session["cards"], start=1)
    ]
    payload = {
        "protocol": VOICE_HANDOFF_PROTOCOL,
        "session_id": str(session["session_id"]),
        "card_count": len(cards),
        "rules": [
            "Use only these cards, in order, for this voice study batch.",
            "Do not call any Action while the learner is in Voice Mode.",
            "Remember the first unaided result, hints used, and final Tutor state for each card.",
            "Continue automatically until the batch ends or the learner says stop or pause.",
            "After Voice Mode ends, wait for the text command 保存本次学习 before persisting results.",
        ],
        "cards": cards,
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    packet_markdown = (
        "<details><summary>语音学习包已载入（学习时无需展开）</summary>"
        f"<pre>{escape(serialized)}</pre></details>"
    )
    return {
        "protocol": VOICE_HANDOFF_PROTOCOL,
        "card_count": len(cards),
        "packet_markdown": packet_markdown,
        "required_pre_voice_behavior": (
            "Place packet_markdown verbatim in the same assistant reply before "
            "asking the first question. After that reply, the learner may enter "
            "Voice Mode and leave the computer; use only the embedded batch and "
            "do not call Actions between cards."
        ),
        "post_voice_save_command": "保存本次学习",
    }
