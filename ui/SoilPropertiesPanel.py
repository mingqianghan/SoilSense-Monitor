"""
SoilPropertiesPanel — non-modal floating dialog showing soil-model results
per (node_id, date). One row per (node_id, date) combination; same key
replaces existing row instead of duplicating.

Self-contained — does not import from HomeGui.py or CommCollectPage.py.
The host wires it via add_or_update_row(record) and refresh(records=...).
"""
from __future__ import annotations
import csv
import datetime
from typing import Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QAbstractItemView,
)


# VWC → pin color (matches Map View Addition 1)
_PIN_COLORS = {
    "none":     "#9ca3af",
    "dry":      "#bfdbfe",
    "moderate": "#60a5fa",
    "wet":      "#1d4ed8",
}


def _vwc_class(vwc) -> str:
    if vwc is None:
        return "none"
    if vwc < 0.15:
        return "dry"
    if vwc <= 0.25:
        return "moderate"
    return "wet"


_HEADERS = ["Node", "Date", "Time", "Status",
            "VWC\nm³/m³", "Bulk EC\ndS/m", "Pore EC\ndS/m", "USDA class"]

# Column-specific colors for LIVE rows
_LIVE_VWC_FG  = "#0c447c"
_LIVE_BULK_FG = "#b45309"
_LIVE_PORE_FG = "#0f6e56"
_PREV_FG      = "#6b7280"   # grey for historical rows


