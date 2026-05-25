from __future__ import annotations
import os
import random
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib import font_manager as fm

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLabel, QGroupBox, QDialog, QDialogButtonBox, QFileDialog,
    QRadioButton, QButtonGroup, QSpinBox, QDoubleSpinBox,
    QCheckBox, QGridLayout, QSizePolicy, QMessageBox,
    QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, QSize, QPointF, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QIcon, QColor, QPen

BG = "#eff0f7"
TEAL = "#008081"

# Publication matplotlib style (IEEE-compatible)
_PUB_STYLE = {
    "font.family":       "serif",
    "font.size":         8,
    "axes.labelsize":    9,
    "xtick.labelsize":   8,
    "ytick.labelsize":   8,
    "legend.fontsize":   7,
    "lines.linewidth":   1.0,
    "axes.linewidth":    0.6,
    "axes.facecolor":    "white",
    "figure.facecolor":  "white",
    "grid.color":        "lightgray",
    "grid.linewidth":    0.4,
}

# IEEE column widths in inches
_WIDTHS = {
    "IEEE Single Column (3.5\")":  3.54,
    "IEEE Double Column (7.16\")": 7.16,
    "Nature Single (3.5\")":       3.54,
    "Nature Double (7.08\")":      7.08,
    "Full page (10\")":            10.0,
}


