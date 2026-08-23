"""Anki launcher for durable, phone-continuable AI Tutor study sessions.

The add-on only selects cards and writes an immutable scheduler snapshot. It
never answers cards or changes Anki scheduling data.
"""

from __future__ import annotations

import importlib
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from anki.utils import ids2str
from aqt import gui_hooks, mw
from aqt.qt import (
    QAction,
    QCheckBox,
    QDesktopServices,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTimer,
    QUrl,
    QVBoxLayout,
    Qt,
)
from aqt.utils import showInfo, tooltip

from .session_store import create_study_session


DEFAULT_CONFIG = {
    "dailyTime": "09:00",
    "timezone": "",
    "decks": [],
    "limit": 5,
    "includeNew": False,
    "chatgptConversationUrl": "",
    "lastPromptDate": "",
}

_dialog: QDialog | None = None
_daily_timer: QTimer | None = None
_menu_action: QAction | None = None


def _config() -> dict[str, Any]:
    configured = mw.addonManager.getConfig(__name__) or {}
    return {**DEFAULT_CONFIG, **configured}


def _write_config(config: dict[str, Any]) -> None:
    mw.addonManager.writeConfig(__name__, config)


def _now(config: dict[str, Any]) -> datetime:
    timezone = str(config.get("timezone", "")).strip()
    return datetime.now(ZoneInfo(timezone)) if timezone else datetime.now().astimezone()


def _escape_deck(deck: str) -> str:
    return deck.replace("\\", "\\\\").replace('"', '\\"')


def _candidate_ids(decks: list[str], include_new: bool) -> list[int]:
    ids: set[int] = set()
    for deck in decks:
        escaped = _escape_deck(deck)
        ids.update(int(cid) for cid in mw.col.find_cards(f'deck:"{escaped}" is:due'))
        if include_new:
            ids.update(
                int(cid) for cid in mw.col.find_cards(f'deck:"{escaped}" is:new')
            )
    return list(ids)


def _note_type_name(note: Any) -> str:
    note_type = note.note_type() if hasattr(note, "note_type") else note.model()
    return str(note_type.get("name", "")) if isinstance(note_type, dict) else ""


def build_daily_queue(
    decks: list[str] | None = None,
    limit: int = 5,
    include_new: bool = False,
) -> dict[str, Any]:
    """Return a native-FSRS queue with card content, without mutation."""
    config = _config()
    selected_decks = [str(deck).strip() for deck in (decks or config["decks"])]
    selected_decks = list(dict.fromkeys(deck for deck in selected_decks if deck))
    if not selected_decks:
        raise ValueError("No Anki decks are configured; choose at least one deck.")
    limit = max(1, min(int(limit), 20))

    available = {item.name for item in mw.col.decks.all_names_and_ids()}
    missing = [deck for deck in selected_decks if deck not in available]
    if missing:
        raise ValueError(f"Unknown Anki deck(s): {', '.join(missing)}")

    card_ids = _candidate_ids(selected_decks, bool(include_new))
    if not card_ids:
        return {
            "decks": selected_decks,
            "card_ids": [],
            "cards": [],
            "total_eligible": 0,
            "selection_method": "anki-native-fsrs-retrievability",
        }

    scheduler = mw.col.sched
    rows = mw.col.db.all(
        f"""
        select id, nid, queue, type, due, ivl, reps, lapses, factor, left, mod,
               extract_fsrs_retrievability(
                   data,
                   case when odue != 0 then odue else due end,
                   ivl, ?, ?, ?
               ) as retrievability
        from cards
        where id in {ids2str(card_ids)}
        """,
        int(scheduler.today),
        int(scheduler.dayCutoff),
        int(time.time()),
    )

    cards = [
        {
            "card_id": int(row[0]),
            "note_id": int(row[1]),
            "queue": int(row[2]),
            "type": int(row[3]),
            "due": int(row[4]),
            "interval": int(row[5]),
            "reps": int(row[6]),
            "lapses": int(row[7]),
            "factor": int(row[8]),
            "left": int(row[9]),
            "modified": int(row[10]),
            "retrievability": None if row[11] is None else float(row[11]),
        }
        for row in rows
    ]

    def sort_key(card: dict[str, Any]) -> tuple[Any, ...]:
        queue = int(card["queue"])
        if queue in (1, 3):
            return (0, int(card["due"]), int(card["card_id"]))
        if queue == 0:
            return (2, int(card["due"]), int(card["card_id"]))
        retrievability = card["retrievability"]
        return (
            1,
            retrievability is None,
            2.0 if retrievability is None else float(retrievability),
            int(card["due"]),
            int(card["card_id"]),
        )

    cards.sort(key=sort_key)
    selected = cards[:limit]
    for item in selected:
        card = mw.col.get_card(item["card_id"])
        note = card.note()
        item["deck"] = str(mw.col.decks.name(card.did))
        item["model"] = _note_type_name(note)
        item["fields"] = {
            str(name): "" if value is None else str(value)
            for name, value in note.items()
        }

    has_native_fsrs = any(
        card["retrievability"] is not None and card["queue"] not in (0, 1, 3)
        for card in cards
    )
    return {
        "decks": selected_decks,
        "card_ids": [card["card_id"] for card in selected],
        "cards": selected,
        "total_eligible": len(cards),
        "selection_method": (
            "anki-native-fsrs-retrievability"
            if has_native_fsrs
            else "anki-native-learning-then-due-order"
        ),
    }


