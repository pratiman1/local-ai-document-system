"""
services/ai_provider.py
-----------------------
Universal multi-provider client architecture for optional online AI Enhancement:
- Abstract Base Provider (BaseAIProvider)
- Anthropic Claude (Anthropic Messages API)
- OpenAI (Chat Completions API)
- Google Gemini (Gemini generateContent REST API)
- Generic OpenAI-Compatible Provider (Qwen, Llama, DeepSeek via custom endpoints)
- Local Server Provider (Ollama, LM Studio, vLLM on localhost, 100% Offline)
- Mock Provider (Offline testing)

Privacy & Security Guarantees:
1. Strictly 100% Offline by default.
2. No network call occurs without explicit user consent.
3. API keys are never logged, printed, or saved to file.
4. Error messages strictly sanitize all keys and payload text.
5. Standard library urllib.request used exclusively (zero unnecessary dependencies).
6. Local servers are recognized as local and display 'Offline' in the UI.
"""

import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Type, List, Union

try:
    import certifi
    _CERTIFI_CA_BUNDLE = certifi.where()
except ImportError:
    _CERTIFI_CA_BUNDLE = None


def get_secure_ssl_context() -> ssl.SSLContext:
    """
    Creates a strictly verified SSLContext for secure HTTPS requests.
    Security guarantees:
    - Certificate verification is ALWAYS strictly enforced (ssl.CERT_REQUIRED).
    - Hostname checking is ALWAYS strictly enabled (check_hostname = True).
    - Unverified SSL contexts are NEVER used.
    - If certifi is available, loads Mozilla's vetted root CA bundle (resolves macOS missing local issuer certificate).
    - Falls back to system default verify paths if certifi is not present.
    """
    if _CERTIFI_CA_BUNDLE and os.path.isfile(_CERTIFI_CA_BUNDLE):
        ctx = ssl.create_default_context(cafile=_CERTIFI_CA_BUNDLE)
    else:
        ctx = ssl.create_default_context()

    # Strictly guarantee verification is enabled
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    return ctx

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "ai_providers.json"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB safety limit
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RETRIES = 2


class AIProviderError(Exception):
    """Raised when an AI provider call fails or returns an error."""
    def __init__(self, message: str, status_code: Optional[int] = None, is_auth_error: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.is_auth_error = is_auth_error


def load_provider_config() -> Dict[str, Any]:
    """Loads default example model names and documentation metadata from config/ai_providers.json."""
    if not CONFIG_PATH.is_file():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_local_endpoint(url: str) -> bool:
    """Returns True if the given endpoint URL points to localhost or loopback."""
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".local")
    except Exception:
        return "localhost" in url.lower() or "127.0.0.1" in url


