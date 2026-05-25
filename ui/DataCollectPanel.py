from __future__ import annotations
import re
import os
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QButtonGroup, QComboBox,
    QFrame, QFileDialog, QSizePolicy, QMessageBox, QLayout,
)
from PyQt6.QtCore import Qt, QRect, QSize, QPoint, pyqtSlot

_COLOR_MAP = {
    "green":   "#15803d",
    "red":     "#cc2200",
    "orange":  "#e68815",
    "black":   "#000000",
    "white":   "#ffffff",
    "#6b994d": "#6b994d",
}


def _q(css_color: str) -> str:
    return _COLOR_MAP.get(css_color, css_color)


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


class _FlowLayout(QLayout):
    """Left-to-right layout that wraps to a new row when width is exceeded.

    Set ``center`` to True to horizontally center each wrapped row.
    """

    def __init__(self, parent=None, hspacing: int = 4, vspacing: int = 4,
                 center: bool = False):
        super().__init__(parent)
        self._items: list = []
        self._hspace = hspacing
        self._vspace = vspacing
        self._center = center
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _arrange(self, rect: QRect, apply: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())

        # First pass: split items into rows that fit in eff.width()
        rows: list[list] = [[]]
        widths: list[int] = [0]
        for it in self._items:
            sz = it.sizeHint()
            cur_w = widths[-1]
            extra = sz.width() if not rows[-1] else self._hspace + sz.width()
            if rows[-1] and cur_w + extra > eff.width():
                rows.append([])
                widths.append(0)
                extra = sz.width()
            rows[-1].append((it, sz))
            widths[-1] = (widths[-1] + extra) if rows[-1] else sz.width()

        # Second pass: place items, optionally centering each row
        y = eff.y()
        for row, row_w in zip(rows, widths):
            if not row:
                continue
            x = eff.x() + max(0, (eff.width() - row_w) // 2) if self._center else eff.x()
            line_h = 0
            for it, sz in row:
                if apply:
                    it.setGeometry(QRect(QPoint(x, y), sz))
                x += sz.width() + self._hspace
                line_h = max(line_h, sz.height())
            y += line_h + self._vspace

        return y - rect.y() + m.bottom() - self._vspace


class _FlowContainer(QWidget):
    """Container that reports height-for-width from its _FlowLayout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        sp = self.sizePolicy()
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        lay = self.layout()
        return lay.heightForWidth(w) if lay else 0


_DOT_SIZE   = 18
_DOT_COL_W  = 22


def _stem() -> QWidget:
    """Vertical line connecting two pipeline rows (timeline stem)."""
    w = QWidget()
    w.setProperty("role", "transparent")
    lo = QHBoxLayout(w)
    lo.setContentsMargins(0, 0, 0, 0)
    lo.setSpacing(0)
    col = QWidget()
    col.setProperty("role", "transparent")
    col.setFixedWidth(_DOT_COL_W)
    col_lo = QHBoxLayout(col)
    col_lo.setContentsMargins(0, 0, 0, 0)
    col_lo.setSpacing(0)
    line = QFrame()
    line.setObjectName("pipelineStem")
    line.setFixedSize(2, 8)
    col_lo.addWidget(line, alignment=Qt.AlignmentFlag.AlignCenter)
    lo.addWidget(col)
    lo.addStretch()
    return w


class _StatusRow(QWidget):
    """Timeline step — numbered circle (✓ / ✗ on completion) + label + status."""

    _DOT_FILL  = {"green": "#15803d", "red": "#cc2200", "orange": "#e68815"}
    _DOT_GLYPH = {"green": "✓", "red": "✗"}
    _ROLE_MAP  = {"green": "status-ok", "red": "status-err", "orange": "status-warn"}

    def __init__(self, step_num: int, label_text: str, parent=None):
        super().__init__(parent)
        self._step_num = step_num
        self.setProperty("role", "transparent")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        # Step indicator (numbered circle) in fixed-width column
        dot_col = QWidget()
        dot_col.setProperty("role", "transparent")
        dot_col.setFixedWidth(_DOT_COL_W)
        dot_lo = QHBoxLayout(dot_col)
        dot_lo.setContentsMargins(0, 0, 0, 0)
        dot_lo.setSpacing(0)
        self.dot = QLabel(str(step_num))
        self.dot.setFixedSize(_DOT_SIZE, _DOT_SIZE)
        self.dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_dot_state("orange")
        dot_lo.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dot_col)

        lbl = QLabel(label_text)
        lbl.setStyleSheet(
            "font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(lbl)
        layout.addStretch()

        self.value_lbl = QLabel("Pending...")
        self.value_lbl.setProperty("role", "status-warn")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.value_lbl)

    def _set_dot_state(self, color: str):
        fill = self._DOT_FILL.get(color, "#e68815")
        glyph = self._DOT_GLYPH.get(color, str(self._step_num))
        font_size = 11 if color in self._DOT_GLYPH else 10
        self.dot.setText(glyph)
        self.dot.setStyleSheet(
            f"background: {fill}; color: #ffffff;"
            f" border-radius: {_DOT_SIZE // 2}px; border: none;"
            f" font-size: {font_size}px; font-weight: 700;"
            f" padding: 0; margin: 0;"
        )

    def set_value(self, text: str, color: str = "orange"):
        self.value_lbl.setText(text)
        role = self._ROLE_MAP.get(color, "status-warn")
        self.value_lbl.setProperty("role", role)
        self.value_lbl.style().unpolish(self.value_lbl)
        self.value_lbl.style().polish(self.value_lbl)
        self._set_dot_state(color)

    def reset(self):
        self.set_value("Pending...", "orange")


class DataCollectPanel(QWidget):
    """Data capture configuration + collection status pipeline."""

    def __init__(self, serial, data, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.data   = data
        self._com_panel_ref = None
        self._dc_proxy      = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_config_section())
        layout.addWidget(self._build_status_section())
        layout.addStretch()

        # Apply the default "All Nodes" selection to self.data.nodes immediately.
        # (setChecked(True) on the button ran before toggled.connect, so the
        #  handler never fired at startup — without this call, no nodes are
        #  marked Working until the user toggles the segment manually.)
        self._on_method_changed()
        # Same fix for the freq toggle: pre-populate fre_IDs with the
        # "send-all-IDs" CMD so the user can hit Start Collection right away.
        self._on_freq_method_changed()

    # ── Data Capture Config ───────────────────────────────────────────────────

    def _build_config_section(self) -> QWidget:
        card, vl = _section_card("Data Capture Config", "cfg")

        # Info label: lighter weight to distinguish from bold button text
        label_css = "font-size: 13px; font-weight: 500; background: transparent;"
        combo_css = (
            "QComboBox { font-size: 13px; border: 1.5px solid #6b7280;"
            " border-radius: 5px; padding: 4px 8px; min-height: 22px; }"
            "QComboBox:focus { border-color: #1d4ed8; }"
            "QComboBox:disabled { border-color: #d1d5db; color: #9ca3af; }"
        )

        # Collection method — segmented pill toggle (clear active vs muted-off)
        method_row = QHBoxLayout()
        method_row.setSpacing(6)
        self.all_nodes_btn   = QPushButton("All Nodes")
        self.single_node_btn = QPushButton("Single Node")
        self.all_nodes_btn.setProperty("role", "segment")
        self.single_node_btn.setProperty("role", "segment")
        self.all_nodes_btn.setCheckable(True)
        self.single_node_btn.setCheckable(True)
        self.all_nodes_btn.setChecked(True)
        self.all_nodes_btn.setFixedHeight(28)
        self.single_node_btn.setFixedHeight(28)
        self.all_nodes_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.single_node_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._method_group = QButtonGroup(self)
        self._method_group.setExclusive(True)
        self._method_group.addButton(self.all_nodes_btn)
        self._method_group.addButton(self.single_node_btn)
        self.all_nodes_btn.toggled.connect(self._on_method_changed)
        method_row.addWidget(self.all_nodes_btn)
        method_row.addWidget(self.single_node_btn)
        vl.addLayout(method_row)

        # Node selector — label indented to align with "Sync Status:" above
        node_row = QHBoxLayout()
        node_row.setSpacing(6)
        node_row.addSpacing(20)
        nl = QLabel("Select Node:")
        nl.setStyleSheet(label_css)
        nl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        node_row.addWidget(nl)
        node_row.addStretch()
        self.node_combo = QComboBox()
        self.node_combo.setMinimumWidth(90)
        self.node_combo.setMaximumWidth(110)
        self.node_combo.setStyleSheet(combo_css)
        self.node_combo.setEnabled(False)
        self._populate_node_combo()
        self.node_combo.currentTextChanged.connect(self._on_node_selected)
        node_row.addWidget(self.node_combo)
        vl.addLayout(node_row)
        vl.addWidget(_divider())

        # Frequency source — segmented pill toggle
        freq_method_row = QHBoxLayout()
        freq_method_row.setSpacing(6)
        self.all_freq_btn  = QPushButton("All Freq")
        self.file_freq_btn = QPushButton("From File")
        self.all_freq_btn.setProperty("role", "segment")
        self.file_freq_btn.setProperty("role", "segment")
        self.all_freq_btn.setCheckable(True)
        self.file_freq_btn.setCheckable(True)
        self.all_freq_btn.setChecked(True)
        self.all_freq_btn.setFixedHeight(28)
        self.file_freq_btn.setFixedHeight(28)
        self.all_freq_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.file_freq_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._freq_group = QButtonGroup(self)
        self._freq_group.setExclusive(True)
        self._freq_group.addButton(self.all_freq_btn)
        self._freq_group.addButton(self.file_freq_btn)
        self.all_freq_btn.toggled.connect(self._on_freq_method_changed)
        freq_method_row.addWidget(self.all_freq_btn)
        freq_method_row.addWidget(self.file_freq_btn)
        vl.addLayout(freq_method_row)

        # Load frequencies — full-width button + Pending status (grouped unit)
        self.load_freq_btn = QPushButton("Load Frequencies")
        self.load_freq_btn.setFixedHeight(28)
        self.load_freq_btn.setStyleSheet("QPushButton { font-size: 13px; padding: 4px 14px; }")
        self.load_freq_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.load_freq_btn.clicked.connect(self._load_freq_file)
        vl.addWidget(self.load_freq_btn)

        self.load_status_lbl = QLabel("Pending...")
        self.load_status_lbl.setProperty("role", "status-warn")
        self.load_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(self.load_status_lbl)
        vl.addWidget(_divider())

        # Start/Stop collection — full-width button
        self.collection_btn = QPushButton("Start Collection")
        self.collection_btn.setProperty("role", "success")
        self.collection_btn.setFixedHeight(34)
        self.collection_btn.setStyleSheet("QPushButton { font-size: 13px; padding: 4px 18px; }")
        self.collection_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.collection_btn.clicked.connect(self.on_collection_clicked)
        vl.addWidget(self.collection_btn)

        return card

    # ── Track Radio Collection ────────────────────────────────────────────────

    def _build_status_section(self) -> QWidget:
        card, vl = _section_card("Track Radio Collection", "trk")

        def _info_row(label_text: str) -> QLabel:
            l = QLabel(label_text)
            l.setStyleSheet("font-size: 13px; font-weight: 500; background: transparent; border: none;")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True)
            return l

        def _value_row(text: str) -> QLabel:
            l = QLabel(text)
            l.setProperty("role", "status-warn")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setWordWrap(True)
            return l

        # Available nodes as blue badge labels (wraps to multiple per row)
        vl.addWidget(_info_row("All Node(s) in Field"))
        badges_w = _FlowContainer()
        badges_w.setProperty("role", "transparent")
        badges_lo = _FlowLayout(badges_w, hspacing=3, vspacing=2, center=True)
        # Test nodes (config.json `"test": true`) participate in collection but
        # are hidden from this in-field badge list.
        test_ids = getattr(self.data, "test_nodes", set())
        node_keys = [k for k in self.data.nodes.keys() if k not in test_ids]
        if node_keys:
            for nid in node_keys:
                badge = QLabel(str(nid))
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setStyleSheet(
                    "background: #dbeafe; color: #1e3a8a; border-radius: 3px;"
                    " padding: 1px 5px; font-size: 11px; font-weight: 700;"
                )
                badges_lo.addWidget(badge)
        else:
            badges_lo.addWidget(_info_row("—"))
        vl.addWidget(badges_w)
        vl.addWidget(_divider())

        # Completed nodes
        vl.addWidget(_info_row("Completed Node(s)"))
        self.complete_nodes_lbl = _value_row("Pending...")
        vl.addWidget(self.complete_nodes_lbl)
        vl.addWidget(_divider())

        # Active node status
        self.node_status_title_lbl = _info_row("Active Node Status")
        vl.addWidget(self.node_status_title_lbl)
        self.node_status_lbl = _value_row("Pending...")
        vl.addWidget(self.node_status_lbl)
        vl.addWidget(_divider())

        # Pipeline steps — tight container so dots + stems flow continuously
        self.ack_row       = _StatusRow(1, "ACK Rec?")
        self.time_cal_row  = _StatusRow(2, "Time Cal?")
        self.freq_id_row   = _StatusRow(3, "Freq IDs TX?")
        self.data_rec_row  = _StatusRow(4, "Data Rec?")
        self.data_save_row = _StatusRow(5, "Data Saved?")

        pipeline = QWidget()
        pipeline.setProperty("role", "transparent")
        pipeline_lo = QVBoxLayout(pipeline)
        pipeline_lo.setContentsMargins(0, 0, 0, 0)
        pipeline_lo.setSpacing(0)
        for row in (self.ack_row, self.time_cal_row, self.freq_id_row,
                    self.data_rec_row, self.data_save_row):
            pipeline_lo.addWidget(row)
            if row is not self.data_save_row:
                pipeline_lo.addWidget(_stem())
        vl.addWidget(pipeline)

        # Public refs used by CommCollectPage widget-map
        self.ack_lbl       = self.ack_row.value_lbl
        self.time_cal_lbl  = self.time_cal_row.value_lbl
        self.freq_id_lbl   = self.freq_id_row.value_lbl
        self.data_rec_lbl  = self.data_rec_row.value_lbl
        self.data_save_lbl = self.data_save_row.value_lbl

        return card

    def _populate_node_combo(self):
        self.node_combo.clear()
        self.node_combo.addItem("-")
        test_ids = getattr(self.data, "test_nodes", set())
        for node_id in self.data.nodes.keys():
            suffix = " (test)" if node_id in test_ids else ""
            self.node_combo.addItem(f"Node {node_id}{suffix}")

    # ── collection logic ──────────────────────────────────────────────────────

    def on_collection_clicked(self):
        if "Start" in self.collection_btn.text():
            self._start_collection()
        else:
            self._end_collection()

    def _start_collection(self):
        if not self.data.sync_ok:
            QMessageBox.critical(
                self, "Not Synced",
                "Configure the serial port and complete synchronization before collecting."
            )
            return
        # Re-apply current UI selection to self.data so it reflects what the
        # user sees, regardless of whether ClearData() wiped it on disconnect
        # or a previous collection left nodes in 'Done' state.
        self._refresh_data_from_ui()
        if not any(v == "Working" for v in self.data.nodes.values()):
            QMessageBox.critical(self, "No Nodes", "No sensor nodes selected.")
            return
        if len(self.data.fre_IDs) == 0:
            QMessageBox.critical(self, "No Frequencies", "No frequencies loaded.")
            return

        self.collection_btn.setText("End Collection")
        self.collection_btn.setProperty("role", "danger")
        self.collection_btn.style().unpolish(self.collection_btn)
        self.collection_btn.style().polish(self.collection_btn)
        self.all_nodes_btn.setEnabled(False)
        self.single_node_btn.setEnabled(False)
        self.node_combo.setEnabled(False)
        self.load_freq_btn.setEnabled(False)
        self.all_freq_btn.setEnabled(False)
        self.file_freq_btn.setEnabled(False)

        self.data.working_nodes = [k for k, v in self.data.nodes.items() if v == "Working"]

        import threading
        self.serial.t1 = threading.Thread(
            target=self.serial.SerialStream,
            args=(self._dc_proxy,),
            daemon=True,
        )
        self.serial.t1.start()

    def _end_collection(self):
        self.serial.threading = False
        if self._com_panel_ref:
            self._com_panel_ref.disconnect_serial()
        self._reset_collection_ui()

    @pyqtSlot()
    def reset_after_collection(self):
        self._reset_collection_ui()

    def _reset_collection_ui(self):
        self.collection_btn.setText("Start Collection")
        self.collection_btn.setProperty("role", "success")
        self.collection_btn.style().unpolish(self.collection_btn)
        self.collection_btn.style().polish(self.collection_btn)
        self.all_nodes_btn.setEnabled(True)
        self.single_node_btn.setEnabled(True)
        self.all_freq_btn.setEnabled(True)
        self.file_freq_btn.setEnabled(True)
        # load_freq_btn stays disabled while "All Freq" is selected.
        # (Don't call _on_freq_method_changed here — it would clear a
        #  user-loaded file's fre_IDs every time a collection ends.)
        self.load_freq_btn.setEnabled(not self.all_freq_btn.isChecked())
        self._on_method_changed()

        for row in (self.ack_row, self.time_cal_row, self.freq_id_row,
                    self.data_rec_row, self.data_save_row):
            row.reset()

        for lbl in (self.node_status_lbl, self.complete_nodes_lbl):
            lbl.setText("Pending...")
            lbl.setProperty("role", "status-warn")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _on_method_changed(self, _: bool = True):
        if self.all_nodes_btn.isChecked():
            self.node_combo.setEnabled(False)
            self.node_combo.setCurrentIndex(0)
            for node_id in self.data.nodes.keys():
                self.data.nodes[node_id] = "Working"
        else:
            self.node_combo.setEnabled(True)
            for node_id in self.data.nodes.keys():
                self.data.nodes[node_id] = "NotSelected"

    def _refresh_data_from_ui(self):
        """Push the current UI selection into self.data. Called right before
        Start Collection so warnings only fire when the UI truly shows no
        selection — not when ClearData() wiped fre_IDs on disconnect or a
        prior collection flipped every node from 'Working' to 'Done'."""
        # Nodes
        if self.all_nodes_btn.isChecked():
            for node_id in self.data.nodes.keys():
                self.data.nodes[node_id] = "Working"
        else:
            for node_id in self.data.nodes.keys():
                self.data.nodes[node_id] = "NotSelected"
            text = self.node_combo.currentText()
            if "-" not in text:
                m = re.search(r"\d+", text)
                if m and m.group() in self.data.nodes:
                    self.data.nodes[m.group()] = "Working"
        # Frequencies
        if self.all_freq_btn.isChecked():
            self.data.fre_IDs = np.array([[97], [108], [102]])
        # else: From File — keep whatever was loaded via _load_freq_file.
        # If ClearData() emptied it, the validation below will catch that
        # and prompt the user to reload.

    def _on_freq_method_changed(self, _: bool = True):
        """All Freq → preload the 'send-all-IDs' magic CMD and grey-out the
        file picker. From File → restore the file-load flow unchanged."""
        if self.all_freq_btn.isChecked():
            self.data.fre_IDs = np.array([[97], [108], [102]])
            self.load_freq_btn.setEnabled(False)
            self._set_load_status("CMD to send all IDs", "status-ok")
        else:
            self.data.fre_IDs = np.array([])
            self.load_freq_btn.setEnabled(True)
            self._set_load_status("Pending...", "status-warn")

    def _on_node_selected(self, text: str):
        for node_id in self.data.nodes.keys():
            self.data.nodes[node_id] = "NotSelected"
        if "-" not in text:
            m = re.search(r"\d+", text)
            if m:
                self.data.nodes[m.group()] = "Working"

    def _load_freq_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select frequency Excel file", "",
            "Excel files (*.xlsx *.xls);;All files (*.*)",
        )
        if not path:
            return
        try:
            df = pd.read_excel(path)
            n  = len(df)
            if n == 3 and df.iloc[0, 0] == 97 and df.iloc[1, 0] == 108 and df.iloc[2, 0] == 102:
                self._set_load_status("CMD to send all IDs", "status-ok")
            else:
                self._set_load_status(f"{n} IDs loaded", "status-ok")
            self.data.fre_IDs = df.to_numpy()
        except Exception:
            self._set_load_status("Error loading IDs", "status-err")

    def _set_load_status(self, text: str, role: str):
        self.load_status_lbl.setText(text)
        self.load_status_lbl.setProperty("role", role)
        self.load_status_lbl.style().unpolish(self.load_status_lbl)
        self.load_status_lbl.style().polish(self.load_status_lbl)
