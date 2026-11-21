"""
services package
----------------
Supporting services for the Local AI Document System (keychain, AI providers).
"""

from services.keychain_manager import (
    store_api_key,
    get_api_key,
    delete_api_key,
    is_keyring_available,
)
from services.ai_provider import (
    BaseAIProvider,
    OpenAIProvider,
    GeminiProvider,
    MockAIProvider,
    AIProviderError,
    get_ai_provider,
)

__all__ = [
    "store_api_key",
    "get_api_key",
    "delete_api_key",
    "is_keyring_available",
    "BaseAIProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "MockAIProvider",
    "AIProviderError",
    "get_ai_provider",
]