class VoiceTutorDialog(QDialog):
    def __init__(self) -> None:
        super().__init__(mw)
        self.setWindowTitle("AI Anki 导师 · 今日复习")
        self.setMinimumSize(520, 520)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        title = QLabel("选择今天允许导师使用的牌组")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        layout.addWidget(
            QLabel(
                "默认只取到期卡；学习/重学卡优先，其余按 FSRS 回忆概率从低到高选择。"
            )
        )

        self.deck_list = QListWidget()
        for deck in sorted(
            mw.col.decks.all_names_and_ids(), key=lambda item: item.name.casefold()
        ):
            item = QListWidgetItem(deck.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.deck_list.addItem(item)
        layout.addWidget(self.deck_list)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("今天复习"))
        self.limit = QSpinBox()
        self.limit.setRange(1, 20)
        self.limit.setValue(int(_config()["limit"]))
        controls.addWidget(self.limit)
        controls.addWidget(QLabel("张"))
        controls.addStretch()
        self.include_new = QCheckBox("包含新卡")
        self.include_new.setChecked(bool(_config()["includeNew"]))
        controls.addWidget(self.include_new)
        layout.addLayout(controls)

        layout.addWidget(
            QLabel(
                "数量可自由调整；开始后会生成可在手机继续的本次复习批次。"
                "只有实际回答后，Tutor 才记录复习结果。"
            )
        )

        buttons = QHBoxLayout()
        save_button = QPushButton("保存设置")
        save_button.clicked.connect(self.save_settings)
        buttons.addWidget(save_button)
        buttons.addStretch()
        later_button = QPushButton("今天稍后")
        later_button.clicked.connect(self.close)
        buttons.addWidget(later_button)
        start_button = QPushButton("开始今天的复习")
        start_button.setDefault(True)
        start_button.clicked.connect(self.start_tutoring)
        buttons.addWidget(start_button)
        layout.addLayout(buttons)

    def selected_decks(self) -> list[str]:
        return [
            self.deck_list.item(index).text()
            for index in range(self.deck_list.count())
            if self.deck_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def save_settings(self, *, show_message: bool = True) -> dict[str, Any] | None:
        decks = self.selected_decks()
        if not decks:
            showInfo("请至少选择一个牌组。")
            return None
        config = _config()
        config.update(
            {
                "decks": decks,
                "limit": self.limit.value(),
                "includeNew": self.include_new.isChecked(),
            }
        )
        _write_config(config)
        if show_message:
            tooltip("AI Anki 导师设置已保存")
        return config

    def start_tutoring(self) -> None:
        config = self.save_settings(show_message=False)
        if config is None:
            return
        tutor_url = str(config.get("chatgptConversationUrl", "")).strip()
        if not tutor_url:
            showInfo("请先在插件配置中设置 chatgptConversationUrl。")
            return
        try:
            queue = build_daily_queue(
                decks=config["decks"],
                limit=int(config["limit"]),
                include_new=bool(config["includeNew"]),
            )
            if not queue["card_ids"]:
                showInfo("所选牌组目前没有符合条件的到期卡。")
                return
            session = create_study_session(
                queue,
                requested_count=int(config["limit"]),
                include_new=bool(config["includeNew"]),
            )
        except Exception as exc:
            showInfo(f"无法准备今日卡片：{exc}")
            return

        self.close()
        QDesktopServices.openUrl(QUrl(tutor_url))
        tooltip(
            f"已创建 {len(session['cards'])} 张卡的远程复习批次；"
            "在 Tutor 中说“开始复习”，之后可用手机继续。",
            period=7000,
        )


def show_daily_dialog(*, force: bool = False) -> bool:
    global _dialog
    if mw.col is None:
        return False
    config = _config()
    now = _now(config)
    if not force and config.get("lastPromptDate") == now.date().isoformat():
        return False
    config["lastPromptDate"] = now.date().isoformat()
    _write_config(config)
    if _dialog is not None:
        _dialog.close()
    _dialog = VoiceTutorDialog()
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return True


def _maybe_prompt() -> None:
    if mw.col is None:
        return
    config = _config()
    now = _now(config)
    try:
        hour, minute = [int(part) for part in str(config["dailyTime"]).split(":", 1)]
    except (TypeError, ValueError):
        hour, minute = 9, 0
    if (now.hour, now.minute) >= (hour, minute):
        show_daily_dialog(force=False)


def _install_ankiconnect_actions() -> bool:
    try:
        anki_connect = importlib.import_module("2055492159")
    except Exception:
        return False

    if not hasattr(anki_connect.AnkiConnect, "voiceTutorDailyQueue"):

        @anki_connect.util.api()
        def voiceTutorDailyQueue(
            self: Any,
            decks: list[str] | None = None,
            limit: int = 5,
            includeNew: bool = False,
        ) -> dict[str, Any]:
            return build_daily_queue(decks, limit, includeNew)

        setattr(anki_connect.AnkiConnect, "voiceTutorDailyQueue", voiceTutorDailyQueue)
    return True


def _profile_opened() -> None:
    global _daily_timer, _menu_action
    _install_ankiconnect_actions()
    if _menu_action is None:
        _menu_action = QAction("AI Anki 导师…", mw)
        _menu_action.triggered.connect(lambda: show_daily_dialog(force=True))
        mw.form.menuTools.addAction(_menu_action)
    if _daily_timer is None:
        _daily_timer = QTimer(mw)
        _daily_timer.timeout.connect(_maybe_prompt)
        _daily_timer.start(60_000)
    QTimer.singleShot(4_000, _maybe_prompt)


gui_hooks.profile_did_open.append(_profile_opened)
