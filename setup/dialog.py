"""
setup.dialog — first-run API setup dialog.

Shown by AppMain before AppRoot is created, when neither an AI provider
nor an OpenWeather key is configured. Lets each end-user paste their own
keys up front; everything goes through the OS keystore via setup.keys and
ai.providers — no keys ship with the app.

The dialog is also reachable later (from AppRoot's menu / a button) to
re-configure keys.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFrame, QWidget, QSizePolicy, QMessageBox,
)

from ai.providers import PROVIDERS, load_settings, save_settings, keyring_available as ai_keyring_available
from setup.keys   import set_weather_key, get_weather_key, keyring_available as wx_keyring_available


class FirstRunSetupDialog(QDialog):
    """Combined AI Provider + OpenWeather key setup, used on first launch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SoilSense — first-time setup")
        self.setModal(True)
        self.resize(520, 540)
        self._build_ui()
        self._load_existing()

    # ── UI scaffolding ──────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Welcome — set up your API keys")
        title.setStyleSheet("font-size: 15px; font-weight: 800;")
        layout.addWidget(title)

        sub = QLabel(
            "SoilSense uses two API services. Configure your own keys "
            "below — they are stored in your operating system's secure "
            "credential store, never in any file shipped with the app. "
            "You can change them later from the Settings dialogs."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(sub)

        if not (ai_keyring_available() and wx_keyring_available()):
            warn = QLabel(
                "⚠ The 'keyring' package isn't installed. Install with "
                "<code>pip install keyring</code> so keys can be saved "
                "securely."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "color: #92400e; background: #fef3c7;"
                " padding: 6px 8px; border-radius: 4px; font-size: 11px;"
            )
            layout.addWidget(warn)

        # ─── AI Provider section ───────────────────────────────────────
        layout.addWidget(self._section_label("AI Provider (for crop summary)"))

        ai_form = QFormLayout()
        ai_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ai_form.setHorizontalSpacing(10)
        ai_form.setVerticalSpacing(6)
        ai_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.ai_provider_combo = QComboBox()
        for key, cls in PROVIDERS.items():
            self.ai_provider_combo.addItem(cls.info.display, userData=key)
        self.ai_provider_combo.currentIndexChanged.connect(self._on_ai_provider_changed)
        ai_form.addRow("Provider:", self.ai_provider_combo)

        self.ai_model_combo = QComboBox()
        ai_form.addRow("Model:", self.ai_model_combo)

        ai_key_w = QWidget()
        ai_key_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ai_key_row = QHBoxLayout(ai_key_w)
        ai_key_row.setContentsMargins(0, 0, 0, 0)
        ai_key_row.setSpacing(6)
        self.ai_key_edit = QLineEdit()
        self.ai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key_edit.setPlaceholderText("Paste AI provider key (optional)")
        ai_key_row.addWidget(self.ai_key_edit, 1)
        self._ai_show_btn = QPushButton("Show")
        self._ai_show_btn.setCheckable(True)
        self._ai_show_btn.setFixedWidth(60)
        self._ai_show_btn.toggled.connect(
            lambda on: self.ai_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        self._ai_show_btn.toggled.connect(
            lambda on: self._ai_show_btn.setText("Hide" if on else "Show")
        )
        ai_key_row.addWidget(self._ai_show_btn)
        ai_form.addRow("API key:", ai_key_w)

        layout.addLayout(ai_form)

        self.ai_info_lbl = QLabel("")
        self.ai_info_lbl.setWordWrap(True)
        self.ai_info_lbl.setStyleSheet(
            "background: #f3f4f6; padding: 6px 8px; border-radius: 5px;"
            " font-size: 11px; color: #374151;"
        )
        self.ai_info_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.ai_info_lbl.setOpenExternalLinks(True)
        layout.addWidget(self.ai_info_lbl)

        layout.addWidget(self._divider())

        # ─── OpenWeather section ───────────────────────────────────────
        layout.addWidget(self._section_label("OpenWeather (for weather panel)"))

        wx_form = QFormLayout()
        wx_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        wx_form.setHorizontalSpacing(10)
        wx_form.setVerticalSpacing(6)
        wx_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        wx_key_w = QWidget()
        wx_key_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wx_key_row = QHBoxLayout(wx_key_w)
        wx_key_row.setContentsMargins(0, 0, 0, 0)
        wx_key_row.setSpacing(6)
        self.wx_key_edit = QLineEdit()
        self.wx_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.wx_key_edit.setPlaceholderText("Paste OpenWeather key (optional)")
        wx_key_row.addWidget(self.wx_key_edit, 1)
        self._wx_show_btn = QPushButton("Show")
        self._wx_show_btn.setCheckable(True)
        self._wx_show_btn.setFixedWidth(60)
        self._wx_show_btn.toggled.connect(
            lambda on: self.wx_key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        self._wx_show_btn.toggled.connect(
            lambda on: self._wx_show_btn.setText("Hide" if on else "Show")
        )
        wx_key_row.addWidget(self._wx_show_btn)
        wx_form.addRow("API key:", wx_key_w)

        layout.addLayout(wx_form)

        wx_info = QLabel(
            "<b>OpenWeather</b> — sign up at "
            "<a href='https://openweathermap.org/'>openweathermap.org</a>.<br>"
            "<b>First-time users:</b> you must subscribe to the "
            "<b>'All-in-one Weather API'</b> plan (One Call 3.0) at "
            "<a href='https://openweathermap.org/api/one-call-3'>"
            "openweathermap.org/api/one-call-3</a> — the free tier covers "
            "1,000 calls/day. Then create a key at "
            "<a href='https://home.openweathermap.org/api_keys'>"
            "openweathermap.org/api_keys</a> and paste it above."
        )
        wx_info.setWordWrap(True)
        wx_info.setStyleSheet(
            "background: #f3f4f6; padding: 6px 8px; border-radius: 5px;"
            " font-size: 11px; color: #374151;"
        )
        wx_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        wx_info.setOpenExternalLinks(True)
        layout.addWidget(wx_info)

        layout.addStretch()

        # ─── Buttons ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        skip_btn = QPushButton("Skip for now")
        skip_btn.setToolTip(
            "Continue without keys. The app will run with limited "
            "functionality; you can configure later."
        )
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()
        save_btn = QPushButton("Save & continue")
        save_btn.setDefault(True)
        save_btn.setStyleSheet(
            "QPushButton { background: #1d4ed8; color: white; "
            "border: none; border-radius: 5px; padding: 6px 16px; "
            "font-weight: 700; }"
            "QPushButton:hover { background: #1e40af; }"
        )
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        # Trigger first provider population
        self._on_ai_provider_changed()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: 800; letter-spacing: 0.6px;"
            " color: #374151; padding: 4px 0 2px 0;"
        )
        return lbl

    @staticmethod
    def _divider() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color: #e5e7eb; background: #e5e7eb;")
        f.setFixedHeight(1)
        return f

    # ── data flow ───────────────────────────────────────────────────────
    def _load_existing(self):
        """Pre-fill fields with any keys/settings already saved."""
        # AI: load saved provider + key
        s = load_settings()
        if s.get("provider") in PROVIDERS:
            idx = self.ai_provider_combo.findData(s["provider"])
            if idx >= 0:
                self.ai_provider_combo.setCurrentIndex(idx)

        # Weather: load existing key
        existing_wx = get_weather_key()
        if existing_wx:
            self.wx_key_edit.setText(existing_wx)

    def _on_ai_provider_changed(self):
        cls = PROVIDERS[self.ai_provider_combo.currentData()]
        # Refresh model list
        self.ai_model_combo.clear()
        for m in cls.info.models:
            self.ai_model_combo.addItem(m)
        # Restore saved model if applicable
        s = load_settings()
        if s.get("provider") == cls.info.name and s.get("model") in cls.info.models:
            self.ai_model_combo.setCurrentText(s["model"])
        # Provider info
        self.ai_info_lbl.setText(
            f"<b>{cls.info.display}</b> — {cls.info.pricing_note}<br>"
            f"Get a key: <a href='{cls.info.docs_url}'>{cls.info.docs_url}</a>"
        )
        # Load existing key for this provider
        self.ai_key_edit.clear()
        existing = cls.get_key()
        if existing:
            self.ai_key_edit.setText(existing)

    def _on_save(self):
        """Persist whatever the user has filled in. Empty fields are skipped
        (so 'Save & continue' with only one section filled is supported)."""
        errors: list[str] = []

        ai_key = self.ai_key_edit.text().strip()
        if ai_key:
            cls = PROVIDERS[self.ai_provider_combo.currentData()]
            ok, msg = cls.set_key(ai_key)
            if ok:
                save_settings(cls.info.name, self.ai_model_combo.currentText())
            else:
                errors.append(f"AI key: {msg}")

        wx_key = self.wx_key_edit.text().strip()
        if wx_key:
            ok, msg = set_weather_key(wx_key)
            if not ok:
                errors.append(f"OpenWeather key: {msg}")

        if errors:
            QMessageBox.critical(self, "Save failed", "\n\n".join(errors))
            return
        self.accept()
