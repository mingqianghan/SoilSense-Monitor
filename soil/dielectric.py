"""
soil.dielectric
===============
Extracts complex permittivity (ε′, ε″) from buried impedance sensor files.

This module is the low-level signal processing layer.
The only function called by the application is extract_permittivity().
All other public functions (sigma_spectrum, extract_ec_band) are helpers
used by soil_model.predict_full().

Signal chain (one .TXT file → ε′, ε″ arrays)
----------------------------------------------
  1. load_spectrum       ADC counts → |H(f)|, |φ(f)|
  2. _both_options       Compute ε for ±cable-sign at every frequency
  3. _dp_sign_select     Pick the sign that minimises ε′ total variation
  4. _fix_ei_spikes      Fix isolated wrong-sign points in ε″
  5. Savitzky-Golay      Light smoothing pass (optional)

Why two sign options?
---------------------
The AD8302 phase detector outputs |φ(f)| — the sign is lost.  The correct
sign flips at each cable quarter-wavelength resonance (≈ 62 MHz for this
installation).  The DP globally minimises Σ|Δε′| to find which sign
choice at each frequency produces the smoothest ε′ curve.

Update these constants per installation
----------------------------------------
  CABLE_L, Z0, Z1, VF   cable geometry and impedances
  _h1, _w2, _width, _d  sensor electrode dimensions (metres)
"""

import numpy as np
from typing import List, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Physical constant
# ─────────────────────────────────────────────────────────────────────────────
EPS_0 = 8.854e-12          # F/m  permittivity of free space

# ─────────────────────────────────────────────────────────────────────────────
# AD8302 signal-chain calibration
# ─────────────────────────────────────────────────────────────────────────────
ADC_MAX    = 4095           # 12-bit full-scale ADC count
ADC_REF    = 3.3            # V  ADC reference voltage
MAG_SLOPE  =  0.06          # V/dB  AD8302 magnitude transfer slope
MAG_OFFSET =  1.8           # V     AD8302 magnitude output at 0 dB
PHS_SLOPE  = -0.01          # V/deg AD8302 phase transfer slope
PHS_OFFSET =  0.9           # V     AD8302 phase output at 0°
PHS_SHIFT  =  90.0          # deg   AD8302 internal phase reference offset

# ─────────────────────────────────────────────────────────────────────────────
# Sensor electrode geometry  (metres)
# ─────────────────────────────────────────────────────────────────────────────
_h1    = 0.044   # triangular soil electrode height
_w2    = 0.026   # rectangular PCB electrode width
_width = 0.042   # common electrode width
_d     = 0.004   # gap between electrodes
_epr2  = 2.5     # PCB substrate relative permittivity (FR4)

# Factor of 5 accounts for fringe fields (empirically determined for this geometry)
C1_0 = 5 * EPS_0         * (0.5 * _h1 * _width) / _d   # soil capacitance [F]
C2   = 5 * _epr2 * EPS_0 * (_w2  * _width)      / _d   # PCB capacitance  [F]

# ─────────────────────────────────────────────────────────────────────────────
# Coaxial cable parameters  (update per installation)
# ─────────────────────────────────────────────────────────────────────────────
CABLE_L = 0.80   # m   cable length from board to buried sensor
Z0      = 50.0   # Ω   cable characteristic impedance
Z1      = 50.0   # Ω   source impedance
VF      = 0.66   # —   velocity factor (typical RG-58)

# ─────────────────────────────────────────────────────────────────────────────
# DP algorithm parameters
# ─────────────────────────────────────────────────────────────────────────────
_EPS_NOMINAL      = 20.0   # representative ε′ for initial sign estimate
_DP_PENALTY_ALPHA = 0.15   # flip penalty = α × median|Δε′| per point
_EI_SPIKE_THRESH  = 3.0    # ε″ spike detection threshold (σ units)
_EI_SPIKE_KERNEL  = 11     # median filter kernel for spike detection (odd)
_SG_WINDOW        = 15     # Savitzky-Golay window (points, odd)
_SG_ORDER         = 3      # Savitzky-Golay polynomial order

