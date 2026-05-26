from __future__ import annotations
import os
import datetime
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QScrollArea,
    QSizePolicy, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSlot

from adapters.bridge import (
    BridgeSignals, ComGuiProxy, DatacollectProxy, LoggerProxy, _BoolProxy,
)
from ui.ComPanel        import ComPanel
from ui.DataCollectPanel import DataCollectPanel
from ui.PlotPanel        import PlotPanel
from ui.LogPanel         import LogPanel
from ui.SoilPropertiesPanel import SoilPropertiesPanel

_COLOR_MAP = {
    "green":   "#15803d",
    "red":     "#cc2200",
    "orange":  "#e68815",
    "black":   "#000000",
    "white":   "#ffffff",
    "#6b994d": "#6b994d",
}


def _q(c: str) -> str:
    return _COLOR_MAP.get(c, c)


class CommCollectPage(QWidget):
    """
    Container for the collection workflow: serial setup, collection config,
    frequency response plot, and serial log.

    Wires together the bridge proxies so Serial_Com_Ctrl.py works unchanged.
    """

    def __init__(self, serial, data, bridge: BridgeSignals,
                 data_root: str = "data/UG nodes", parent=None):
        super().__init__(parent)
        self.serial    = serial
        self.data      = data
        self.bridge    = bridge
        self.data_root = data_root

        self._widget_state: dict[str, dict[str, str]] = {}
        # Curve label → (node_id, date) so we can drop the matching soil-table
        # row when the curve is removed.
        self._curve_label_to_key: dict[str, tuple[str, datetime.date]] = {}

        self._build_panels()
        self._wire_bridge()
        self._build_layout()

    # ── build ────────────────────────────────────────────────────────────────

    def _build_panels(self):
        self.com_panel  = ComPanel(self.serial, self.data, bridge=self.bridge)
        self.dc_panel   = DataCollectPanel(self.serial, self.data)
        self.plot_panel = PlotPanel()
        self.log_panel  = LogPanel()

        # Non-modal soil-properties dialog; lives until the app closes.
        # Starts empty — rows are added/removed in lockstep with plot curves.
        self.soil_panel = SoilPropertiesPanel(self)
        self.plot_panel.soil_properties_btn.clicked.connect(self._show_soil_panel)

        self.dc_panel._com_panel_ref = self.com_panel

        auto_scroll_proxy = self.log_panel.auto_scroll_proxy
        logger_proxy = LoggerProxy(self.bridge, auto_scroll_proxy)

        self.dc_proxy = DatacollectProxy(
            data         = self.data,
            signals      = self.bridge,
            plot_panel   = self.plot_panel,
            logger_proxy = logger_proxy,
        )

        self.gui_proxy = ComGuiProxy(
            data              = self.data,
            signals           = self.bridge,
            com_getter        = self.com_panel.selected_com,
            bd_getter         = self.com_panel.selected_baud,
            datacollect_proxy = self.dc_proxy,
            logger_proxy      = logger_proxy,
        )

        self.com_panel._gui_proxy = self.gui_proxy
        self.com_panel._dc_proxy  = self.dc_proxy
        self.dc_panel._dc_proxy   = self.dc_proxy

    def _wire_bridge(self):
        self.bridge.widget_update.connect(self._apply_widget_update)
        self.bridge.log_append.connect(self.log_panel.append_text)
        self.bridge.log_scroll.connect(self.log_panel.scroll_to_end)
        self.bridge.show_info.connect(self._show_info)
        self.bridge.show_error.connect(self._show_error)
        self.bridge.collection_done.connect(self._on_collection_done)
        self.bridge.plot_update.connect(self.plot_panel.update_plot)
        # Soil-properties table mirrors the plot's curves.
        self.plot_panel.line_added.connect(self._on_plot_line_added)
        self.plot_panel.line_removed.connect(self._on_plot_line_removed)
        self.plot_panel.lines_cleared.connect(self._on_plot_lines_cleared)

    def _build_layout(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── Config scroll (210 px fixed initial, user can drag) ──────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(210)
        left_scroll.setMaximumWidth(300)
        left_scroll.setStyleSheet("border: none;")

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.com_panel)
        left_layout.addWidget(self.dc_panel)
        left_layout.addStretch()
        left_scroll.setWidget(left_container)

        # ── 3-panel splitter: config | plot | log ────────────────────────────
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(3)

        self.plot_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.log_panel.setMinimumWidth(150)
        self.log_panel.setMaximumWidth(370)

        self.main_splitter.addWidget(left_scroll)
        self.main_splitter.addWidget(self.plot_panel)
        self.main_splitter.addWidget(self.log_panel)
        # Side panels open at their maximum width; chart takes the rest.
        self.main_splitter.setSizes([300, 900, 370])

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)

        main.addWidget(self.main_splitter)

    # ── bridge slots ─────────────────────────────────────────────────────────

    @pyqtSlot(str, str, str)
    def _apply_widget_update(self, name: str, prop: str, value: str):
        """
        Dispatch Serial_Com_Ctrl widget updates to the correct Qt widget.
        Maintains per-widget state so bg+fg can be combined into one stylesheet.
        """
        state = self._widget_state.setdefault(name, {})
        state[prop] = value

        # ── ComPanel widgets ──────────────────────────────────────────────────
        if name in ("sync_status", "btn_connect", "btn_refresh", "drop_baud", "drop_com"):
            self.com_panel.apply_bridge_update(name, prop, value)
            return

        # ── DataCollectPanel widgets ──────────────────────────────────────────
        _ROLE_MAP = {"green": "status-ok", "red": "status-err", "orange": "status-warn"}

        widget_map: dict[str, object] = {
            "complete_nodes":   self.dc_panel.complete_nodes_lbl,
            "node_status_txt":  self.dc_panel.node_status_title_lbl,
            "node_status":      self.dc_panel.node_status_lbl,
            "ACK_status":       self.dc_panel.ack_lbl,
            "time_cal_status":  self.dc_panel.time_cal_lbl,
            "freID_status":     self.dc_panel.freq_id_lbl,
            "data_rec_status":  self.dc_panel.data_rec_lbl,
            "data_save_status": self.dc_panel.data_save_lbl,
            "load_status":      self.dc_panel.load_status_lbl,
        }
        btn_map = {
            "btn_collection": self.dc_panel.collection_btn,
        }
        enable_map = {
            "clt_m1":   self.dc_panel.all_nodes_btn,
            "clt_m2":   self.dc_panel.single_node_btn,
            "Load_fre": self.dc_panel.load_freq_btn,
        }

        if name in widget_map:
            from PyQt6.QtWidgets import QLabel
            w = widget_map[name]
            if prop == "text":
                w.setText(value)
            elif prop == "fg":
                role = _ROLE_MAP.get(value, "status-warn")
                w.setProperty("role", role)
                w.style().unpolish(w)
                w.style().polish(w)

        elif name in btn_map:
            w = btn_map[name]
            if prop == "text":
                w.setText(value)
            elif prop == "state":
                w.setEnabled(value in ("normal", "active"))
            elif prop in ("bg", "fg"):
                bg = _q(state.get("bg", "#dde0e8"))
                fg = _q(state.get("fg", "black"))
                w.setStyleSheet(
                    f"QPushButton {{ background-color: {bg}; color: {fg}; "
                    f"font-size: 14px; font-weight: bold; border-radius: 3px; border: none; }}"
                )

        elif name in enable_map:
            if prop == "state":
                enable_map[name].setEnabled(value in ("normal", "active"))

    @pyqtSlot()
    def _on_collection_done(self):
        """SerialStream completed normally — close serial and reset UI."""
        try:
            if (hasattr(self.serial, "ser")
                    and self.serial.ser is not None
                    and self.serial.ser.is_open):
                self.serial.ser.write(self.data.disconnect_out.encode())
        except Exception:
            pass
        # Stop the monitor thread and let it exit before closing the port.
        if hasattr(self.serial, "monitor_thread_running"):
            self.serial.monitor_thread_running = False
        mt = getattr(self.serial, "monitor_thread", None)
        if mt is not None and mt.is_alive():
            mt.join(timeout=0.5)
        self.serial.SerialClose()
        self.data.ClearData()
        self.com_panel.reset_connection_state()
        self.dc_panel.reset_after_collection()

        # After a collection finishes, re-scan the data folder and refresh
        # both the local soil panel and the Map View (via bridge).
        self._refresh_soil_data_after_collection()

    @pyqtSlot(str, str)
    def _show_info(self, title: str, msg: str):
        QMessageBox.information(self, title, msg)

    @pyqtSlot(str, str)
    def _show_error(self, title: str, msg: str):
        QMessageBox.critical(self, title, msg)

    # ── soil-properties wiring ──────────────────────────────────────────────
    def _show_soil_panel(self):
        self.soil_panel.show()
        self.soil_panel.raise_()
        self.soil_panel.activateWindow()

    def _refresh_soil_data_after_collection(self):
        """
        Notify the Map View via bridge.soil_data_updated so its pins reflect
        the freshly written file. The local soil-properties table follows the
        plot curves directly (via line_added / line_removed signals), so it
        does NOT need a disk re-scan here.
        """
        try:
            self.bridge.soil_data_updated.emit()
        except Exception:
            pass

    # ── per-curve soil-properties update ─────────────────────────────────────
    def _on_plot_line_added(self, label: str, source_path: str, is_live: bool):
        """
        Slot for PlotPanel.line_added — fires every time a curve is drawn
        (live radio or imported file).

        Resolves the underlying filepath, runs predict_full on it, and adds
        a row to the Soil Properties table. For live data, also fires
        bridge.soil_data_updated so the Map View popups pick up the new
        values immediately (no need to wait for end-of-collection).
        """
        # Resolve filepath.
        # - Imported curve → source_path is already an absolute file path.
        # - Live curve   → _PlotProxy.update_plot snapshots the just-written
        #   file's full path on the serial thread (save_root + current_node
        #   + filename1) and forwards it via the plot_update signal, so it
        #   arrives here in source_path. We DO NOT read self.data.filename1
        #   on the main thread — that attribute can race ahead to the next
        #   node before this slot runs.
        filepath = source_path or ""
        if not filepath or not os.path.exists(filepath):
            return

        try:
            from soil.node_loader import predict_full
            pred = predict_full(filepath)
        except Exception as e:
            # Print AND log to a file next to the exe so errors are visible
            # in bundled mode where stdout is suppressed.
            import sys, traceback, datetime
            msg = (
                f"[{datetime.datetime.now().isoformat(timespec='seconds')}] "
                f"soil model failed for {filepath}\n"
                f"  error: {type(e).__name__}: {e}\n"
                f"  traceback:\n{traceback.format_exc()}\n"
            )
            print(msg)
            try:
                log_dir = (os.path.dirname(sys.executable)
                           if getattr(sys, "frozen", False)
                           else os.getcwd())
                with open(os.path.join(log_dir, "soilsense_errors.log"),
                          "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception:
                pass
            return

        # Node id from the parent folder name (authoritative source).
        try:
            from soil.node_loader import _node_id_from_folder, _parse_file_date
            from pathlib import Path
            p       = Path(filepath)
            node_id = _node_id_from_folder(p.parent) or "S?"
            fdate   = _parse_file_date(p.name) or datetime.date.fromtimestamp(p.stat().st_mtime)
        except Exception:
            return

        try:
            from soil.node_loader import _parse_file_time
            ftime = _parse_file_time(p.name)
        except Exception:
            ftime = None
        if ftime is None:
            ftime = datetime.datetime.fromtimestamp(
                os.path.getmtime(filepath)
            ).strftime("%H:%M")
        rec = {
            "node_id"  : node_id,
            "date"     : fdate,
            "time"     : ftime,
            "is_live"  : bool(is_live) and (fdate == datetime.date.today()),
            "filepath" : filepath,
            **pred,
        }
        self.soil_panel.add_or_update_row(rec)
        self._curve_label_to_key[label] = (node_id, fdate)

        # Live data → notify Map View so popup values reflect this immediately.
        if is_live:
            try:
                self.bridge.soil_data_updated.emit()
            except Exception:
                pass

    def _on_plot_line_removed(self, label: str):
        key = self._curve_label_to_key.pop(label, None)
        if key is not None:
            self.soil_panel.remove_row(*key)

    def _on_plot_lines_cleared(self):
        self._curve_label_to_key.clear()
        self.soil_panel.clear_all()
