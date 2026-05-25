"""
setup.keys — OS-keystore helpers for non-AI API keys.

Same pattern as ai.providers: each end-user supplies their own key, the
key is stored encrypted via the `keyring` package (Windows Credential
Manager / macOS Keychain / Linux Secret Service), and the app ships with
no keys baked in.

Currently manages: OpenWeather. Add new services by adding another pair
of get_*/set_*/clear_* helpers using the same _KEYRING_SERVICE constant.
"""
from __future__ import annotations
import os

try:
    import keyring   # type: ignore
    _HAS_KEYRING = True
except Exception:
    _HAS_KEYRING = False


# Shared with ai.providers — same service name so all of this app's
# credentials show up under one entry in the OS credential manager.
_KEYRING_SERVICE = "SoilSenseMonitor"

# Slot names within the service. These are arbitrary strings; pick once
# and stick with them so existing user keys aren't orphaned.
_SLOT_OPENWEATHER = "openweather"


# ── OpenWeather ─────────────────────────────────────────────────────────
def get_weather_key() -> str | None:
    """Return the user's OpenWeather key, preferring the OS keystore.
    Falls back to API_KEY / OPENWEATHER_API_KEY env vars for dev setups."""
    if _HAS_KEYRING:
        try:
            k = keyring.get_password(_KEYRING_SERVICE, _SLOT_OPENWEATHER)
            if k:
                return k
        except Exception:
            pass
    return (os.environ.get("OPENWEATHER_API_KEY")
            or os.environ.get("API_KEY")
            or None)


def set_weather_key(key: str) -> tuple[bool, str]:
    """Save OpenWeather key to OS keystore. Returns (ok, message)."""
    if not _HAS_KEYRING:
        return False, (
            "keyring package not installed — "
            "run: pip install keyring"
        )
    try:
        keyring.set_password(_KEYRING_SERVICE, _SLOT_OPENWEATHER, key)
        return True, "Saved to OS credential store."
    except Exception as e:
        return False, f"Failed to save: {e}"


def clear_weather_key() -> None:
    if _HAS_KEYRING:
        try:
            keyring.delete_password(_KEYRING_SERVICE, _SLOT_OPENWEATHER)
        except Exception:
            pass


def has_weather_key() -> bool:
    return bool(get_weather_key())


# ── Convenience: is any API key configured at all? ──────────────────────
def has_any_key() -> bool:
    """True if at least one user-configured API key exists (AI or weather).
    Used by AppMain to decide whether to show the first-run setup dialog."""
    if has_weather_key():
        return True
    try:
        from ai.providers import is_configured
        return bool(is_configured())
    except Exception:
        return False


def keyring_available() -> bool:
    return _HAS_KEYRING
