"""Append-only local persistence for Tutor decisions and learner evidence."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from pathlib import Path
from typing import Any

from models import (
    AnkiRating,
    FirstAttemptResult,
    LearnerState,
    ReviewEvent,
    ReviewSyncStatus,
    SchedulerSnapshot,
)


def default_store_path() -> Path:
    configured = os.environ.get("TUTOR_STORE_PATH")
    if configured:
        return Path(configured).expanduser()
    return (
        Path.home()
        / ".local"
        / "share"
        / "voice-mastery-tutor"
        / "tutor-events.jsonl"
    )


def default_review_store_path() -> Path:
    configured = os.environ.get("TUTOR_REVIEW_STORE_PATH")
    if configured:
        return Path(configured).expanduser()
    return default_store_path().with_name("review-events.sqlite3")


class JsonlLearnerStore:
    def __init__(self, path: str | Path | None = None) -> None:
        selected = Path(path) if path is not None else default_store_path()
        selected = selected.expanduser()
        self.path = Path(os.path.abspath(selected))

    def _ensure_safe_file_target(self) -> None:
        if self.path.is_symlink():
            raise ValueError("Tutor store path must not be a symbolic link")
        if self.path.exists() and not self.path.is_file():
            raise ValueError("Tutor store path must be a regular file")

    def append(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._ensure_safe_file_target()
        line = (json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(
            self.path,
            flags,
            0o600,
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("Tutor store path must be a regular file")
            os.fchmod(descriptor, 0o600)
            written = os.write(descriptor, line)
            if written != len(line):
                raise OSError("Tutor event was not fully appended")
        finally:
            os.close(descriptor)

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        self._ensure_safe_file_target()
        events: list[dict[str, Any]] = []
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("Tutor store path must be a regular file")
        with os.fdopen(
            descriptor, encoding="utf-8", errors="replace"
        ) as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
        return events

    def latest_for_card(self, card_id: int) -> dict[str, Any] | None:
        latest = None
        for event in self.read_card_events(card_id):
            latest = event
        return latest

    def read_card_events(self, card_id: int) -> list[dict[str, Any]]:
        if card_id < 1:
            raise ValueError("card_id must be a positive integer")
        return [
            event
            for event in self.read_all()
            if event.get("card_id") == card_id
        ]

    def has_state_for_card(self, card_id: int, states: set[str]) -> bool:
        return any(
            event.get("card_id") == card_id and event.get("state") in states
            for event in self.read_all()
        )


class SqliteReviewStore:
    _SCHEMA = """
        create table if not exists review_events (
            event_id text primary key,
            card_id integer not null,
            note_id integer,
            first_attempt_result text not null,
            mapped_anki_rating text not null,
            tutor_state text not null,
            hints_used integer not null,
            scheduler_snapshot text not null,
            created_at text not null,
            sync_status text not null,
            sync_attempts integer not null default 0,
            last_error text
        )
    """

    def __init__(self, path: str | Path | None = None) -> None:
        selected = Path(path) if path is not None else default_review_store_path()
        selected = selected.expanduser()
        self.path = Path(os.path.abspath(selected))

    def _ensure_safe_file_target(self) -> None:
        if self.path.is_symlink():
            raise ValueError("Review store path must not be a symbolic link")
        if self.path.exists() and not self.path.is_file():
            raise ValueError("Review store path must be a regular file")

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._ensure_safe_file_target()
        if not self.path.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(self.path, flags, 0o600)
            except FileExistsError:
                self._ensure_safe_file_target()
            else:
                os.close(descriptor)
        connection = sqlite3.connect(self.path)
        os.chmod(self.path, 0o600)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma synchronous = full")
        connection.execute(self._SCHEMA)
        connection.commit()
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ReviewEvent:
        return ReviewEvent(
            event_id=str(row["event_id"]),
            card_id=int(row["card_id"]),
            note_id=None if row["note_id"] is None else int(row["note_id"]),
            first_attempt_result=FirstAttemptResult(row["first_attempt_result"]),
            mapped_anki_rating=AnkiRating(row["mapped_anki_rating"]),
            tutor_state=LearnerState(row["tutor_state"]),
            hints_used=int(row["hints_used"]),
            scheduler_snapshot=SchedulerSnapshot.from_mapping(
                json.loads(row["scheduler_snapshot"])
            ),
            created_at=str(row["created_at"]),
            sync_status=ReviewSyncStatus(row["sync_status"]),
            sync_attempts=int(row["sync_attempts"]),
            last_error=row["last_error"],
        )

    def create_or_get(self, event: ReviewEvent) -> tuple[ReviewEvent, bool]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert or ignore into review_events (
                    event_id, card_id, note_id, first_attempt_result,
                    mapped_anki_rating, tutor_state, hints_used,
                    scheduler_snapshot, created_at, sync_status,
                    sync_attempts, last_error
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.card_id,
                    event.note_id,
                    event.first_attempt_result.value,
                    event.mapped_anki_rating.value,
                    event.tutor_state.value,
                    event.hints_used,
                    json.dumps(
                        event.scheduler_snapshot.to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    event.created_at,
                    event.sync_status.value,
                    event.sync_attempts,
                    event.last_error,
                ),
            )
            created = cursor.rowcount == 1
            row = connection.execute(
                "select * from review_events where event_id = ?",
                (event.event_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("ReviewEvent insert did not produce a durable row")
        stored = self._from_row(row)
        if stored.first_attempt_result != event.first_attempt_result:
            raise ValueError(
                "this card/scheduler snapshot already has a ReviewEvent with a "
                "different first-attempt result"
            )
        return stored, created

    def get(self, event_id: str) -> ReviewEvent | None:
        if not self.path.exists():
            return None
        self._ensure_safe_file_target()
        with self._connect() as connection:
            row = connection.execute(
                "select * from review_events where event_id = ?",
                (event_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list_by_status(
        self, status: ReviewSyncStatus, limit: int = 100
    ) -> list[ReviewEvent]:
        if not self.path.exists():
            return []
        self._ensure_safe_file_target()
        with self._connect() as connection:
            rows = connection.execute(
                """
                select * from review_events
                where sync_status = ?
                order by created_at, event_id
                limit ?
                """,
                (status.value, limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def record_sync_attempt(
        self,
        event_id: str,
        *,
        status: ReviewSyncStatus,
        last_error: str | None,
    ) -> ReviewEvent:
        if status not in {
            ReviewSyncStatus.PENDING,
            ReviewSyncStatus.APPLIED,
            ReviewSyncStatus.CONFLICTED,
            ReviewSyncStatus.FAILED,
        }:
            raise ValueError(f"unsupported sync transition: {status.value}")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                update review_events
                set sync_status = ?,
                    sync_attempts = sync_attempts + 1,
                    last_error = ?
                where event_id = ? and sync_status = ?
                """,
                (
                    status.value,
                    last_error,
                    event_id,
                    ReviewSyncStatus.PENDING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "ReviewEvent is no longer pending; refusing duplicate transition"
                )
            row = connection.execute(
                "select * from review_events where event_id = ?",
                (event_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("ReviewEvent disappeared after sync transition")
        return self._from_row(row)
