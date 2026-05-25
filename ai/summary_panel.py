"""
ai.summary_panel — one-shot AI agronomic summary for the Map View.

Provider-agnostic: dispatches to whichever AI provider the user picked in
the AI Settings dialog (Anthropic Claude / OpenAI GPT / Google Gemini).
Each user supplies their own API key — see ai.providers.
"""
from __future__ import annotations
import html
import json
import math
import re
from datetime import date
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextBrowser,
)

from ai.providers import (
    get_active_provider, is_configured,
)


_MAX_TOKENS = 4096


# ── prompt builder ──────────────────────────────────────────────────────
def _fmt_node_line(rec: dict) -> str:
    vwc      = rec.get("vwc")
    bulk     = rec.get("sigma_bulk")
    pore     = rec.get("sigma_pore")
    is_live  = bool(rec.get("is_live"))
    rec_date = rec.get("date")

    tag    = "[live]" if is_live else f"[prev {rec_date}]"
    vwc_s  = f"{vwc:.3f}"  if vwc  is not None else "—"
    bulk_s = f"{bulk:.3f}" if bulk is not None else "—"
    pore_s = f"{pore:.2f}" if pore is not None else "—"
    return f"    {rec['node_id']:>3}:  VWC={vwc_s}  Bulk EC={bulk_s}  Pore EC={pore_s}  {tag}"


def _fmt_weather(weather: dict | None) -> str:
    """Format current/past/next-week weather summaries into a readable block.

    Returns lines suitable for splicing into the prompt. Handles missing
    sections (None) and individual missing fields (None / NaN) gracefully —
    the WeatherLoader thread may not have completed before the user clicks
    AI Summary, in which case we just say so rather than omitting the
    section entirely.
    """
    if not weather:
        return "  (weather data not available — still loading or fetch failed)"

    def _is_nan(x):
        return isinstance(x, float) and math.isnan(x)

    def _s(val, fmt):
        if val is None or _is_nan(val):
            return "—"
        try:
            return fmt.format(val)
        except (ValueError, TypeError):
            return "—"

    lines: list[str] = []

    cur = weather.get("current")
    if cur:
        desc = cur.get("weather_description")
        desc_part = f", {desc}" if desc and desc != "N/A" else ""
        lines.append(
            f"  Current:  {_s(cur.get('temp'), '{:.1f}')}°C, "
            f"{_s(cur.get('humidity'), '{:.0f}')}% humidity, "
            f"{_s(cur.get('wind_speed'), '{:.1f}')} m/s wind"
            f"{desc_part}"
        )

    past = weather.get("past_week")
    if past:
        lines.append(
            f"  Past 7 days:  "
            f"temp {_s(past.get('lowest_temp'), '{:.1f}')}–{_s(past.get('highest_temp'), '{:.1f}')}°C "
            f"(avg {_s(past.get('avg_temp'), '{:.1f}')}°C), "
            f"humidity avg {_s(past.get('avg_humidity'), '{:.0f}')}%, "
            f"rainfall {_s(past.get('total_rainfall'), '{:.1f}')} mm, "
            f"avg wind {_s(past.get('avg_wind_speed'), '{:.1f}')} m/s"
        )

    nxt = weather.get("next_week")
    if nxt:
        lines.append(
            f"  Next 7 days (forecast):  "
            f"temp {_s(nxt.get('lowest_temp'), '{:.1f}')}–{_s(nxt.get('highest_temp'), '{:.1f}')}°C "
            f"(avg {_s(nxt.get('avg_temp'), '{:.1f}')}°C), "
            f"humidity avg {_s(nxt.get('avg_humidity'), '{:.0f}')}%, "
            f"expected rainfall {_s(nxt.get('total_rainfall'), '{:.1f}')} mm, "
            f"avg wind {_s(nxt.get('avg_wind_speed'), '{:.1f}')} m/s"
        )

    return "\n".join(lines) if lines else (
        "  (weather data not available — still loading or fetch failed)"
    )


