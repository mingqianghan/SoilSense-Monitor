from __future__ import annotations
import os
import json
import math
import socket
from datetime import datetime, date

import requests
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QFileDialog,
    QDateEdit, QMessageBox, QFrame, QCalendarWidget, QAbstractItemView,
    QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate
from PyQt6.QtGui import QPixmap, QPalette, QColor, QTextCharFormat

from comm.weather_summary import WeatherSummary


_CAL_LIGHT = dict(
    base="#ffffff", alt="#f3f4f6", text="#111827",
    hl_bg="#dbeafe", hl_fg="#1e3a8a", weekend="#991b1b",
    nav_bg="#f3f4f6", nav_fg="#111827", nav_bd="#d1d5db",
    nav_hov="#e5e7eb",
)
_CAL_DARK = dict(
    base="#161b22", alt="#1f242c", text="#f0f6fc",
    hl_bg="#1f3a8a", hl_fg="#ffffff", weekend="#f87171",
    nav_bg="#21262d", nav_fg="#f0f6fc", nav_bd="#30363d",
    nav_hov="#30363d",
)


def _build_calendar(dark: bool = False) -> QCalendarWidget:
    """Create a QCalendarWidget with an explicit palette for the given theme."""
    cal = QCalendarWidget()
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    _apply_calendar_palette(cal, dark=dark)
    return cal


def _apply_calendar_palette(cal: QCalendarWidget, dark: bool = False) -> None:
    """
    Force visible date-cell text by setting palette on BOTH the QCalendarWidget
    and its internal QAbstractItemView (qt_calendar_calendarview). The cell
    delegate paints day numbers from the view's palette, so we have to reach it
    directly — QSS color rules and the outer widget's palette alone don't.

    Re-call after a global setStyleSheet() — re-polish wipes palettes.
    """
    c = _CAL_DARK if dark else _CAL_LIGHT
    txt   = QColor(c["text"])
    base  = QColor(c["base"])
    alt   = QColor(c["alt"])
    hl_bg = QColor(c["hl_bg"])
    hl_fg = QColor(c["hl_fg"])

    def _paint(pal: QPalette) -> QPalette:
        for grp in (QPalette.ColorGroup.Active,
                    QPalette.ColorGroup.Inactive):
            pal.setColor(grp, QPalette.ColorRole.Base,            base)
            pal.setColor(grp, QPalette.ColorRole.AlternateBase,   alt)
            pal.setColor(grp, QPalette.ColorRole.Window,          base)
            pal.setColor(grp, QPalette.ColorRole.Text,            txt)
            pal.setColor(grp, QPalette.ColorRole.WindowText,      txt)
            pal.setColor(grp, QPalette.ColorRole.ButtonText,      txt)
            pal.setColor(grp, QPalette.ColorRole.Highlight,       hl_bg)
            pal.setColor(grp, QPalette.ColorRole.HighlightedText, hl_fg)
        # Greyed-out days (previous/next month): muted but still visible
        muted = QColor(c["text"])
        muted.setAlpha(110)
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       muted)
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, muted)
        return pal

    cal.setPalette(_paint(cal.palette()))

    # Reach the internal QTableView — this is the widget whose delegate
    # actually draws the day numbers. Setting palette on the view alone is
    # not enough for its background; the viewport widget also has to be
    # told to auto-fill with the same palette.
    view = cal.findChild(QAbstractItemView, "qt_calendar_calendarview")
    if view is not None:
        view.setPalette(_paint(view.palette()))
        view.setBackgroundRole(QPalette.ColorRole.Base)
        vp = view.viewport()
        if vp is not None:
            vp.setAutoFillBackground(True)
            vp.setPalette(_paint(vp.palette()))
            vp.setBackgroundRole(QPalette.ColorRole.Base)

    # Day-of-week header labels — independent of palette.
    weekday_fmt = QTextCharFormat()
    weekday_fmt.setForeground(txt)
    weekend_fmt = QTextCharFormat()
    weekend_fmt.setForeground(QColor(c["weekend"]))
    for d in (Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
              Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday):
        cal.setWeekdayTextFormat(d, weekday_fmt)
    cal.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, weekend_fmt)
    cal.setWeekdayTextFormat(Qt.DayOfWeek.Sunday,   weekend_fmt)

    # Self-contained stylesheet on the calendar so it isn't dependent on the
    # global app QSS reaching this widget (which it doesn't reliably, since
    # the popup may live in a top-level frame outside the normal hierarchy).
    cal.setStyleSheet(f"""
        QCalendarWidget {{
            background: {c["base"]};
        }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background: {c["nav_bg"]};
            border-bottom: 1px solid {c["nav_bd"]};
        }}
        QCalendarWidget QToolButton {{
            background: transparent;
            color: {c["nav_fg"]};
            border: none;
            padding: 4px 8px;
            font-size: 13px;
            font-weight: 600;
        }}
        QCalendarWidget QToolButton:hover {{ background: {c["nav_hov"]}; }}
        QCalendarWidget QToolButton::menu-indicator {{ image: none; }}
        QCalendarWidget QSpinBox {{
            background: {c["base"]};
            color: {c["nav_fg"]};
            border: 1px solid {c["nav_bd"]};
            selection-background-color: {c["hl_bg"]};
            selection-color: {c["hl_fg"]};
        }}
        QCalendarWidget QMenu {{
            background: {c["base"]};
            color: {c["nav_fg"]};
            border: 1px solid {c["nav_bd"]};
        }}
        QCalendarWidget QMenu::item:selected {{
            background: {c["hl_bg"]};
            color: {c["hl_fg"]};
        }}
        QCalendarWidget QAbstractItemView {{
            background: {c["base"]};
            color: {c["text"]};
            selection-background-color: {c["hl_bg"]};
            selection-color: {c["hl_fg"]};
            alternate-background-color: {c["alt"]};
            outline: 0;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {c["text"]}80;
        }}
    """)

    # Force the whole calendar to repaint with the new palette
    cal.update()
    if view is not None:
        view.viewport().update()


def _calculate_center(markers: list[dict]) -> tuple[float, float]:
    if not markers:
        return 39.21, -96.59
    lats = [m["latitude"]  for m in markers]
    lons = [m["longitude"] for m in markers]
    return sum(lats) / len(lats), sum(lons) / len(lons)


# ── internet check ────────────────────────────────────────────────────────────

def _check_internet(timeout: int = 2) -> bool:
    for host in ("8.8.8.8", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((host, 443))
            return True
        except OSError:
            continue
    return False


# ── slippy-map tile math ──────────────────────────────────────────────────────

def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_r = math.radians(lat)
    n = 1 << zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _tile_nw_corner(tx: int, ty: int, zoom: int) -> tuple[float, float]:
    n = 1 << zoom
    lon = tx / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * ty / n))))
    return lat, lon


# ── background weather loader ─────────────────────────────────────────────────

class WeatherLoader(QThread):
    """Background thread for OpenWeather API calls. Emits a status alongside
    the data so HomeGui can show a banner when something goes wrong."""

    # status is one of: "ok" | "no_key" | "no_internet" | "api_error"
    finished = pyqtSignal(dict, dict, dict, str)
    error    = pyqtSignal(str)

    def __init__(self, ws: "WeatherSummary", quiet: bool = False):
        super().__init__()
        self.ws    = ws
        self.quiet = quiet

    def run(self):
        # Empty dicts the panel renders as "—" / NaN, matching the existing
        # WeatherSummary fallback shape.
        empty_current = {"temp": float("nan"), "humidity": float("nan"),
                         "wind_speed": float("nan"),
                         "weather_description": "N/A", "icon_url": "-"}
        empty_week = {"highest_temp": float("nan"), "lowest_temp": float("nan"),
                      "avg_temp": float("nan"),
                      "highest_humidity": float("nan"),
                      "lowest_humidity": float("nan"),
                      "avg_humidity": float("nan"),
                      "avg_wind_speed": float("nan"),
                      "total_rainfall": float("nan")}

        # ── Pre-flight: no key → don't fetch ────────────────────────────
        key = getattr(self.ws, "api_key", "")
        if not key:
            self.finished.emit(empty_current, dict(empty_week), dict(empty_week),
                               "no_key")
            return

        # ── Pre-flight: no internet → don't spam retries ────────────────
        if not _check_internet(timeout=1):
            self.finished.emit(empty_current, dict(empty_week), dict(empty_week),
                               "no_internet")
            return

        # ── Fetch ───────────────────────────────────────────────────────
        # Weather_Summary.fetch_data prints "Connection error. Retrying ..."
        # for every failed request, and that file is on the do-not-modify list.
        # Redirect stdout when we want quiet behavior.
        import contextlib
        import io
        ctx = (contextlib.redirect_stdout(io.StringIO())
               if self.quiet else contextlib.nullcontext())
        try:
            with ctx:
                self.ws.generate_current_weather_summary()
                self.ws.generate_past_week_summary()
                self.ws.generate_next_week_summary()
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(empty_current, dict(empty_week), dict(empty_week),
                               "api_error")
            return

        cur  = self.ws.current_weather_summary or empty_current
        past = self.ws.past_week_summary       or dict(empty_week)
        nxt  = self.ws.next_week_summary       or dict(empty_week)

        # Post-flight: if the description is still "N/A" we have a key + the
        # internet, but the API still didn't return usable data — typically
        # an invalid key, exhausted free tier, or upstream 5xx.
        status = "ok"
        if cur.get("weather_description") in (None, "N/A"):
            status = "api_error"

        self.finished.emit(cur, past, nxt, status)


