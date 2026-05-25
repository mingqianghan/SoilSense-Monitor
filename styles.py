"""
Light and dark QSS stylesheets for SoilSense Monitor.
Apply with:  QApplication.instance().setStyleSheet(LIGHT)  or  DARK
"""

_BASE = """
QWidget {{
    background: {bg};
    color: {fg};
    font-family: "Segoe UI";
    font-size: 14px;
}}

/* ── Transparent inline elements (must come after QWidget rule) ─ */
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QWidget[role="transparent"] {{ background: transparent; }}

/* ── Structural containers ───────────────────────────────────── */
QWidget#sidebar    {{ background: {sf}; }}
QWidget#titleBar   {{ background: {sf}; }}
QFrame#titleBarSep {{ background: {bd}; max-height: 1px; }}
QFrame#sidebarSep  {{ background: {bd}; max-width:  1px; }}
QFrame#sidebarDiv  {{ background: {bd}; max-height: 1px; }}

/* ── Sidebar time card ──────────────────────────────────────── */
QFrame[role="time-card"] {{
    background: {sf2};
    border: 1px solid {bd};
    border-radius: 8px;
}}
QFrame[role="time-card"] > QLabel {{ background: transparent; }}
QLabel[role="clock-time"] {{
    color: {nav_on_fg};
    font-family: 'Consolas';
    font-size: 15px;
    font-weight: 800;
}}
QLabel[role="clock-date"] {{
    color: {fg};
    font-family: 'Segoe UI';
    font-size: 11px;
    font-weight: 600;
}}
QLabel[role="clock-year"] {{
    color: {muted};
    font-family: 'Segoe UI';
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QWidget#configPanel  {{ background: {sf}; }}
QWidget#logPanelBody {{ background: {sf2}; }}
QWidget#logHeader    {{ background: {sf}; }}
QWidget#logFooter    {{ background: {sf}; }}
QWidget#chartToolbar {{ background: {sf}; }}
QFrame#sectionDivider {{ background: {bd}; max-height: 1px; }}
/* Tooltips are rendered by _ThemedToolTipFilter (AppRoot.py), not QToolTip —
   styling QToolTip via QSS or palette is unreliable on Windows. */

/* ── Section card (one tinted variant per group) ──────────────── */
QFrame[role="section-card-com"] {{
    background: {card_com_bg};
    border: 1.5px solid {card_com_bd};
    border-radius: 6px;
}}
QFrame[role="section-card-cfg"] {{
    background: {card_cfg_bg};
    border: 1.5px solid {card_cfg_bd};
    border-radius: 6px;
}}
QFrame[role="section-card-trk"] {{
    background: {card_trk_bg};
    border: 1.5px solid {card_trk_bd};
    border-radius: 6px;
}}
QFrame[role="section-card-com"] > QWidget#sectionCardBody {{ background: {card_com_bg}; }}
QFrame[role="section-card-cfg"] > QWidget#sectionCardBody {{ background: {card_cfg_bg}; }}
QFrame[role="section-card-trk"] > QWidget#sectionCardBody {{ background: {card_trk_bg}; }}

/* Colored section headers (one tint per group) */
QLabel[role="section-head-com"] {{
    background: {head_com_bg};
    color: {head_com_fg};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 4px 8px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}}
QLabel[role="section-head-cfg"] {{
    background: {head_cfg_bg};
    color: {head_cfg_fg};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 4px 8px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}}
QLabel[role="section-head-trk"] {{
    background: {head_trk_bg};
    color: {head_trk_fg};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 4px 8px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}}

/* Segmented selector (pill-shaped, clear active vs muted-off state) */
QPushButton[role="segment"] {{
    background: {seg_off_bg};
    color: {seg_off_fg};
    border: 1.5px solid {seg_off_bd};
    border-radius: 14px;
    font-size: 12px;
    font-weight: 700;
    padding: 5px 8px;
    text-align: center;
}}
QPushButton[role="segment"]:checked {{
    background: {pri_bg};
    color: {pri_fg};
    border-color: {pri_bd};
}}
QPushButton[role="segment"]:hover:!checked {{
    background: {seg_off_hov};
    color: {fg};
}}
QPushButton[role="segment"]:disabled {{
    background: {seg_off_bg};
    color: {muted};
    border-color: {seg_off_bd};
}}
QPushButton[role="segment"]:checked:disabled {{
    background: {pri_dis_bg};
    color: {pri_dis_fg};
    border-color: {pri_dis_bd};
}}

/* ── Sidebar nav ─────────────────────────────────────────────── */
QPushButton[role="nav"] {{
    background: {nav_bg};
    color: {nav_fg};
    border: 2px solid {nav_bd};
    border-radius: 7px;
    font-size: 13px;
    font-weight: 700;
    padding: 9px 4px;
    text-align: center;
}}
QPushButton[role="nav"]:checked {{
    background: {nav_on_bg};
    color: {nav_on_fg};
    border-color: {nav_on_bd};
}}
QPushButton[role="nav"]:hover:!checked {{ background: {sf2}; }}

QPushButton[role="nav-exit"] {{
    background: {exit_bg};
    color: {exit_fg};
    border: 2px solid {exit_bd};
    border-radius: 7px;
    font-size: 13px;
    font-weight: 700;
    padding: 9px 4px;
    text-align: center;
}}
QPushButton[role="nav-exit"]:hover {{ background: {exit_hov}; }}

/* ── Theme toggle ────────────────────────────────────────────── */
QPushButton[role="theme-toggle"] {{
    background: {sf};
    color: {fg};
    border: 1.5px solid {bd2};
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    padding: 4px 16px 6px 16px;
}}
QPushButton[role="theme-toggle"]:hover {{ background: {sf2}; }}

/* ── Generic button ──────────────────────────────────────────── */
QPushButton {{
    background: {btn_bg};
    color: {btn_fg};
    border: 1.5px solid {btn_bd};
    border-radius: 5px;
    font-size: 14px;
    font-weight: 700;
    padding: 5px 10px;
}}
QPushButton:hover    {{ background: {btn_hov}; }}
QPushButton:disabled {{ background: {btn_dis_bg}; color: {btn_dis_fg}; border-color: {btn_dis_bd}; }}

/* ── Plot navigation buttons (Home / Pan / Zoom) ─────────────── */
QPushButton[role="navtool"] {{
    background: {btn_bg};
    color: {btn_fg};
    border: 1.5px solid {btn_bd};
    border-radius: 5px;
    font-size: 13px;
    font-weight: 700;
    padding: 4px 10px;
}}
QPushButton[role="navtool"]:hover    {{ background: {btn_hov}; }}
QPushButton[role="navtool"]:checked  {{
    background: {pri_bg};
    color: {pri_fg};
    border-color: {pri_bd};
}}
QPushButton[role="navtool"]:disabled {{
    background: {btn_dis_bg}; color: {btn_dis_fg}; border-color: {btn_dis_bd};
}}

/* ── Semantic button roles ───────────────────────────────────── */
QPushButton[role="primary"] {{
    background: {pri_bg};
    color: {pri_fg};
    border: 1.5px solid {pri_bd};
}}
QPushButton[role="primary"]:hover {{ background: {pri_hov}; }}
QPushButton[role="primary"]:disabled {{ background: {pri_dis_bg}; color: {pri_dis_fg}; border-color: {pri_dis_bd}; }}

QPushButton[role="success"] {{
    background: {suc_bg};
    color: {suc_fg};
    border: 1.5px solid {suc_bd};
}}
QPushButton[role="success"]:hover {{ background: {suc_hov}; }}

QPushButton[role="danger"] {{
    background: {dan_bg};
    color: {dan_fg};
    border: 1.5px solid {dan_bd};
}}
QPushButton[role="danger"]:hover {{ background: {dan_hov}; }}

/* ── Toggle pair ─────────────────────────────────────────────── */
QPushButton[role="toggle-left"] {{
    background: {bg};
    color: {fg};
    border: 1.5px solid {bd2};
    border-radius: 5px 0px 0px 5px;
    font-size: 13px;
    font-weight: 700;
    padding: 5px 0px;
    text-align: center;
}}
QPushButton[role="toggle-left"]:checked {{
    background: #1d4ed8;
    color: #ffffff;
    border-color: #1d4ed8;
}}
QPushButton[role="toggle-left"]:hover:!checked {{ background: {sf2}; }}

QPushButton[role="toggle-right"] {{
    background: {bg};
    color: {fg};
    border: 1.5px solid {bd2};
    border-left: none;
    border-radius: 0px 5px 5px 0px;
    font-size: 13px;
    font-weight: 700;
    padding: 5px 0px;
    text-align: center;
}}
QPushButton[role="toggle-right"]:checked {{
    background: #1d4ed8;
    color: #ffffff;
    border-color: #1d4ed8;
}}
QPushButton[role="toggle-right"]:hover:!checked {{ background: {sf2}; }}

/* Standalone bordered toggle (each button keeps its own full border) */
QPushButton[role="toggle-bordered"] {{
    background: {bg};
    color: {fg};
    border: 1.5px solid {bd2};
    border-radius: 5px;
    font-size: 13px;
    font-weight: 700;
    padding: 4px 8px;
    text-align: center;
}}
QPushButton[role="toggle-bordered"]:checked {{
    background: #1d4ed8;
    color: #ffffff;
    border-color: #1d4ed8;
}}
QPushButton[role="toggle-bordered"]:hover:!checked {{ background: {sf2}; }}

/* ── Inputs ──────────────────────────────────────────────────── */
QComboBox, QDateEdit {{
    background: {inp_bg};
    color: {fg};
    border: 1.5px solid {bd};
    border-radius: 5px;
    font-size: 14px;
    padding: 4px 7px;
    selection-background-color: #1d4ed8;
}}
QComboBox:focus, QDateEdit:focus {{ border-color: #1d4ed8; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{ width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background: {inp_bg};
    color: {fg};
    border: 1px solid {bd};
    selection-background-color: {nav_on_bg};
    selection-color: {nav_on_fg};
}}

/* ── QDateEdit calendar popup (chrome only — date cells are painted from
   the palette, set programmatically in HomeGui._apply_calendar_palette) ── */
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: {sf};
    border-bottom: 1px solid {bd};
}}
QCalendarWidget QToolButton {{
    background: transparent;
    color: {fg};
    border: none;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 600;
}}
QCalendarWidget QToolButton:hover {{ background: {sf2}; }}
QCalendarWidget QToolButton::menu-indicator {{ image: none; }}
QCalendarWidget QSpinBox {{
    background: {inp_bg};
    color: {fg};
    border: 1px solid {bd};
    selection-background-color: {nav_on_bg};
    selection-color: {nav_on_fg};
}}

/* ── Labels ──────────────────────────────────────────────────── */
QLabel[role="section-title"] {{
    font-size: 11px;
    font-weight: 700;
    color: {sec_title};
    letter-spacing: 0.5px;
}}
QLabel[role="data-value"] {{
    font-family: "Consolas";
    font-size: 13px;
    font-weight: 700;
    color: {fg};
}}
QLabel[role="data-value-blue"] {{
    font-family: "Consolas";
    font-size: 13px;
    font-weight: 700;
    color: {val_blue};
}}
QLabel[role="wx-value"] {{
    font-family: "Consolas";
    font-size: 13px;
    font-weight: 700;
    color: {fg};
}}
QLabel[role="wx-value-blue"] {{
    font-family: "Consolas";
    font-size: 13px;
    font-weight: 700;
    color: {val_blue};
}}
QLabel[role="status-ok"]   {{ color: {ok_color};   font-weight: 700; font-size: 13px; }}
QLabel[role="status-warn"] {{ color: {warn_color}; font-weight: 700; font-size: 13px; }}
QLabel[role="status-err"]  {{ color: {err_color};  font-weight: 700; font-size: 13px; }}


/* ── Pill badge (sync status / freq load) ───────────────────── */
QFrame[role="pill-warn"] {{ background: #fef3c7; border-radius: 10px; }}
QFrame[role="pill-warn"] QLabel {{ color: #92400e; background: transparent; }}
QFrame[role="pill-ok"]   {{ background: #dcfce7; border-radius: 10px; }}
QFrame[role="pill-ok"]   QLabel {{ color: #14532d; background: transparent; }}
QFrame[role="pill-err"]  {{ background: #fee2e2; border-radius: 10px; }}
QFrame[role="pill-err"]  QLabel {{ color: #991b1b; background: transparent; }}

/* ── Weather panel cards and metric boxes ───────────────────── */
QFrame[role="wx-card"] {{
    border: 1.5px solid {bd};
    border-radius: 8px;
    background: {bg};
}}
QFrame[role="wx-card"] > QLabel {{ background: transparent; }}
QFrame[role="wx-metric"] {{
    background: transparent;
}}
QFrame[role="wx-metric"] QLabel {{ background: transparent; }}

/* ── Pipeline rows ───────────────────────────────────────────── */
QFrame[role="pipeline-row"] {{ background: {sf2}; border-radius: 5px; }}
QFrame[role="pipeline-row"] QLabel {{ background: transparent; }}
QFrame#pipelineStem {{ background: {bd2}; border: none; }}

/* ── Serial log ──────────────────────────────────────────────── */
QPlainTextEdit {{
    background: {log_bg};
    color: {log_fg};
    border: none;
    font-family: "Consolas";
    font-size: 8pt;
}}

/* ── Scroll bars ─────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {sf};
    width: 6px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {bd};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {sf};
    height: 6px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {bd};
    border-radius: 3px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Status bar ──────────────────────────────────────────────── */
QStatusBar {{
    background: {sf};
    border-top: 1px solid {bd};
    font-size: 13px;
    font-weight: 600;
    color: {sec_title};
}}
QStatusBar::item {{ border: none; }}

/* ── Group box (fallback for any remaining) ──────────────────── */
QGroupBox {{
    border: 1px solid {bd};
    border-radius: 5px;
    margin-top: 16px;
    font-size: 13px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

/* ── Checkbox / Radio ────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    font-size: 14px;
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
}}

/* ── Splitter ────────────────────────────────────────────────── */
QSplitter::handle {{ background: {bd}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical   {{ height: 1px; }}
"""