def _build_prompt(config: dict, node_data: list[dict],
                  weather: dict | None = None) -> str:
    field = config.get("field", {})
    plots = config.get("plots", [])
    today = date.today().isoformat()
    by_id = {r.get("node_id"): r for r in node_data if r.get("node_id")}

    plot_blocks: list[str] = []
    for plot in plots:
        name     = plot.get("name", "?")
        planted  = plot.get("planting_date")
        node_ids = plot.get("nodes", [])
        recs     = [by_id[nid] for nid in node_ids if nid in by_id]
        if not recs:
            continue

        days_str = ""
        if planted:
            try:
                d = date.fromisoformat(planted)
                days_str = f"  ({(date.today() - d).days} days ago)"
            except ValueError:
                pass

        def _avg(key):
            vals = [r[key] for r in recs if r.get(key) is not None]
            return sum(vals) / len(vals) if vals else None

        avg_vwc, avg_bulk, avg_pore = _avg("vwc"), _avg("sigma_bulk"), _avg("sigma_pore")
        avg_vwc_s  = f"{avg_vwc:.3f}"  if avg_vwc  is not None else "—"
        avg_bulk_s = f"{avg_bulk:.3f}" if avg_bulk is not None else "—"
        avg_pore_s = f"{avg_pore:.2f}" if avg_pore is not None else "—"

        suffix = name[-1] if name.startswith("PD") and name[-1].isdigit() else ""
        title  = f"{name} — Planting Date {suffix}" if suffix else name

        block_lines = [
            f"=== {title} ===",
            f"  Planted: {planted or '—'}{days_str}",
            f"  Average: VWC={avg_vwc_s} m³/m³  Bulk EC={avg_bulk_s} dS/m  Pore EC={avg_pore_s} dS/m",
            "  Nodes:",
            *[_fmt_node_line(r) for r in recs],
        ]
        plot_blocks.append("\n".join(block_lines))

    return (
        "You are an agronomist assistant for a precision agriculture experiment.\n\n"
        f"Field:  {field.get('name', '—')}, {field.get('location', '—')}\n"
        f"Season: {field.get('season', '—')}   Today: {today}\n"
        f"Crop:   {field.get('crop', '—')} ({field.get('variety', '—')})\n\n"
        "Weather (units: °C, m/s, mm):\n"
        + _fmt_weather(weather) + "\n\n"
        "Soil sensor readings:\n\n"
        + ("\n\n".join(plot_blocks) if plot_blocks else "  (no readings available)")
        + "\n\n"
        "Soil moisture reference thresholds:\n"
        "  VWC < 0.15  →  dry, potential water stress\n"
        "  VWC 0.15–0.25  →  moderate\n"
        "  VWC > 0.25  →  adequate\n"
        "  Bulk EC > 2 dS/m  →  salinity concern\n\n"
        "Provide a concise agronomic report:\n"
        "1. Soil moisture and salinity status per plot.\n"
        "2. Effect of planting date difference on crop development given current\n"
        "   conditions and recent weather.\n"
        "3. Irrigation or management recommendations per plot, factoring in the\n"
        "   forecast rainfall and temperature for the coming week.\n"
        "4. Any urgent actions for this week (e.g. weather-driven risks like heat\n"
        "   stress, heavy rain leading to runoff, or extended dry spells).\n\n"
        "Use plain language for a field agronomist. Be specific and practical."
    )


# ── worker thread ───────────────────────────────────────────────────────
class _ApiWorker(QThread):
    """One-shot call to the active AI provider, off the UI thread."""
    result_ready   = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, provider, model: str, prompt: str, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._model    = model
        self._prompt   = prompt

    def run(self):
        try:
            text = self._provider.generate(
                self._prompt, self._model, _MAX_TOKENS
            )
            self.result_ready.emit(text)
        except ImportError as e:
            self.error_occurred.emit(
                f"Missing dependency: {e}.\n"
                "Install the required SDK (e.g. 'pip install anthropic openai')."
            )
        except Exception as e:
            self.error_occurred.emit(str(e).splitlines()[0][:300] or repr(e))