class BaseAIProvider(ABC):
    """Abstract base class for all AI enhancement providers."""

    def __init__(self, api_key: str = "", model_name: str = "", is_local: bool = False):
        self.api_key = (api_key or "").strip()
        self.model_name = (model_name or "").strip()
        self.is_local = is_local

    def _sanitize_error(self, message: str) -> str:
        """Removes API keys, bearer tokens, and sensitive headers from error messages."""
        if not message:
            return ""
        sanitized = str(message)
        if self.api_key:
            sanitized = sanitized.replace(self.api_key, "[REDACTED_KEY]")
        # Redact Bearer tokens
        sanitized = re.sub(r"Bearer\s+[\w\-.]+", "Bearer [REDACTED_KEY]", sanitized, flags=re.IGNORECASE)
        # Redact x-api-key or x-goog-api-key
        sanitized = re.sub(r"(x-(?:goog-)?api-key:?\s*)[\w\-.]+", r"\1[REDACTED_KEY]", sanitized, flags=re.IGNORECASE)
        # Redact key in query params (?key=... or &key=...)
        sanitized = re.sub(r"([?&]key=)[^&\s'\"]+", r"\1[REDACTED_KEY]", sanitized)
        # Redact Google API key format (AIzaSy...)
        sanitized = re.sub(r"AIzaSy[A-Za-z0-9_-]{33}", "[REDACTED_KEY]", sanitized)
        return sanitized

    @abstractmethod
    def name(self) -> str:
        """Returns the human-readable provider name."""
        pass

    def get_name(self) -> str:
        """Alias for name() for backward compatibility."""
        return self.name()

    def get_host_name(self) -> str:
        """Returns the primary target hostname for transparent disclosure."""
        return "external server"

    def is_configured(self) -> bool:
        """Returns True if the provider is ready to send requests."""
        if self.is_local:
            return True
        return bool(self.api_key)

    def estimate_cost_info(self, text: str) -> Dict[str, Any]:
        """
        Estimates characters and approximate tokens sent.
        Does not claim hardcoded price facts; reminds the user to check provider rates.
        """
        chars = len(text)
        approx_tokens = max(1, chars // 4)
        est_kb = round(chars / 1024, 2)
        return {
            "character_count": chars,
            "approx_tokens": approx_tokens,
            "estimated_payload_kb": est_kb,
            "pricing_notice": (
                "No prices are hardcoded or guaranteed by this app. "
                "Consult the provider's official pricing page for active rates."
            ),
            "user_cost_estimate": "User-supplied / Not configured",
        }

    def describe_data_sent(
        self,
        text: str,
        task: str = "",
        source_lang: str = "eng",
        target_lang: str = "eng",
    ) -> str:
        """Describes exact data payload to be transmitted for transparent user consent."""
        chars = len(text)
        tokens = max(1, chars // 4)
        dest = "Local Server on this device (Zero data leaves computer)" if self.is_local else f"External server ({self.name()})"
        return (
            f"Destination: {dest}\n"
            f"Scope: Selected text ({chars:,} characters, ~{tokens:,} tokens)\n"
            f"Task: {task or 'General enhancement'}\n"
            f"Languages: {source_lang} -> {target_lang}\n"
            f"Included Data: Only the text snippet shown below. No document metadata or other pages are sent."
        )

    def build_prompt_parts(
        self,
        text: str,
        task: str = "grammar",
        source_lang: str = "eng",
        target_lang: str = "eng",
        user_instructions: str = "",
    ) -> Tuple[str, str]:
        """Builds standardized system prompt and user message for enhancement tasks."""
        task_lower = (task or "grammar").lower()

        if "grammar" in task_lower or "spelling" in task_lower:
            sys_prompt = (
                f"You are a professional multilingual document editor. "
                f"Fix grammar, spelling, punctuation, and syntax in the provided text ({target_lang}). "
                f"Strictly preserve all numbers, proper names, section headings, and glossary terms. "
                f"Do not add, remove, or fabricate content. Return ONLY the edited text."
            )
        elif "doubtful" in task_lower or "translation" in task_lower or "source" in task_lower:
            sys_prompt = (
                f"You are a professional multilingual translator and editor. "
                f"Review the translated text against the source text ({source_lang} -> {target_lang}). "
                f"Fix mistranslated idioms, false friends, and awkward phrasing while strictly preserving "
                f"the original meaning, numbers, proper names, section headings, and domain glossary terms. "
                f"Do not add or remove content. Return ONLY the corrected translation."
            )
        elif "natural" in task_lower or "rewrite" in task_lower or "fluent" in task_lower:
            sys_prompt = (
                f"You are a professional editor. Rewrite the translation to sound natural, fluent, "
                f"and idiomatic in {target_lang}. Strictly preserve the original meaning, all numbers, "
                f"proper names, section headings, and glossary terms. Do not add or remove information. "
                f"Return ONLY the rewritten text."
            )
        else:
            sys_prompt = (
                f"You are a professional multilingual document editor ({target_lang}). "
                f"Enhance the text while strictly preserving all numbers, names, headings, and glossary terms. "
                f"Do not add or remove content. Return ONLY the enhanced text."
            )

        if user_instructions:
            sys_prompt += f" User instructions: {user_instructions}"

        user_content = text.strip()
        return sys_prompt, user_content

    @abstractmethod
    def enhance(
        self,
        text: str,
        task: str = "grammar",
        source_lang: str = "eng",
        target_lang: str = "eng",
        user_instructions: str = "",
    ) -> str:
        """Executes the enhancement request after explicit user confirmation."""
        pass

    def enhance_text(self, text: str, instructions: str = "") -> str:
        """Alias for enhance() for backward compatibility."""
        return self.enhance(text, task="grammar", user_instructions=instructions)

    def _execute_http_request(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        method: str = "POST",
    ) -> Dict[str, Any]:
        """
        Executes HTTP request using Python standard library urllib with retry logic,
        strict timeouts, response size limits, and sanitized error messages.
        """
        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body_bytes, headers=headers, method=method)

        ssl_ctx = None
        if endpoint.lower().startswith("https://"):
            ssl_ctx = get_secure_ssl_context()

        last_err: Optional[Exception] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS, context=ssl_ctx) as resp:
                    resp_bytes = resp.read(MAX_RESPONSE_BYTES + 1)
                    if len(resp_bytes) > MAX_RESPONSE_BYTES:
                        raise AIProviderError("Response exceeded maximum permitted size (5 MB limit).")
                    decoded = resp_bytes.decode("utf-8")
                    try:
                        return json.loads(decoded)
                    except json.JSONDecodeError:
                        raise AIProviderError("Malformed response received: Response is not valid JSON.")

            except urllib.error.HTTPError as http_err:
                code = http_err.code
                err_text = ""
                try:
                    if http_err.fp:
                        err_text = http_err.read().decode("utf-8")
                except Exception:
                    pass

                sanitized_msg = self._sanitize_error(err_text or str(http_err))

                if code in (401, 403):
                    raise AIProviderError(
                        f"Authentication failed ({code}): API key appears invalid or unauthorized. "
                        f"Please check your API key in Settings.",
                        status_code=code,
                        is_auth_error=True,
                    )
                elif code == 429:
                    last_err = AIProviderError(
                        f"Rate limit or quota exhausted ({code}): Provider rate limit reached. "
                        f"Check your account billing / rate limits.",
                        status_code=code,
                    )
                elif code in (400, 422):
                    raise AIProviderError(
                        f"Invalid request or content refused ({code}): {sanitized_msg}",
                        status_code=code,
                    )
                elif code in (500, 502, 503, 504):
                    last_err = AIProviderError(
                        f"Provider server error ({code}): Temporary server glitch. {sanitized_msg}",
                        status_code=code,
                    )
                else:
                    raise AIProviderError(
                        f"Provider HTTP error ({code}): {sanitized_msg}",
                        status_code=code,
                    )

            except urllib.error.URLError as url_err:
                sanitized_reason = self._sanitize_error(str(url_err.reason))
                last_err = AIProviderError(
                    f"Network error: Unable to connect to {urllib.parse.urlparse(endpoint).netloc}. "
                    f"Details: {sanitized_reason}"
                )
            except Exception as ex:
                if isinstance(ex, AIProviderError):
                    raise
                last_err = AIProviderError(f"Request failed: {self._sanitize_error(str(ex))}")

            # Retry with short backoff on transient errors (rate limit or 5xx)
            if attempt < MAX_RETRIES:
                time.sleep(1.0 * (attempt + 1))

        if last_err:
            raise last_err
        raise AIProviderError("Request failed after retries.")


