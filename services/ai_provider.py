"""
services/ai_provider.py
-----------------------
Abstract interface and client implementations for optional online AI Enhancement.
Supports OpenAI and Google Gemini providers with strict privacy controls.
All network calls occur ONLY when the user explicitly initiates and confirms them.
"""

import json
import urllib.request
import urllib.error
import re
from abc import ABC, abstractmethod
from typing import Dict, Type, Optional


class AIProviderError(Exception):
    """Raised when an online AI enhancement call fails."""
    pass


class BaseAIProvider(ABC):
    """Abstract base class for cloud AI enhancement providers."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _sanitize_error(self, message: str) -> str:
        """Removes API keys and sensitive tokens from error messages."""
        if not message:
            return ""
        sanitized = str(message)
        if self.api_key:
            sanitized = sanitized.replace(self.api_key, "[REDACTED_KEY]")
        # Redact ?key=... and &key=... query parameters
        sanitized = re.sub(r"([?&]key=)[^&\s'\"]+", r"\1[REDACTED_KEY]", sanitized)
        # Redact Google API key pattern (AIzaSy...)
        sanitized = re.sub(r"AIzaSy[A-Za-z0-9_-]{33}", "[REDACTED_KEY]", sanitized)
        return sanitized

    @abstractmethod
    def get_name(self) -> str:
        """Returns the human-readable provider name."""
        pass

    @abstractmethod
    def enhance_text(self, text: str, instructions: str = "") -> str:
        """
        Submits text to the provider for correction, formatting, or translation enhancement.
        Must be called ONLY after explicit user confirmation.
        """
        pass


class OpenAIProvider(BaseAIProvider):
    """Enhancement provider using OpenAI Chat Completions API."""

    def get_name(self) -> str:
        return "OpenAI (GPT-4o / GPT-4o-mini)"

    def enhance_text(self, text: str, instructions: str = "") -> str:
        if not self.api_key:
            raise AIProviderError("OpenAI API key is missing. Please enter your API key in Settings.")

        endpoint = "https://api.openai.com/v1/chat/completions"
        system_prompt = (
            "You are a professional multilingual document editor. "
            "Clean up OCR errors, restore proper punctuation, fix formatting, "
            "and preserve the original language and meaning exactly. Return only the enhanced text."
        )
        if instructions:
            system_prompt += f" Additional user instructions: {instructions}"

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as http_err:
            err_msg = http_err.read().decode("utf-8") if http_err.fp else str(http_err)
            raise AIProviderError(f"OpenAI API Error ({http_err.code}): {self._sanitize_error(err_msg)}")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            raise AIProviderError(f"Network request to OpenAI failed: {self._sanitize_error(str(e))}")


class GeminiProvider(BaseAIProvider):
    """Enhancement provider using Google Gemini API."""

    def get_name(self) -> str:
        return "Google Gemini (Gemini 1.5 Flash)"

    def enhance_text(self, text: str, instructions: str = "") -> str:
        if not self.api_key:
            raise AIProviderError("Gemini API key is missing. Please enter your API key in Settings.")

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        system_instruction = (
            "Clean up OCR noise and formatting, restoring proper punctuation "
            "while strictly preserving original multilingual text meaning and language."
        )
        if instructions:
            system_instruction += f" {instructions}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\nDocument Text:\n{text}"}
                    ]
                }
            ]
        }

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    return candidates[0]["content"]["parts"][0]["text"].strip()
                raise AIProviderError("Gemini returned empty candidate response.")
        except urllib.error.HTTPError as http_err:
            err_msg = http_err.read().decode("utf-8") if http_err.fp else str(http_err)
            raise AIProviderError(f"Gemini API Error ({http_err.code}): {self._sanitize_error(err_msg)}")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            raise AIProviderError(f"Network request to Gemini failed: {self._sanitize_error(str(e))}")


class GenericOpenAICompatibleProvider(BaseAIProvider):
    """
    Enhancement provider connecting to any custom OpenAI-compatible endpoint
    (e.g., local Ollama, vLLM, OpenRouter, Together AI, LM Studio, etc.).
    Base URL, model name, and API key are completely user-configurable.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:11434/v1",
        model_name: str = "qwen2.5:7b",
    ):
        super().__init__(api_key=api_key)
        self.base_url = (base_url or "http://localhost:11434/v1").rstrip("/")
        self.model_name = model_name or "qwen2.5:7b"

    def get_name(self) -> str:
        return f"OpenAI-Compatible ({self.model_name} @ {self.base_url})"

    def enhance_text(self, text: str, instructions: str = "") -> str:
        endpoint = f"{self.base_url}/chat/completions"
        system_prompt = (
            "You are a professional multilingual document editor. "
            "Clean up OCR errors, restore proper punctuation, fix formatting, "
            "and preserve the original language and meaning exactly. Return only the enhanced text."
        )
        if instructions:
            system_prompt += f" Additional user instructions: {instructions}"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as http_err:
            err_msg = http_err.read().decode("utf-8") if http_err.fp else str(http_err)
            raise AIProviderError(f"API Error ({http_err.code}): {self._sanitize_error(err_msg)}")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            raise AIProviderError(f"Network request to {endpoint} failed: {self._sanitize_error(str(e))}")


class MockAIProvider(BaseAIProvider):
    """Mock provider for unit testing without performing real external network calls."""

    def get_name(self) -> str:
        return "Mock AI Provider (Offline Test)"

    def enhance_text(self, text: str, instructions: str = "") -> str:
        if not self.api_key:
            raise AIProviderError("Mock API key is missing.")
        return f"[AI Enhanced] {text.strip()}"


_PROVIDER_REGISTRY: Dict[str, Type[BaseAIProvider]] = {
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "mock": MockAIProvider,
    "openai_compatible": GenericOpenAICompatibleProvider,
    "generic": GenericOpenAICompatibleProvider,
}


def get_ai_provider(
    provider_name: str,
    api_key: str,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseAIProvider:
    key = provider_name.lower().strip()
    if key in ("openai_compatible", "generic", "custom", "openai-compatible"):
        return GenericOpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url or "http://localhost:11434/v1",
            model_name=model_name or "qwen2.5:7b",
        )
    if key not in _PROVIDER_REGISTRY:
        supported = ", ".join(_PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown AI provider '{provider_name}'. Supported: {supported}")
    return _PROVIDER_REGISTRY[key](api_key=api_key)