# ─────────────────────────────────────────────────────────────────────────────
# EC band search range
# ─────────────────────────────────────────────────────────────────────────────
# Band-averaging for EC is done over the valid frequency sub-range found
# during calibration.  These constants define the outer search window.
EC_SEARCH_LOW  = 15e6   # Hz  lower bound (below this, electrode polarisation)
EC_SEARCH_HIGH = 60e6   # Hz  upper bound (above this, ε′ converges and
                         #     the Hilhorst denominator becomes unstable)
HILHORST_EPS_MIN = 8.0  # minimum ε′ for stable Hilhorst inversion

# ─────────────────────────────────────────────────────────────────────────────
# Firmware frequency array  (1110 log-spaced points)
# ─────────────────────────────────────────────────────────────────────────────
def _build_frequency_array() -> np.ndarray:
    """
    Reconstruct the STM32 firmware sweep: three log-spaced segments
    covering 100 Hz to 1 GHz in 1110 points.
    """
    f = np.empty(1110)
    for idx in range(1110):
        i = idx + 1
        if   i <= 10:  f[idx] = i * 100.0
        elif i <= 110: f[idx] = 10 ** (0.03  * (i - 10)  + 3)
        else:          f[idx] = 10 ** (0.003 * (i - 110) + 6)
    return f

F_ALL  = _build_frequency_array()
_MASK  = F_ALL > 1e7          # exclude f < 10 MHz (electrode polarisation)
FREQS  = F_ALL[_MASK]         # working frequency array used throughout
_N     = len(FREQS)

