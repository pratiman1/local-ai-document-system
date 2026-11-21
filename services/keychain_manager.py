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

from typing import Optional, Dict

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
    _SESSION_CONFIGS[key_name] = dict(config)


def get_provider_config(provider: str) -> Dict[str, str]:
    """Retrieves non-secret provider configuration."""
    key_name = provider.lower().strip()
    return _SESSION_CONFIGS.get(key_name, {})


def store_api_key(provider: str, api_key: str) -> bool:
    """
    Stores an API key for the specified provider (e.g. 'openai', 'gemini').
    Returns True if securely stored in OS keychain, False if kept in session memory.
    """
    key_name = provider.lower().strip()
    if _KEYRING_AVAILABLE and keyring:
        try:
            keyring.set_password(_SERVICE_NAME, key_name, api_key)
            return True
        except Exception:
            pass

    _SESSION_KEYS[key_name] = api_key
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
    Deletes the API key for a provider.
    """
    key_name = provider.lower().strip()
    if _KEYRING_AVAILABLE and keyring:
        try:
            keyring.delete_password(_SERVICE_NAME, key_name)
        except Exception:
            pass
    if key_name in _SESSION_KEYS:
        del _SESSION_KEYS[key_name]
