"""
ai.settings_dialog — provider + key configuration UI.

Lets each end-user pick a provider, choose a model, paste their own API
key, and optionally run a small "Test connection" call. Keys go to the
OS credential store via ai.providers.AIProvider.set_key().
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFrame, QWidget, QCheckBox, QMessageBox,
    QSizePolicy,
)

from ai.providers import (
    PROVIDERS, AIProvider, load_settings, save_settings, keyring_available,
)


class _ProbeWorker(QThread):
    """Tiny one-shot call (~5 output tokens) to verify a key works."""
    done = pyqtSignal(bool, str)

    def __init__(self, provider: AIProvider, model: str, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._model = model

    def run(self):
        try:
            txt = self._provider.generate(
                prompt="Reply with the single word OK.",
                model=self._model,
                max_tokens=16,
            )
            self.done.emit(True, f"OK — got: {txt.strip()[:60]}")
        except Exception as e:
            # Strip noisy SDK wrappers for cleaner display
            self.done.emit(False, str(e).splitlines()[0][:200])


class AISettingsDialog(QDialog):
    """Configure AI provider + model + per-user API key.

    Emits `settings_saved` when the user clicks Save with a usable config.
    """
    settings_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Provider Settings")
        self.setModal(True)
        self.resize(460, 360)
        self._probe: _ProbeWorker | None = None
        self._build_ui()
        self._load_current()
        self._on_provider_changed()

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header
        title = QLabel("AI Provider Settings")
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        layout.addWidget(title)

        sub = QLabel(
            "The app needs an API key from one of the providers below. "
            "Your key is stored in your operating system's secure credential "
            "store — never in the app's files."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)

        if not keyring_available():
            warn = QLabel(
                "⚠ The 'keyring' package isn't installed. Install with "
                "<code>pip install keyring</code> so keys can be saved securely."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "color: #92400e; background: #fef3c7; "
                "padding: 6px 8px; border-radius: 4px; font-size: 11px;"
            )
            layout.addWidget(warn)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #e5e7eb; background: #e5e7eb;")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        # Form
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        # Make every field stretch to fill the dialog width — without this,
        # any field that isn't a QComboBox (whose default size policy is
        # Expanding) ends up narrower than the row above it.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.provider_combo = QComboBox()
        for key, cls in PROVIDERS.items():
            self.provider_combo.addItem(cls.info.display, userData=key)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self.provider_combo)

        self.model_combo = QComboBox()
        form.addRow("Model:", self.model_combo)

        # API key row — line edit + show/hide toggle
        key_w = QWidget()
        # Match the size policy of the QComboBoxes above so the row stretches
        # to fill the dialog width on every provider.
        key_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        key_row = QHBoxLayout(key_w)
        key_row.setContentsMargins(0, 0, 0, 0)   # drop the default 9–11px margins
        key_row.setSpacing(6)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Paste API key here")
        self.key_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        key_row.addWidget(self.key_edit, 1)
        self.show_key_btn = QPushButton("Show")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.setFixedWidth(60)
        self.show_key_btn.toggled.connect(self._toggle_key_visible)
        key_row.addWidget(self.show_key_btn, 0)
        form.addRow("API key:", key_w)

        layout.addLayout(form)

        # Info panel — refreshed on provider change
        self.info_lbl = QLabel()
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setStyleSheet(
            "background: #f3f4f6; padding: 8px 10px; border-radius: 5px;"
            " font-size: 11px; color: #374151;"
        )
        self.info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.info_lbl.setOpenExternalLinks(True)
        layout.addWidget(self.info_lbl)

        # Test connection
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Test connection")
        self.test_btn.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self.test_btn)
        self.test_status = QLabel("")
        self.test_status.setStyleSheet("font-size: 11px;")
        self.test_status.setWordWrap(True)
        self.test_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        test_row.addWidget(self.test_status, 1)
        layout.addLayout(test_row)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear stored key")
        clear_btn.clicked.connect(self._on_clear_key)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        save_btn.setStyleSheet(
            "QPushButton { background: #1d4ed8; color: white; "
            "border: none; border-radius: 5px; padding: 5px 16px; font-weight: 700; }"
            "QPushButton:hover { background: #1e40af; }"
        )
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    # ── data flow ───────────────────────────────────────────────────────
    def _current_provider_cls(self) -> type[AIProvider]:
        return PROVIDERS[self.provider_combo.currentData()]

    def _load_current(self):
        s = load_settings()
        name = s.get("provider")
        if name and name in PROVIDERS:
            idx = self.provider_combo.findData(name)
            if idx >= 0:
                self.provider_combo.setCurrentIndex(idx)

    def _on_provider_changed(self):
        cls = self._current_provider_cls()
        # Repopulate models
        self.model_combo.clear()
        for m in cls.info.models:
            self.model_combo.addItem(m)
        # Restore saved model if it matches this provider
        s = load_settings()
        if s.get("provider") == cls.info.name:
            saved_model = s.get("model")
            if saved_model and saved_model in cls.info.models:
                self.model_combo.setCurrentText(saved_model)
        # Info text
        self.info_lbl.setText(
            f"<b>{cls.info.display}</b><br>"
            f"{cls.info.pricing_note}<br>"
            f"Get an API key: <a href='{cls.info.docs_url}'>{cls.info.docs_url}</a><br>"
            f"Fallback env var: <code>{cls.info.key_env_var}</code>"
        )
        # Load existing key into field
        self.key_edit.clear()
        existing = cls.get_key()
        if existing:
            self.key_edit.setText(existing)
        self.test_status.setText("")

    def _toggle_key_visible(self, on: bool):
        self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )
        self.show_key_btn.setText("Hide" if on else "Show")

    # ── actions ─────────────────────────────────────────────────────────
    def _on_test_clicked(self):
        cls = self._current_provider_cls()
        key = self.key_edit.text().strip()
        if not key:
            self._set_status("Enter a key first.", ok=False)
            return
        # Temporarily save then probe — but if save fails just probe with an
        # ad-hoc instance that reads from a private attribute.
        ok, msg = cls.set_key(key)
        if not ok:
            self._set_status(msg, ok=False)
            return

        self._set_status("Testing…", ok=None)
        self.test_btn.setEnabled(False)
        worker = _ProbeWorker(cls(), self.model_combo.currentText(), parent=self)
        worker.done.connect(self._on_probe_done)
        worker.finished.connect(lambda: setattr(self, "_probe", None))
        worker.start()
        self._probe = worker

    def _on_probe_done(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        self._set_status(msg, ok=ok)

    def _on_clear_key(self):
        cls = self._current_provider_cls()
        cls.clear_key()
        self.key_edit.clear()
        self._set_status("Key cleared from credential store.", ok=None)

    def _on_save(self):
        cls = self._current_provider_cls()
        model = self.model_combo.currentText()
        key = self.key_edit.text().strip()

        if not key:
            QMessageBox.warning(
                self, "Missing key",
                f"Enter an API key for {cls.info.display} before saving."
            )
            return

        ok, msg = cls.set_key(key)
        if not ok:
            QMessageBox.critical(self, "Save failed", msg)
            return

        save_settings(cls.info.name, model)
        self.settings_saved.emit()
        self.accept()

    def _set_status(self, msg: str, ok: bool | None):
        if ok is True:
            color = "#15803d"   # green
        elif ok is False:
            color = "#b91c1c"   # red
        else:
            color = "#6b7280"   # neutral
        self.test_status.setStyleSheet(f"font-size: 11px; color: {color};")
        self.test_status.setText(msg)
