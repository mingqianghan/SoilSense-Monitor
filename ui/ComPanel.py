from __future__ import annotations
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSlot


def _divider() -> QFrame:
    f = QFrame()
    f.setObjectName("sectionDivider")
    f.setFixedHeight(1)
    return f


def _section_card(title: str, variant: str) -> tuple[QFrame, QVBoxLayout]:
    """Tinted card container; variant is 'com', 'cfg', or 'trk'."""
    card = QFrame()
    card.setProperty("role", f"section-card-{variant}")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    header = QLabel(title.upper())
    header.setProperty("role", f"section-head-{variant}")
    header.setAlignment(Qt.AlignmentFlag.AlignCenter)
    outer.addWidget(header)

    body = QWidget()
    body.setObjectName("sectionCardBody")
    body_lo = QVBoxLayout(body)
    body_lo.setContentsMargins(10, 6, 10, 6)
    body_lo.setSpacing(6)
    outer.addWidget(body)

    return card, body_lo


class ComPanel(QWidget):
    """Serial port setup: port selection, baud rate, connect/sync status."""

    def __init__(self, serial, data, bridge=None, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.data   = data
        self.bridge = bridge   # BridgeSignals — used to broadcast connection state

        self._dc_proxy  = None
        self._gui_proxy = None

        self._build_ui()
        self._refresh_ports()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(0)

        card, body = _section_card("Serial Setup", "com")
        layout.addWidget(card)
        layout.addStretch()

        # Info label: lighter weight to differentiate from bold button text
        label_css = "font-size: 13px; font-weight: 500; background: transparent;"
        combo_css = (
            "QComboBox { font-size: 13px; border: 1.5px solid #6b7280;"
            " border-radius: 5px; padding: 4px 8px; min-height: 22px; }"
            "QComboBox:focus { border-color: #1d4ed8; }"
        )

        # Port row — label LEFT, combo RIGHT
        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        pl = QLabel("Available Port(s):")
        pl.setStyleSheet(label_css)
        pl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        port_row.addWidget(pl)
        port_row.addStretch()
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(90)
        self.port_combo.setMaximumWidth(110)
        self.port_combo.setStyleSheet(combo_css)
        self.port_combo.currentTextChanged.connect(self._check_connect_enabled)
        port_row.addWidget(self.port_combo)
        body.addLayout(port_row)

        # Baud row — label LEFT, combo RIGHT
        baud_row = QHBoxLayout()
        baud_row.setSpacing(6)
        bl = QLabel("Baud Rate:")
        bl.setStyleSheet(label_css)
        bl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        baud_row.addWidget(bl)
        baud_row.addStretch()
        self.baud_combo = QComboBox()
        self.baud_combo.setMinimumWidth(90)
        self.baud_combo.setMaximumWidth(110)
        self.baud_combo.setStyleSheet(combo_css)
        for r in ["-", "300", "600", "1200", "2400", "4800", "9600",
                  "14400", "19200", "28800", "38400", "56000", "57600",
                  "115200", "128000", "256000"]:
            self.baud_combo.addItem(r)
        self.baud_combo.setCurrentText("115200")
        self.baud_combo.currentTextChanged.connect(self._check_connect_enabled)
        baud_row.addWidget(self.baud_combo)
        body.addLayout(baud_row)

        # Refresh + Connect — side by side, equal width
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        btn_css = "QPushButton { font-size: 13px; padding: 4px 8px; }"

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedHeight(28)
        self.refresh_btn.setStyleSheet(btn_css)
        self.refresh_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.refresh_btn.clicked.connect(self._refresh_ports)
        btn_row.addWidget(self.refresh_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setProperty("role", "primary")
        self.connect_btn.setFixedHeight(28)
        self.connect_btn.setStyleSheet(btn_css)
        self.connect_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.connect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        btn_row.addWidget(self.connect_btn)
        body.addLayout(btn_row)
        body.addWidget(_divider())

        # Sync status row — two equal halves so labels align under Refresh / Connect
        sync_row = QHBoxLayout()
        sync_row.setSpacing(6)
        sync_header = QLabel("Sync Status:")
        sync_header.setStyleSheet(label_css)
        sync_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sync_header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sync_row.addWidget(sync_header)

        self.sync_status_lbl = QLabel("..Sync..")
        self.sync_status_lbl.setProperty("role", "status-warn")
        self.sync_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sync_status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sync_row.addWidget(self.sync_status_lbl)
        body.addLayout(sync_row)

        # Apply initial status colors after widget is fully constructed
        self._set_pill_state("orange")

    # ── port helpers ──────────────────────────────────────────────────────────

    def _refresh_ports(self):
        self.serial.getCOMList()
        self.port_combo.clear()
        for p in self.serial.com_list:
            self.port_combo.addItem(p)
        self._check_connect_enabled()

    def _check_connect_enabled(self):
        port_ok = "-" not in self.port_combo.currentText()
        baud_ok = "-" not in self.baud_combo.currentText()
        self.connect_btn.setEnabled(port_ok and baud_ok)

    def selected_com(self) -> str:
        return self.port_combo.currentText()

    def selected_baud(self) -> str:
        return self.baud_combo.currentText()

    # ── connect / disconnect ──────────────────────────────────────────────────

    def _on_connect_clicked(self):
        if self.connect_btn.text() == "Connect":
            self._connect_serial()
        else:
            self.disconnect_serial()

    def _connect_serial(self):
        if self._gui_proxy is None:
            return
        self.serial.SerialOpen(self._gui_proxy)
        if not self.serial.ser.status:
            QMessageBox.critical(
                self, "Connection Failed",
                f"Failed to open {self.port_combo.currentText()}."
            )
            return

        QMessageBox.information(
            self, "Connected",
            f"UART connected on {self.port_combo.currentText()}."
        )
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setProperty("role", "danger")
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        self.refresh_btn.setEnabled(False)
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)

        if self.bridge is not None:
            self.bridge.connection_state.emit(
                True, self.port_combo.currentText(), self.baud_combo.currentText()
            )

        self.serial.t1 = threading.Thread(
            target=self.serial.SerialSync,
            args=(self._gui_proxy,),
            daemon=True,
        )
        self.serial.t1.start()

        self.serial.monitor_thread = threading.Thread(
            target=self.serial.Monitor_Connection,
            args=(self._gui_proxy,),
            daemon=True,
        )
        self.serial.monitor_thread.start()

    def disconnect_serial(self):
        if not hasattr(self.serial, "ser") or self.serial.ser is None:
            return
        try:
            self.serial.ser.write(self.data.disconnect_out.encode())
        except Exception:
            pass
        # Signal the worker + monitor threads, then wait for them to exit
        # before closing the port. Otherwise an in-flight write races with
        # SerialClose and SerialSync's `except: print(e)` dumps
        # "WriteFile failed (PermissionError ...)" to the console.
        self.serial.threading = False
        if hasattr(self.serial, "monitor_thread_running"):
            self.serial.monitor_thread_running = False
        for tname in ("t1", "monitor_thread"):
            t = getattr(self.serial, tname, None)
            if t is not None and t.is_alive():
                t.join(timeout=0.5)
        self.serial.SerialClose()
        self.data.ClearData()
        self.reset_connection_state()

    def reset_connection_state(self):
        self.connect_btn.setText("Connect")
        self.connect_btn.setProperty("role", "primary")
        self.connect_btn.style().unpolish(self.connect_btn)
        self.connect_btn.style().polish(self.connect_btn)
        self.refresh_btn.setEnabled(True)
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)

        self.sync_status_lbl.setText("..Sync..")
        self._set_pill_state("orange")
        self._check_connect_enabled()

        if self.bridge is not None:
            self.bridge.connection_state.emit(False, "", "")

    # ── bridge update handler ─────────────────────────────────────────────────

    _COLOR_TO_ROLE = {
        "green":  "status-ok",
        "red":    "status-err",
        "orange": "status-warn",
    }

    def _set_pill_state(self, color: str):
        role = self._COLOR_TO_ROLE.get(color, "status-warn")
        self.sync_status_lbl.setProperty("role", role)
        self.sync_status_lbl.style().unpolish(self.sync_status_lbl)
        self.sync_status_lbl.style().polish(self.sync_status_lbl)

    @pyqtSlot(str, str, str)
    def apply_bridge_update(self, name: str, prop: str, value: str):
        if name == "sync_status":
            if prop == "text":
                self.sync_status_lbl.setText(value)
            elif prop == "fg":
                self._set_pill_state(value)

        elif name == "btn_connect":
            if prop == "text":
                self.connect_btn.setText(value)

        elif name == "btn_refresh":
            if prop == "state":
                self.refresh_btn.setEnabled(value in ("normal", "active"))

        elif name == "drop_baud":
            if prop == "state":
                self.baud_combo.setEnabled(value in ("normal", "active"))

        elif name == "drop_com":
            if prop == "state":
                self.port_combo.setEnabled(value in ("normal", "active"))