_LIGHT_VARS = dict(
    bg="#ffffff",       sf="#f3f4f6",       sf2="#e5e7eb",
    fg="#111827",       muted="#9ca3af",    sec_title="#374151",
    bd="#d1d5db",       bd2="#9ca3af",
    inp_bg="#ffffff",
    # nav
    nav_bg="#ffffff",   nav_fg="#111827",   nav_bd="#9ca3af",
    nav_on_bg="#dbeafe",nav_on_fg="#1e3a8a",nav_on_bd="#1d4ed8",
    # exit
    exit_bg="#fee2e2",  exit_fg="#991b1b",  exit_bd="#fca5a5",
    exit_hov="#fecaca",
    # semantic buttons
    pri_bg="#2563eb",       pri_fg="#ffffff",       pri_bd="#1d4ed8",       pri_hov="#1d4ed8",
    pri_dis_bg="#bfdbfe",   pri_dis_fg="#60a5fa",   pri_dis_bd="#93c5fd",
    suc_bg="#dcfce7",       suc_fg="#14532d",       suc_bd="#15803d",       suc_hov="#bbf7d0",
    dan_bg="#fee2e2",       dan_fg="#991b1b",       dan_bd="#fca5a5",       dan_hov="#fecaca",
    # default button (light-blue tint, visible on tinted card bodies)
    btn_bg="#dbeafe",       btn_fg="#1e3a8a",       btn_bd="#60a5fa",       btn_hov="#bfdbfe",
    btn_dis_bg="#f1f5f9",   btn_dis_fg="#94a3b8",   btn_dis_bd="#cbd5e1",
    # segment off-state (clearly visible, reads as inactive)
    seg_off_bg="#ffffff",   seg_off_fg="#64748b",   seg_off_bd="#94a3b8",   seg_off_hov="#f1f5f9",
    # data
    val_blue="#1d4ed8",
    ok_color="#15803d", warn_color="#92400e", err_color="#991b1b",
    # hi/avg/low
    hi_bg="#fef3c7",    avg_bg="#e5e7eb",   lo_bg="#fee2e2",
    # section header tints (com=rose, cfg=violet, trk=teal)
    head_com_bg="#fda4af", head_com_fg="#881337",
    head_cfg_bg="#c4b5fd", head_cfg_fg="#4c1d95",
    head_trk_bg="#5eead4", head_trk_fg="#134e4a",
    # section card body + border (very light wash matching the header hue)
    card_com_bg="#fff1f2", card_com_bd="#fda4af",
    card_cfg_bg="#f5f3ff", card_cfg_bd="#c4b5fd",
    card_trk_bg="#f0fdfa", card_trk_bd="#5eead4",
    # log (dark text on near-white for readability)
    log_bg="#f9fafb",   log_fg="#1f2937",
)