# ── result dialog ───────────────────────────────────────────────────────
class _ResultDialog(QDialog):
    """Non-modal floating dialog with scrollable text + Copy/Close buttons.

    Theming strategy
    ────────────────
    All theme-sensitive colors live in the `_DARK` / `_LIGHT` dicts below.
    A single `_apply_theme()` method styles every widget in the dialog
    (dialog background, title, provider sub-line, divider, text view +
    its scrollbar) using the active palette. It's called on:

    * dialog construction (initial render)
    * every state change — set_loading / set_text / set_error
    * the parent AppRoot's `theme_changed` signal (so the dialog repaints
      live when the user toggles theme while it's open)

    This is the *only* place colors are defined. No widget reaches outside
    the palette dict.
    """

    # ── Theme palettes ──────────────────────────────────────────────────
    _DARK = {
        "dialog_bg":     "#0d1117",   # outer dialog body
        "panel_bg":      "#161b22",   # text-view background
        "panel_border":  "#30363d",   # text-view + scrollbar border
        "text":          "#f0f6fc",   # primary body text
        "muted":         "#9ca3af",   # provider sub-line, loading state
        "divider":       "#30363d",   # horizontal rule under header
        "scroll_track":  "#161b22",
        "scroll_handle": "#30363d",
        "scroll_hover":  "#6b7280",
        "error":         "#f87171",
    }
    _LIGHT = {
        "dialog_bg":     "#ffffff",
        "panel_bg":      "#ffffff",
        "panel_border":  "#e5e7eb",
        "text":          "#111827",
        "muted":         "#6b7280",
        "divider":       "#e5e7eb",
        "scroll_track":  "#f3f4f6",
        "scroll_handle": "#9ca3af",
        "scroll_hover":  "#6b7280",
        "error":         "#b91c1c",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Crop Summary")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)
        self.resize(580, 500)
        self._raw_text = ""
        self._state    = "empty"   # "empty" | "loading" | "text" | "error"
        self._build_ui()
        self._apply_theme()
        self._connect_theme_signal()

    # ── UI scaffolding ──────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_lbl = QLabel("AI Crop Summary & Recommendations")
        header.addWidget(self.title_lbl)
        header.addStretch()
        self.copy_btn = QPushButton("Copy text")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_text)
        header.addWidget(self.copy_btn)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        self.provider_lbl = QLabel("")
        layout.addWidget(self.provider_lbl)

        self._divider = QFrame()
        self._divider.setFrameShape(QFrame.Shape.HLine)
        self._divider.setFixedHeight(1)
        layout.addWidget(self._divider)

        self._text_view = QTextBrowser()
        self._text_view.setReadOnly(True)
        self._text_view.setOpenExternalLinks(True)
        self._text_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self._text_view, 1)

    def set_provider_label(self, label: str):
        self.provider_lbl.setText(label)

    # ── theme detection ─────────────────────────────────────────────────
    def _is_dark(self) -> bool:
        """Walk up to AppRoot for the authoritative `_dark` flag."""
        w = self.parent()
        while w is not None:
            val = getattr(w, "_dark", None)
            if isinstance(val, bool):
                return val
            w = w.parent()
        try:
            return self.palette().color(self.backgroundRole()).lightness() < 128
        except Exception:
            return False

    def _palette(self) -> dict:
        return self._DARK if self._is_dark() else self._LIGHT

    def _connect_theme_signal(self):
        """Hook AppRoot's theme_changed signal so the dialog repaints when
        the user toggles theme *while the dialog is already showing*. Use a
        bound method (not a lambda) so Qt auto-disconnects when this dialog
        is destroyed."""
        w = self.parent()
        while w is not None:
            sig = getattr(w, "theme_changed", None)
            if sig is not None:
                try:
                    sig.connect(self._on_theme_changed)
                    return
                except Exception:
                    pass
            w = w.parent()

    def _on_theme_changed(self, _dark: bool):
        self._apply_theme()

    # ── unified theming (the only place colors are written) ─────────────
    def _apply_theme(self):
        p = self._palette()

        # Dialog body
        self.setStyleSheet(f"QDialog {{ background: {p['dialog_bg']}; }}")

        # Header title
        self.title_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 700; "
            f"color: {p['text']}; background: transparent;"
        )

        # Provider sub-line (muted)
        self.provider_lbl.setStyleSheet(
            f"font-size: 11px; color: {p['muted']}; background: transparent;"
        )

        # Divider line
        self._divider.setStyleSheet(
            f"background: {p['divider']}; color: {p['divider']}; border: none;"
        )

        # Text view + scrollbar — owned by this method, always uses current state
        self._apply_text_view_style()

    def _apply_text_view_style(self):
        """Re-style the QTextBrowser according to the current theme AND the
        current state (text vs loading vs error)."""
        p = self._palette()
        if self._state == "loading":
            fg, italic = p["muted"], "font-style: italic;"
        elif self._state == "error":
            fg, italic = p["error"], ""
        else:
            fg, italic = p["text"], ""

        self._text_view.setStyleSheet(
            # ── document area ─────────────────────────────────────────
            f"QTextBrowser {{"
            f" background: {p['panel_bg']};"
            f" color: {fg};"
            f" border: 1px solid {p['panel_border']};"
            f" border-radius: 4px;"
            f" padding: 8px;"
            f" font-size: 12px;"
            f" {italic}"
            f"}}"
            # ── vertical scrollbar — explicit, no native dependence ───
            f"QTextBrowser QScrollBar:vertical {{"
            f" background: {p['scroll_track']};"
            f" width: 10px;"
            f" margin: 2px 1px 2px 0;"
            f" border-radius: 5px;"
            f"}}"
            f"QTextBrowser QScrollBar::handle:vertical {{"
            f" background: {p['scroll_handle']};"
            f" min-height: 30px;"
            f" border-radius: 4px;"
            f"}}"
            f"QTextBrowser QScrollBar::handle:vertical:hover {{"
            f" background: {p['scroll_hover']};"
            f"}}"
            # Hide the up/down arrow buttons — modern minimal scrollbar look
            f"QTextBrowser QScrollBar::add-line:vertical,"
            f"QTextBrowser QScrollBar::sub-line:vertical {{"
            f" height: 0; width: 0; background: transparent; border: none;"
            f"}}"
            f"QTextBrowser QScrollBar::add-page:vertical,"
            f"QTextBrowser QScrollBar::sub-page:vertical {{"
            f" background: transparent;"
            f"}}"
        )

    # ── state setters ───────────────────────────────────────────────────
    def set_loading(self):
        self._raw_text = ""
        self._state = "loading"
        self.copy_btn.setEnabled(False)
        self._apply_text_view_style()
        self._text_view.setHtml("Calling AI model — usually 5–15 seconds…")

    def set_text(self, text: str):
        self._raw_text = text
        self._state = "text"
        self.copy_btn.setEnabled(True)
        self._apply_text_view_style()
        self._text_view.setHtml(_md_to_html(text))

    def set_error(self, msg: str):
        self._raw_text = ""
        self._state = "error"
        self.copy_btn.setEnabled(False)
        self._apply_text_view_style()
        err_html = (
            f"<b>Error:</b> {html.escape(msg)}".replace("\n", "<br>")
        )
        self._text_view.setHtml(err_html)

    def _copy_text(self):
        if self._raw_text:
            QGuiApplication.clipboard().setText(self._raw_text)


