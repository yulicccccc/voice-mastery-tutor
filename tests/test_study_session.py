from __future__ import annotations

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path

from study_session import StudySessionStore, build_voice_handoff


WRITER_PATH = (
    Path(__file__).parents[1]
    / "anki_addon"
    / "voice_mastery_tutor"
    / "session_store.py"
)
WRITER_SPEC = importlib.util.spec_from_file_location(
    "voice_tutor_session_writer", WRITER_PATH
)
assert WRITER_SPEC is not None and WRITER_SPEC.loader is not None
WRITER = importlib.util.module_from_spec(WRITER_SPEC)
WRITER_SPEC.loader.exec_module(WRITER)


def queue() -> dict:
    cards = []
    for offset in range(2):
        cards.append(
            {
                "card_id": 100 + offset,
                "note_id": 200 + offset,
                "deck": "000-WuCai Inbox",
                "model": "Basic",
                "fields": {"Prompt": f"Q{offset}", "Response": f"A{offset}"},
                "modified": 1000 + offset,
                "reps": offset,
                "lapses": 0,
                "queue": 2,
                "type": 2,
                "due": 300 + offset,
                "interval": 4,
                "factor": 2500,
                "left": 0,
                "retrievability": 0.4 + offset / 10,
            }
        )
    return {
        "decks": ["000-WuCai Inbox"],
        "selection_method": "anki-native-fsrs-retrievability",
        "cards": cards,
    }


class StudySessionTests(unittest.TestCase):
    def test_anki_writer_creates_restart_durable_active_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = WRITER.create_study_session(
                queue(),
                requested_count=2,
                include_new=False,
                data_directory=directory,
            )

            restarted = StudySessionStore(directory)
            recovered = restarted.load()

            self.assertEqual(recovered, manifest)
            self.assertEqual(len(recovered["cards"]), 2)
            self.assertEqual(recovered["cards"][0]["fields"]["Prompt"], "Q0")
            self.assertEqual(
                recovered["cards"][0]["scheduler_snapshot"]["card_type"], 2
            )
            self.assertEqual(
                stat.S_IMODE(restarted.active_path.stat().st_mode), 0o600
            )
            session_path = (
                restarted.sessions_directory / f"{manifest['session_id']}.json"
            )
            self.assertEqual(stat.S_IMODE(session_path.stat().st_mode), 0o600)

    def test_each_batch_is_preserved_when_a_new_batch_becomes_active(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = WRITER.create_study_session(
                queue(), requested_count=2, include_new=False, data_directory=directory
            )
            second = WRITER.create_study_session(
                queue(), requested_count=2, include_new=False, data_directory=directory
            )
            store = StudySessionStore(directory)

            self.assertEqual(store.load()["session_id"], second["session_id"])
            self.assertEqual(
                store.load(first["session_id"])["session_id"], first["session_id"]
            )

    def test_candidate_manifest_rejects_cards_outside_selected_deck_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate_queue = queue()
            candidate_queue["decks"] = ["Selected Deck"]
            candidate_queue["cards"][0]["deck"] = "Selected Deck"
            candidate_queue["cards"][1]["deck"] = "Other Deck"

            with self.assertRaisesRegex(ValueError, "selected deck scope"):
                WRITER.create_study_session(
                    candidate_queue,
                    requested_count=2,
                    include_new=False,
                    data_directory=directory,
                )

            self.assertFalse(
                (Path(directory) / "active-study-session.json").exists()
            )

    def test_invalid_session_id_cannot_escape_session_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StudySessionStore(directory)
            with self.assertRaises(ValueError):
                store.load("../review-events.sqlite3")

    def test_voice_handoff_contains_the_entire_batch_without_scheduler_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = WRITER.create_study_session(
                queue(), requested_count=2, include_new=False, data_directory=directory
            )

            handoff = build_voice_handoff(manifest)

            self.assertEqual(handoff["card_count"], 2)
            self.assertIn(manifest["session_id"], handoff["packet_markdown"])
            self.assertIn("Q0", handoff["packet_markdown"])
            self.assertIn("A0", handoff["packet_markdown"])
            self.assertIn("Q1", handoff["packet_markdown"])
            self.assertIn("A1", handoff["packet_markdown"])
            self.assertIn("Do not call any Action", handoff["packet_markdown"])
            self.assertNotIn("scheduler_snapshot", handoff["packet_markdown"])
            self.assertNotIn('"due"', handoff["packet_markdown"])
            self.assertEqual(handoff["post_voice_save_command"], "保存本次学习")


if __name__ == "__main__":
    unittest.main()
