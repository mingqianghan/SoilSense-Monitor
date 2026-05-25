from __future__ import annotations
import os
import json
import re
import ctypes
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QStatusBar,
    QButtonGroup, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent, QPoint
from PyQt6.QtGui import QIcon
from dotenv import load_dotenv

from HomeGui import HomeGui
from ui.CommCollectPage import CommCollectPage
from adapters.bridge import BridgeSignals, install_messagebox_patch
import styles


class AppRoot(QMainWindow):
    theme_changed = pyqtSignal(bool)  # True = dark

    def __init__(self, serial, data):
        super().__init__()
        load_dotenv()
        # Prefer the user's keyring entry, fall back to .env for dev setups.
        # setup.keys.get_weather_key() already handles the env-var fallback,
        # so this returns whichever source has a value — or empty string
        # if neither does (HomeGui handles that with a banner).
        from setup.keys import get_weather_key
        self.api_key = get_weather_key() or ""
        self.serial  = serial
        self.data    = data
        self._dark   = False

        config = self._load_config()
        self.data.config = config.get("markers", [])
        self.data.plots  = config.get("plots", [])
        # Two separate folders, configurable independently in config.json:
        #   data_root → where the UI READS historical files (map view, soil
        #               properties panel, available-dates dropdown).
        #   save_root → where Data_Com_Ctrl.RadioDataToFile WRITES new
        #               collections (per-node subfolder + d/r CSVs).
        # Each falls back to the legacy relative folder if unset.
        self.data_root      = config.get("data_root", "data/UG nodes")
        self.data.save_root = config.get("save_root", "data\\UG nodes")
        self.data.nodes  = {
            re.search(r"\d+", n["name"]).group(): "NotSelected"
            for n in self.data.config
        }
        # Test nodes still participate in data collection but are hidden from
        # the field map and the "All Node(s) in Field" badges. Marked in
        # config.json with `"test": true`.
        self.data.test_nodes = {
            re.search(r"\d+", n["name"]).group()
            for n in self.data.config if n.get("test")
        }

        self.bridge = BridgeSignals()
        install_messagebox_patch(self.bridge)

        self._setup_window()
        self._build_ui()
        self._setup_clock()

        QApplication.instance().setStyleSheet(styles.LIGHT)
        # setStyleSheet re-polishes widgets and can wipe palettes set in
        # _build_ui — re-apply theme-sensitive palettes after.
        self.home_page.set_dark_theme(False)

        # Install our own tooltip widget — see _ThemedToolTipFilter for why
        # this is needed instead of styling QToolTip.
        self._tt_filter = _ThemedToolTipFilter(self)
        QApplication.instance().installEventFilter(self._tt_filter)
        self.show_page("Home")

    # ── window setup ─────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        try:
            with open("config.json") as f:
                return json.load(f)
        except Exception:
            return {"markers": []}

    def _setup_window(self):
        self.setWindowTitle("SoilSense Monitor")
        try:
            appid = "soilweather.interface.v2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
            self.setWindowIcon(QIcon("assets/app_icon.ico"))
        except Exception:
            pass
        self.setMinimumSize(900, 600)
        self.setWindowState(Qt.WindowState.WindowMaximized)

    # ── UI build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_title_bar())

        sep = QFrame()
        sep.setObjectName("titleBarSep")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        hl.addWidget(self._make_sidebar())

        side_sep = QFrame()
        side_sep.setObjectName("sidebarSep")
        side_sep.setFixedWidth(1)
        hl.addWidget(side_sep)

        self.stack = QStackedWidget()
        hl.addWidget(self.stack, stretch=1)
        root.addWidget(row, stretch=1)

        sb = QStatusBar()
        sb.setFixedHeight(26)
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)
        self.status_bar = sb

        # Permanent widgets sit on the right; addWidget() puts items on the left.
        self.conn_lbl = QLabel("● Disconnected")
        self.conn_lbl.setProperty("role", "status-warn")
        sb.addWidget(self.conn_lbl)

        self.rx_lbl = QLabel("Last RX: —")
        sb.addPermanentWidget(self.rx_lbl)

        self.bridge.connection_state.connect(self._on_connection_state)
        self.bridge.log_append.connect(self._on_log_append)

        self._build_pages()

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(46)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(10)

        icon_lbl = QLabel("🌿")
        icon_lbl.setStyleSheet("font-size: 22px; background: transparent;")
        hl.addWidget(icon_lbl)

        title = QLabel("SoilSense Monitor")
        title.setStyleSheet("font-size: 16px; font-weight: 700; background: transparent;")
        hl.addWidget(title)
        hl.addStretch()

        self.theme_btn = QPushButton(" ☀  Light ")
        self.theme_btn.setProperty("role", "theme-toggle")
        self.theme_btn.setFixedHeight(30)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self._toggle_theme)
        hl.addWidget(self.theme_btn)

        return bar

    def _make_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(86)

        vl = QVBoxLayout(sidebar)
        vl.setContentsMargins(6, 10, 6, 10)
        vl.setSpacing(8)

        # ── Time card: prominent clock + "Sun, May 24" date + small year
        time_card = QFrame()
        time_card.setProperty("role", "time-card")
        tcl = QVBoxLayout(time_card)
        tcl.setContentsMargins(4, 6, 4, 6)
        tcl.setSpacing(1)

        self.clock_lbl = QLabel("--:--:--")
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_lbl.setProperty("role", "clock-time")
        tcl.addWidget(self.clock_lbl)

        # Combined weekday + month-day, e.g. "Sun, May 24". Proportional
        # font reads faster than Consolas at this size.
        self.date_lbl = QLabel("---, --- --")
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_lbl.setProperty("role", "clock-date")
        tcl.addWidget(self.date_lbl)

        # Year on its own small muted line — rarely the thing you need at a
        # glance, so it gets the least visual weight.
        self.year_lbl = QLabel("----")
        self.year_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.year_lbl.setProperty("role", "clock-year")
        tcl.addWidget(self.year_lbl)

        vl.addWidget(time_card)

        div = QFrame()
        div.setObjectName("sidebarDiv")
        div.setFixedHeight(1)
        vl.addWidget(div)

        # ── Center all three nav buttons as a single group ──────────────
        vl.addStretch(1)

        grp = QButtonGroup(self)
        grp.setExclusive(True)
        self._nav_group = grp

        self.btn_home    = self._make_nav_btn("Map\nView")
        self.btn_collect = self._make_nav_btn("Collect\nData")
        for btn in (self.btn_home, self.btn_collect):
            grp.addButton(btn)
            vl.addWidget(btn)

        btn_exit = QPushButton("Exit")
        btn_exit.setProperty("role", "nav-exit")
        btn_exit.setFixedHeight(52)
        btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exit.clicked.connect(self.close)
        vl.addWidget(btn_exit)

        vl.addStretch(1)

        self.btn_home.clicked.connect(lambda: self.show_page("Home"))
        self.btn_collect.clicked.connect(lambda: self.show_page("Collect"))

        return sidebar

    def _make_nav_btn(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("role", "nav")
        btn.setCheckable(True)
        btn.setFixedHeight(52)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _build_pages(self):
        # Test nodes are excluded from the map view.
        visible_markers = [m for m in self.data.config if not m.get("test")]
        self.home_page    = HomeGui(self.api_key, visible_markers, self.data.plots,
                                    data_root=self.data_root, bridge=self.bridge)
        self.collect_page = CommCollectPage(self.serial, self.data, self.bridge,
                                            data_root=self.data_root)
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.collect_page)
        self.theme_changed.connect(self.collect_page.plot_panel.set_dark_theme)
        self.theme_changed.connect(self.home_page.set_dark_theme)

    # ── navigation ────────────────────────────────────────────────────────────

    def show_page(self, name: str):
        if name == "Home":
            self.stack.setCurrentWidget(self.home_page)
            self.btn_home.setChecked(True)
        else:
            self.stack.setCurrentWidget(self.collect_page)
            self.btn_collect.setChecked(True)

    # ── theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        dark = not self._dark
        self._dark = dark
        QApplication.instance().setStyleSheet(styles.DARK if dark else styles.LIGHT)
        self.theme_btn.setText(" 🌙  Dark " if dark else " ☀  Light ")
        self.theme_changed.emit(dark)

    # ── status bar ────────────────────────────────────────────────────────────

    def _on_connection_state(self, connected: bool, com: str, baud: str):
        if connected:
            self.conn_lbl.setText(f"● Connected — {com} @ {baud}")
            self.conn_lbl.setProperty("role", "status-ok")
        else:
            self.conn_lbl.setText("● Disconnected")
            self.conn_lbl.setProperty("role", "status-warn")
            self.rx_lbl.setText("Last RX: —")
        self.conn_lbl.style().unpolish(self.conn_lbl)
        self.conn_lbl.style().polish(self.conn_lbl)

    def _on_log_append(self, _text: str):
        self.rx_lbl.setText("Last RX: " + datetime.now().strftime("%H:%M:%S"))

    # ── clock ─────────────────────────────────────────────────────────────────

    def _setup_clock(self):
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1000)
        self._tick()

    def _tick(self):
        now = datetime.now()
        self.clock_lbl.setText(now.strftime("%H:%M:%S"))
        # "Sun, May 24" — proportional font, easy to scan
        self.date_lbl.setText(now.strftime("%a, %b %d"))
        self.year_lbl.setText(now.strftime("%Y"))

    # ── shutdown ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if hasattr(self.serial, "threading"):
            self.serial.threading = False
        if hasattr(self.serial, "monitor_thread_running"):
            self.serial.monitor_thread_running = False
        if hasattr(self.serial, "ser"):
            self.serial.Close_Com()
        event.accept()