class PubExportDialog(QDialog):
    """Publication-quality export settings dialog."""

    def __init__(self, fig, parent=None):
        super().__init__(parent)
        self.fig = fig
        self.setWindowTitle("Export Figure")
        self.setModal(True)
        self.resize(420, 360)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)

        # Format
        grid.addWidget(QLabel("Format:"), 0, 0)
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["PNG", "PDF", "SVG", "EPS"])
        self.fmt_combo.currentTextChanged.connect(self._on_format_changed)
        grid.addWidget(self.fmt_combo, 0, 1)

        # DPI
        grid.addWidget(QLabel("DPI:"), 1, 0)
        self.dpi_combo = QComboBox()
        self.dpi_combo.addItems(["150", "300", "600"])
        self.dpi_combo.setCurrentText("300")
        grid.addWidget(self.dpi_combo, 1, 1)

        # Column width
        grid.addWidget(QLabel("Width preset:"), 2, 0)
        self.width_combo = QComboBox()
        self.width_combo.addItems(list(_WIDTHS.keys()) + ["Custom"])
        self.width_combo.currentTextChanged.connect(self._on_width_changed)
        grid.addWidget(self.width_combo, 2, 1)

        # Custom width
        self.custom_w_label = QLabel("  Width (in):")
        self.custom_w_spin = QDoubleSpinBox()
        self.custom_w_spin.setRange(1.0, 20.0)
        self.custom_w_spin.setValue(7.16)
        self.custom_w_spin.setSingleStep(0.1)
        self.custom_w_label.setVisible(False)
        self.custom_w_spin.setVisible(False)
        grid.addWidget(self.custom_w_label, 3, 0)
        grid.addWidget(self.custom_w_spin, 3, 1)

        # Aspect ratio
        grid.addWidget(QLabel("Height (in):"), 4, 0)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1.0, 20.0)
        self.height_spin.setValue(4.5)
        self.height_spin.setSingleStep(0.1)
        grid.addWidget(self.height_spin, 4, 1)

        # Publication style
        self.pub_style_cb = QCheckBox("Apply publication style (clean IEEE/ACS)")
        self.pub_style_cb.setChecked(True)
        grid.addWidget(self.pub_style_cb, 5, 0, 1, 2)

        layout.addLayout(grid)

        info = QLabel(
            "Publication style: white background, serif font,\n"
            "no top/right spines, 8pt tick labels (IEEE-compatible)."
        )
        info.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._export)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_format_changed(self, fmt: str):
        is_raster = fmt in ("PNG",)
        self.dpi_combo.setEnabled(is_raster)

    def _on_width_changed(self, text: str):
        is_custom = text == "Custom"
        self.custom_w_label.setVisible(is_custom)
        self.custom_w_spin.setVisible(is_custom)

    def _export(self):
        folder = QFileDialog.getExistingDirectory(self, "Select save folder")
        if not folder:
            return

        fmt = self.fmt_combo.currentText().lower()
        dpi = int(self.dpi_combo.currentText())
        width_key = self.width_combo.currentText()
        width_in  = self.custom_w_spin.value() if width_key == "Custom" else _WIDTHS[width_key]
        height_in = self.height_spin.value()
        pub_style = self.pub_style_cb.isChecked()

        # ── Snapshot every piece of state we are about to touch, so the
        # on-screen figure can be restored EXACTLY after savefig() — no
        # hardcoded colors, no leftover hidden spines, no shrunk fonts. ──
        orig_size       = self.fig.get_size_inches()
        orig_fig_color  = self.fig.get_facecolor()
        orig_rc         = {}
        orig_ax_state   = []
        for ax in self.fig.get_axes():
            orig_ax_state.append({
                "facecolor":     ax.get_facecolor(),
                "top_visible":   ax.spines["top"].get_visible(),
                "right_visible": ax.spines["right"].get_visible(),
                "xlabel_size":   ax.xaxis.label.get_fontsize(),
                "ylabel_size":   ax.yaxis.label.get_fontsize(),
                "xtick_sizes":   [t.get_fontsize() for t in ax.get_xticklabels()],
                "ytick_sizes":   [t.get_fontsize() for t in ax.get_yticklabels()],
            })
        orig_legend_sizes = [
            [t.get_fontsize() for t in legend.get_texts()]
            for legend in self.fig.legends
        ]

        try:
            if pub_style:
                orig_rc = {k: matplotlib.rcParams[k] for k in _PUB_STYLE
                           if k in matplotlib.rcParams}
                matplotlib.rcParams.update(_PUB_STYLE)
                # Existing artists were created with explicit fontproperties,
                # so rcParams alone won't shrink them. Override directly.
                lbl_sz   = _PUB_STYLE["axes.labelsize"]
                xtick_sz = _PUB_STYLE["xtick.labelsize"]
                ytick_sz = _PUB_STYLE["ytick.labelsize"]
                lgd_sz   = _PUB_STYLE["legend.fontsize"]
                self.fig.patch.set_facecolor("white")
                for ax in self.fig.get_axes():
                    ax.set_facecolor("white")
                    ax.spines["top"].set_visible(False)
                    ax.spines["right"].set_visible(False)
                    ax.xaxis.label.set_fontsize(lbl_sz)
                    ax.yaxis.label.set_fontsize(lbl_sz)
                    for t in ax.get_xticklabels():
                        t.set_fontsize(xtick_sz)
                    for t in ax.get_yticklabels():
                        t.set_fontsize(ytick_sz)
                for legend in self.fig.legends:
                    for t in legend.get_texts():
                        t.set_fontsize(lgd_sz)

            self.fig.set_size_inches(width_in, height_in)

            now  = datetime.now()
            name = f"fig_{now.year%100:02d}{now.month:02d}{now.day:02d}_{now.hour:02d}{now.minute:02d}.{fmt}"
            path = os.path.join(folder, name)
            self.fig.savefig(path, dpi=dpi, bbox_inches="tight")

            QMessageBox.information(self, "Saved", f"Figure saved to:\n{path}")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
        finally:
            # ── Restore everything to exactly the pre-export state ────────
            self.fig.set_size_inches(*orig_size)
            if orig_rc:
                matplotlib.rcParams.update(orig_rc)
            self.fig.patch.set_facecolor(orig_fig_color)
            for ax, state in zip(self.fig.get_axes(), orig_ax_state):
                ax.set_facecolor(state["facecolor"])
                ax.spines["top"].set_visible(state["top_visible"])
                ax.spines["right"].set_visible(state["right_visible"])
                ax.xaxis.label.set_fontsize(state["xlabel_size"])
                ax.yaxis.label.set_fontsize(state["ylabel_size"])
                for t, sz in zip(ax.get_xticklabels(), state["xtick_sizes"]):
                    t.set_fontsize(sz)
                for t, sz in zip(ax.get_yticklabels(), state["ytick_sizes"]):
                    t.set_fontsize(sz)
            for legend, sizes in zip(self.fig.legends, orig_legend_sizes):
                for t, sz in zip(legend.get_texts(), sizes):
                    t.set_fontsize(sz)
            # Repaint so the change is visible immediately
            if self.fig.canvas is not None:
                self.fig.canvas.draw_idle()


