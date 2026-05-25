"""
bridge.py — Tkinter→PyQt6 adapter layer.

Serial_Com_Ctrl.py was written against a Tkinter widget interface.
This module exposes proxy objects with the same dict-style property API
(gui.sync_status["text"] = "OK") and routes all writes through Qt signals
so the main thread can safely update PyQt6 widgets.

Serial_Com_Ctrl.py and Data_Com_Ctrl.py are NOT modified.
"""
from __future__ import annotations
import tkinter.messagebox as _tk_msgbox
from PyQt6.QtCore import QObject, pyqtSignal


# ─────────────────────────── signals ────────────────────────────────────────

class BridgeSignals(QObject):
    """
    Single shared instance carrying all hardware→GUI notifications.
    Qt queued connections deliver signals from background threads to
    slots running on the main thread — no manual locking needed.
    """
    widget_update   = pyqtSignal(str, str, str)         # (widget_name, prop, value)
    log_append      = pyqtSignal(str)                   # text to append to log
    log_scroll      = pyqtSignal()                      # scroll log to bottom
    show_info       = pyqtSignal(str, str)              # (title, message)
    show_error      = pyqtSignal(str, str)
    collection_done = pyqtSignal()                      # SerialStream reached MXStop
    plot_update     = pyqtSignal(object, object, object, str)  # (freq, mag, phs, label)
    connection_state = pyqtSignal(bool, str, str)       # (connected, com, baud)
    soil_data_updated = pyqtSignal()                    # any soil/file change worth re-loading


def install_messagebox_patch(signals: BridgeSignals) -> None:
    """
    Replace tkinter.messagebox callables with Qt-signal wrappers.
    Must be called before the first serial connect action.
    Serial_Com_Ctrl imports 'messagebox' as a module reference so
    patching the module attributes is sufficient.
    """
    _tk_msgbox.showinfo  = lambda title, msg: signals.show_info.emit(str(title), str(msg))
    _tk_msgbox.showerror = lambda title, msg: signals.show_error.emit(str(title), str(msg))


# ─────────────────────────── proxy primitives ───────────────────────────────

class WidgetProxy:
    """
    Mimics a Tkinter widget's dict-style property access.

    Serial_Com_Ctrl writes:
        gui.sync_status["text"] = "OK"
        gui.sync_status["fg"]   = "green"
        some_btn.config(state="normal")

    Each write emits widget_update(name, prop, value) on the signals object
    so the Qt main thread can apply the change to the real widget.
    """
    def __init__(self, name: str, signals: BridgeSignals):
        self._name    = name
        self._signals = signals
        self._state: dict[str, str] = {}

    def __setitem__(self, key: str, value):
        self._state[key] = str(value)
        self._signals.widget_update.emit(self._name, key, str(value))

    def __getitem__(self, key: str) -> str:
        return self._state.get(key, "")

    def config(self, **kwargs):
        for k, v in kwargs.items():
            self[k] = v

    def get(self) -> str:
        return self._state.get("text", "")


class _BoolProxy:
    """Mimics Tkinter BooleanVar — used for the auto-scroll checkbox."""
    def __init__(self, initial: bool = True):
        self._v = initial

    def get(self) -> bool:
        return self._v

    def set(self, v: bool):
        self._v = v


class _LogTextProxy:
    """Mimics Tkinter Text.insert / Text.see for the serial log."""
    END = "end"

    def __init__(self, signals: BridgeSignals):
        self._signals = signals

    def insert(self, pos, text):
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        self._signals.log_append.emit(str(text))

    def see(self, pos):
        self._signals.log_scroll.emit()


class LoggerProxy:
    """Mimics the LoggerGui attributes that Serial_Com_Ctrl accesses."""
    def __init__(self, signals: BridgeSignals, auto_scroll: _BoolProxy):
        self.logger      = _LogTextProxy(signals)
        self.auto_scroll = auto_scroll


