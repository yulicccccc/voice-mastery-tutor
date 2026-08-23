"""Durable, read-only access to Anki-created study-session manifests."""

from __future__ import annotations

import json
import os
import re
import stat
from html import escape
from pathlib import Path
from typing import Any

from models import SchedulerSnapshot


SESSION_ID_PATTERN = re.compile(r"^study_[0-9a-f]{32}$")
VOICE_HANDOFF_PROTOCOL = "voice-study-batch-v1"


def default_data_directory() -> Path:
    configured = os.environ.get("VOICE_MASTERY_TUTOR_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "voice-mastery-tutor"


class StudySessionStore:
    """Read manifests written by the Anki add-on and survive process restarts."""

    def __init__(self, data_directory: str | Path | None = None) -> None:
        selected = (
            Path(data_directory)
            if data_directory is not None
            else default_data_directory()
        )
        self.data_directory = Path(os.path.abspath(selected.expanduser()))
        self.sessions_directory = self.data_directory / "study-sessions"
        self.active_path = self.data_directory / "active-study-session.json"

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