class PlotPanel(QWidget):
    """
    Dual-axis frequency response plot (magnitude dB + phase °).
    Exposes calculate_freq_mag_phase / create_label / update_plot
    so the bridge proxy can call them from the serial thread.
    """

    # Emitted whenever a new line is drawn — host uses this to trigger soil-
    # property calculation. Args: (label, source_path, is_live)
    #   label       displayed legend label (same one passed to update_plot)
    #   source_path absolute path of the file the curve came from. Empty when
    #               unknown (live data — the host resolves via DataMaster).
    #   is_live     True for radio-received data, False for user-imported.
    line_added = pyqtSignal(str, str, bool)

    # Emitted when a single curve is removed (label) or every curve is cleared.
    # The host uses these to keep the soil-properties table in sync.
    line_removed  = pyqtSignal(str)
    lines_cleared = pyqtSignal()

    # Curated palette — distinguishable, color-blind-friendlier than random RGB
    _LINE_COLORS = [
        "#1d4ed8",  # blue
        "#dc2626",  # red
        "#15803d",  # green
        "#a21caf",  # purple
        "#ea580c",  # orange
        "#0891b2",  # cyan
        "#be185d",  # pink
        "#65a30d",  # lime
        "#7c3aed",  # violet
        "#0f766e",  # teal
    ]

    # Frequency span we want visible by default (Hz)
    _X_MIN = 1e2
    _X_MAX = 1e9

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.lines_ax1: list = []
        self.lines_ax2: list = []
        self.legend = None

        # Nav-icon colors. Light mode defaults — set_dark_theme() flips them.
        self._nav_icon_off = "#1e3a8a"   # btn_fg (light mode)
        self._nav_icon_on  = "#ffffff"   # pri_fg (white in both themes)

        # Separate font sizes for axis labels vs ticks vs legend.
        # family="Segoe UI" matches the app-wide QFont set in AppMain.
        self.label_font  = fm.FontProperties(family="Segoe UI", size=9)
        self.tick_font   = fm.FontProperties(family="Segoe UI", size=8.5)
        self.legend_font = fm.FontProperties(family="Segoe UI", size=8)
        self.annot_font  = fm.FontProperties(family="Segoe UI", size=8)
        # Kept for backward compat with any external reference
        self.custom_font = self.tick_font

        self._build_ui()
        self._draw_plot()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Canvas placeholder — filled by _draw_plot
        self.canvas_container = QWidget()
        self.canvas_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.canvas_container, stretch=1)

        # Bottom toolbar (Export / Import / Soil properties / Remove line).
        # Home / Pan / Zoom buttons live ABOVE the figure now — see _draw_plot.
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("chartToolbar")
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(6, 2, 6, 2)
        toolbar.setSpacing(8)
        self._toolbar_layout = toolbar

        self.export_btn = QPushButton("Export Figure")
        self.export_btn.clicked.connect(self._open_export_dialog)
        toolbar.addWidget(self.export_btn)

        self.import_btn = QPushButton("Import Data to Compare")
        self.import_btn.clicked.connect(self._import_data)
        toolbar.addWidget(self.import_btn)

        # "Soil properties" — opens a non-modal floating panel.
        # The CommCollectPage host wires soil_properties_btn.clicked to its
        # SoilPropertiesPanel.show(); the button is just a launcher here so
        # this widget stays decoupled from the host's data flow.
        self.soil_properties_btn = QPushButton("Soil properties")
        toolbar.addWidget(self.soil_properties_btn)

        # Trailing stretch keeps Remove-line snug against the right edge.
        toolbar.addStretch()

        toolbar.addWidget(QLabel("Remove line:"))
        self.line_combo = QComboBox()
        self.line_combo.setMinimumWidth(160)
        self.line_combo.activated.connect(self._delete_selected_line)
        toolbar.addWidget(self.line_combo)

        # Horizontal scroll area: only kicks in when the toolbar's natural
        # width exceeds the panel; otherwise it behaves like a plain row.
        toolbar_scroll = QScrollArea()
        toolbar_scroll.setWidget(toolbar_widget)
        toolbar_scroll.setWidgetResizable(True)
        toolbar_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        toolbar_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        toolbar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        toolbar_scroll.setStyleSheet("QScrollArea { background: transparent; }")
        toolbar_scroll.setFixedHeight(38)
        layout.addWidget(toolbar_scroll)

        canvas_layout = QVBoxLayout(self.canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self._canvas_layout = canvas_layout

    def _draw_plot(self):
        self.fig, (self.ax1, self.ax2) = plt.subplots(nrows=2, ncols=1, sharex=True)
        # Tight margins: just enough for tick labels + axis labels. No more
        # giant blank gutter on the left or floating x-title at the bottom.
        self.fig.subplots_adjust(
            top=0.97, bottom=0.18, left=0.085, right=0.985, hspace=0.07,
        )

        from styles import PLOT_LIGHT as _P
        self.fig.set_facecolor(_P["fig_bg"])
        for ax in (self.ax1, self.ax2):
            ax.set_facecolor(_P["ax_bg"])
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            # Keep a subtle left spine so the y-axis is anchored visually
            ax.spines["left"].set_visible(True)
            ax.spines["left"].set_color(_P["grid"])
            ax.spines["left"].set_linewidth(0.6)
            ax.spines["bottom"].set_color(_P["grid"])
            ax.spines["bottom"].set_linewidth(0.6)
            ax.set_xscale("log")
            ax.set_xlim(self._X_MIN, self._X_MAX)
            # Major gridlines on both axes, minor decade ticks on x
            ax.grid(True, which="major", axis="both",
                    color=_P["grid"], linewidth=0.6, alpha=0.85)
            ax.grid(True, which="minor", axis="x",
                    color=_P["grid"], linewidth=0.35, alpha=0.5)
            ax.tick_params(axis="x", which="both",
                           color=_P["tick"], width=0.6)
            ax.tick_params(axis="y", color=_P["tick"], width=0.6)

        # Axis labels — bigger, semibold, snug against the axis
        self.ax1.set_ylabel("Magnitude Ratio (dB)",
                            fontproperties=self.label_font, labelpad=4)
        self.ax2.set_ylabel("Absolute Phase Difference (°)",
                            fontproperties=self.label_font, labelpad=4)
        # X-label attached directly to ax2 instead of fig.supxlabel — sits
        # right under the tick labels, not floating in the bottom margin.
        self.ax2.set_xlabel("Frequency (Hz)",
                            fontproperties=self.label_font, labelpad=4)
        # Keep a no-op handle so set_dark_theme can still color it.
        self._supxlabel = self.ax2.xaxis.label

        for label in (self.ax1.get_yticklabels() + self.ax2.get_yticklabels()
                      + self.ax2.get_xticklabels()):
            label.set_fontproperties(self.tick_font)

        self.annot = self.fig.text(
            0, 0, "", bbox=dict(boxstyle="round", fc="w"),
            ha="center", fontproperties=self.annot_font, visible=False,
        )

        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.mpl_connect("motion_notify_event", self._hover)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self._canvas_layout.addWidget(self.canvas)

        # Backend nav toolbar — kept around purely so we can call .home(),
        # .pan(), .zoom() from our own buttons. The QToolBar widget itself is
        # never shown (its built-in PNG icons don't theme, so they vanish in
        # dark mode). Our themed QPushButtons drive it instead.
        self.nav_toolbar = NavigationToolbar2QT(self.canvas, self)
        self.nav_toolbar.hide()

        # Themed Home / Pan / Zoom buttons — icon-only, painted by QPainter so
        # they're visible in both light and dark mode. Compact size; the buttons
        # live in a small mini-bar that hugs the top edge of the figure.
        icon_size = QSize(14, 14)
        for attr, kind, tip in (
            ("home_btn", "home", "Home — reset view to original"),
            ("pan_btn",  "pan",  "Pan — click-drag to move the view"),
            ("zoom_btn", "zoom", "Zoom — drag a rectangle to zoom in"),
        ):
            btn = QPushButton()
            btn.setProperty("role", "navtool")
            btn.setToolTip(tip)
            btn.setIcon(self._build_nav_icon(kind))
            btn.setIconSize(icon_size)
            btn.setFixedSize(QSize(26, 22))
            if kind in ("pan", "zoom"):
                btn.setCheckable(True)
            setattr(self, attr, btn)

        self.home_btn.clicked.connect(self.nav_toolbar.home)
        self.pan_btn.clicked.connect(self._toggle_pan)
        self.zoom_btn.clicked.connect(self._toggle_zoom)

        # Mini nav-bar that hugs the figure on top. No extra vertical space:
        # `setFixedHeight` matches the button height so the row consumes only
        # what the buttons themselves need.
        nav_bar = QWidget()
        nav_bar.setFixedHeight(24)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(2, 1, 2, 1)
        nav_layout.setSpacing(3)
        nav_layout.addWidget(self.home_btn)
        nav_layout.addWidget(self.pan_btn)
        nav_layout.addWidget(self.zoom_btn)
        nav_layout.addStretch()
        # Add BEFORE the canvas so it sits directly above the figure.
        self._canvas_layout.insertWidget(0, nav_bar)

    # ── public API called by the bridge proxy ────────────────────────────────

    def calculate_freq_mag_phase(self, IDs, mag, phs):
        IDs = np.asarray(IDs)
        mag = np.asarray(mag, dtype=float)
        phs = np.asarray(phs, dtype=float)

        fre = np.zeros(len(IDs))
        fre[IDs <= 10]                        = 100 * IDs[IDs <= 10]
        mask_mid = (IDs > 10) & (IDs <= 110)
        fre[mask_mid] = 10 ** (0.03 * (IDs[mask_mid] - 10)) * 1000
        fre[IDs > 110] = 10 ** (0.003 * (IDs[IDs > 110] - 110)) * 1e6

        mag = (mag / 4095 * 3.3 / 1.8 - 1.8) / 0.06
        phs = (phs / 4095 * 3.3 / 1.8 - 0.9) / (-0.01) + 90
        phs = phs + abs(phs.min())
        return fre, mag, phs

    def create_label(self, file_path: str, filetype: str) -> str:
        parts = file_path.replace("\\", "/").split("/")
        if ".csv" in filetype:
            filename = parts[-1]
            try:
                node_number = filename.split("-")[0][1:]
                date_txt    = filename.split("-")[1]
                time_txt    = filename.split("-")[2]
                date_parts  = date_txt.split("_")
                time_parts  = time_txt.split("_")
                return f"Node {node_number} " + "".join(date_parts) + "_" + "".join(time_parts[:2])
            except Exception:
                return os.path.splitext(parts[-1])[0]
        else:
            if "Lab" in parts:
                return f"{parts[-3]} {parts[-2]} {os.path.splitext(parts[-1])[0]}"
            if "UG nodes" in parts:
                nm = {"EP_WN": 3, "EP_ON": 5, "LP_WN": 7, "LP_ON": 9}
                try:
                    p1  = parts[-3]
                    p2  = parts[-2].split("_")[0]
                    num = nm.get(f"{p1}_{p2}", "?")
                    p3  = os.path.splitext(parts[-1])[0].split("_")[1]
                    p4  = os.path.splitext(parts[-1])[0].split("_")[2][:4]
                    return f"Node {num} {p3}_{p4}"
                except Exception:
                    pass
            return os.path.splitext(parts[-1])[0]

    def update_plot(self, freq, mag_dB, phs_deg, label: str,
                    source_path: str = "", is_live: bool = True):
        """
        Add a new pair of lines to both axes and emit `line_added`.

        Called two ways:
          - via bridge.plot_update signal (live radio data) — source_path
            is empty here; we pop it from _pending_source_paths (populated
            on the serial thread by _PlotProxy.update_plot, in the same
            FIFO order as the queued signals).
          - directly from _load_file() for user-imported files — passes
            source_path=path, is_live=False.
        """
        # Resolve source_path for the live path. List ops are atomic under
        # the GIL, so this pop and the proxy's append are safe across threads.
        if not source_path:
            q = getattr(self, "_pending_source_paths", None)
            if q:
                source_path = q.pop(0)

        freq    = np.asarray(freq)
        mag_dB  = np.asarray(mag_dB)
        phs_deg = np.asarray(phs_deg)

        color = self._LINE_COLORS[len(self.lines_ax1) % len(self._LINE_COLORS)]

        line1, = self.ax1.plot(freq, mag_dB,  linestyle="-", linewidth=1.6,
                               color=color, label=label, alpha=0.92)
        line2, = self.ax2.plot(freq, phs_deg, linestyle="-", linewidth=1.6,
                               color=color, label=label, alpha=0.92)
        self.lines_ax1.append(line1)
        self.lines_ax2.append(line2)

        # Autoscale y only — keep the fixed log-frequency x-range
        self.ax1.relim(); self.ax1.autoscale_view(scalex=False)
        self.ax2.relim(); self.ax2.autoscale_view(scalex=False)

        if self.legend:
            self.legend.remove()
        labels = [l.get_label() for l in self.lines_ax1]
        self.legend = self.fig.legend(
            self.lines_ax1, labels,
            loc="lower center", bbox_to_anchor=(0.5, 0.005),
            ncol=4, prop=self.legend_font, columnspacing=0.95,
        )

        self._refresh_line_combo()
        self.canvas.draw()

        # Tell the host (CommCollectPage) so it can update the soil-properties
        # table — and the map view, when this curve is live.
        self.line_added.emit(label, source_path, is_live)

    # ── toolbar actions ──────────────────────────────────────────────────────

    def _open_export_dialog(self):
        dlg = PubExportDialog(self.fig, self)
        dlg.exec()

    def _import_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select data file", "",
            "CSV and Text files (*.csv *.txt);;All files (*.*)",
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        ext = os.path.splitext(path)[-1].lower()
        try:
            if ext == ".csv":
                fre_idx = pd.read_csv(path, usecols=["fre_idx"]).squeeze()
                mag     = pd.read_csv(path, usecols=["mag (dig)"]).squeeze()
                phs     = pd.read_csv(path, usecols=["phs (dig)"]).squeeze()
            else:
                fre_idx = pd.read_csv(path, delimiter=r"\s+", header=None, usecols=[0]).squeeze()
                mag     = pd.read_csv(path, delimiter=r"\s+", header=None, usecols=[2]).squeeze()
                phs     = pd.read_csv(path, delimiter=r"\s+", header=None, usecols=[3]).squeeze()

            fre, mag_dB, phs_deg = self.calculate_freq_mag_phase(fre_idx, mag, phs)
            label = self.create_label(path, ext)
            self.update_plot(fre, mag_dB, phs_deg, label,
                             source_path=path, is_live=False)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load:\n{path}\n\n{e}")

    def _delete_selected_line(self, index: int):
        label = self.line_combo.currentText()
        if not label or label == "-":
            return

        if label == "Clear All Lines":
            for line in self.lines_ax1 + self.lines_ax2:
                line.remove()
            self.lines_ax1.clear()
            self.lines_ax2.clear()
            self.lines_cleared.emit()
        else:
            for collection, lines in ((self.lines_ax1, self.lines_ax1),
                                      (self.lines_ax2, self.lines_ax2)):
                for line in list(lines):
                    if line.get_label() == label:
                        line.remove()
                        lines.remove(line)
                        break
            self.line_removed.emit(label)

        if self.legend:
            self.legend.remove()
            self.legend = None

        remaining = [l.get_label() for l in self.lines_ax1]
        if remaining:
            self.legend = self.fig.legend(
                self.lines_ax1, remaining,
                loc="upper center", bbox_to_anchor=(0.5, 0.10),
                ncol=4, prop=self.legend_font, columnspacing=0.95,
            )

        self.ax1.relim(); self.ax1.autoscale_view(scalex=False)
        self.ax2.relim(); self.ax2.autoscale_view(scalex=False)
        self._refresh_line_combo()
        self.canvas.draw()

    def _refresh_line_combo(self):
        self.line_combo.clear()
        self.line_combo.addItem("-")
        if self.lines_ax1:
            for l in self.lines_ax1:
                self.line_combo.addItem(l.get_label())
            self.line_combo.addItem("Clear All Lines")

    def set_dark_theme(self, dark: bool):
        from styles import PLOT_DARK, PLOT_LIGHT
        p = PLOT_DARK if dark else PLOT_LIGHT

        self.fig.set_facecolor(p["fig_bg"])
        for ax in (self.ax1, self.ax2):
            ax.set_facecolor(p["ax_bg"])
            ax.grid(True, which="major", axis="both",
                    color=p["grid"], linewidth=0.6, alpha=0.85)
            ax.grid(True, which="minor", axis="x",
                    color=p["grid"], linewidth=0.35, alpha=0.5)
            ax.tick_params(colors=p["tick"])
            for spine in ax.spines.values():
                spine.set_edgecolor(p["grid"])

        self.ax1.yaxis.label.set_color(p["fg"])
        self.ax2.yaxis.label.set_color(p["fg"])
        if hasattr(self, "_supxlabel"):
            self._supxlabel.set_color(p["fg"])

        for label in (self.ax1.get_yticklabels() + self.ax2.get_yticklabels()
                      + self.ax2.get_xticklabels()):
            label.set_color(p["tick"])

        # Repaint nav-button icons to match the new theme's button-text color
        # (btn_fg in styles.py — dark blue in light mode, light blue in dark).
        self._nav_icon_off = "#bfdbfe" if dark else "#1e3a8a"
        self._refresh_nav_icons()

        self.canvas.draw_idle()

    # ── theme-aware nav icons ────────────────────────────────────────────────

    def _paint_nav_icon(self, kind: str, color: str, size: int = 18) -> QPixmap:
        """Vector-paint a Home / Pan / Zoom icon in the given color."""
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.GlobalColor.transparent)
        s = float(size)

        if kind == "home":
            peak  = QPointF(s * 0.50, s * 0.18)
            eave_l = QPointF(s * 0.18, s * 0.50)
            eave_r = QPointF(s * 0.82, s * 0.50)
            floor_l = QPointF(s * 0.22, s * 0.82)
            floor_r = QPointF(s * 0.78, s * 0.82)
            # Roof
            p.drawLine(eave_l, peak)
            p.drawLine(peak, eave_r)
            # Walls
            p.drawLine(eave_l, floor_l)
            p.drawLine(eave_r, floor_r)
            # Floor
            p.drawLine(floor_l, floor_r)

        elif kind == "pan":
            cx = cy = s / 2.0
            L = s * 0.35     # arm length (from center to tip)
            H = s * 0.13     # arrowhead size
            # Up
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy - L))
            p.drawLine(QPointF(cx, cy - L), QPointF(cx - H, cy - L + H))
            p.drawLine(QPointF(cx, cy - L), QPointF(cx + H, cy - L + H))
            # Down
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + L))
            p.drawLine(QPointF(cx, cy + L), QPointF(cx - H, cy + L - H))
            p.drawLine(QPointF(cx, cy + L), QPointF(cx + H, cy + L - H))
            # Left
            p.drawLine(QPointF(cx, cy), QPointF(cx - L, cy))
            p.drawLine(QPointF(cx - L, cy), QPointF(cx - L + H, cy - H))
            p.drawLine(QPointF(cx - L, cy), QPointF(cx - L + H, cy + H))
            # Right
            p.drawLine(QPointF(cx, cy), QPointF(cx + L, cy))
            p.drawLine(QPointF(cx + L, cy), QPointF(cx + L - H, cy - H))
            p.drawLine(QPointF(cx + L, cy), QPointF(cx + L - H, cy + H))

        elif kind == "zoom":
            # Lens (circle) toward upper-left
            r = s * 0.24
            center = QPointF(s * 0.40, s * 0.40)
            p.drawEllipse(center, r, r)
            # Handle — thicker stroke, projects from circle edge to bottom-right
            handle_pen = QPen(QColor(color))
            handle_pen.setWidthF(2.4)
            handle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(handle_pen)
            edge = QPointF(center.x() + r * 0.71, center.y() + r * 0.71)
            tail = QPointF(s * 0.82, s * 0.82)
            p.drawLine(edge, tail)

        p.end()
        return pix

    def _build_nav_icon(self, kind: str) -> QIcon:
        """QIcon with separate Off (idle) and On (checked) pixmaps."""
        icon = QIcon()
        icon.addPixmap(self._paint_nav_icon(kind, self._nav_icon_off),
                       QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap(self._paint_nav_icon(kind, self._nav_icon_on),
                       QIcon.Mode.Normal, QIcon.State.On)
        return icon

    def _refresh_nav_icons(self):
        """Regenerate the three nav-button icons in the current theme color."""
        if hasattr(self, "home_btn"):
            self.home_btn.setIcon(self._build_nav_icon("home"))
            self.pan_btn.setIcon(self._build_nav_icon("pan"))
            self.zoom_btn.setIcon(self._build_nav_icon("zoom"))

    # ── view controls ────────────────────────────────────────────────────────

    def _toggle_pan(self):
        """Toggle pan mode via the backend nav toolbar and sync checked state."""
        self.nav_toolbar.pan()
        # matplotlib's mode string is "pan/zoom" while pan is active, "" when off
        active = self.nav_toolbar.mode == "pan/zoom"
        self.pan_btn.setChecked(active)
        # Mutually exclusive with zoom — clear the other indicator
        self.zoom_btn.setChecked(False)

    def _toggle_zoom(self):
        """Toggle zoom-rectangle mode and sync checked state."""
        self.nav_toolbar.zoom()
        active = self.nav_toolbar.mode == "zoom rect"
        self.zoom_btn.setChecked(active)
        self.pan_btn.setChecked(False)

    def _on_scroll(self, event):
        """Mouse-wheel zoom centered on the cursor.
        - Wheel up → zoom in, wheel down → zoom out
        - Operates in log space on the shared x-axis, linear space on y
        - X-zoom syncs across both subplots; Y-zoom only on the hovered axis
        """
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        import math
        scale = 0.85 if event.button == "up" else 1.18

        # X (shared, log-scale)
        x = event.xdata
        xl, xr = self.ax2.get_xlim()
        try:
            lx, llo, lhi = math.log10(x), math.log10(xl), math.log10(xr)
        except (ValueError, ZeroDivisionError):
            return
        new_llo = lx + (llo - lx) * scale
        new_lhi = lx + (lhi - lx) * scale
        # Clamp to the firmware-supported span
        x_min_log, x_max_log = math.log10(self._X_MIN), math.log10(self._X_MAX)
        new_llo = max(new_llo, x_min_log)
        new_lhi = min(new_lhi, x_max_log)
        if new_lhi - new_llo < 0.05:    # don't zoom past ~12% of a decade
            return
        self.ax2.set_xlim(10 ** new_llo, 10 ** new_lhi)  # shared → ax1 follows

        # Y (linear, only on the axis under the cursor)
        ax = event.inaxes
        y = event.ydata
        yl, yh = ax.get_ylim()
        new_yl = y + (yl - y) * scale
        new_yh = y + (yh - y) * scale
        ax.set_ylim(new_yl, new_yh)

        self.canvas.draw_idle()

    # ── hover tooltip ────────────────────────────────────────────────────────

    def _hover(self, event):
        for ax, lines in ((self.ax1, self.lines_ax1), (self.ax2, self.lines_ax2)):
            for line in lines:
                cont, ind = line.contains(event)
                if cont:
                    x, y = line.get_data()
                    xp = x[ind["ind"][0]]
                    yp = y[ind["ind"][0]]
                    self.annot.set_text(f"f={xp/1000:.2f}k, Y={yp:.2f}")
                    self.annot.set_position((xp, yp))
                    self.annot.set_transform(ax.transData)
                    self.annot.set_visible(True)
                    self.fig.canvas.draw_idle()
                    return
        if self.annot.get_visible():
            self.annot.set_visible(False)
            self.fig.canvas.draw_idle()