class AnthropicProvider(BaseAIProvider):
    """
    Anthropic Claude client using the Anthropic Messages API.
    Official Documentation: https://docs.anthropic.com/en/api/messages
    Endpoint: POST https://api.anthropic.com/v1/messages
    """

    def __init__(self, api_key: str, model_name: str = "claude-3-5-sonnet-20241022"):
        super().__init__(api_key=api_key, model_name=model_name or "claude-3-5-sonnet-20241022")

    def name(self) -> str:
        return f"Anthropic Claude ({self.model_name})"

    def get_host_name(self) -> str:
        return "api.anthropic.com"

    def enhance(
        self,
        text: str,
        task: str = "grammar",
        source_lang: str = "eng",
        target_lang: str = "eng",
        user_instructions: str = "",
    ) -> str:
        if not self.api_key:
            raise AIProviderError(
                "Anthropic API key is missing. Please enter your Anthropic API key in Settings.",
                is_auth_error=True,
            )

        endpoint = "https://api.anthropic.com/v1/messages"
        sys_prompt, user_content = self.build_prompt_parts(
            text, task=task, source_lang=source_lang, target_lang=target_lang, user_instructions=user_instructions
        )

        payload = {
            "model": self.model_name,
            "max_tokens": 4096,
            "system": sys_prompt,
            "messages": [
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        data = self._execute_http_request(endpoint, payload, headers)

        try:
            content_list = data.get("content", [])
            for block in content_list:
                if block.get("type") == "text":
                    return block.get("text", "").strip()
            if content_list and "text" in content_list[0]:
                return content_list[0]["text"].strip()
            raise AIProviderError("Anthropic response contained no text block.")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            raise AIProviderError(f"Failed to parse Anthropic response: {self._sanitize_error(str(e))}")


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI client using the Chat Completions API.
    Official Documentation: https://platform.openai.com/docs/api-reference/chat/create
    Endpoint: POST https://api.openai.com/v1/chat/completions
    """

    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        super().__init__(api_key=api_key, model_name=model_name or "gpt-4o-mini")

    def name(self) -> str:
        return f"OpenAI ({self.model_name})"

    def get_host_name(self) -> str:
        return "api.openai.com"

    def enhance(
        self,
        text: str,
        task: str = "grammar",
        source_lang: str = "eng",
        target_lang: str = "eng",
        user_instructions: str = "",
    ) -> str:
        if not self.api_key:
            raise AIProviderError(
                "OpenAI API key is missing. Please enter your OpenAI API key in Settings.",
                is_auth_error=True,
            )

        endpoint = "https://api.openai.com/v1/chat/completions"
        sys_prompt, user_content = self.build_prompt_parts(
            text, task=task, source_lang=source_lang, target_lang=target_lang, user_instructions=user_instructions
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        data = self._execute_http_request(endpoint, payload, headers)

        try:
            choices = data.get("choices", [])
            if choices and "message" in choices[0]:
                return choices[0]["message"].get("content", "").strip()
            raise AIProviderError("OpenAI response contained no choices or message content.")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            raise AIProviderError(f"Failed to parse OpenAI response: {self._sanitize_error(str(e))}")


class GeminiProvider(BaseAIProvider):
    """
    Google Gemini client using the generateContent REST API.
    Official Documentation: https://ai.google.dev/api/generate-content
    Endpoint: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    """

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        super().__init__(api_key=api_key, model_name=model_name or "gemini-1.5-flash")

    def name(self) -> str:
        return f"Google Gemini ({self.model_name})"

    def get_host_name(self) -> str:
        return "generativelanguage.googleapis.com"

    def enhance(
        self,
        text: str,
        task: str = "grammar",
        source_lang: str = "eng",
        target_lang: str = "eng",
        user_instructions: str = "",
    ) -> str:
        if not self.api_key:
            raise AIProviderError(
                "Gemini API key is missing. Please enter your Gemini API key in Settings.",
                is_auth_error=True,
            )

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        sys_prompt, user_content = self.build_prompt_parts(
            text, task=task, source_lang=source_lang, target_lang=target_lang, user_instructions=user_instructions
        )

        payload = {
            "systemInstruction": {
                "parts": [{"text": sys_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_content}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2
            }
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        data = self._execute_http_request(endpoint, payload, headers)

        try:
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip()
            raise AIProviderError("Gemini returned empty candidate or blocked content response.")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            raise AIProviderError(f"Failed to parse Gemini response: {self._sanitize_error(str(e))}")


class GenericOpenAICompatibleProvider(BaseAIProvider):
    """
    Generic client supporting any custom OpenAI-compatible server or cloud provider:
    - Qwen, Llama, DeepSeek via Together AI, Groq, OpenRouter, vLLM, etc.
    - Local servers on localhost (Ollama, LM Studio, llama.cpp, etc.)
    Official Documentation: https://platform.openai.com/docs/api-reference/chat
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "http://localhost:11434/v1",
        model_name: str = "qwen2.5:7b",
        is_local: Optional[bool] = None,
    ):
        clean_base = (base_url or "http://localhost:11434/v1").rstrip("/")
        local_flag = is_local if is_local is not None else is_local_endpoint(clean_base)
        super().__init__(api_key=api_key, model_name=model_name or "qwen2.5:7b", is_local=local_flag)
        self.base_url = clean_base

    def name(self) -> str:
        prefix = "Local Server (Offline)" if self.is_local else "OpenAI-Compatible"
        return f"{prefix} ({self.model_name} @ {self.base_url})"

    def get_host_name(self) -> str:
        try:
            return urllib.parse.urlparse(self.base_url).netloc or "external host"
        except Exception:
            return "external host"

    def enhance(
        self,
        text: str,
        task: str = "grammar",
        source_lang: str = "eng",
        target_lang: str = "eng",
        user_instructions: str = "",
    ) -> str:
        if not self.is_local and not self.api_key:
            raise AIProviderError(
                "API key is missing for custom cloud provider. Please enter your API key in Settings.",
                is_auth_error=True,
            )

        endpoint = f"{self.base_url}/chat/completions"
        sys_prompt, user_content = self.build_prompt_parts(
            text, task=task, source_lang=source_lang, target_lang=target_lang, user_instructions=user_instructions
        )

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = self._execute_http_request(endpoint, payload, headers)

        try:
            choices = data.get("choices", [])
            if choices and "message" in choices[0]:
                return choices[0]["message"].get("content", "").strip()
            raise AIProviderError("OpenAI-compatible server returned empty message choices.")
        except Exception as e:
            if isinstance(e, AIProviderError):
                raise
            raise AIProviderError(f"Failed to parse server response: {self._sanitize_error(str(e))}")


class DeepSeekProvider(GenericOpenAICompatibleProvider):
    """
    Dedicated DeepSeek AI provider using the OpenAI-compatible Chat Completions API.
    Official Documentation: https://api-docs.deepseek.com/
    Endpoint: POST https://api.deepseek.com/chat/completions
    Authentication: Authorization: Bearer <key>
    Supported Models: deepseek-chat (default, DeepSeek-V3), deepseek-reasoner (DeepSeek-R1)
    """

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
    ):
        clean_model = (model_name or "").strip() or "deepseek-chat"
        clean_url = (base_url or "").strip() or "https://api.deepseek.com"
        super().__init__(
            api_key=api_key,
            base_url=clean_url,
            model_name=clean_model,
            is_local=False,
        )

    def name(self) -> str:
        return f"DeepSeek ({self.model_name})"

    def get_host_name(self) -> str:
        return "api.deepseek.com"