# ── offline matplotlib map (fallback when no WebEngine) ──────────────────────

class OfflineMapWidget(QWidget):
    def __init__(self, markers: list[dict], clat: float, clon: float,
                 plots: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.markers = markers
        self.plots   = plots or []
        self.clat    = clat
        self.clon    = clon
        self._setup_canvas()
        self._draw_map()
        self._add_recenter_button()

    def _setup_canvas(self):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.fig    = Figure(facecolor="#0d1117")
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.ax     = self.fig.add_subplot(111)
        layout.addWidget(self.canvas)

    def _add_recenter_button(self):
        self._recenter_btn = QPushButton("⊕  Fit to nodes", self)
        self._recenter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._recenter_btn.setStyleSheet(
            "QPushButton {"
            " background: rgba(255,255,255,0.94);"
            " color: #111827;"
            " border: 1px solid #d1d5db;"
            " border-radius: 6px;"
            " padding: 4px 9px;"
            " font-size: 12px;"
            " font-weight: 700;"
            " }"
            "QPushButton:hover { background: #f3f4f6; }"
            "QPushButton:pressed { background: #e5e7eb; }"
        )
        self._recenter_btn.clicked.connect(self.recenter)
        self._recenter_btn.adjustSize()
        self._recenter_btn.move(10, 10)
        self._recenter_btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_recenter_btn"):
            self._recenter_btn.move(10, 10)
            self._recenter_btn.raise_()

    def recenter(self):
        self._draw_map()

    def _draw_map(self):
        import matplotlib.image as mpimg
        ax = self.ax
        ax.clear()
        ax.set_facecolor("#161b22")

        bg_png  = "assets/map_background.png"
        bg_json = "assets/map_bounds.json"
        has_bg  = False

        if os.path.exists(bg_png) and os.path.exists(bg_json):
            try:
                with open(bg_json) as f:
                    bounds = json.load(f)
                img = mpimg.imread(bg_png)
                ax.imshow(img,
                          extent=[bounds["west"], bounds["east"],
                                  bounds["south"], bounds["north"]],
                          aspect="auto", zorder=0)
                ax.set_xlim(bounds["west"], bounds["east"])
                ax.set_ylim(bounds["south"], bounds["north"])
                has_bg = True
            except Exception:
                pass

        if not has_bg:
            ax.grid(True, color="#21262d", linewidth=0.8, linestyle="--")
            ax.text(self.clon, self.clat,
                    "No cached map — connect to internet to load satellite view.",
                    ha="center", va="center",
                    color="#6b7280", fontsize=11, style="italic",
                    fontfamily="DejaVu Sans")

        # ── Field plots (polygons + corner markers) ───────────────────────
        if self.plots:
            from matplotlib.patches import Polygon
            plot_palette = ["#22d3ee", "#a78bfa", "#fbbf24", "#f472b6", "#34d399"]
            for i, plot in enumerate(self.plots):
                corners = plot.get("corners", [])
                if len(corners) < 3:
                    continue
                color = plot_palette[i % len(plot_palette)]
                pts = [(c["longitude"], c["latitude"]) for c in corners]
                poly = Polygon(
                    pts, closed=True,
                    facecolor=color, alpha=0.15,
                    edgecolor=color, linewidth=1.8, zorder=3,
                )
                self.ax.add_patch(poly)
                # Corner dots (no labels)
                cxs = [p[0] for p in pts]
                cys = [p[1] for p in pts]
                self.ax.scatter(cxs, cys, c=color, s=42, zorder=4,
                                edgecolors="white", linewidth=1.0)

        lats = [m["latitude"]  for m in self.markers]
        lons = [m["longitude"] for m in self.markers]
        if lats:
            # Green sensor markers with white border
            ax.scatter(lons, lats, c="#22c55e", s=80, zorder=5,
                       edgecolors="white", linewidth=1.0)
            for m in self.markers:
                ax.annotate(
                    m["name"],
                    xy=(m["longitude"], m["latitude"]),
                    xytext=(8, 8), textcoords="offset points",
                    fontsize=11, fontweight="bold", color="white",
                    fontfamily="DejaVu Sans",
                    zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35",
                              fc="#0d1117", ec="#30363d",
                              alpha=0.88, linewidth=0.8),
                )
            if not has_bg:
                pad = max(0.0002, (max(lons) - min(lons)) * 0.18 + 0.0001)
                ax.set_xlim(min(lons) - pad, max(lons) + pad)
                ax.set_ylim(min(lats) - pad, max(lats) + pad)

        # ACTIVE NODES overlay card
        if self.markers:
            n_nodes = len(self.markers)
            sep     = "─" * 32
            rows    = [
                f"  ● {m['name']}    {m['latitude']:.5f},  {m['longitude']:.5f}"
                for m in self.markers
            ]
            card_text = f"ACTIVE NODES  ({n_nodes})\n{sep}\n" + "\n".join(rows)
            ax.text(
                0.985, 0.985, card_text,
                transform=ax.transAxes,
                fontsize=9.5,
                verticalalignment="top", horizontalalignment="right",
                fontfamily="DejaVu Sans",
                fontweight="normal",
                linespacing=1.6,
                bbox=dict(
                    boxstyle="round,pad=0.65",
                    facecolor="white", edgecolor="#d1d5db",
                    alpha=0.94, linewidth=1.0,
                ),
                color="#374151",
                zorder=10,
            )

        ax.set_xlabel("Longitude", color="#8b9297", fontsize=10, fontfamily="DejaVu Sans")
        ax.set_ylabel("Latitude",  color="#8b9297", fontsize=10, fontfamily="DejaVu Sans")
        ax.tick_params(colors="#8b9297", labelsize=9)
        for sp in ax.spines.values():
            sp.set_edgecolor("#30363d")
        ax.set_title("Sensor Node Map", color="#cdd9e5", fontsize=13,
                     fontweight="bold", fontfamily="DejaVu Sans", pad=6)
        self.fig.tight_layout(pad=0.5)
        self.canvas.draw()


# ── map widget factory ────────────────────────────────────────────────────────

def _build_map_widget(markers: list[dict], clat: float, clon: float,
                      plots: list[dict] | None = None,
                      marker_soil: list[dict] | None = None,
                      has_net: bool | None = None) -> QWidget:
    if has_net is None:
        has_net = _check_internet(timeout=1)

    # Try the Leaflet/WebEngine path for both online and offline modes.
    # Offline uses tiles + leaflet.js/css from the local cache populated
    # by TileCacheDownloader on a prior online run.
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        from PyQt6.QtCore import QUrl

        if has_net:
            offline = False
        else:
            from setup.offline_map import tiles_cache_available
            if not tiles_cache_available():
                # No internet AND no usable cache → matplotlib fallback.
                return OfflineMapWidget(markers, clat, clon, plots or [])
            offline = True

        view = QWebEngineView()
        settings = view.settings()
        # Let the local Leaflet page reach the cached tiles via file:// URLs.
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        # Set baseUrl to the project root so relative paths like
        # "assets/tiles/..." in the HTML resolve to local files.
        base_url = QUrl.fromLocalFile(os.path.abspath(".") + os.sep)
        view.setHtml(
            _leaflet_html(markers, clat, clon, plots or [],
                          marker_soil or [], offline=offline),
            baseUrl=base_url,
        )
        return view
    except ImportError:
        pass

    return OfflineMapWidget(markers, clat, clon, plots or [])


# ── Soil/VWC helpers (shared with SoilPropertiesPanel) ───────────────────────
_PIN_COLOR = {
    "none":     ("#9ca3af", "#6b7280"),   # fill, border
    "dry":      ("#bfdbfe", "#93c5fd"),
    "moderate": ("#60a5fa", "#2563eb"),
    "wet":      ("#1d4ed8", "#1e3a8a"),
}