class SoilPropertiesPanel(QDialog):
    """
    Floating soil-properties table. Stays on top of the main window
    without blocking it (Qt.Tool flag).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Soil properties")
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setModal(False)
        self.resize(720, 340)

        # (node_id, date) → row index in the table
        self._row_index: dict[tuple[str, datetime.date], int] = {}

        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("Soil properties")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        header.addWidget(title)

        self.count_lbl = QLabel("0 rows")
        self.count_lbl.setStyleSheet("color: #6b7280; font-size: 12px;")
        header.addWidget(self.count_lbl)
        header.addStretch()

        self.save_btn = QPushButton("Save CSV")
        self.save_btn.clicked.connect(self._save_csv)
        header.addWidget(self.save_btn)

        layout.addLayout(header)

        self.table = QTableWidget(0, len(_HEADERS), self)
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # Let the table grow with the dialog rather than being capped at 300px.
        from PyQt6.QtWidgets import QSizePolicy
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        # stretch=1 — table takes all remaining vertical space below the header row
        layout.addWidget(self.table, 1)

    # ── public API ──────────────────────────────────────────────────────
    def add_or_update_row(self, rec: dict) -> None:
        """
        Add or replace a row for (node_id, date). Record fields used:
            node_id, date, time, is_live, vwc, sigma_bulk, sigma_pore, salinity
        """
        key = (rec["node_id"], rec["date"])
        self.table.setSortingEnabled(False)
        try:
            if key in self._row_index:
                row = self._row_index[key]
            else:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._row_index[key] = row
            self._fill_row(row, rec)
        finally:
            self.table.setSortingEnabled(True)
        self._update_count()

    def remove_row(self, node_id: str, date: datetime.date) -> None:
        """Drop the row for (node_id, date); no-op if it's not present."""
        key = (node_id, date)
        row = self._row_index.pop(key, None)
        if row is None:
            return
        self.table.setSortingEnabled(False)
        try:
            self.table.removeRow(row)
            # Row indices shift down by one for every entry after the removed row.
            for k, idx in list(self._row_index.items()):
                if idx > row:
                    self._row_index[k] = idx - 1
        finally:
            self.table.setSortingEnabled(True)
        self._update_count()

    def clear_all(self) -> None:
        """Remove every row."""
        self.table.setSortingEnabled(False)
        try:
            self.table.setRowCount(0)
            self._row_index.clear()
        finally:
            self.table.setSortingEnabled(True)
        self._update_count()

    def refresh(self, records: Iterable[dict]) -> None:
        """Replace the whole table contents from an iterable of records."""
        self.table.setSortingEnabled(False)
        try:
            self.table.setRowCount(0)
            self._row_index.clear()
            for rec in records:
                key = (rec["node_id"], rec["date"])
                row = self.table.rowCount()
                self.table.insertRow(row)
                self._row_index[key] = row
                self._fill_row(row, rec)
        finally:
            self.table.setSortingEnabled(True)
        self._update_count()

    # ── helpers ─────────────────────────────────────────────────────────
    def _fill_row(self, row: int, rec: dict) -> None:
        live = bool(rec.get("is_live"))
        vwc        = rec.get("vwc")
        sigma_bulk = rec.get("sigma_bulk")
        sigma_pore = rec.get("sigma_pore")
        salinity   = (rec.get("salinity") or {}).get("class", "—")

        pin_color = _PIN_COLORS[_vwc_class(vwc)]
        node_item = QTableWidgetItem(rec["node_id"])
        node_item.setForeground(QColor(pin_color))
        node_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.table.setItem(row, 0, node_item)

        # ─ Column 1: Date
        self._set_text(row, 1, str(rec["date"]),
                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       fg=None if live else _PREV_FG)

        # ─ Column 2: Time
        self._set_text(row, 2, rec.get("time", ""),
                       align=Qt.AlignmentFlag.AlignCenter,
                       fg=None if live else _PREV_FG)

        # ─ Column 3: Status pill (Live / Prev)
        status_txt = "Live" if live else "Prev"
        status_item = QTableWidgetItem(status_txt)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if live:
            status_item.setForeground(QColor("#14532d"))
            status_item.setBackground(QColor("#dcfce7"))
        else:
            status_item.setForeground(QColor("#92400e"))
            status_item.setBackground(QColor("#fef3c7"))
        self.table.setItem(row, 3, status_item)

        # ─ Columns 4-6: numeric values
        self._set_text(row, 4, f"{vwc:.3f}"        if vwc        is not None else "—",
                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       fg=_LIVE_VWC_FG  if live else _PREV_FG, bold=live)
        self._set_text(row, 5, f"{sigma_bulk:.3f}" if sigma_bulk is not None else "—",
                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       fg=_LIVE_BULK_FG if live else _PREV_FG, bold=live)
        self._set_text(row, 6, f"{sigma_pore:.2f}" if sigma_pore is not None else "—",
                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       fg=_LIVE_PORE_FG if live else _PREV_FG, bold=live)

        # ─ Column 7: USDA class
        self._set_text(row, 7, salinity,
                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       fg=None if live else _PREV_FG)

    def _set_text(self, row: int, col: int, text: str,
                  align: Qt.AlignmentFlag,
                  fg: str | None = None, bold: bool = False) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(align)
        if fg:
            item.setForeground(QColor(fg))
        if bold:
            f = item.font()
            f.setBold(True)
            item.setFont(f)
        self.table.setItem(row, col, item)

    def _update_count(self) -> None:
        n = self.table.rowCount()
        self.count_lbl.setText(f"{n} row" if n == 1 else f"{n} rows")

    # ── save CSV ────────────────────────────────────────────────────────
    def _save_csv(self) -> None:
        default_name = f"soil_properties_{datetime.date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Soil Properties CSV", default_name, "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            # utf-8-sig writes a BOM so Excel auto-detects UTF-8 (otherwise it
            # opens the file as Windows-1252 and any non-ASCII glyph becomes
            # mojibake). The em-dash "—" used in the on-screen table as the
            # "no data" placeholder is replaced with empty string here — CSV
            # convention is to leave missing numeric fields blank rather than
            # use a non-ASCII glyph.
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([h.replace("\n", " ") for h in _HEADERS])
                for r in range(self.table.rowCount()):
                    row = []
                    for c in range(self.table.columnCount()):
                        it = self.table.item(r, c)
                        txt = it.text() if it is not None else ""
                        if txt == "—":
                            txt = ""
                        row.append(txt)
                    w.writerow(row)
            QMessageBox.information(self, "Saved", f"CSV written to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