# ─────────────────────────────────────────────────────────────────────────────
# Transmission-line inversion
# ─────────────────────────────────────────────────────────────────────────────
def _calc_zload(Zin: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Recover sensor load impedance from measured input impedance Zin."""
    t = np.tan(2 * np.pi * f / (VF * 2.9979e8) * CABLE_L)
    return (Zin * Z0 - 1j * Z0**2 * t) / (Z0 - 1j * Zin * t)

# ─────────────────────────────────────────────────────────────────────────────
# Cable-geometry phase sign  (pre-computed once at import)
# ─────────────────────────────────────────────────────────────────────────────
def _cable_sign(f: np.ndarray) -> np.ndarray:
    """
    Compute the expected sign of H(f) assuming a nominal capacitive load
    (ε′ = 20, ε″ = 0).  Sign flips at each quarter-wavelength resonance.
    Used as starting estimate; the DP corrects errors afterwards.
    """
    w   = 2 * np.pi * f
    Zn  = 1.0 / (1j * w * C1_0 * _EPS_NOMINAL)
    t   = np.tan(2 * np.pi * f / (VF * 2.9979e8) * CABLE_L)
    Zin = Z0 * (Zn + 1j * Z0 * t) / (Z0 + 1j * Zn * t)
    return np.sign(np.angle(Zin / (Z1 + Zin)))

_SIGN_INIT = _cable_sign(F_ALL)   # reused for every file (1110 points)

# ─────────────────────────────────────────────────────────────────────────────
# Both sign options  (vectorised, once per file)
# ─────────────────────────────────────────────────────────────────────────────
def _both_options(
    mag:     np.ndarray,
    phs_abs: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute ε′ and ε″ for both +/- cable sign at every frequency in FREQS.
    Because each frequency is independent the two options can be pre-computed
    and the DP selects between them without recomputation.
    """
    sign = _SIGN_INIT[_MASK]
    w    = 2 * np.pi * FREQS
    mg   = mag[_MASK]
    ph   = phs_abs[_MASK]

    def _eps(s):
        pa = s * ph
        H  = mg * (np.cos(np.deg2rad(pa)) + 1j * np.sin(np.deg2rad(pa)))
        Zi = Z1 * H / (1.0 - H)
        ZL = _calc_zload(Zi, FREQS)
        # Invert ε = (1/(jωZL) + C2) / C1_0  (includes PCB substrate correction)
        e  = (1.0 / (1j * w * ZL) + C2) / C1_0
        return np.real(e), -np.imag(e)

    er_p, ei_p = _eps( sign)
    er_m, ei_m = _eps(-sign)
    return er_p, ei_p, er_m, ei_m

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic programming sign selection  (O(N), globally optimal)
# ─────────────────────────────────────────────────────────────────────────────
def _dp_sign_select(
    er_p:          np.ndarray,
    er_m:          np.ndarray,
    penalty_alpha: float = _DP_PENALTY_ALPHA,
) -> np.ndarray:
    """
    Select between er_p[i] and er_m[i] at each frequency to minimise:

        Σ |ε′[i] − ε′[i−1]|  +  penalty × n_flipped

    penalty = alpha × median(|Δε′|) — scales automatically with signal level.

    State 0 = cable sign (er_p), State 1 = flipped (er_m).
    Transitions:
        0→0: |er_p[i] − er_p[i−1]|
        1→0: |er_p[i] − er_m[i−1]|           (no extra cost to return)
        0→1: |er_m[i] − er_p[i−1]| + penalty
        1→1: |er_m[i] − er_m[i−1]| + penalty
    """
    n   = len(er_p)
    pen = penalty_alpha * max(np.median(np.abs(np.diff(er_p))), 1e-9)
    cost = np.array([0.0, pen])
    ptr  = np.zeros((n, 2), dtype=np.int8)

    for i in range(1, n):
        pp = er_p[i-1]; pm = er_m[i-1]
        cp = er_p[i];   cm = er_m[i]
        c0_0 = cost[0] + abs(cp - pp)
        c0_1 = cost[1] + abs(cp - pm)
        if c0_0 <= c0_1: ptr[i, 0] = 0; new_c0 = c0_0
        else:            ptr[i, 0] = 1; new_c0 = c0_1
        c1_0 = cost[0] + abs(cm - pp) + pen
        c1_1 = cost[1] + abs(cm - pm) + pen
        if c1_0 <= c1_1: ptr[i, 1] = 0; new_c1 = c1_0
        else:            ptr[i, 1] = 1; new_c1 = c1_1
        cost = np.array([new_c0, new_c1])

    flip = np.zeros(n, dtype=bool)
    s    = int(cost[1] < cost[0])
    for i in range(n - 1, -1, -1):
        flip[i] = bool(s)
        s = int(ptr[i, s])
    return flip

# ─────────────────────────────────────────────────────────────────────────────
# Point-wise ε″ spike correction
# ─────────────────────────────────────────────────────────────────────────────
def _fix_ei_spikes(
    eps_imag:  np.ndarray,
    ei_p:      np.ndarray,
    ei_m:      np.ndarray,
    flip:      np.ndarray,
    threshold: float = _EI_SPIKE_THRESH,
    kernel:    int   = _EI_SPIKE_KERNEL,
) -> np.ndarray:
    """
    After the DP corrects ε′ sign errors, check ε″ for isolated spikes
    that the ε′-only DP could not detect.

    A spike at point k is detected when its deviation from a local median
    exceeds threshold × σ.  The flip is accepted only if it moves ε″[k]
    closer to the median — preventing over-correction.
    """
    from scipy.signal import medfilt
    if kernel % 2 == 0:
        kernel += 1
    flip_new   = flip.copy()
    ei_current = eps_imag.copy()
    ei_ref     = medfilt(ei_current, kernel_size=kernel)
    residual   = ei_current - ei_ref
    sigma      = np.std(residual)
    if sigma < 1e-9:
        return flip_new
    for k in np.where(np.abs(residual) > threshold * sigma)[0]:
        ei_alt = ei_m[k] if not flip_new[k] else ei_p[k]
        if abs(ei_alt - ei_ref[k]) < abs(ei_current[k] - ei_ref[k]):
            flip_new[k]   = not flip_new[k]
            ei_current[k] = ei_alt
    return flip_new

# ─────────────────────────────────────────────────────────────────────────────
# ADC counts → calibrated magnitude and phase
# ─────────────────────────────────────────────────────────────────────────────
def load_spectrum(filepath: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Read a raw .TXT file and return calibrated |H(f)| and |φ(f)|.

    File format: space-separated, one row per frequency point.
        column 2 : magnitude ADC count  (0–4095)
        column 3 : phase ADC count      (0–4095)

    Returns
    -------
    mag     : (1110,)  linear transfer-function magnitude
    phs_abs : (1110,)  absolute phase in degrees (≥ 0; sign added by DP)
    """
    data  = np.loadtxt(filepath)
    mag_v = data[:, 2] / ADC_MAX * ADC_REF
    phs_v = data[:, 3] / ADC_MAX * ADC_REF
    mag   = 10 ** ((mag_v / MAG_OFFSET - MAG_OFFSET) / MAG_SLOPE / 20)
    phs   = (phs_v / MAG_OFFSET - PHS_OFFSET) / PHS_SLOPE + PHS_SHIFT
    return mag, np.maximum(phs, 0.0)

# ─────────────────────────────────────────────────────────────────────────────
# Main extraction  — called once per node file
# ─────────────────────────────────────────────────────────────────────────────
def extract_permittivity(
    filepath:      str,
    smooth:        bool  = True,
    penalty_alpha: float = _DP_PENALTY_ALPHA,
    ei_threshold:  float = _EI_SPIKE_THRESH,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extract ε′(f) and ε″(f) from one node .TXT file.

    Returns arrays over FREQS (frequencies > 10 MHz).

    Parameters
    ----------
    smooth        Apply Savitzky-Golay smoothing after DP (recommended).
    penalty_alpha DP flip penalty strength.  Lower = more aggressive.
    ei_threshold  ε″ spike detection sensitivity in σ units.
    """
    from scipy.signal import savgol_filter

    mag, phs_abs         = load_spectrum(filepath)
    er_p, ei_p, er_m, ei_m = _both_options(mag, phs_abs)

    flip     = _dp_sign_select(er_p, er_m, penalty_alpha=penalty_alpha)
    eps_real = np.where(flip, er_m, er_p)
    eps_imag = np.where(flip, ei_m, ei_p)

    flip     = _fix_ei_spikes(eps_imag, ei_p, ei_m, flip, threshold=ei_threshold)
    eps_real = np.where(flip, er_m, er_p)
    eps_imag = np.where(flip, ei_m, ei_p)

    if smooth:
        w        = _SG_WINDOW if _SG_WINDOW % 2 else _SG_WINDOW + 1
        eps_real = savgol_filter(eps_real, window_length=w, polyorder=_SG_ORDER)
        eps_imag = savgol_filter(eps_imag, window_length=w, polyorder=_SG_ORDER)

    return eps_real, eps_imag

# ─────────────────────────────────────────────────────────────────────────────
# Conductivity spectrum
# ─────────────────────────────────────────────────────────────────────────────
def sigma_spectrum(eps_imag: np.ndarray) -> np.ndarray:
    """
    Compute σ(f) = ε₀ · ε″ · 2πf  [dS/m] over FREQS.

    For high-clay soils no true DC plateau exists in 10–100 MHz.
    The minimum of σ(f) is the closest approximation to DC conductivity.
    """
    return EPS_0 * eps_imag * 2 * np.pi * FREQS * 10.0

# ─────────────────────────────────────────────────────────────────────────────
# Band-averaged EC extraction
# ─────────────────────────────────────────────────────────────────────────────
def extract_ec_band(
    eps_real: np.ndarray,
    eps_imag: np.ndarray,
    f_lo:     float,
    f_hi:     float,
) -> Tuple[float, float]:
    """
    Extract bulk EC and ε′ averaged over frequency band [f_lo, f_hi].

    Both quantities are averaged over the SAME band so the Hilhorst model
    receives matched inputs:
        σ_pore = σ_bulk × ε_water / (ε′ − ε_offset)

    Averaging over the band (typically 10–80 points) suppresses point
    noise and reduces the coefficient of variation compared with a single
    frequency pick.

    Returns
    -------
    sigma_bulk  : float  mean σ(f) [dS/m] over band
    eps_real_at : float  mean ε′(f) over band
    """
    mask = (FREQS >= f_lo) & (FREQS <= f_hi)
    sig  = EPS_0 * eps_imag[mask] * 2 * np.pi * FREQS[mask] * 10.0
    return float(np.mean(sig)), float(np.mean(eps_real[mask]))
