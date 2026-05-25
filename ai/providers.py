"""
ai.providers — multi-provider AI backend.

Lets the app call Anthropic Claude, OpenAI GPT, or Google Gemini with a
single uniform interface. Each user supplies their own API key via the
AI Settings dialog; keys are stored in the OS credential store
(Windows Credential Manager / macOS Keychain / Linux Secret Service)
via the `keyring` package — never in any file shipped with the app.

User preference (which provider + model) lives in a tiny JSON file
under the user's home directory, NOT alongside the app source.
"""
from __future__ import annotations
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

# ── optional deps ───────────────────────────────────────────────────────
try:
    import keyring  # type: ignore
    _HAS_KEYRING = True
except Exception:
    _HAS_KEYRING = False


_KEYRING_SERVICE = "SoilSenseMonitor"
_SETTINGS_DIR    = Path.home() / ".soilsense"
_SETTINGS_FILE   = _SETTINGS_DIR / "ai_settings.json"


# ── provider classes ────────────────────────────────────────────────────
@dataclass(frozen=True)
class ProviderInfo:
    """Static metadata for a provider — shown in the Settings UI."""
    name:          str        # internal id ("anthropic", "openai", "gemini")
    display:       str        # UI label
    key_env_var:   str        # fallback env var for power users
    docs_url:      str        # where the user gets a key
    pricing_note:  str        # short blurb shown in Settings
    default_model: str
    models:        tuple[str, ...]


class AIProvider(ABC):
    info: ProviderInfo

    # ── key storage (keyring + env-var fallback) ────────────────────────
    @classmethod
    def get_key(cls) -> str | None:
        if _HAS_KEYRING:
            try:
                k = keyring.get_password(_KEYRING_SERVICE, cls.info.name)
                if k:
                    return k
            except Exception:
                pass
        return os.environ.get(cls.info.key_env_var) or None

    @classmethod
    def set_key(cls, key: str) -> tuple[bool, str]:
        """Save key to keyring. Returns (ok, message)."""
        if not _HAS_KEYRING:
            return False, (
                "keyring package not installed.\n"
                "Run:  pip install keyring\n"
                "(Required to securely store API keys per user.)"
            )
        try:
            keyring.set_password(_KEYRING_SERVICE, cls.info.name, key)
            return True, "Saved to OS credential store."
        except Exception as e:
            return False, f"Failed to save key: {e}"

    @classmethod
    def clear_key(cls) -> None:
        if _HAS_KEYRING:
            try:
                keyring.delete_password(_KEYRING_SERVICE, cls.info.name)
            except Exception:
                pass

    @classmethod
    def has_key(cls) -> bool:
        return bool(cls.get_key())

    # ── unified API ─────────────────────────────────────────────────────
    @abstractmethod
    def generate(self, prompt: str, model: str, max_tokens: int) -> str:
        """Run a single non-streaming text generation. Raises on error."""


# ── Anthropic Claude ────────────────────────────────────────────────────
class AnthropicProvider(AIProvider):
    info = ProviderInfo(
        name          = "anthropic",
        display       = "Anthropic Claude",
        key_env_var   = "ANTHROPIC_API_KEY",
        docs_url      = "https://console.anthropic.com/settings/keys",
        pricing_note  = "Paid. Top quality. Often the most thorough reports.",
        default_model = "claude-opus-4-7",
        models        = (
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ),
    )

    def generate(self, prompt: str, model: str, max_tokens: int) -> str:
        import anthropic
        key = self.get_key()
        if not key:
            raise RuntimeError("No Anthropic API key configured.")
        client = anthropic.Anthropic(api_key=key)
        kwargs: dict = {
            "model":      model,
            "max_tokens": max_tokens,
            "messages":   [{"role": "user", "content": prompt}],
        }
        # Adaptive thinking on Opus (genuine reasoning lift on synthesis tasks)
        if model.startswith("claude-opus"):
            kwargs["thinking"] = {"type": "adaptive"}
        msg = client.messages.create(**kwargs)
        text = next(
            (b.text for b in msg.content if getattr(b, "type", None) == "text"),
            "",
        )
        if not text.strip():
            raise RuntimeError("Empty response from Anthropic.")
        return text


# ── OpenAI GPT ──────────────────────────────────────────────────────────
class OpenAIProvider(AIProvider):
    info = ProviderInfo(
        name          = "openai",
        display       = "OpenAI GPT",
        key_env_var   = "OPENAI_API_KEY",
        docs_url      = "https://platform.openai.com/api-keys",
        pricing_note  = "Paid. New accounts sometimes get free trial credits.",
        default_model = "gpt-4o",
        models        = (
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
        ),
    )

    def generate(self, prompt: str, model: str, max_tokens: int) -> str:
        from openai import OpenAI
        key = self.get_key()
        if not key:
            raise RuntimeError("No OpenAI API key configured.")
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise RuntimeError("Empty response from OpenAI.")
        return text


# ── Google Gemini (free tier) ───────────────────────────────────────────
class GeminiProvider(AIProvider):
    """Gemini via its OpenAI-compatible endpoint — no extra dependency
    beyond the openai package."""
    info = ProviderInfo(
        name          = "gemini",
        display       = "Google Gemini",
        key_env_var   = "GOOGLE_API_KEY",
        docs_url      = "https://aistudio.google.com/apikey",
        pricing_note  = "FREE tier — ~1500 requests/day on Flash models. Get a key at aistudio.google.com.",
        default_model = "gemini-2.0-flash",
        models        = (
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
        ),
    )

    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def generate(self, prompt: str, model: str, max_tokens: int) -> str:
        from openai import OpenAI
        key = self.get_key()
        if not key:
            raise RuntimeError("No Google API key configured.")
        client = OpenAI(api_key=key, base_url=self._BASE_URL)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise RuntimeError("Empty response from Gemini.")
        return text


PROVIDERS: dict[str, type[AIProvider]] = {
    "anthropic": AnthropicProvider,
    "openai":    OpenAIProvider,
    "gemini":    GeminiProvider,
}


# ── user preference persistence (NO keys here) ──────────────────────────
def load_settings() -> dict:
    """Read the current provider + model preference. Keys live in keyring."""
    try:
        with open(_SETTINGS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_settings(provider: str, model: str) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_FILE, "w") as f:
        json.dump({"provider": provider, "model": model}, f, indent=2)


def get_active_provider() -> tuple[type[AIProvider] | None, str]:
    """Returns (ProviderClass, model) for the user's selected provider, or
    (None, "") if no provider has been configured yet."""
    s = load_settings()
    name = s.get("provider")
    if not name or name not in PROVIDERS:
        return None, ""
    cls = PROVIDERS[name]
    model = s.get("model") or cls.info.default_model
    if model not in cls.info.models:
        model = cls.info.default_model
    return cls, model


def is_configured() -> bool:
    """True if a provider is selected AND has a usable key."""
    cls, _ = get_active_provider()
    return cls is not None and cls.has_key()


def keyring_available() -> bool:
    return _HAS_KEYRING