def _md_to_html(text: str) -> str:
    """Minimal Markdown → HTML for QLabel rich-text mode.

    Handles ATX headings (`#` … `######`), **bold**, *italic*, and converts
    line breaks to <br>. Sized so the report reads well at the dialog's
    12px base font.
    """
    # Inline style per heading level — explicit sizing because QLabel rich
    # text doesn't apply browser-default <h*> sizes consistently.
    _HEAD_STYLES = {
        1: "font-size:17px; font-weight:800;",
        2: "font-size:15px; font-weight:800;",
        3: "font-size:14px; font-weight:700;",
        4: "font-size:13px; font-weight:700;",
        5: "font-size:12px; font-weight:700;",
        6: "font-size:12px; font-weight:600;",
    }

    out = html.escape(text)

    # Headings — match longest-first so `####` is recognized as h4 before
    # being mistaken for h3 + extra `#`. Anchored to start of each line.
    for level in range(6, 0, -1):
        pattern = r"^" + "#" * level + r"\s+(.+)$"
        repl    = rf'<h{level} style="{_HEAD_STYLES[level]}">\1</h{level}>'
        out = re.sub(pattern, repl, out, flags=re.MULTILINE)

    # **bold** runs before *italic* so the italic pattern doesn't eat the
    # opening `**`.
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", out)

    # The closing </h*> tag is block-level; the following newline would
    # otherwise turn into a redundant <br>.
    out = re.sub(r"(</h\d>)\n", r"\1", out)

    # Everything else → <br> for QLabel.
    return out.replace("\n", "<br>")


