from __future__ import annotations
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QCheckBox, QFrame, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor

from adapters.bridge import _BoolProxy


class LogPanel(QWidget):
    """Serial communication log: themed text area + controls."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.auto_scroll_proxy = _BoolProxy(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setObjectName("logHeader")
        hdr.setFixedHeight(32)
        hdr_hl = QHBoxLayout(hdr)
        hdr_hl.setContentsMargins(10, 0, 10, 0)
        title = QLabel("Serial Log")
        title.setStyleSheet("font-size: 14px; font-weight: 700; background: transparent;")
        hdr_hl.addWidget(title)
        layout.addWidget(hdr)

        # ── Body: plain text ──────────────────────────────────────────────────
        body = QWidget()
        body.setObjectName("logPanelBody")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(4, 4, 4, 0)
        bl.setSpacing(0)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 8))
        self.text.setMaximumBlockCount(5000)
        bl.addWidget(self.text)
        layout.addWidget(body, stretch=1)

        # ── Footer: controls ──────────────────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("logFooter")
        footer.setFixedHeight(36)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(8, 0, 8, 0)
        fl.setSpacing(6)

        self.auto_scroll_cb = QCheckBox("Auto-Scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.setStyleSheet("font-size: 13px; background: transparent;")
        self.auto_scroll_cb.stateChanged.connect(self._on_autoscroll_changed)
        fl.addWidget(self.auto_scroll_cb)
        fl.addStretch()

        for label, slot in (("Clear", self.text.clear), ("Save", self._save_log)):
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setFixedWidth(58)
            btn.setStyleSheet("QPushButton { padding: 2px 6px; font-size: 12px; }")
            btn.clicked.connect(slot)
            fl.addWidget(btn)

        layout.addWidget(footer)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_autoscroll_changed(self, _state):
        # PyQt6's stateChanged may emit Qt.CheckState (an Enum) whose bool()
        # is always True. Read the checkbox state directly to be unambiguous.
        self.auto_scroll_proxy.set(self.auto_scroll_cb.isChecked())

    @pyqtSlot(str)
    def append_text(self, text: str):
        # Insert at end of document using a *separate* cursor so the visible
        # cursor and scroll position aren't yanked to the bottom on every
        # incoming line. Only follow the tail when auto-scroll is on.
        cursor = QTextCursor(self.text.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        if self.auto_scroll_proxy.get():
            self.text.moveCursor(QTextCursor.MoveOperation.End)
            self.text.ensureCursorVisible()

    @pyqtSlot()
    def scroll_to_end(self):
        if self.auto_scroll_proxy.get():
            self.text.moveCursor(QTextCursor.MoveOperation.End)
            self.text.ensureCursorVisible()

    def _save_log(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder to save log")
        if not folder:
            return
        now  = datetime.now()
        name = (f"{now.year%100:02d}_{now.month:02d}_{now.day:02d}"
                f"-{now.hour:02d}_{now.minute:02d}_{now.second:02d}.txt")
        path = f"{folder}/{name}"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
