"""
soil.node_loader
================
Production data layer for the SoilSense Monitor dashboard.

Provides the same three-function API as soil.model_stub — drop-in
replacement, no other code needs to change. Backed by the real
soil.model.predict_full() pipeline and the saved calibration in
`result.pkl`.

Public API
----------
    predict_full(filepath) -> dict
    load_node_data(data_root) -> list[dict]
    get_available_dates(data_root) -> list[datetime.date]

File-format handling
--------------------
Both raw .TXT field files (`N{nn}_{YYMMDD}.TXT`, space-separated,
mag-ADC in col 2, phase-ADC in col 3) and the .csv export format
(`d{n}-{YY_MM_DD}-{HH_MM_SS}(wo).csv`, columns: fre_idx, mag (dig),
phs (dig)) are accepted. Only csv files whose basename starts with
"d" are scanned — the "r"-prefixed companion files are skipped.

Error handling
--------------
1. Missing result.pkl → FileNotFoundError at import.
2. Any single file failing predict_full → logged, file skipped.
3. Folder with no soil files → skipped silently.
4. Unparseable filename date → falls back to mtime + log warning.
"""
from __future__ import annotations
import os
import sys
import pickle
import datetime
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from soil.model import predict_full as _predict_full_real


# Path to saved calibration result.
#   • Source mode: result.pkl lives at the project root, 2 levels up
#     from soil/node_loader.py.
#   • PyInstaller-frozen mode: __file__ may point inside the bundle
#     archive (not a real filesystem path), so we resolve relative to
#     sys.executable instead. The .spec file places result.pkl next to
#     the .exe (datas = [("result.pkl", ".")] + contents_directory=".").
if getattr(sys, "frozen", False):
    PKL_PATH = os.path.join(os.path.dirname(sys.executable), "result.pkl")
else:
    PKL_PATH = str(Path(__file__).resolve().parent.parent / "result.pkl")


# ─────────────────────────────────────────────────────────────────────────────
# Load calibration once at module level
# ─────────────────────────────────────────────────────────────────────────────
if not os.path.exists(PKL_PATH):
    raise FileNotFoundError(
        f"node_loader: required calibration file '{PKL_PATH}' not found. "
        f"Generate it with run_soil_analysis.py before importing this module."
    )

with open(PKL_PATH, "rb") as _f:
    _saved: Dict = pickle.load(_f)

