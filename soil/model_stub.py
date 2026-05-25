"""
soil.model_stub
===============
Drop-in replacement for soil_model.py during dashboard development.

Returns realistic fake data so the dashboard can be built and tested
without running the real permittivity extraction pipeline.

Replace each function call with the real one when the dashboard is ready:

    from soil.model_stub  import predict_full, load_node_data
    # → later replace with:
    from soil.model       import predict_full
    from soil.node_loader import load_node_data
"""

import datetime
import random
from pathlib import Path
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Return type — matches real predict_full() exactly
# ─────────────────────────────────────────────────────────────────────────────
def predict_full(filepath: str) -> Dict:
    """
    Stub: returns fake soil properties for any .TXT file.

    Real version signature (soil_model.py):
        predict_full(filepath, vwc_model, f_opt_real, f_opt_imag,
                     f_ec_ref, ec_band_lo, ec_band_hi) -> Dict

    Returns
    -------
    {
        'vwc'        : float   m³/m³
        'gwc'        : float   g/g
        'sigma_bulk' : float   dS/m
        'sigma_pore' : float | None   dS/m
        'salinity'   : { 'class': str, 'risk': str }
    }
    """
    rng = random.Random(str(filepath))
    vwc = round(rng.uniform(0.10, 0.42), 3)
    gwc = round(vwc / 1.2, 3)
    bulk = round(rng.uniform(0.10, 0.45), 3)
    pore = round(rng.uniform(1.1, 2.5), 2) if vwc > 0.12 else None
    return {
        'vwc'        : vwc,
        'gwc'        : gwc,
        'sigma_bulk' : bulk,
        'sigma_pore' : pore,
        'salinity'   : {'class': 'Non-saline', 'risk': 'none'},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scan node folders and return one result per node
# ─────────────────────────────────────────────────────────────────────────────
def load_node_data(data_root: str) -> List[Dict]:
    """
    Stub: scan folders 1/…16/ under data_root, load most recent file
    per node, call predict_full(), return list of node result dicts.

    Real version: same signature, real predict_full() with saved model.

    Returns
    -------
    List of dicts, one per node:
    {
        'node_id'    : str          e.g. 'S1' (matches Map View markers)
        'date'       : datetime.date
        'time'       : str          'HH:MM'
        'is_live'    : bool         True when date == today
        'filepath'   : str
        'vwc'        : float
        'gwc'        : float
        'sigma_bulk' : float
        'sigma_pore' : float | None
        'salinity'   : dict
    }
    """
    today = datetime.date.today()
    results = []
    root = Path(data_root)

    for node_num in range(1, 17):
        folder = root / str(node_num)
        if not folder.exists():
            # Stub: generate fake entry even when folder is missing
            fake_date = today if node_num % 5 != 0 else today - datetime.timedelta(weeks=1)
            fake_path = str(folder / f"N{node_num:02d}_{fake_date.strftime('%y%m%d')}.TXT")
            pred = predict_full(fake_path)
            results.append({
                'node_id'   : f"S{node_num}",
                'date'      : fake_date,
                'time'      : '09:00',
                'is_live'   : fake_date == today,
                'filepath'  : fake_path,
                **pred,
            })
            continue

        # Find most recent .TXT file
        files = sorted(folder.glob("*.TXT"), reverse=True)
        if not files:
            continue

        latest = files[0]
        # Parse date from filename: N01_260521.TXT → 2026-05-21
        try:
            date_str = latest.stem.split('_')[-1]
            year  = 2000 + int(date_str[0:2])
            month = int(date_str[2:4])
            day   = int(date_str[4:6])
            file_date = datetime.date(year, month, day)
        except (ValueError, IndexError):
            file_date = today

        pred = predict_full(str(latest))
        results.append({
            'node_id'   : f"S{node_num}",
            'date'      : file_date,
            'time'      : datetime.datetime.fromtimestamp(
                              latest.stat().st_mtime
                          ).strftime('%H:%M'),
            'is_live'   : file_date == today,
            'filepath'  : str(latest),
            **pred,
        })

    return results


def get_available_dates(data_root: str) -> List[datetime.date]:
    """
    Return sorted list of all unique collection dates found across all
    node folders.  Used to populate the Map View date selector bar.
    """
    dates = set()
    root = Path(data_root)
    for node_num in range(1, 17):
        for f in (root / str(node_num)).glob("*.TXT"):
            try:
                ds = f.stem.split('_')[-1]
                dates.add(datetime.date(2000+int(ds[:2]), int(ds[2:4]), int(ds[4:6])))
            except (ValueError, IndexError):
                pass
    if not dates:
        # Stub: return fake dates
        today = datetime.date.today()
        dates = {today - datetime.timedelta(weeks=i) for i in range(5)}
    return sorted(dates, reverse=True)