# ── orchestrator ────────────────────────────────────────────────────────
class AISummaryPanel:
    """Owns the dialog + worker. `run(node_data)` from a button click.

    `open_settings_callback` is invoked when the user clicks the AI Summary
    button but no provider is configured — the host wires this to its
    settings-dialog launcher.
    """

    def __init__(self, config_path: str | Path,
                 parent=None,
                 open_settings_callback=None):
        self._config_path = Path(config_path)
        self._parent      = parent
        self._open_settings = open_settings_callback
        self._dialog: _ResultDialog | None = None
        self._worker: _ApiWorker | None    = None

    def run(self, node_data: list[dict],
            weather: dict | None = None) -> None:
        # Re-surface a pending dialog instead of stacking calls
        if self._worker is not None and self._worker.isRunning():
            if self._dialog:
                self._dialog.raise_()
                self._dialog.activateWindow()
            return

        # No provider configured → open Settings instead of erroring
        if not is_configured():
            if self._open_settings:
                self._open_settings()
            else:
                self._ensure_dialog()
                self._dialog.show()
                self._dialog.set_error(
                    "No AI provider configured.\n"
                    "Open AI Settings to choose a provider and enter your API key."
                )
            return

        provider_cls, model = get_active_provider()
        if provider_cls is None:
            return  # defensive — is_configured() already gated this

        try:
            with open(self._config_path) as f:
                config = json.load(f)
        except Exception as e:
            self._ensure_dialog()
            self._dialog.show()
            self._dialog.set_error(f"Failed to read {self._config_path}: {e}")
            return

        if not node_data:
            self._ensure_dialog()
            self._dialog.show()
            self._dialog.set_provider_label(
                f"{provider_cls.info.display} · {model}"
            )
            self._dialog.set_error(
                "No soil records loaded yet. Collect data or select a date "
                "with available historical readings, then try again."
            )
            return

        prompt = _build_prompt(config, node_data, weather=weather)

        self._ensure_dialog()
        self._dialog.set_provider_label(
            f"{provider_cls.info.display} · {model}"
        )
        self._dialog.set_loading()
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

        worker = _ApiWorker(provider_cls(), model, prompt, parent=self._parent)
        worker.result_ready.connect(self._dialog.set_text)
        worker.error_occurred.connect(self._dialog.set_error)
        worker.finished.connect(self._on_worker_done)
        worker.start()
        self._worker = worker

    def _ensure_dialog(self):
        if self._dialog is None:
            self._dialog = _ResultDialog(self._parent)

    def _on_worker_done(self):
        self._worker = None
