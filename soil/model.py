"""
soil.model
==========
Runtime prediction module for the SoilSense Monitor dashboard.

This is the deployment-only version.  The calibration pipeline
(run_all, build_dataset, cross_validate, plot_*) has been removed —
those functions were used to produce result.pkl, which is already saved.

The only public function is predict_full(), called by node_loader.py
after each successful Comm Collect cycle.

Typical call (from node_loader.py)
------------------------------------
    import pickle
    from soil.model import predict_full

    with open('result.pkl', 'rb') as f:
        saved = pickle.load(f)

    result = predict_full(
        'path/to/N08_260521.TXT',
        vwc_model  = saved['final_model'],
        f_opt_real = saved['f_opt_real'],
        f_opt_imag = saved['f_opt_imag'],
        f_ec_ref   = saved['f_ec_ref'],
        ec_band_lo = saved['ec_band_lo'],
        ec_band_hi = saved['ec_band_hi'],
    )
    # result = {
    #     'vwc'        : 0.312,           # m³/m³
    #     'gwc'        : 0.260,           # g/g
    #     'sigma_bulk' : 0.291,           # dS/m
    #     'sigma_pore' : 1.62,            # dS/m  (None if VWC too low)
    #     'salinity'   : {'class': 'Non-saline', 'risk': 'none'},
    # }
"""

import numpy as np
from typing import Dict, Optional

from soil.dielectric import (
    extract_permittivity, FREQS,
    extract_ec_band, EC_SEARCH_LOW,
)

# ─────────────────────────────────────────────────────────────────────────────
# Site constants  (update if soil or sensor changes)
# ─────────────────────────────────────────────────────────────────────────────
RHO_B = 1.2   # g/cm³  soil bulk density  (converts GWC to VWC)

# ─────────────────────────────────────────────────────────────────────────────
# Hilhorst (2000) EC model constants
# ─────────────────────────────────────────────────────────────────────────────
EPS_WATER  = 80.3   # permittivity of liquid water at 25°C
EPS_OFFSET = 4.1    # permittivity of dry mineral soil (universal constant)

# ─────────────────────────────────────────────────────────────────────────────
# Dispersion slope feature endpoints  (used for F3, stored in saved model)
# ─────────────────────────────────────────────────────────────────────────────
F_SLOPE_LOW  = 10e6   # Hz   lower anchor for slope feature
F_SLOPE_HIGH = 40e6   # Hz   upper anchor for slope feature

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _load_spectrum(filepath: str):
    """Extract ε′ and ε″ arrays from a raw .TXT node file."""
    return extract_permittivity(filepath, smooth=True)


def _nearest(fhz: float) -> int:
    """Index into FREQS nearest to fhz."""
    return int(np.argmin(np.abs(FREQS - fhz)))


def _extract_features(
    eps_real:   np.ndarray,
    eps_imag:   np.ndarray,
    f_opt_real: float,
    f_opt_imag: float,
    f_ec_ref:   float,
    ec_band_lo: float,
    ec_band_hi: float,
) -> Dict[str, float]:
    """
    Extract the scalar features used by the fitted VWC model.

    F1  ε′ at f_opt_real    (single point, max R² frequency from calibration)
    F2  ε″ at f_opt_imag    (single point, max R² frequency from calibration)
    F3  dispersion slope    (ε′ drop rate across 10–40 MHz)
    F_EC mean σ(f) [dS/m]  (bulk EC, band-averaged)
    F_ER mean ε′(f)        (band-averaged, paired with F_EC for Hilhorst)
    """
    f1 = float(eps_real[_nearest(f_opt_real)])
    f2 = float(eps_imag[_nearest(f_opt_imag)])
    f3 = float((eps_real[_nearest(F_SLOPE_LOW)] -
                eps_real[_nearest(F_SLOPE_HIGH)]) /
               np.log10(F_SLOPE_HIGH / F_SLOPE_LOW))
    sigma_bulk, eps_real_band = extract_ec_band(
        eps_real, eps_imag, ec_band_lo, ec_band_hi
    )
    return {
        'F1'  : f1,
        'F2'  : f2,
        'F3'  : f3,
        'F_EC': sigma_bulk,
        'F_ER': eps_real_band,
    }


