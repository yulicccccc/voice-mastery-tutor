"""Pure-Python writer for portable local study-session manifests."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def default_data_directory() -> Path:
    configured = os.environ.get("VOICE_MASTERY_TUTOR_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "voice-mastery-tutor"


def _atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("study session path must be a regular file")
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
            raise OSError("study session was not fully written")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def create_study_session(
    queue: dict[str, Any],
    *,
    requested_count: int,
    include_new: bool,
    data_directory: str | Path | None = None,
) -> dict[str, Any]:
    if requested_count < 1 or requested_count > 20:
        raise ValueError("requested_count must be between 1 and 20")
    session_id = f"study_{uuid4().hex}"
    cards = []
    for card in queue.get("cards", []):
        cards.append(
            {
                "card_id": int(card["card_id"]),
                "note_id": int(card["note_id"]),
                "deck": str(card["deck"]),
                "model": str(card["model"]),
                "fields": {
                    str(name): str(value)
                    for name, value in card.get("fields", {}).items()
                },
                "scheduler_snapshot": {
                    "modified": int(card["modified"]),
                    "reps": int(card["reps"]),
                    "lapses": int(card["lapses"]),
                    "queue": int(card["queue"]),
                    "card_type": int(card["type"]),
                    "due": int(card["due"]),
                    "interval": int(card["interval"]),
                    "factor": int(card["factor"]),
                    "left": int(card["left"]),
                },
                "retrievability": card.get("retrievability"),
            }
        )

    manifest = {
        "schema_version": 1,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
        "decks": list(queue["decks"]),
        "requested_count": requested_count,
        "include_new": bool(include_new),
        "selection_method": str(queue["selection_method"]),
        "cards": cards,
    }
    base = (
        Path(data_directory).expanduser()
        if data_directory is not None
        else default_data_directory()
    )
    base = Path(os.path.abspath(base))
    _atomic_private_json(
        base / "study-sessions" / f"{session_id}.json", manifest
    )
    _atomic_private_json(
        base / "active-study-session.json", {"session_id": session_id}
    )
    return manifest