_DARK_VARS = dict(
    bg="#0d1117",       sf="#161b22",       sf2="#21262d",
    fg="#f0f6fc",       muted="#6b7280",    sec_title="#cdd9e5",
    bd="#30363d",       bd2="#6b7280",
    inp_bg="#21262d",
    # nav
    nav_bg="#21262d",   nav_fg="#f0f6fc",   nav_bd="#6b7280",
    nav_on_bg="#0d1b2e",nav_on_fg="#93c5fd",nav_on_bd="#1d4ed8",
    # exit
    exit_bg="#2d0f0f",  exit_fg="#fca5a5",  exit_bd="#991b1b",
    exit_hov="#3d1515",
    # semantic buttons
    pri_bg="#3b82f6",       pri_fg="#ffffff",       pri_bd="#2563eb",       pri_hov="#2563eb",
    pri_dis_bg="#1e3a8a",   pri_dis_fg="#60a5fa",   pri_dis_bd="#1d4ed8",
    suc_bg="#0d2012",       suc_fg="#86efac",       suc_bd="#3fb950",       suc_hov="#142a1a",
    dan_bg="#2d0f0f",       dan_fg="#fca5a5",       dan_bd="#991b1b",       dan_hov="#3d1515",
    # default button
    btn_bg="#1e3a8a",       btn_fg="#bfdbfe",       btn_bd="#3b82f6",       btn_hov="#1e40af",
    btn_dis_bg="#1f2937",   btn_dis_fg="#64748b",   btn_dis_bd="#374151",
    # segment off-state
    seg_off_bg="#0d1117",   seg_off_fg="#94a3b8",   seg_off_bd="#475569",   seg_off_hov="#1e293b",
    # data
    val_blue="#60a5fa",
    ok_color="#3fb950", warn_color="#fcd34d", err_color="#f87171",
    # hi/avg/low
    hi_bg="#2d1900",    avg_bg="#21262d",   lo_bg="#2d0f0f",
    # section header tints
    head_com_bg="#7f1d1d", head_com_fg="#fecaca",
    head_cfg_bg="#4c1d95", head_cfg_fg="#ddd6fe",
    head_trk_bg="#115e59", head_trk_fg="#99f6e4",
    # section card body + border (darker wash matching the header hue)
    card_com_bg="#1f0e11", card_com_bd="#7f1d1d",
    card_cfg_bg="#14102b", card_cfg_bd="#4c1d95",
    card_trk_bg="#0d1f1c", card_trk_bd="#115e59",
    # log (light text on very dark for readability)
    log_bg="#0d1117",   log_fg="#e6edf3",
)

# Matplotlib colors per theme
PLOT_LIGHT = dict(fig_bg="white",   ax_bg="white",   fg="#111827", grid="#e5e7eb", tick="#374151")
PLOT_DARK  = dict(fig_bg="#0d1117", ax_bg="#0d1117", fg="#f0f6fc", grid="#30363d", tick="#cdd9e5")

LIGHT: str = _BASE.format(**_LIGHT_VARS)
DARK:  str = _BASE.format(**_DARK_VARS)