def _apply_vwc_model(features: Dict, model: Dict) -> float:
    """
    Apply the fitted linear model: VWC = a + b₁·F1 + b₂·F2 + …
    Returns VWC clipped to the physically valid range [0, 0.65] m³/m³.
    """
    feat_names = model['features']
    X = np.array([[features[f] for f in feat_names]])
    X_b = np.column_stack([np.ones(len(X)), X])
    return float(np.clip(X_b @ model['coeffs_full'], 0.0, 0.65))


def _classify_salinity(sigma_bulk_dsm: float) -> Dict:
    """
    Map bulk EC to USDA salinity class (Richards 1954).

    Note: USDA thresholds are defined for ECe (saturated paste extract).
    Bulk EC from buried sensors is typically lower than ECe, so the
    classification is conservative.
    """
    thresholds = [
        (2.0, 'Non-saline',         'none',   'No crop restriction'),
        (4.0, 'Slightly saline',    'low',    'Sensitive crops affected'),
        (8.0, 'Moderately saline',  'medium', 'Many crops affected'),
        (16., 'Highly saline',      'high',   'Only tolerant crops'),
        (1e9, 'Very highly saline', 'high',   'Very few crops survive'),
    ]
    for thr, cls, risk, desc in thresholds:
        if sigma_bulk_dsm < thr:
            return {'class': cls, 'risk': risk, 'description': desc}

# ─────────────────────────────────────────────────────────────────────────────
# Main prediction function  — called by node_loader.py
# ─────────────────────────────────────────────────────────────────────────────
def predict_full(
    filepath:   str,
    vwc_model:  Dict,
    f_opt_real: float,
    f_opt_imag: float,
    f_ec_ref:   float,
    ec_band_lo: Optional[float] = None,
    ec_band_hi: Optional[float] = None,
) -> Dict:
    """
    Predict soil properties from one node measurement file.

    All calibration parameters come from result.pkl (produced once by
    run_soil_analysis.py).  They are passed explicitly so the function
    is stateless and safe to call from multiple threads.

    Parameters
    ----------
    filepath    Path to the node .TXT measurement file.
    vwc_model   Fitted OLS model dict from result.pkl['final_model'].
    f_opt_real  ε′ feature frequency [Hz] from result.pkl.
    f_opt_imag  ε″ feature frequency [Hz] from result.pkl.
    f_ec_ref    EC reference frequency [Hz] from result.pkl.
    ec_band_lo  EC averaging band lower bound [Hz] from result.pkl.
    ec_band_hi  EC averaging band upper bound [Hz] from result.pkl.

    Returns
    -------
    dict
        vwc         float  Volumetric water content [m³/m³]
        gwc         float  Gravimetric water content [g/g]
        sigma_bulk  float  Bulk EC [dS/m]  — always available
        sigma_pore  float  Pore water EC [dS/m] via Hilhorst (2000)
                           None if ε′ is too low for stable inversion
        salinity    dict   USDA class, risk level
    """
    if ec_band_lo is None:
        ec_band_lo = EC_SEARCH_LOW
    if ec_band_hi is None:
        ec_band_hi = f_ec_ref

    # 1. Extract permittivity spectra
    eps_real, eps_imag = _load_spectrum(filepath)

    # 2. Extract scalar features
    feats = _extract_features(
        eps_real, eps_imag,
        f_opt_real, f_opt_imag,
        f_ec_ref, ec_band_lo, ec_band_hi,
    )

    # 3. VWC from linear model (feature F2 = ε″ at f_opt_imag)
    vwc = _apply_vwc_model(feats, vwc_model)
    gwc = vwc / RHO_B

    # 4. Bulk EC directly from σ(f) band average — no model required
    sigma_bulk = feats['F_EC']

    # 5. Pore water EC via Hilhorst (2000):
    #       σ_pore = σ_bulk × ε_water / (ε′ − ε_offset)
    #    Returns None when ε′ is too close to ε_offset (denominator < 1)
    #    which happens at very low VWC — consistent with Rhoades instability.
    denom      = feats['F_ER'] - EPS_OFFSET
    sigma_pore = (float(np.clip(sigma_bulk * EPS_WATER / denom, 0.0, 50.0))
                  if denom > 1.0 else None)

    # 6. USDA salinity classification from bulk EC
    salinity = _classify_salinity(sigma_bulk)

    return {
        'vwc'        : vwc,
        'gwc'        : gwc,
        'sigma_bulk' : sigma_bulk,
        'sigma_pore' : sigma_pore,
        'salinity'   : salinity,
    }