# ── Custom tooltip ──────────────────────────────────────────────────────────
#
# Qt's QToolTip on Windows is notoriously hard to style reliably. Neither QSS
# (`QToolTip { background: ... }`) nor `QToolTip.setPalette()` consistently
# overrides the Windows native tooltip rendering — depending on the OS dark-
# mode setting and Qt platform-integration build flags, the tooltip can show
# in dark-on-dark or with the wrong palette regardless of what we set.
#
# The clean fix is to bypass QToolTip entirely:
#   • install a global event filter on QApplication
#   • when a `QEvent.ToolTip` is about to fire, swallow it and instead
#     show our own QLabel widget with explicit colors we control
#
# Because the widget is a plain QLabel that we own, its stylesheet always
# applies, the theme is always correct, and there's no Windows-specific
# behavior to fight.

class _ThemedToolTipFilter(QObject):
    """Global event filter that replaces Qt's QToolTip with a themed QLabel."""

    def __init__(self, app_root: "AppRoot"):
        super().__init__()
        self._root  = app_root
        # The reusable tooltip widget. Frameless top-level QLabel — same role
        # as Qt's internal QTipLabel but fully under our control.
        self._label = QLabel()
        self._label.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._label.setWordWrap(True)
        self._label.hide()

    def _restyle(self):
        if bool(getattr(self._root, "_dark", False)):
            bg, fg, bd = "#21262d", "#f0f6fc", "#30363d"
        else:
            bg, fg, bd = "#e5e7eb", "#111827", "#d1d5db"
        self._label.setStyleSheet(
            f"QLabel {{"
            f" background: {bg};"
            f" color: {fg};"
            f" border: 1px solid {bd};"
            f" border-radius: 4px;"
            f" padding: 5px 8px;"
            f" font-size: 12px;"
            f"}}"
        )

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Type.ToolTip:
            if isinstance(obj, QWidget):
                text = obj.toolTip()
                if text:
                    self._restyle()
                    self._label.setText(text)
                    self._label.adjustSize()
                    gp = obj.mapToGlobal(event.pos())
                    self._label.move(self._clamp_to_screen(gp))
                    self._label.show()
                    return True   # consume — Qt's QToolTip won't fire
        elif et in (
            QEvent.Type.Leave,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.KeyPress,
            QEvent.Type.Wheel,
            QEvent.Type.WindowDeactivate,
            QEvent.Type.FocusOut,
        ):
            self._label.hide()
        return False

    def _clamp_to_screen(self, cursor_pos: QPoint) -> QPoint:
        """Position the tooltip near the cursor but fully inside the screen
        the cursor is on. If the natural below-right position would clip,
        flip to above and/or left of the cursor."""
        # Default offset: below-right of the cursor (common convention).
        offset_x, offset_y = 12, 16
        tip_w = self._label.sizeHint().width()
        tip_h = self._label.sizeHint().height()

        # Use the screen the cursor is actually on (multi-monitor safe).
        screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        geom   = screen.availableGeometry()

        # Try below-right first.
        x = cursor_pos.x() + offset_x
        y = cursor_pos.y() + offset_y
        # Flip horizontally if it would clip the right edge.
        if x + tip_w > geom.right():
            x = cursor_pos.x() - offset_x - tip_w
        # Flip vertically if it would clip the bottom edge.
        if y + tip_h > geom.bottom():
            y = cursor_pos.y() - offset_y - tip_h
        # Final clamp in case the flip itself goes past the left/top edge
        # (very narrow screen or huge tooltip).
        x = max(geom.left()   + 2, min(x, geom.right()  - tip_w - 2))
        y = max(geom.top()    + 2, min(y, geom.bottom() - tip_h - 2))
        return QPoint(x, y)