def _vwc_class(vwc) -> str:
    if vwc is None:
        return "none"
    if vwc < 0.15:
        return "dry"
    if vwc <= 0.25:
        return "moderate"
    return "wet"


def _marker_to_node_id(marker_name: str) -> str:
    """'S1' → 'S1', 'S18' → 'S18'. Normalizes digits (drops leading zeros)
    so the result matches _node_id_from_folder."""
    digits = "".join(ch for ch in marker_name if ch.isdigit())
    if not digits:
        return ""
    return f"S{int(digits)}"


def _leaflet_html(markers: list[dict], clat: float, clon: float,
                  plots: list[dict] | None = None,
                  marker_soil: list[dict] | None = None,
                  offline: bool = False) -> str:
    plots = plots or []
    # Field plot polygons + corner markers (drawn first so sensor markers sit on top)
    polygon_js = ""
    plot_palette = ["#22d3ee", "#a78bfa", "#fbbf24", "#f472b6", "#34d399"]
    for i, plot in enumerate(plots):
        corners = plot.get("corners", [])
        if len(corners) < 3:
            continue
        color = plot_palette[i % len(plot_palette)]
        latlng = "[" + ",".join(
            f"[{c['latitude']},{c['longitude']}]" for c in corners
        ) + "]"
        polygon_js += (
            f"L.polygon({latlng},"
            f"{{color:'{color}',weight:2,fillColor:'{color}',fillOpacity:0.15,"
            f"interactive:false}})"
            f".addTo(map);\n"
        )
        # One small dot per corner (no labels)
        for c in corners:
            polygon_js += (
                f"L.circleMarker([{c['latitude']},{c['longitude']}],"
                f"{{radius:5,color:'#fff',weight:1.5,fillColor:'{color}',"
                f"fillOpacity:1,interactive:false}}).addTo(map);\n"
            )
    # Build a fast lookup: node_id → soil record (already filtered by host)
    soil_by_id: dict[str, dict] = {
        r["node_id"]: r for r in (marker_soil or [])
    }

    circle_js = ""
    coords_js  = "["
    # Tallies for the Field Status side panel
    class_counts = {"dry": 0, "moderate": 0, "wet": 0, "none": 0}
    saline_count = 0
    latest_dt: datetime | None = None
    for m in markers:
        lat, lon, name = m["latitude"], m["longitude"], m["name"]
        nid  = _marker_to_node_id(name)
        rec  = soil_by_id.get(nid)
        is_nearest = bool(rec and rec.get("_nearest"))

        if rec:
            cls = _vwc_class(rec.get("vwc"))
            class_counts[cls] = class_counts.get(cls, 0) + 1
            sal_rec = rec.get("salinity") or {}
            if sal_rec.get("risk") in ("low", "medium", "high"):
                saline_count += 1
            try:
                rec_date = rec["date"]
                if not isinstance(rec_date, date):
                    rec_date = date.fromisoformat(str(rec_date))
                hh, mm = (rec.get("time") or "00:00").split(":")[:2]
                dt = datetime(rec_date.year, rec_date.month, rec_date.day,
                              int(hh), int(mm))
                if latest_dt is None or dt > latest_dt:
                    latest_dt = dt
            except Exception:
                pass
        else:
            cls = "none"
            class_counts["none"] += 1
        fill, border = _PIN_COLOR[cls]

        # Popup HTML — VWC / Bulk EC / Date row added below Lat/Lon divider.
        if rec:
            date_str = str(rec["date"])
            is_live  = bool(rec.get("is_live"))
            if is_live:
                date_badge = (
                    "<span style=\\\"background:#dcfce7;color:#14532d;"
                    "padding:1px 7px;border-radius:9px;font-size:11px;"
                    "font-weight:700;\\\">Today</span>"
                )
            elif is_nearest:
                date_badge = (
                    f"<span style=\\\"background:#fef3c7;color:#92400e;"
                    f"padding:1px 7px;border-radius:9px;font-size:11px;"
                    f"font-weight:700;\\\">{date_str} (nearest)</span>"
                )
            else:
                date_badge = (
                    f"<span style=\\\"background:#dbeafe;color:#1e3a8a;"
                    f"padding:1px 7px;border-radius:9px;font-size:11px;"
                    f"font-weight:700;\\\">{date_str}</span>"
                )

            val_fg = "#374151" if (is_nearest and not is_live) else None
            vwc_fg  = val_fg or "#0c447c"
            bulk_fg = val_fg or "#b45309"
            pore_fg = val_fg or "#0f6e56"

            vwc_v   = rec.get("vwc")
            bulk_v  = rec.get("sigma_bulk")
            pore_v  = rec.get("sigma_pore")
            vwc_txt  = f"{vwc_v:.3f} m³/m³"  if vwc_v  is not None else "—"
            bulk_txt = f"{bulk_v:.3f} dS/m"  if bulk_v is not None else "—"
            pore_txt = f"{pore_v:.2f} dS/m"  if pore_v is not None else "—"

            # USDA salinity badge — color follows the risk level
            sal       = rec.get("salinity") or {}
            sal_cls   = sal.get("class") or "—"
            sal_risk  = sal.get("risk")  or "none"
            _SAL_BG = {
                "none":   ("#dcfce7", "#14532d"),  # green
                "low":    ("#fef3c7", "#92400e"),  # amber
                "medium": ("#fed7aa", "#9a3412"),  # orange
                "high":   ("#fee2e2", "#991b1b"),  # red
            }
            sal_bg, sal_fg = _SAL_BG.get(sal_risk, ("#e5e7eb", "#374151"))
            sal_badge = (
                f"<span style=\\\"background:{sal_bg};color:{sal_fg};"
                f"padding:1px 7px;border-radius:9px;font-size:11px;"
                f"font-weight:700;\\\">{sal_cls}</span>"
            )

            soil_rows = (
                "<hr style=\\\"border:none;border-top:1px solid #e5e7eb;margin:5px 0;\\\"/>"
                f"<table style=\\\"font-size:12px;border-collapse:collapse;\\\">"
                f"<tr><td style=\\\"color:#6b7280;padding-right:8px;\\\">VWC</td>"
                f"<td style=\\\"color:{vwc_fg};font-weight:700;\\\">{vwc_txt}</td></tr>"
                f"<tr><td style=\\\"color:#6b7280;padding-right:8px;\\\">Bulk EC</td>"
                f"<td style=\\\"color:{bulk_fg};font-weight:700;\\\">{bulk_txt}</td></tr>"
                f"<tr><td style=\\\"color:#6b7280;padding-right:8px;\\\">Pore EC</td>"
                f"<td style=\\\"color:{pore_fg};font-weight:700;\\\">{pore_txt}</td></tr>"
                f"<tr><td style=\\\"color:#6b7280;padding-right:8px;\\\">Salinity</td>"
                f"<td>{sal_badge}</td></tr>"
                f"<tr><td style=\\\"color:#6b7280;padding-right:8px;\\\">Date</td>"
                f"<td>{date_badge}</td></tr>"
                f"</table>"
            )
        else:
            soil_rows = (
                "<hr style=\\\"border:none;border-top:1px solid #e5e7eb;margin:5px 0;\\\"/>"
                "<span style=\\\"color:#9ca3af;font-size:12px;\\\">No soil data</span>"
            )

        popup_html = (
            f"<b style=\\\"font-size:16px;\\\">{name}</b><br>"
            f"<span style=\\\"color:#6b7280;font-size:12px;\\\">"
            f"Lat: {lat:.6f}<br>Lon: {lon:.6f}</span>"
            f"{soil_rows}"
        )

        # Pin styling. Nearest-historical = dashed amber ring with no fill.
        if is_nearest and rec and not rec.get("is_live"):
            circle_js += (
                f"L.circleMarker([{lat},{lon}],"
                f"{{radius:7,color:'#d97706',weight:2.5,fillColor:'{fill}',"
                f"fillOpacity:0.5,dashArray:'4,3'}})"
            )
        else:
            circle_js += (
                f"L.circleMarker([{lat},{lon}],"
                f"{{radius:6,color:'{border}',weight:2,fillColor:'{fill}',"
                f"fillOpacity:1}})"
            )
        circle_js += (
            f".addTo(map)"
            f'.bindPopup("{popup_html}")'
            f".bindTooltip('{name}',"
            f"{{permanent:true,direction:'right',className:'node-tip'}});\n"
        )

        coords_js += f"[{lat},{lon}],"
    coords_js += "]"
    n = len(markers)

    # ── Field Status summary panel content ─────────────────────────────────
    _CLASS_META = [
        ("dry",      "Dry",       "#bfdbfe", "#93c5fd"),
        ("moderate", "Moderate",  "#60a5fa", "#2563eb"),
        ("wet",      "Wet",       "#1d4ed8", "#1e3a8a"),
        ("none",     "No data",   "#9ca3af", "#6b7280"),
    ]
    summary_rows = ""
    for key, label, fill_c, border_c in _CLASS_META:
        count = class_counts.get(key, 0)
        if count == 0 and key == "none":
            continue
        summary_rows += (
            f"<div class='sr'>"
            f"<span class='sr-dot' style='background:{fill_c};border-color:{border_c};'></span>"
            f"<span class='sr-lbl'>{label}</span>"
            f"<span class='sr-val'>{count}</span>"
            f"</div>"
        )

    sal_color = "#991b1b" if saline_count > 0 else "#14532d"
    saline_block = (
        f"<div class='sr sr-saline'>"
        f"<span class='sr-icon'>⚠</span>"
        f"<span class='sr-lbl'>Saline</span>"
        f"<span class='sr-val' style='color:{sal_color};'>{saline_count}</span>"
        f"</div>"
    ) if any(class_counts.get(k, 0) for k in ("dry", "moderate", "wet")) else ""

    if latest_dt is not None:
        delta = datetime.now() - latest_dt
        secs = int(delta.total_seconds())
        if secs < 60:
            updated_txt = "just now"
        elif secs < 3600:
            updated_txt = f"{secs // 60} min ago"
        elif secs < 86400:
            updated_txt = f"{secs // 3600} hr ago"
        else:
            updated_txt = latest_dt.strftime("%b %d")
    else:
        updated_txt = "—"
    updated_block = (
        f"<div class='sr sr-updated'>"
        f"<span class='sr-lbl'>Updated</span>"
        f"<span class='sr-val sr-time'>{updated_txt}</span>"
        f"</div>"
    )
    # Online: pull Leaflet from the CDN and tiles from Google.
    # Offline: serve everything from the local cache populated by
    # TileCacheDownloader. The page's baseUrl (set in _build_map_widget)
    # makes these relative URLs resolve to file:// paths under the project.
    if offline:
        leaflet_css_href = "assets/leaflet/leaflet.css"
        leaflet_js_src   = "assets/leaflet/leaflet.js"
        tile_url         = "assets/tiles/{z}/{x}/{y}.png"
        tile_attribution = "Cached satellite tiles (offline)"
        tile_max_zoom    = 20
        tile_min_zoom    = 17
    else:
        leaflet_css_href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        leaflet_js_src   = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        tile_url         = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
        tile_attribution = "© Google"
        tile_max_zoom    = 22
        tile_min_zoom    = 0

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>
<link rel="stylesheet" href="{leaflet_css_href}"/>
<script src="{leaflet_js_src}"></script>
<style>
  body,html{{margin:0;padding:0;}}
  #map{{height:100vh;width:100%;}}
  /* node label tooltips */
  .node-tip{{
    background:rgba(13,17,23,0.88)!important;
    border:1px solid #30363d!important;
    border-radius:5px!important;
    color:#f0f6fc!important;
    font:bold 13px/1 'Segoe UI',system-ui,sans-serif!important;
    padding:3px 7px!important;
    box-shadow:none!important;
  }}
  .node-tip::before{{display:none!important;}}
  /* FIELD STATUS panel */
  #panel{{
    position:absolute;top:12px;right:12px;z-index:1000;
    background:rgba(255,255,255,0.95);
    border:1px solid #d1d5db;border-radius:10px;
    box-shadow:0 2px 12px rgba(0,0,0,0.18);
    padding:10px 12px;
    width:fit-content;min-width:148px;max-width:200px;
    font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
  }}
  #panel h3{{
    margin:0 0 2px 0;font-size:11px;font-weight:700;
    color:#374151;letter-spacing:0.5px;text-transform:uppercase;
    white-space:nowrap;
  }}
  #panel .sub{{font-size:11px;color:#9ca3af;margin-bottom:7px;white-space:nowrap;}}
  .sr{{display:flex;align-items:center;gap:8px;padding:2px 0;
       white-space:nowrap;}}
  .sr-dot{{width:9px;height:9px;border-radius:50%;
          border:1.5px solid;flex-shrink:0;}}
  .sr-icon{{font-size:11px;color:#92400e;width:9px;text-align:center;flex-shrink:0;}}
  .sr-lbl{{font-size:12px;color:#374151;flex:1;}}
  .sr-val{{font-size:13px;font-weight:700;color:#111827;}}
  .sr-saline{{margin-top:4px;padding-top:5px;border-top:1px solid #f3f4f6;}}
  .sr-updated{{margin-top:4px;padding-top:5px;border-top:1px solid #f3f4f6;}}
  .sr-time{{font-size:11px;font-weight:600;color:#6b7280;}}
  /* Fit-to-nodes button */
  .recenter-btn{{
    background:rgba(255,255,255,0.94)!important;
    border:1px solid #d1d5db!important;
    border-radius:6px!important;
    color:#111827!important;
    font:700 12px/1 'Segoe UI',system-ui,sans-serif!important;
    padding:5px 9px!important;
    cursor:pointer;
    box-shadow:0 1px 4px rgba(0,0,0,0.12);
  }}
  .recenter-btn:hover{{background:#f3f4f6!important;}}
  /* VWC legend (bottom-left) */
  .vwc-legend{{
    background:rgba(255,255,255,0.95);
    border:1px solid #d1d5db;border-radius:8px;
    box-shadow:0 1px 6px rgba(0,0,0,0.14);
    padding:7px 10px;
    font-family:'Segoe UI',system-ui,sans-serif;
    color:#374151;
  }}
  .vwc-legend .lg-title{{
    font-size:11px;font-weight:700;letter-spacing:0.4px;
    text-transform:uppercase;color:#6b7280;margin-bottom:4px;
  }}
  .vwc-legend .lg-unit{{
    font-size:11px;font-weight:600;letter-spacing:0.2px;
    text-transform:none;color:#9ca3af;margin-left:3px;
  }}
  .vwc-legend .lg-row{{display:flex;align-items:center;gap:7px;font-size:12px;line-height:1.5;}}
  .vwc-legend .lg-dot{{
    width:11px;height:11px;border-radius:50%;
    border:1.5px solid;display:inline-block;flex-shrink:0;
  }}
</style>
</head><body>
<div id="map"></div>
<div id="panel">
  <h3>Field Status</h3>
  <div class="sub">{n} sensor{"s" if n != 1 else ""} deployed</div>
  {summary_rows}
  {saline_block}
  {updated_block}
</div>
<script>
var map=L.map('map',{{zoomControl:true,minZoom:{tile_min_zoom},maxZoom:{tile_max_zoom}}}).setView([{clat},{clon}],20);
// Plain-text "Leaflet" — strips the default link + Ukrainian flag emoji
// from the bottom-right attribution control.
map.attributionControl.setPrefix('Leaflet');
L.tileLayer('{tile_url}',
  {{attribution:'{tile_attribution}',maxZoom:{tile_max_zoom},minZoom:{tile_min_zoom}}}).addTo(map);
{polygon_js}
{circle_js}
var nodeCoords = {coords_js};
var initialCenter = [{clat},{clon}];
var initialZoom = 20;
function recenterMap() {{
  if (nodeCoords.length > 1) {{
    map.fitBounds(L.latLngBounds(nodeCoords), {{padding:[40,40], maxZoom:20}});
  }} else if (nodeCoords.length === 1) {{
    map.setView(nodeCoords[0], initialZoom);
  }} else {{
    map.setView(initialCenter, initialZoom);
  }}
}}
var RecenterControl = L.Control.extend({{
  options: {{position:'topleft'}},
  onAdd: function(m) {{
    var btn = L.DomUtil.create('button','recenter-btn');
    btn.innerHTML = '⊕  Fit to nodes';
    btn.title = 'Fit map to all sensor nodes';
    L.DomEvent.disableClickPropagation(btn);
    L.DomEvent.on(btn,'click',function(e){{ L.DomEvent.preventDefault(e); recenterMap(); }});
    return btn;
  }}
}});
map.addControl(new RecenterControl());

// VWC legend — bottom-left corner
var VwcLegend = L.Control.extend({{
  options: {{position:'bottomleft'}},
  onAdd: function(m) {{
    var box = L.DomUtil.create('div','vwc-legend');
    box.innerHTML =
      "<div class='lg-title'>VWC<span class='lg-unit'>(m³/m³)</span></div>"
      + "<div class='lg-row'><span class='lg-dot' style='background:#9ca3af;border-color:#6b7280;'></span>No data</div>"
      + "<div class='lg-row'><span class='lg-dot' style='background:#bfdbfe;border-color:#93c5fd;'></span>Dry &lt; 0.15</div>"
      + "<div class='lg-row'><span class='lg-dot' style='background:#60a5fa;border-color:#2563eb;'></span>Moderate 0.15–0.25</div>"
      + "<div class='lg-row'><span class='lg-dot' style='background:#1d4ed8;border-color:#1e3a8a;'></span>Wet &gt; 0.25</div>";
    return box;
  }}
}});
map.addControl(new VwcLegend());
</script></body></html>"""


# ── shared layout helpers ─────────────────────────────────────────────────────

def _section_title(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setProperty("role", "section-title")
    return lbl


def _wx_section_title(text: str) -> QLabel:
    """Section title used inside weather cards."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        "font-size: 14px; font-weight: 800;"
        " letter-spacing: 0.6px; background: transparent;"
        " padding: 0px 0px 3px 0px;"
    )
    return lbl


def _wx_group_header(title: str, unit: str) -> QFrame:
    """Compact header row inside a weather card — title left, unit right."""
    f = QFrame()
    f.setStyleSheet("QFrame { background: transparent; }")
    hl = QHBoxLayout(f)
    hl.setContentsMargins(1, 1, 1, 0)
    hl.setSpacing(0)
    t = QLabel(title)
    t.setStyleSheet(
        "font-size: 13px; font-weight: 700; background: transparent;"
    )
    hl.addWidget(t)
    hl.addStretch()
    u = QLabel(unit)
    u.setStyleSheet(
        "font-size: 11px; font-weight: 600; color: #6b7280; background: transparent;"
    )
    hl.addWidget(u)
    return f


def _divider() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("QFrame { background: #d1d5db; }")
    return f


_HILO_CELL_STYLES = {
    "hilo-high":      ("#fef3c7", "#92400e"),
    "hilo-high-blue": ("#dbeafe", "#1e3a8a"),
    "hilo-avg":       ("#e5e7eb", "#374151"),
    "hilo-low":       ("#fee2e2", "#991b1b"),
}


def _hilo_cell(value: str, sub: str, role: str) -> QFrame:
    bg, text_col = _HILO_CELL_STYLES.get(role, ("#e5e7eb", "#374151"))
    f = QFrame()
    f.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 5px; }}")

    vl = QVBoxLayout(f)
    vl.setContentsMargins(3, 3, 3, 3)
    vl.setSpacing(0)

    col_css = f" color: {text_col};" if text_col else ""
    val_lbl = QLabel(value)
    val_lbl.setStyleSheet(
        f"font-family: Consolas; font-size: 13px; font-weight: 800;"
        f" background: transparent;{col_css}"
    )
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vl.addWidget(val_lbl)

    sub_lbl = QLabel(sub.upper())
    sub_lbl.setStyleSheet(
        f"font-size: 9px; font-weight: 700; letter-spacing: 0.3px;"
        f" background: transparent;{col_css}"
    )
    sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vl.addWidget(sub_lbl)
    return f


def _hilo_row(high: str, avg: str, low: str,
              high_role: str = "hilo-high") -> QHBoxLayout:
    hl = QHBoxLayout()
    hl.setSpacing(4)
    hl.addWidget(_hilo_cell(high, "high",    high_role))
    hl.addWidget(_hilo_cell(avg,  "average", "hilo-avg"))
    hl.addWidget(_hilo_cell(low,  "low",     "hilo-low"))
    return hl


def _wx_card() -> tuple[QFrame, QVBoxLayout]:
    """Bordered card container for each weather section."""
    card = QFrame()
    card.setFrameShape(QFrame.Shape.StyledPanel)
    card.setProperty("role", "wx-card")
    vl = QVBoxLayout(card)
    vl.setContentsMargins(7, 5, 7, 5)
    vl.setSpacing(3)
    return card, vl


def _metric_box(label: str, value: str,
                val_role: str = "wx-value", icon: str = "") -> QFrame:
    """Single metric row — optional icon, label, value (right-aligned)."""
    f = QFrame()
    f.setProperty("role", "wx-metric")
    hl = QHBoxLayout(f)
    hl.setContentsMargins(1, 2, 1, 2)
    hl.setSpacing(6)
    if icon:
        ic = QLabel(icon)
        ic.setFixedWidth(18)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(
            "background: transparent; color: #64748b; font-size: 13px;"
        )
        hl.addWidget(ic)
    lbl = QLabel(label)
    lbl.setStyleSheet("font-size: 13px; background: transparent;")
    hl.addWidget(lbl)
    hl.addStretch()
    val = QLabel(value)
    val.setProperty("role", val_role)
    hl.addWidget(val)
    return f


_ICON_BOX = {
    "wx-icon-red":  ("#fee2e2", "#dc2626"),
    "wx-icon-blue": ("#dbeafe", "#0ea5e9"),
    "wx-icon-gray": ("#e5e7eb", "#64748b"),
}


def _icon_metric_row(layout: QVBoxLayout, icon: str, box_role: str,
                     label: str, value: str, val_role: str = "wx-value"):
    """Metric row with a small colored icon on the left (used in Current Conditions)."""
    hl = QHBoxLayout()
    hl.setContentsMargins(0, 1, 0, 1)
    hl.setSpacing(7)

    _, fg = _ICON_BOX.get(box_role, ("#e5e7eb", "#64748b"))
    ic = QLabel(icon)
    ic.setFixedWidth(18)
    ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet(
        f"background: transparent; color: {fg}; font-size: 14px;"
    )
    hl.addWidget(ic)

    lbl = QLabel(label)
    lbl.setStyleSheet("font-size: 13px; background: transparent;")
    hl.addWidget(lbl)
    hl.addStretch()

    val = QLabel(value)
    val.setProperty("role", val_role)
    hl.addWidget(val)

    layout.addLayout(hl)


# ── main widget ───────────────────────────────────────────────────────────────

class HomeGui(QWidget):
    def __init__(self, api_key: str, config: list[dict],
                 plots: list[dict] | None = None,
                 data_root: str = "data/UG nodes",
                 bridge=None, parent=None):
        super().__init__(parent)
        self.api_key    = api_key
        self.config     = config
        self.plots      = plots or []
        self.data_root  = data_root
        self.bridge     = bridge
        self.center_lat, self.center_lon = _calculate_center(config)
        self.weather    = WeatherSummary(self.center_lat, self.center_lon, self.api_key)

        # Soil model state (live data + selected historical date)
        from soil.node_loader import load_node_data, get_available_dates
        self._load_node_data    = load_node_data
        self._get_available_dates = get_available_dates
        self.soil_records: list[dict] = []
        self.available_dates: list = []
        self.selected_date         = None  # None == "Today (live)"
        self._refresh_soil_data()

        # AI Summary helper — owns its own dialog + worker thread.
        # `open_settings_callback` is the host's settings-dialog launcher,
        # so the panel can prompt the user to configure a provider if none
        # is set yet.
        from ai.summary_panel import AISummaryPanel
        self._ai_panel = AISummaryPanel(
            config_path="config.json",
            parent=self,
            open_settings_callback=self._open_ai_settings,
        )

        # One-shot internet probe so map build + downloader decisions stay
        # consistent and we don't pay the timeout cost twice on startup.
        self._has_net_cached = _check_internet(timeout=1)

        self._build_ui()
        self._load_weather()
        self._maybe_download_offline_map()

        if bridge is not None:
            bridge.soil_data_updated.connect(self._on_soil_data_updated)

    # ── offline map auto-cache ──────────────────────────────────────────────
    def _maybe_download_offline_map(self):
        """When we have internet, top up the local tile + Leaflet cache so the
        next offline launch can render the same Leaflet view. Runs every
        online launch; the downloader skips tiles already on disk so the
        steady-state cost is near zero."""
        if not self.config:
            return
        if not getattr(self, "_has_net_cached", False):
            return
        try:
            from setup.offline_map import TileCacheDownloader
        except Exception:
            return

        self._map_dl = TileCacheDownloader(self.config, parent=self)
        self._map_dl.done.connect(self._on_offline_map_downloaded)
        self._map_dl.start()

    def _on_offline_map_downloaded(self, downloaded: int, total: int):
        # Silent: the cache populates in the background; no need to log
        # status to the console on every launch.
        pass
        # If the current view is the matplotlib fallback, it'll keep showing
        # whatever it had. The next launch (offline) will pick up the cache.

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Map column: date selector bar (top) + map widget (below) ────────
        map_col = QWidget()
        map_vl  = QVBoxLayout(map_col)
        map_vl.setContentsMargins(0, 0, 0, 0)
        map_vl.setSpacing(0)

        self._date_bar = self._build_date_bar()
        map_vl.addWidget(self._date_bar)

        self._map_holder = QWidget()
        self._map_holder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._map_holder_layout = QVBoxLayout(self._map_holder)
        self._map_holder_layout.setContentsMargins(0, 0, 0, 0)
        self._map_holder_layout.setSpacing(0)
        self._map_widget = None
        self._rebuild_map()
        map_vl.addWidget(self._map_holder, stretch=1)

        layout.addWidget(map_col, stretch=1)

        # ── Weather panel (right, fixed width — comfortable cards) ───────────
        self._weather_scroll = QScrollArea()
        self._weather_scroll.setFixedWidth(244)
        self._weather_scroll.setWidgetResizable(True)
        self._weather_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._weather_scroll.setStyleSheet("border: none; background: transparent;")

        self._weather_inner = QWidget()
        self._weather_inner.setObjectName("configPanel")
        self._weather_layout = QVBoxLayout(self._weather_inner)
        self._weather_layout.setContentsMargins(6, 6, 6, 6)
        self._weather_layout.setSpacing(5)

        self._loading_lbl = QLabel("Loading weather data…")
        self._loading_lbl.setStyleSheet("font-size: 14px; background: transparent;")
        self._loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._weather_layout.addWidget(self._loading_lbl)
        self._weather_layout.addStretch()
        self._weather_scroll.setWidget(self._weather_inner)

        layout.addWidget(self._weather_scroll)

    # ── weather loading ───────────────────────────────────────────────────────

    def _load_weather(self):
        # When offline, run the loader in quiet mode so Weather_Summary's
        # retry prints don't flood the console. The summary methods still
        # populate their dicts with NaN / 'N/A' fallbacks, so the weather
        # sections render the same metric layout — just with empty values.
        quiet = not getattr(self, "_has_net_cached", True)
        self.loader = WeatherLoader(self.weather, quiet=quiet)
        self.loader.finished.connect(self._on_weather_loaded)
        self.loader.error.connect(self._on_weather_error)
        self.loader.start()

    def _on_weather_error(self, msg: str):
        self._loading_lbl.setText(f"Weather unavailable:\n{msg}")

    def _on_weather_loaded(self, current: dict, past: dict, nxt: dict,
                           status: str):
        while self._weather_layout.count():
            item = self._weather_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Banner first — only shown for non-OK states. The cards still
        # render below with NaN/em-dash so the layout stays consistent.
        if status != "ok":
            self._weather_layout.addWidget(self._build_weather_banner(status))

        self._weather_layout.addWidget(self._build_current_section(current))
        self._weather_layout.addWidget(_divider())
        self._weather_layout.addWidget(self._build_past_section(past))
        self._weather_layout.addWidget(_divider())
        self._weather_layout.addWidget(self._build_forecast_section(nxt))
        self._weather_layout.addWidget(_divider())
        self._weather_layout.addWidget(self._build_export_section())
        self._weather_layout.addStretch()

    def _build_weather_banner(self, status: str) -> QWidget:
        """Compact banner at the top of the weather column explaining why
        the cards below are empty. Theme-agnostic colors (light amber/red)
        that read on both backgrounds."""
        if status == "no_key":
            text   = "⚠  OpenWeather API key not set."
            tone   = "warn"
            action = ("Set up key", self._open_weather_settings)
        elif status == "no_internet":
            text   = "⚠  No internet — weather unavailable."
            tone   = "warn"
            action = ("Retry", self._retry_weather)
        else:  # "api_error"
            text   = "⚠  Weather fetch failed — check key or try later."
            tone   = "err"
            action = ("Retry", self._retry_weather)

        if tone == "err":
            bg, fg, bd = "#fee2e2", "#991b1b", "#fca5a5"
        else:
            bg, fg, bd = "#fef3c7", "#92400e", "#fcd34d"

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {bd};"
            f" border-radius: 5px; padding: 6px 8px; }}"
        )
        row = QVBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {fg}; font-size: 11px; font-weight: 700;"
            " background: transparent;"
        )
        lbl.setWordWrap(True)
        row.addWidget(lbl)

        btn_label, btn_callback = action
        btn = QPushButton(btn_label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: white; color: {fg};"
            f" border: 1px solid {bd}; border-radius: 4px;"
            f" padding: 3px 10px; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {bg}; }}"
        )
        btn.clicked.connect(btn_callback)
        btn.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)

        return frame

    def _open_weather_settings(self):
        """Opens a tiny dialog with just the OpenWeather key field. After
        saving, replaces the WeatherSummary's key (no need to restart the
        app) and re-runs the loader so the banner clears."""
        from PyQt6.QtWidgets import QInputDialog, QLineEdit
        from setup.keys import set_weather_key, get_weather_key
        existing = get_weather_key() or ""
        key, ok = QInputDialog.getText(
            self, "OpenWeather API key",
            "Enter your OpenWeather API key.\n"
            "Get one at openweathermap.org/api_keys (free tier available).",
            QLineEdit.EchoMode.Password,
            existing,
        )
        if not ok or not key.strip():
            return
        saved, msg = set_weather_key(key.strip())
        if not saved:
            QMessageBox.critical(self, "Save failed", msg)
            return
        # Patch the live WeatherSummary instance + re-fetch.
        self.weather.api_key = key.strip()
        self._retry_weather()

    def _retry_weather(self):
        # Re-run the loader; _on_weather_loaded will rebuild the column.
        self._load_weather()

    # ── section builders ──────────────────────────────────────────────────────

    def _build_current_section(self, s: dict) -> QWidget:
        card, vl = _wx_card()
        vl.addWidget(_wx_section_title("Current Conditions"))

        def _fmt_v(v, fmt=".1f", unit="") -> str:
            return f"{v:{fmt}}{unit}" if isinstance(v, (int, float)) else "—"

        # Top row: icon box | big temperature | description column
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setContentsMargins(0, 0, 0, 0)

        icon_box = QFrame()
        icon_box.setFixedSize(38, 38)
        icon_box.setStyleSheet("QFrame { background: #dbeafe; border-radius: 8px; }")
        box_lo = QHBoxLayout(icon_box)
        box_lo.setContentsMargins(2, 2, 2, 2)
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        box_lo.addWidget(icon_lbl)

        icon_url = s.get("icon_url", "")
        if icon_url:
            try:
                resp = requests.get(icon_url, timeout=4)
                if resp.status_code == 200:
                    px = QPixmap()
                    px.loadFromData(resp.content)
                    icon_lbl.setPixmap(
                        px.scaled(32, 32,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                    )
            except Exception:
                pass

        top_row.addWidget(icon_box)

        big_temp = QLabel(_fmt_v(s.get("temp"), ".1f", "°"))
        big_temp.setStyleSheet(
            "font-family: Consolas; font-size: 19px; font-weight: 800;"
            " color: #1d4ed8; background: transparent;"
        )
        big_temp.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(big_temp)

        desc_col = QVBoxLayout()
        desc_col.setContentsMargins(0, 0, 0, 0)
        desc_col.setSpacing(2)
        desc = QLabel(str(s.get("weather_description", "—")).capitalize())
        desc.setStyleSheet(
            "font-size: 13px; font-weight: 700; background: transparent;"
        )
        desc.setWordWrap(True)
        desc_col.addWidget(desc)
        loc = QLabel(f"{self.center_lat:.3f}°, {self.center_lon:.3f}°")
        loc.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #6b7280; background: transparent;"
        )
        desc_col.addWidget(loc)
        top_row.addLayout(desc_col, stretch=1)
        vl.addLayout(top_row)

        _icon_metric_row(vl, "💧", "wx-icon-blue", "Humidity",
                         _fmt_v(s.get("humidity"), ".1f", "%"))
        _icon_metric_row(vl, "💨", "wx-icon-gray", "Wind",
                         _fmt_v(s.get("wind_speed"), ".2f", " m/s"))
        vis = s.get("visibility")
        if vis is not None:
            _icon_metric_row(vl, "👁", "wx-icon-gray", "Visibility",
                             f"{vis:.1f} km" if isinstance(vis, (int, float)) else f"{vis} km")

        return card

    def _build_hilo_section(self, title: str, s: dict) -> QWidget:
        """Shared layout for Past 7 Days and 7-Day Forecast cards."""
        card, vl = _wx_card()
        vl.addWidget(_wx_section_title(title))

        def _fmt(v, suffix="") -> str:
            return f"{v:.1f}{suffix}" if isinstance(v, (int, float)) else "—"

        vl.addWidget(_wx_group_header("Temperature", "°C"))
        vl.addLayout(_hilo_row(
            _fmt(s.get("highest_temp"), "°"),
            _fmt(s.get("avg_temp"),     "°"),
            _fmt(s.get("lowest_temp"),  "°"),
        ))

        vl.addSpacing(2)
        vl.addWidget(_wx_group_header("Humidity", "%"))
        vl.addLayout(_hilo_row(
            _fmt(s.get("highest_humidity"), "%"),
            _fmt(s.get("avg_humidity"),     "%"),
            _fmt(s.get("lowest_humidity"),  "%"),
            high_role="hilo-high-blue",
        ))

        vl.addSpacing(1)
        vl.addWidget(_metric_box("Average wind",
                                 _fmt(s.get("avg_wind_speed"), " m/s"),
                                 icon="💨"))
        vl.addWidget(_metric_box("Total precipitation",
                                 _fmt(s.get("total_rainfall"), " mm"),
                                 icon="🌧"))

        return card

    def _build_past_section(self, s: dict) -> QWidget:
        return self._build_hilo_section("Past 7 Days", s)

    def _build_forecast_section(self, s: dict) -> QWidget:
        return self._build_hilo_section("7-Day Forecast", s)

    def _build_export_section(self) -> QWidget:
        card, vl = _wx_card()
        vl.addWidget(_wx_section_title("Export"))

        date_css = (
            "QDateEdit {"
            " background: #ffffff;"
            " color: #111827;"
            " border: 1.5px solid #d1d5db;"
            " border-radius: 5px;"
            " padding: 3px 6px;"
            " font-size: 12px;"
            " }"
            "QDateEdit:focus { border-color: #1d4ed8; }"
        )

        start_lbl = QLabel("Start date")
        start_lbl.setStyleSheet("font-size: 12px; background: transparent;")
        vl.addWidget(start_lbl)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setCalendarWidget(_build_calendar(dark=False))
        self.start_date.setDate(QDate.currentDate().addDays(-30))
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setFixedHeight(27)
        self.start_date.setStyleSheet(date_css)
        vl.addWidget(self.start_date)

        end_lbl = QLabel("End date")
        end_lbl.setStyleSheet("font-size: 12px; background: transparent;")
        vl.addWidget(end_lbl)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setCalendarWidget(_build_calendar(dark=False))
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setFixedHeight(27)
        self.end_date.setStyleSheet(date_css)
        vl.addWidget(self.end_date)

        btn = QPushButton("⬇  Save for period")
        btn.setFixedHeight(29)
        btn.setStyleSheet(
            "QPushButton {"
            " background: #f9fafb;"
            " color: #111827;"
            " border: 1.5px solid #9ca3af;"
            " border-radius: 5px;"
            " font-size: 12px;"
            " font-weight: 700;"
            " padding: 4px 9px;"
            " }"
            "QPushButton:hover { background: #e5e7eb; }"
            "QPushButton:pressed { background: #d1d5db; }"
        )
        btn.clicked.connect(self._export_historical)
        vl.addWidget(btn)

        # ── Divider between Export and AI Assistant ───────────────────
        vl.addSpacing(8)
        ai_divider = QFrame()
        ai_divider.setFrameShape(QFrame.Shape.HLine)
        ai_divider.setStyleSheet(
            "color: #d1d5db; background: #d1d5db; max-height: 1px;"
        )
        vl.addWidget(ai_divider)
        vl.addSpacing(6)

        # ── AI Assistant section ──────────────────────────────────────
        vl.addWidget(_wx_section_title("AI Assistant"))

        # Action row — primary button + gear
        ai_row = QHBoxLayout()
        ai_row.setSpacing(6)

        ai_btn = QPushButton("✦  Generate AI Summary")
        ai_btn.setToolTip(
            "Generate an AI agronomic report from the current sensor data"
        )
        ai_btn.setFixedHeight(32)
        ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_btn.setStyleSheet(
            "QPushButton {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "   stop:0 #6366f1, stop:1 #4f46e5);"      # indigo gradient — stands out
            " color: white;"
            " border: 1px solid #4338ca;"
            " border-radius: 6px;"
            " font-size: 12px;"
            " font-weight: 700;"
            " padding: 4px 9px;"
            " }"
            "QPushButton:hover {"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            "   stop:0 #4f46e5, stop:1 #4338ca);"
            " }"
            "QPushButton:pressed {"
            " background: #3730a3;"
            " }"
        )
        ai_btn.clicked.connect(self._open_ai_summary)
        ai_row.addWidget(ai_btn, 1)

        ai_settings_btn = QPushButton("⚙")
        ai_settings_btn.setToolTip("Configure AI provider and API key")
        ai_settings_btn.setFixedSize(32, 32)
        ai_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Note on the gear glyph: Segoe UI's '⚙' has ascender/descender
        # metrics that overflow a small fixed-size button at 15px. Pin the
        # symbol-friendly font family + smaller size so it sits centered.
        ai_settings_btn.setStyleSheet(
            "QPushButton {"
            " background: #f9fafb;"
            " color: #4338ca;"
            " border: 1px solid #c7d2fe;"
            " border-radius: 6px;"
            " font-family: 'Segoe UI Symbol', 'Apple Symbols', 'Noto Sans Symbols2', sans-serif;"
            " font-size: 13px;"
            " font-weight: 700;"
            " padding: 0;"
            " }"
            "QPushButton:hover { background: #eef2ff; border-color: #818cf8; }"
            "QPushButton:pressed { background: #c7d2fe; }"
        )
        ai_settings_btn.clicked.connect(self._open_ai_settings)
        ai_row.addWidget(ai_settings_btn)

        vl.addLayout(ai_row)

        return card

    # ── export logic ──────────────────────────────────────────────────────────

    def _export_historical(self):
        try:
            from meteostat import Point, Daily
        except ImportError:
            QMessageBox.critical(self, "Missing Package",
                                 "Install meteostat:\n  pip install meteostat")
            return

        sd = self.start_date.date().toPyDate()
        ed = self.end_date.date().toPyDate()

        if sd > ed:
            QMessageBox.critical(self, "Date Error", "Start date must be before end date.")
            return
        if ed > date.today():
            QMessageBox.critical(self, "Date Error", "End date cannot be in the future.")
            return

        folder = QFileDialog.getExistingDirectory(self, "Select save folder")
        if not folder:
            return

        try:
            loc  = Point(self.center_lat, self.center_lon)
            data = Daily(loc,
                         start=datetime.combine(sd, datetime.min.time()),
                         end=datetime.combine(ed, datetime.min.time())).fetch()
            data.reset_index(inplace=True)
            path = f"{folder}/{sd}_to_{ed}.csv"
            data.to_csv(path, index=False)
            QMessageBox.information(self, "Saved", f"Data saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── AI Summary ───────────────────────────────────────────────────────────
    def _open_ai_summary(self):
        """Kick off a one-shot AI call against the currently-viewed soil
        records via whichever provider the user picked in Settings.

        Also includes a weather snapshot (current, past 7 days, forecast)
        so the AI's irrigation/management recommendations can factor in
        rainfall and temperature."""
        try:
            records = self._records_for_view()
        except Exception:
            records = list(self.soil_records or [])

        # Snapshot whatever WeatherLoader has populated by now. Any of
        # these can be None (still loading or fetch failed) — _fmt_weather
        # handles that case.
        weather = {
            "current":   getattr(self.weather, "current_weather_summary", None),
            "past_week": getattr(self.weather, "past_week_summary",       None),
            "next_week": getattr(self.weather, "next_week_summary",       None),
        }
        self._ai_panel.run(records, weather=weather)

    def _open_ai_settings(self):
        """Open the AI provider/key settings dialog."""
        from ai.settings_dialog import AISettingsDialog
        dlg = AISettingsDialog(self)
        dlg.exec()

    # ── theme ────────────────────────────────────────────────────────────────
    def set_dark_theme(self, dark: bool):
        """Re-apply theme-aware calendar palettes after a global stylesheet swap."""
        for de in (getattr(self, "start_date", None), getattr(self, "end_date", None)):
            if de is not None:
                cal = de.calendarWidget()
                if cal is not None:
                    _apply_calendar_palette(cal, dark=dark)

    # ── soil-model integration ───────────────────────────────────────────────
    def _refresh_soil_data(self) -> None:
        """Pull fresh soil records + available dates from the model stub."""
        try:
            self.soil_records    = self._load_node_data(self.data_root) or []
            self.available_dates = self._get_available_dates(self.data_root) or []
        except Exception:
            self.soil_records, self.available_dates = [], []

    def _records_for_view(self) -> list[dict]:
        """
        Resolve the per-node soil record to show on the map for the currently
        selected date. Each returned record gets a '_nearest' flag set when
        there's no exact match for the selected date and we fell back to the
        most recent file.

        selected_date is None → show live (today) data, no nearest fallback.
        """
        sel = self.selected_date

        # Index records by node, keeping the newest-on-or-before sel_date.
        by_node: dict[str, list[dict]] = {}
        for r in self.soil_records:
            by_node.setdefault(r["node_id"], []).append(r)
        # Sort each per-node list by date descending
        for lst in by_node.values():
            lst.sort(key=lambda r: r["date"], reverse=True)

        out: list[dict] = []
        for nid, recs in by_node.items():
            if sel is None:
                pick = recs[0]  # most recent
                pick = dict(pick)
                pick["_nearest"] = False
                out.append(pick)
                continue
            exact = next((r for r in recs if r["date"] == sel), None)
            if exact is not None:
                pick = dict(exact)
                pick["_nearest"] = False
            else:
                older = [r for r in recs if r["date"] <= sel]
                pick_src = older[0] if older else recs[0]
                pick = dict(pick_src)
                pick["is_live"] = False     # date doesn't match selection
                pick["_nearest"] = True
            out.append(pick)
        return out

    def _rebuild_map(self) -> None:
        """Regenerate the map widget with current soil data and reload."""
        # Remove the previous map widget
        if self._map_widget is not None:
            self._map_holder_layout.removeWidget(self._map_widget)
            self._map_widget.deleteLater()
            self._map_widget = None

        marker_soil = self._records_for_view()
        new_w = _build_map_widget(
            self.config, self.center_lat, self.center_lon,
            self.plots, marker_soil=marker_soil,
            has_net=getattr(self, "_has_net_cached", None),
        )
        new_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._map_holder_layout.addWidget(new_w)
        self._map_widget = new_w

    def _build_date_bar(self) -> QWidget:
        """Centered bar: 'View date' dropdown + LIVE/HIST badge + dates-count.

        Uses `palette(...)` selectors so the bar adapts to light + dark mode
        without needing a manual theme callback. The colored badges keep their
        own (intentionally fixed) green/amber palettes.
        """
        wrap = QWidget()
        wrap.setObjectName("dateBar")
        wrap.setStyleSheet(
            # Soft surface tint so the bar visually belongs to the map area
            "QWidget#dateBar {"
            "   background: palette(alternate-base);"
            "   border-bottom: 1px solid palette(mid);"
            " }"
            " QLabel[role='date-bar-label'] {"
            "   color: palette(window-text); font-size: 12px; font-weight: 600;"
            "   background: transparent;"
            " }"
            " QLabel[role='date-bar-foot'] {"
            "   color: palette(window-text); font-size: 12px;"
            "   font-weight: 500; background: transparent;"
            " }"
            " QComboBox[role='date-combo'] {"
            "   background: palette(base); color: palette(text);"
            "   border: 1px solid palette(mid); border-radius: 6px;"
            "   padding: 3px 10px; font-size: 12px; font-weight: 600;"
            "   min-width: 170px;"
            " }"
            " QComboBox[role='date-combo']:focus { border-color: #1d4ed8; }"
            " QComboBox[role='date-combo']::drop-down { border: none; width: 18px; }"
            " QComboBox[role='date-combo'] QAbstractItemView {"
            "   background: palette(base); color: palette(text);"
            "   border: 1px solid palette(mid);"
            "   selection-background-color: #dbeafe; selection-color: #1e3a8a;"
            " }"
            " QLabel[role='live-badge'] {"
            "   background: #dcfce7; color: #14532d;"
            "   border: 1px solid #15803d; border-radius: 10px;"
            "   padding: 2px 9px; font-size: 11px; font-weight: 700;"
            " }"
            " QLabel[role='hist-badge'] {"
            "   background: #fef3c7; color: #92400e;"
            "   border: 1px solid #d97706; border-radius: 10px;"
            "   padding: 2px 9px; font-size: 11px; font-weight: 700;"
            " }"
            # Soft separator dot between the badge and the dates-count
            " QLabel[role='date-bar-sep'] {"
            "   color: palette(mid); font-size: 12px;"
            "   background: transparent;"
            " }"
        )

        outer = QHBoxLayout(wrap)
        outer.setContentsMargins(10, 7, 10, 7)
        outer.setSpacing(0)

        # Push the cluster toward center: stretch on both sides
        outer.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("View date:")
        lbl.setProperty("role", "date-bar-label")
        row.addWidget(lbl)

        self._date_combo = QComboBox()
        self._date_combo.setProperty("role", "date-combo")
        self._date_combo.setCursor(Qt.CursorShape.PointingHandCursor)

        # Item 0 = "auto / latest". userData = None means "use the most-recent
        # file per node". The label is dynamic so the dropdown reflects what
        # is actually being shown: "Today (live)" when newest data IS today,
        # otherwise "Latest: <date>" so the user can see at a glance which day
        # the auto-mode is currently displaying.
        first_label, first_is_today = self._auto_item_label()
        self._date_combo.addItem(first_label, userData=None)

        non_today = [d for d in self.available_dates if d != date.today()]
        for d in non_today:
            self._date_combo.addItem(d.strftime("%b %d, %Y"), userData=d)

        # Restore previous selection if any
        target_idx = 0
        if self.selected_date is not None:
            for i in range(1, self._date_combo.count()):
                if self._date_combo.itemData(i) == self.selected_date:
                    target_idx = i
                    break
        self._date_combo.setCurrentIndex(target_idx)
        self._date_combo.currentIndexChanged.connect(self._on_date_combo_changed)
        row.addWidget(self._date_combo)

        # Mode badge — green "LIVE" or "LATEST" for the auto item, amber
        # "HISTORICAL" when the user has picked a specific past date.
        if self.selected_date is None:
            badge_text = "LIVE" if first_is_today else "LATEST"
            badge_role = "live-badge"
        else:
            badge_text = "HISTORICAL"
            badge_role = "hist-badge"
        self._date_mode_badge = QLabel(badge_text)
        self._date_mode_badge.setProperty("role", badge_role)
        row.addWidget(self._date_mode_badge)

        sep = QLabel("•")
        sep.setProperty("role", "date-bar-sep")
        row.addWidget(sep)

        n_dates = len(self.available_dates)
        self._date_footer = QLabel(f"{n_dates} collection dates available")
        self._date_footer.setProperty("role", "date-bar-foot")
        row.addWidget(self._date_footer)

        outer.addLayout(row)
        outer.addStretch(1)

        return wrap

    def _auto_item_label(self) -> tuple[str, bool]:
        """
        Label for the dropdown's auto/latest item (userData=None). Returns
        (label, is_today). When newest data is today → 'Today (live)'.
        When newest data is older → 'Latest: <date>' so the dropdown
        accurately reflects what the auto-mode is currently displaying.
        """
        if self.available_dates:
            newest = self.available_dates[0]   # list is sorted newest-first
            if newest == date.today():
                return ("● Today (live)", True)
            return (f"● Latest: {newest.strftime('%b %d, %Y')}", False)
        return ("● Today (live)", True)

    def _on_date_combo_changed(self, idx: int) -> None:
        d = self._date_combo.itemData(idx)
        # Update badge appearance for the new mode
        if d is None:
            _, is_today = self._auto_item_label()
            self._date_mode_badge.setText("LIVE" if is_today else "LATEST")
            self._date_mode_badge.setProperty("role", "live-badge")
        else:
            self._date_mode_badge.setText("HISTORICAL")
            self._date_mode_badge.setProperty("role", "hist-badge")
        # Re-polish so the QSS attribute selector picks up the new role
        self._date_mode_badge.style().unpolish(self._date_mode_badge)
        self._date_mode_badge.style().polish(self._date_mode_badge)
        self._on_date_clicked(d)

    def _on_date_clicked(self, d) -> None:
        self.selected_date = d
        self._rebuild_map()

    def _on_soil_data_updated(self) -> None:
        """Re-load soil records and rebuild the date bar + map."""
        self._refresh_soil_data()
        # Rebuild the date bar so newly-available dates appear
        new_bar = self._build_date_bar()
        old_bar = self._date_bar
        parent_layout = old_bar.parentWidget().layout() if old_bar.parentWidget() else None
        if parent_layout is not None:
            parent_layout.replaceWidget(old_bar, new_bar)
            old_bar.deleteLater()
            self._date_bar = new_bar
        self._rebuild_map()