class _PlotProxy:
    """
    Routes plot calls from the serial thread to the real PlotPanel.
    Pure-calculation methods run inline (thread-safe).
    update_plot() goes through a signal for main-thread safety, and
    snapshots the just-written file's full path *here on the serial
    thread* so the main-thread slot doesn't read self.data.filename1
    after the serial thread has moved on to the next node.
    """
    def __init__(self, plot_panel, signals: BridgeSignals, data=None):
        self._panel   = plot_panel
        self._signals = signals
        self._data    = data    # DataMaster — used to reconstruct source path

    def calculate_freq_mag_phase(self, fre_id, mag, phs):
        return self._panel.calculate_freq_mag_phase(fre_id, mag, phs)

    def create_label(self, filename: str, ext: str) -> str:
        return self._panel.create_label(filename, ext)

    def _current_source_path(self) -> str:
        """Build the absolute path to the file Data_Com_Ctrl.RadioDataToFile()
        just wrote — filename1 is basename-only, so we reconstruct it from
        save_root + current_node + filename1. Called on the serial thread,
        so the snapshot can't race against a later RadioDataToFile() call."""
        import os
        d = self._data
        if d is None:
            return ""
        fname = getattr(d, "filename1", None) or ""
        node  = getattr(d, "current_node", None)
        root  = getattr(d, "save_root", None) or "data\\UG nodes"
        if not fname or node is None:
            return ""
        return os.path.join(root, str(node), fname)

    def update_plot(self, freq, mag_dB, phs_deg, label: str):
        f = freq.tolist()   if hasattr(freq,    "tolist") else list(freq)
        m = mag_dB.tolist() if hasattr(mag_dB,  "tolist") else list(mag_dB)
        p = phs_deg.tolist()if hasattr(phs_deg, "tolist") else list(phs_deg)

        # Source-path handoff: stash on the panel's pending-paths queue
        # (list .append / .pop are atomic under the GIL). Qt signals across
        # threads are FIFO-ordered, so the slot pops the entry corresponding
        # to this emission. Bypasses Qt's cross-thread arg-marshalling
        # entirely — the signal itself only carries the 4 plot arrays.
        src = self._current_source_path()
        if not hasattr(self._panel, "_pending_source_paths"):
            self._panel._pending_source_paths = []
        self._panel._pending_source_paths.append(src)

        self._signals.plot_update.emit(f, m, p, label)


class _StringVarProxy:
    """Mimics Tkinter StringVar.get() by delegating to a live getter callable."""
    def __init__(self, getter):
        self._getter = getter

    def get(self) -> str:
        return self._getter()


# ─────────────────────────── composite proxies ──────────────────────────────

class DatacollectProxy:
    """
    Mimics DataCollectGui — the 'gui' object passed to SerialStream().
    Every attribute mirrors an original widget name in Serial_Com_Ctrl.
    """
    def __init__(
        self,
        data,
        signals: BridgeSignals,
        plot_panel,
        logger_proxy: LoggerProxy,
    ):
        self.data     = data
        self._signals = signals

        def wp(name: str) -> WidgetProxy:
            return WidgetProxy(name, signals)

        self.complete_nodes   = wp("complete_nodes")
        self.node_status_txt  = wp("node_status_txt")
        self.node_status      = wp("node_status")
        self.ACK_status       = wp("ACK_status")
        self.time_cal_status  = wp("time_cal_status")
        self.freID_status     = wp("freID_status")
        self.data_rec_status  = wp("data_rec_status")
        self.data_save_status = wp("data_save_status")

        # Widgets stop_monitor_thread resets via gui.datacollect.*
        self.clt_m1      = wp("clt_m1")
        self.clt_m2      = wp("clt_m2")
        self.Load_fre    = wp("Load_fre")
        self.load_status = wp("load_status")
        self.btn_collection = wp("btn_collection")

        self.logger = logger_proxy
        self.plot   = _PlotProxy(plot_panel, signals, data=data)

    def collection_ctrl(self):
        """Called by SerialStream at MXStop — signal the main thread."""
        self._signals.collection_done.emit()


class ComGuiProxy:
    """
    Mimics ComGui — the 'gui' object passed to SerialSync,
    Monitor_Connection, and SerialOpen.
    """
    def __init__(
        self,
        data,
        signals:          BridgeSignals,
        com_getter,                          # callable() → str
        bd_getter,                           # callable() → str
        datacollect_proxy: DatacollectProxy,
        logger_proxy:      LoggerProxy,
    ):
        self.data = data
        self._signals = signals

        self.selected_com = _StringVarProxy(com_getter)
        self.selected_bd  = _StringVarProxy(bd_getter)

        def wp(name: str) -> WidgetProxy:
            return WidgetProxy(name, signals)

        self.sync_status = wp("sync_status")
        self.btn_connect = wp("btn_connect")
        self.btn_refresh = wp("btn_refresh")
        self.drop_baud   = wp("drop_baud")
        self.drop_com    = wp("drop_com")

        self.datacollect = datacollect_proxy
        self.logger      = logger_proxy