_REQUIRED_KEYS = (
    "final_model", "f_opt_real", "f_opt_imag",
    "f_ec_ref", "ec_band_lo", "ec_band_hi",
)
_missing = [k for k in _REQUIRED_KEYS if k not in _saved]
if _missing:
    raise KeyError(
        f"node_loader: '{PKL_PATH}' is missing required key(s): {_missing}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# File adapters — CSV → temp TXT
# ─────────────────────────────────────────────────────────────────────────────
def _csv_to_temp_txt(csv_path: str) -> str:
    """
    Convert the CSV export format (columns: fre_idx, mag (dig), phs (dig)) to
    a temporary space-separated TXT in the same layout that
    soil_dielectric.load_spectrum() reads via np.loadtxt: column 0 = fre_idx,
    column 2 = magnitude ADC count, column 3 = phase ADC count. Column 1 is
    filled with zeros as a placeholder (load_spectrum doesn't read it).
    Caller is responsible for deleting the returned path.
    """
    df      = pd.read_csv(csv_path)
    fre_idx = df["fre_idx"].to_numpy(dtype=float)
    mag     = df["mag (dig)"].to_numpy(dtype=float)
    phs     = df["phs (dig)"].to_numpy(dtype=float)
    data    = np.column_stack([
        fre_idx, np.zeros(len(fre_idx)), mag, phs,
    ])
    tmp = tempfile.NamedTemporaryFile(
        suffix=".TXT", delete=False, mode="w", newline="",
    )
    np.savetxt(tmp.name, data, fmt="%g")
    tmp.close()
    return tmp.name


# ─────────────────────────────────────────────────────────────────────────────
# Public — predict_full
# ─────────────────────────────────────────────────────────────────────────────
def predict_full(filepath: str) -> Dict:
    """
    Run the calibrated soil model on a single node file. Accepts .TXT or .csv;
    csv files are converted to a temp .TXT before the underlying pipeline runs.

    Returns
    -------
    {
        'vwc'        : float,         # m³/m³
        'gwc'        : float,         # g/g
        'sigma_bulk' : float,         # dS/m
        'sigma_pore' : float | None,  # dS/m (None when Hilhorst denom < 1)
        'salinity'   : {'class': str, 'risk': str},
    }
    """
    ext = os.path.splitext(filepath)[-1].lower()
    if ext == ".csv":
        path    = _csv_to_temp_txt(filepath)
        cleanup = True
    else:
        path    = filepath
        cleanup = False

    try:
        return _predict_full_real(
            filepath   = path,
            vwc_model  = _saved["final_model"],
            f_opt_real = _saved["f_opt_real"],
            f_opt_imag = _saved["f_opt_imag"],
            f_ec_ref   = _saved["f_ec_ref"],
            ec_band_lo = _saved["ec_band_lo"],
            ec_band_hi = _saved["ec_band_hi"],
        )
    finally:
        if cleanup and os.path.exists(path):
            try:
                os.unlink(path)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Filename date parsing
# ─────────────────────────────────────────────────────────────────────────────
def _parse_file_date(name: str) -> Optional[datetime.date]:
    """
    Best-effort date parser covering the known naming schemes:
      - s{nnn}_{YYMMDD}_{HHMMSS}.txt        (live capture, sensor-tagged,
                                             's016_260521_143956')
      - s_{YYMMDD}_{HHMMSS}.txt             (live capture, legacy untagged,
                                             's_260521_143956')
      - d{n}-{YY_MM_DD}-{HH_MM_SS}(wo).csv  (field export, 'd5-25_01_23-16_30_26(wo)')

    Returns None if the date can't be parsed by any rule — caller is
    expected to fall back to file mtime and log a warning.
    """
    stem = os.path.splitext(os.path.basename(name))[0]

    # Underscore-separated forms: any chunk that's exactly 6 digits is a YYMMDD
    # candidate. Covers 'N08_260521' (last chunk) AND 's_260521_143956' (middle).
    if "_" in stem:
        for chunk in stem.split("_"):
            if len(chunk) == 6 and chunk.isdigit():
                try:
                    return datetime.date(
                        2000 + int(chunk[0:2]), int(chunk[2:4]), int(chunk[4:6])
                    )
                except ValueError:
                    pass

    # Field-export format: 'd<n>-<YY_MM_DD>-<HH_MM_SS>(wo)' — second
    # dash-separated chunk is 'YY_MM_DD'.
    if "-" in stem:
        parts = stem.split("-")
        if len(parts) >= 2:
            try:
                y, m, d = parts[1].split("_")
                return datetime.date(2000 + int(y), int(m), int(d))
            except (ValueError, IndexError):
                pass

    return None


def _parse_file_time(name: str) -> Optional[str]:
    """
    Best-effort HH:MM parser mirroring _parse_file_date. Schemes:
      - s{nnn}_{YYMMDD}_{HHMMSS}.txt        → '14:39' from '143956'
      - s_{YYMMDD}_{HHMMSS}.txt             → '14:39' from '143956'
      - d{n}-{YY_MM_DD}-{HH_MM_SS}(wo).csv  → '16:30' from '16_30_26'

    Returns None when no time can be parsed — caller may fall back to mtime.
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    # Strip trailing tags like '(wo)' that follow the time field
    if "(" in stem:
        stem = stem.split("(")[0]

    # Field-export: third dash-separated chunk is 'HH_MM_SS'
    if "-" in stem:
        parts = stem.split("-")
        if len(parts) >= 3:
            try:
                h, m, _s = parts[2].split("_")
                hh, mm = int(h), int(m)
                if 0 <= hh < 24 and 0 <= mm < 60:
                    return f"{hh:02d}:{mm:02d}"
            except (ValueError, IndexError):
                pass

    # Underscore forms: HHMMSS chunk follows a YYMMDD chunk
    if "_" in stem:
        chunks = stem.split("_")
        date_seen = False
        for chunk in chunks:
            if len(chunk) == 6 and chunk.isdigit():
                if date_seen:
                    try:
                        hh = int(chunk[0:2]); mm = int(chunk[2:4])
                        if 0 <= hh < 24 and 0 <= mm < 60:
                            return f"{hh:02d}:{mm:02d}"
                    except ValueError:
                        pass
                    break
                date_seen = True

    return None


def _iter_node_files(folder: Path) -> List[Path]:
    """
    All soil-data files in a node folder.

    Includes:
      - *.TXT / *.txt
      - d*.csv / d*.CSV   (only 'd'-prefixed csv files; 'r' companions excluded)
    """
    files: List[Path] = []
    for pat in ("*.TXT", "*.txt", "d*.csv", "d*.CSV"):
        files.extend(folder.glob(pat))
    # Deduplicate (a single path may match multiple patterns on case-insensitive FS).
    seen = set()
    uniq: List[Path] = []
    for p in files:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _resolved_date(path: Path) -> datetime.date:
    """Filename date if parsable, otherwise file mtime."""
    d = _parse_file_date(path.name)
    if d is not None:
        return d
    return datetime.date.fromtimestamp(path.stat().st_mtime)


def _node_id_from_folder(folder: Path) -> Optional[str]:
    """
    Authoritative node-id source: the parent folder name's digits.

    Examples:
      '5'      -> 'S5'
      'node8'  -> 'S8'
      '016'    -> 'S16'

    Matches the marker naming used in config.json / the Map View (no
    zero-padding). Returns None if the folder name contains no digits.
    """
    digits = "".join(ch for ch in folder.name if ch.isdigit())
    if not digits:
        return None
    return f"S{int(digits)}"


def _iter_node_folders(root: Path) -> List[Path]:
    """All immediate subfolders of root whose names contain digits."""
    if not root.exists():
        return []
    return [p for p in sorted(root.iterdir())
            if p.is_dir() and any(ch.isdigit() for ch in p.name)]


# ─────────────────────────────────────────────────────────────────────────────
# Public — load_node_data
# ─────────────────────────────────────────────────────────────────────────────
def load_node_data(data_root: str) -> List[Dict]:
    """
    Discover every subfolder of data_root whose name contains digits; treat
    each as one sensor (node-id = 'N' + zero-padded digits from the folder
    name). For each folder, take the file with the latest parsed date and
    run predict_full() on it. Folders without soil files are skipped. A
    predict_full() failure on a single file logs to stderr and skips that
    node — no crash.
    """
    out: List[Dict] = []
    root  = Path(data_root)
    today = datetime.date.today()

    for folder in _iter_node_folders(root):
        node_id = _node_id_from_folder(folder)
        if node_id is None:
            continue

        files = _iter_node_files(folder)
        if not files:
            continue

        latest = max(files, key=_resolved_date)

        try:
            pred = predict_full(str(latest))
        except Exception as e:
            print(f"[node_loader] {latest}: {e}")
            continue

        file_date = _parse_file_date(latest.name)
        if file_date is None:
            print(f"[node_loader] {latest.name}: filename date not parseable; using mtime")
            file_date = datetime.date.fromtimestamp(latest.stat().st_mtime)

        file_time = _parse_file_time(latest.name)
        if file_time is None:
            file_time = datetime.datetime.fromtimestamp(
                latest.stat().st_mtime
            ).strftime("%H:%M")
        out.append({
            "node_id"  : node_id,
            "date"     : file_date,
            "time"     : file_time,
            "is_live"  : file_date == today,
            "filepath" : str(latest),
            **pred,
        })

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Public — get_available_dates
# ─────────────────────────────────────────────────────────────────────────────
def get_available_dates(data_root: str) -> List[datetime.date]:
    """
    Sorted (newest first) list of unique dates seen across every node folder
    under data_root. Unparseable filenames fall back to file mtime.
    """
    dates: set = set()

    for folder in _iter_node_folders(Path(data_root)):
        for f in _iter_node_files(folder):
            d = _parse_file_date(f.name)
            if d is None:
                d = datetime.date.fromtimestamp(f.stat().st_mtime)
            dates.add(d)

    return sorted(dates, reverse=True)
