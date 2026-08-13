"""Read-only MCP bridge from ChatGPT to local Anki via AnkiConnect.

MVP scope: expose one teacher-facing tool, get_due_cards().
The server uses stdio by default so OpenAI Secure MCP Tunnel can launch it locally.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ANKICONNECT_URL = os.environ.get("ANKICONNECT_URL", "http://127.0.0.1:8765")
DEFAULT_DECK = os.environ.get("ANKI_DEFAULT_DECK", "000-WuCai Inbox")
ANKICONNECT_VERSION = 6
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("ANKICONNECT_TIMEOUT", "8"))
MAX_CARDS_PER_CALL = 100

mcp = FastMCP("voice-mastery-tutor")


def _anki_call(action: str, params: dict[str, Any] | None = None) -> Any:
    payload = json.dumps(
        {
            "action": action,
            "version": ANKICONNECT_VERSION,
            "params": params or {},
        }
    ).encode("utf-8")

    request = Request(
        ANKICONNECT_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except (URLError, HTTPError, TimeoutError) as exc:
        raise RuntimeError(
            "Cannot reach AnkiConnect. Make sure desktop Anki is open and "
            f"AnkiConnect is listening at {ANKICONNECT_URL}."
        ) from exc

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AnkiConnect returned invalid JSON.") from exc

    if not isinstance(decoded, dict) or "error" not in decoded or "result" not in decoded:
        raise RuntimeError("Unexpected AnkiConnect response shape.")

    if decoded["error"] is not None:
        raise RuntimeError(f"AnkiConnect error: {decoded['error']}")

    return decoded["result"]


def _deck_due_query(deck: str) -> str:
    # Anki search syntax uses backslash escaping inside a quoted deck name.
    escaped = deck.replace("\\", "\\\\").replace('"', '\\"')
    return f'deck:"{escaped}" is:due'


def _field_values(fields: Any) -> dict[str, str]:
    """Convert AnkiConnect's {field: {value, order}} shape to plain strings."""
    if not isinstance(fields, dict):
        return {}

    values: dict[str, str] = {}
    for name, data in fields.items():
        if isinstance(data, dict):
            value = data.get("value", "")
        else:
            value = data
        values[str(name)] = "" if value is None else str(value)
    return values


def _teacher_card(card: dict[str, Any]) -> dict[str, Any]:
    """Keep teacher-relevant source + scheduling fields; omit rendered HTML noise."""
    return {
        "card_id": card.get("cardId"),
        "note_id": card.get("note"),
        "deck": card.get("deckName"),
        "model": card.get("modelName"),
        "fields": _field_values(card.get("fields")),
        "due": card.get("due"),
        "queue": card.get("queue"),
        "type": card.get("type"),
        "reps": card.get("reps"),
        "lapses": card.get("lapses"),
        "interval": card.get("interval"),
        "factor": card.get("factor"),
        "left": card.get("left"),
        "modified": card.get("mod"),
        "next_reviews": card.get("nextReviews"),
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Read due Anki cards",
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
    )
)
def get_due_cards(deck: str = DEFAULT_DECK, limit: int = 20) -> dict[str, Any]:
    """Get teacher-facing Anki material that is due in a deck.

    Use this before a tutoring/review session. The returned `fields` are the source
    note fields; do NOT assume Front/Back are necessarily question/answer. `is:due`
    can include cards in learning/relearning as well as review cards. This tool is
    read-only and never changes Anki or FSRS state.
    """
    deck = deck.strip()
    if not deck:
        raise ValueError("deck must not be empty")
    if limit < 1 or limit > MAX_CARDS_PER_CALL:
        raise ValueError(f"limit must be between 1 and {MAX_CARDS_PER_CALL}")

    query = _deck_due_query(deck)
    card_ids = _anki_call("findCards", {"query": query})
    if not isinstance(card_ids, list):
        raise RuntimeError("AnkiConnect findCards did not return a list.")

    selected_ids = card_ids[:limit]
    cards: list[dict[str, Any]] = []
    if selected_ids:
        raw_cards = _anki_call("cardsInfo", {"cards": selected_ids})
        if not isinstance(raw_cards, list):
            raise RuntimeError("AnkiConnect cardsInfo did not return a list.")
        cards = [_teacher_card(card) for card in raw_cards if isinstance(card, dict)]

    return {
        "deck": deck,
        "query": query,
        "total_due": len(card_ids),
        "returned": len(cards),
        "cards": cards,
    }


if __name__ == "__main__":
    # stdio is the MCP SDK default and is supported by OpenAI Secure MCP Tunnel.
    mcp.run()
