"""
services/keychain_manager.py
----------------------------
Secure OS keychain credential manager for optional online AI API keys.
Uses the Python 'keyring' library if available to store keys in:
- macOS Keychain
- Windows Credential Locker
- Linux Secret Service / Keyring

If 'keyring' is unavailable, maintains keys in transient in-memory memory for
the current session only. Never writes credentials to project files, .env, logs, or git.
"""

from typing import Optional, Dict, Any

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    keyring = None
    _KEYRING_AVAILABLE = False

_SERVICE_NAME = "LocalAI_DocSystem"
_SESSION_KEYS: Dict[str, str] = {}
_SESSION_CONFIGS: Dict[str, Dict[str, str]] = {}


def is_keyring_available() -> bool:
    """Returns True if the OS keychain provider is available via 'keyring'."""
    return _KEYRING_AVAILABLE


def store_provider_config(provider: str, config: Dict[str, str]):
    """Stores non-secret configuration (such as base URL or model name) in session memory."""
    key_name = provider.lower().strip()
    if key_name not in _SESSION_CONFIGS:
        _SESSION_CONFIGS[key_name] = {}
    _SESSION_CONFIGS[key_name].update(config)


def get_provider_config(provider: str) -> Dict[str, str]:
    """Retrieves non-secret provider configuration."""
    key_name = provider.lower().strip()
    return _SESSION_CONFIGS.get(key_name, {})


def store_api_key(provider: str, api_key: str) -> bool:
    """
    Stores an API key for the specified provider (e.g. 'anthropic', 'openai', 'gemini').
    Returns True if securely stored in OS keychain, False if kept in session memory.
    """
    key_name = provider.lower().strip()
    clean_key = (api_key or "").strip()
    if _KEYRING_AVAILABLE and keyring:
        try:
            keyring.set_password(_SERVICE_NAME, key_name, clean_key)
            return True
        except Exception:
            pass

    _SESSION_KEYS[key_name] = clean_key
    return False


def get_api_key(provider: str) -> Optional[str]:
    """
    Retrieves the stored API key for a provider.
    """
    key_name = provider.lower().strip()
    if _KEYRING_AVAILABLE and keyring:
        try:
            val = keyring.get_password(_SERVICE_NAME, key_name)
            if val:
                return val
        except Exception:
            pass

    return _SESSION_KEYS.get(key_name)


def delete_api_key(provider: str):
    """
    Deletes the API key for a provider from both OS keychain and session memory.
    """
    key_name = provider.lower().strip()
    if _KEYRING_AVAILABLE and keyring:
        try:
            keyring.delete_password(_SERVICE_NAME, key_name)
        except Exception:
            pass
    if key_name in _SESSION_KEYS:
        del _SESSION_KEYS[key_name]


def is_provider_configured(provider: str, is_local: bool = False) -> bool:
    """Checks if a provider has an API key configured (or is a local server needing no key)."""
    if is_local:
        return True
    key = get_api_key(provider)
    return bool(key and key.strip())


def get_key_storage_type(provider: str, is_local: bool = False) -> str:
    """
    Returns storage status:
    - 'local_no_key': Local server on device, no key required
    - 'keychain': Stored securely in OS keychain
    - 'memory': Stored in transient in-memory session (keyring unavailable)
    - 'none': Not configured
    """
    if is_local:
        return "local_no_key"
    key = get_api_key(provider)
    if not key:
        return "none"
    if _KEYRING_AVAILABLE and keyring:
        return "keychain"
    return "memory"


def mask_key(api_key: Optional[str]) -> str:
    """Returns a masked representation of an API key for safe UI display (e.g. '••••••••sk-1234')."""
    if not api_key:
        return ""
    clean = api_key.strip()
    if len(clean) <= 6:
        return "••••••••"
    return "••••••••" + clean[-4:]