class LocalServerProvider(GenericOpenAICompatibleProvider):
    """
    Dedicated local on-device provider (Ollama, LM Studio, vLLM on localhost).
    Strictly 100% Offline: zero data leaves this computer.
    Requires no API key.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model_name: str = "qwen2.5:7b",
        api_key: str = "",
    ):
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name, is_local=True)

    def name(self) -> str:
        return f"Local Model Server ({self.model_name} @ {self.base_url})"

    def get_host_name(self) -> str:
        return "localhost (on-device)"


class MockAIProvider(BaseAIProvider):
    """Mock provider for unit testing without performing external network calls."""

    def __init__(self, api_key: str = "mock-key", model_name: str = "mock-model"):
        super().__init__(api_key=api_key, model_name=model_name)

    def name(self) -> str:
        return "Mock AI Provider (Offline Test)"

    def get_host_name(self) -> str:
        return "localhost (test-mock)"

    def enhance(
        self,
        text: str,
        task: str = "grammar",
        source_lang: str = "eng",
        target_lang: str = "eng",
        user_instructions: str = "",
    ) -> str:
        if not self.api_key:
            raise AIProviderError("Mock API key is missing.", is_auth_error=True)
        return f"[AI Enhanced: {task}] {text.strip()}"


_PROVIDER_CLASSES: Dict[str, Type[BaseAIProvider]] = {
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "google": GeminiProvider,
    "deepseek": DeepSeekProvider,
    "openai_compatible": GenericOpenAICompatibleProvider,
    "generic": GenericOpenAICompatibleProvider,
    "local_server": LocalServerProvider,
    "local": LocalServerProvider,
    "mock": MockAIProvider,
}


def get_ai_provider(
    provider_name: str,
    api_key: str = "",
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
) -> BaseAIProvider:
    """Factory creating configured provider instance."""
    key = provider_name.lower().strip()
    config_data = load_provider_config().get("providers", {})
    provider_meta = config_data.get(key, {})

    resolved_model = model_name or provider_meta.get("default_model", "")

    if key in ("anthropic", "claude"):
        return AnthropicProvider(api_key=api_key, model_name=resolved_model or "claude-3-5-sonnet-20241022")
    elif key in ("openai",):
        return OpenAIProvider(api_key=api_key, model_name=resolved_model or "gpt-4o-mini")
    elif key in ("gemini", "google"):
        return GeminiProvider(api_key=api_key, model_name=resolved_model or "gemini-1.5-flash")
    elif key in ("deepseek",):
        b_url = base_url or provider_meta.get("default_base_url", "https://api.deepseek.com")
        return DeepSeekProvider(api_key=api_key, base_url=b_url, model_name=resolved_model or "deepseek-chat")
    elif key in ("local_server", "local"):
        b_url = base_url or provider_meta.get("default_base_url", "http://localhost:11434/v1")
        return LocalServerProvider(base_url=b_url, model_name=resolved_model or "qwen2.5:7b", api_key=api_key)
    elif key in ("openai_compatible", "generic", "custom"):
        b_url = base_url or provider_meta.get("default_base_url", "https://api.together.xyz/v1")
        return GenericOpenAICompatibleProvider(api_key=api_key, base_url=b_url, model_name=resolved_model or "Qwen/Qwen2.5-72B-Instruct")
    elif key in ("mock",):
        return MockAIProvider(api_key=api_key or "mock-key", model_name=resolved_model or "mock-model")

    supported = ", ".join(["anthropic", "openai", "gemini", "deepseek", "openai_compatible", "local_server"])
    raise ValueError(f"Unknown AI provider '{provider_name}'. Supported: {supported}")
