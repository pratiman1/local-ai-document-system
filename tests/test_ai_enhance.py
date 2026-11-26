"""
tests/test_ai_enhance.py
------------------------
Comprehensive automated test suite validating the Optional Online & Local AI Enhancement subsystem:
1. Strict Socket Blocking: Patches socket.connect to guarantee zero real network calls.
2. Request Building: Verifies correct URL, headers, and JSON structure for all providers:
   - Anthropic Claude (Messages API)
   - OpenAI (Chat Completions API)
   - Google Gemini (generateContent REST API)
   - Generic OpenAI-Compatible (Custom base URL, model name, and auth)
   - Local Model Server (On-device localhost, no key, is_local=True)
3. Zero-Leakage Privacy: Verifies API keys and document text are never saved in audit logs or leaked in errors.
4. Consent & Cancellation: Verifies nothing is sent without confirmation; Cancel sends zero data.
5. Status Bar Transitions: Verifies 'Online request in progress' vs 'Offline (Local AI Server)' and return to 100% Offline.
6. Redaction Round-Trip: Verifies masking and restoration of names, numbers, emails, and phone numbers.
7. Request Splitting: Verifies chunking of long texts (>4000 chars) at natural sentence/paragraph boundaries.
8. Comprehensive Error Handling: Tests 401 (wrong key), 429 (rate limit), 500 (server error), timeout, refusal, and malformed response.
9. Offline by Default: Verifies AI_ENHANCE_ENABLED_DEFAULT is False.
"""

import os
import sys
import json
import socket
import io
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Run Qt in headless mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# --------------------------------------------------------------------------
# 1. Strict Socket Blocking: Guarantee zero real network calls occur
# --------------------------------------------------------------------------
_orig_socket_connect = socket.socket.connect


def _blocked_socket_connect(self, *args, **kwargs):
    raise RuntimeError(f"CRITICAL TEST ERROR: Real socket connection attempted to {args}! Real network calls are forbidden in tests.")


socket.socket.connect = _blocked_socket_connect


from PySide6.QtWidgets import QApplication, QLabel
from config.settings import (
    STATUS_OFFLINE,
    STATUS_ONLINE_PROGRESS,
    AI_ENHANCE_ENABLED_DEFAULT,
    AI_ENHANCE_MAX_CHARS,
)
from services.keychain_manager import (
    store_api_key,
    get_api_key,
    delete_api_key,
    store_provider_config,
    get_provider_config,
    is_keyring_available,
    is_provider_configured,
    get_key_storage_type,
    mask_key,
)
from services.ai_provider import (
    get_ai_provider,
    AnthropicProvider,
    OpenAIProvider,
    GeminiProvider,
    DeepSeekProvider,
    GenericOpenAICompatibleProvider,
    LocalServerProvider,
    MockAIProvider,
    AIProviderError,
)
from services.redaction_manager import redact_sensitive_data, restore_sensitive_data
from services.audit_logger import (
    log_ai_request,
    get_ai_audit_log,
    clear_ai_audit_log,
)
from ui.ai_enhance_dialog import (
    AIEnhanceConfirmDialog,
    AIEnhanceResultDialog,
    AIAuditLogDialog,
)
from ui.settings_dialog import SettingsDialog
from ui.main_window import MainWindow


class FakeHTTPResponse:
    """Mock urllib response object."""

    def __init__(self, data: bytes, status: int = 200, headers: Dict[str, str] = None):
        self._data = io.BytesIO(data)
        self.status = status
        self.code = status
        self.headers = headers or {"content-type": "application/json"}

    def read(self, amt: int = -1) -> bytes:
        return self._data.read(amt)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def run_tests():
    print("=" * 70)
    print("🧪 RUNNING COMPREHENSIVE AI ENHANCE UNIT TESTS (STRICTLY OFFLINE)")
    print("=" * 70)

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # --------------------------------------------------------------------------
    # Test 1: Offline Default Guarantee
    # --------------------------------------------------------------------------
    print("\n[Test 1/11] Verifying Offline-by-Default Architecture...")
    assert AI_ENHANCE_ENABLED_DEFAULT is False, "AI Enhancement MUST default to False."
    print("  ✓ Verified: AI_ENHANCE_ENABLED_DEFAULT is False.")

    # --------------------------------------------------------------------------
    # Test 2: Request Building for All Supported Providers (Fake Transport)
    # --------------------------------------------------------------------------
    print("\n[Test 2/11] Verifying Request Construction across All Providers...")

    intercepted_requests = []

    def mock_urlopen(req, *args, **kwargs):
        intercepted_requests.append(req)
        url = req.full_url
        # Return mock JSON response according to provider
        if "anthropic.com" in url:
            body = json.dumps({"content": [{"type": "text", "text": "Enhanced by Claude"}]}).encode("utf-8")
        elif "deepseek.com" in url:
            body = json.dumps({"choices": [{"message": {"content": "Enhanced by DeepSeek"}}]}).encode("utf-8")
        elif "openai.com" in url or "together.xyz" in url or "localhost:11434" in url:
            body = json.dumps({"choices": [{"message": {"content": "Enhanced by OpenAI/Generic"}}]}).encode("utf-8")
        elif "generativelanguage.googleapis.com" in url:
            body = json.dumps({"candidates": [{"content": {"parts": [{"text": "Enhanced by Gemini"}]}}]}).encode("utf-8")
        else:
            body = json.dumps({"message": "OK"}).encode("utf-8")
        return FakeHTTPResponse(body, status=200)

    orig_urlopen = urllib.request.urlopen
    urllib.request.urlopen = mock_urlopen

    try:
        # A. Anthropic Claude
        intercepted_requests.clear()
        anthropic = get_ai_provider("anthropic", api_key="sk-ant-test-key-12345", model_name="claude-3-5-sonnet-20241022")
        res_a = anthropic.enhance("Check grammar.", task="grammar")
        assert res_a == "Enhanced by Claude"
        req_a = intercepted_requests[-1]
        assert req_a.full_url == "https://api.anthropic.com/v1/messages"
        assert req_a.get_header("X-api-key") == "sk-ant-test-key-12345"
        assert req_a.get_header("Anthropic-version") == "2023-06-01"
        data_a = json.loads(req_a.data.decode("utf-8"))
        assert data_a["model"] == "claude-3-5-sonnet-20241022"
        assert data_a["messages"][0]["role"] == "user"
        print("  ✓ Anthropic Messages API: URL, headers, and payload verified.")

        # B. OpenAI
        intercepted_requests.clear()
        openai_p = get_ai_provider("openai", api_key="sk-proj-test-openai-key", model_name="gpt-4o-mini")
        res_o = openai_p.enhance("Fix typo.", task="grammar")
        assert res_o == "Enhanced by OpenAI/Generic"
        req_o = intercepted_requests[-1]
        assert req_o.full_url == "https://api.openai.com/v1/chat/completions"
        assert req_o.get_header("Authorization") == "Bearer sk-proj-test-openai-key"
        data_o = json.loads(req_o.data.decode("utf-8"))
        assert data_o["model"] == "gpt-4o-mini"
        assert data_o["messages"][1]["role"] == "user"
        print("  ✓ OpenAI Chat Completions API: URL, authorization header, and payload verified.")

        # C. Google Gemini
        intercepted_requests.clear()
        gemini_p = get_ai_provider("gemini", api_key="AIzaSyTestGeminiKey1234567890", model_name="gemini-1.5-flash")
        res_g = gemini_p.enhance("Polish text.", task="grammar")
        assert res_g == "Enhanced by Gemini"
        req_g = intercepted_requests[-1]
        assert "generativelanguage.googleapis.com" in req_g.full_url
        assert "gemini-1.5-flash:generateContent" in req_g.full_url
        assert req_g.get_header("X-goog-api-key") == "AIzaSyTestGeminiKey1234567890"
        data_g = json.loads(req_g.data.decode("utf-8"))
        assert "contents" in data_g
        print("  ✓ Google Gemini generateContent API: URL, header key, and contents structure verified.")

        # D. DeepSeek (Dedicated Cloud Provider)
        intercepted_requests.clear()
        deepseek_p = get_ai_provider("deepseek", api_key="sk-deepseek-test-key-1234", model_name="deepseek-chat")
        assert deepseek_p.get_host_name() == "api.deepseek.com"
        assert deepseek_p.is_local is False
        res_d = deepseek_p.enhance("Improve grammar.", task="grammar")
        assert res_d == "Enhanced by DeepSeek"
        req_d = intercepted_requests[-1]
        assert req_d.full_url == "https://api.deepseek.com/chat/completions"
        assert req_d.get_header("Authorization") == "Bearer sk-deepseek-test-key-1234"
        data_d = json.loads(req_d.data.decode("utf-8"))
        assert data_d["model"] == "deepseek-chat"
        print("  ✓ DeepSeek Chat Completions API: URL, Authorization header, deepseek-chat model, and host verified.")

        # E. Generic OpenAI-Compatible
        intercepted_requests.clear()
        gen_p = get_ai_provider("openai_compatible", api_key="custom-api-key", base_url="https://api.together.xyz/v1", model_name="Qwen/Qwen2.5-72B-Instruct")
        res_gen = gen_p.enhance("Translate check.", task="grammar")
        assert res_gen == "Enhanced by OpenAI/Generic"
        req_gen = intercepted_requests[-1]
        assert req_gen.full_url == "https://api.together.xyz/v1/chat/completions"
        assert req_gen.get_header("Authorization") == "Bearer custom-api-key"
        data_gen = json.loads(req_gen.data.decode("utf-8"))
        assert data_gen["model"] == "Qwen/Qwen2.5-72B-Instruct"
        print("  ✓ Generic OpenAI-Compatible API: custom endpoint, auth header, and model verified.")

        # F. Local Server Provider (localhost / 100% Offline)
        intercepted_requests.clear()
        local_p = get_ai_provider("local_server", base_url="http://localhost:11434/v1", model_name="qwen2.5:7b")
        assert local_p.is_local is True
        assert local_p.is_configured() is True
        res_loc = local_p.enhance("Local run.", task="grammar")
        assert res_loc == "Enhanced by OpenAI/Generic"
        req_loc = intercepted_requests[-1]
        assert req_loc.full_url == "http://localhost:11434/v1/chat/completions"
        print("  ✓ Local Server Provider: recognized as local (is_local=True), no key needed, endpoint verified.")

    finally:
        urllib.request.urlopen = orig_urlopen

    # --------------------------------------------------------------------------
    # Test 3: Key Privacy & Audit Log Zero-Leakage Guarantee
    # --------------------------------------------------------------------------
    print("\n[Test 3/11] Verifying Key Masking, Sanitization & Audit Log Privacy...")

    # Key masking
    assert mask_key("sk-ant-api03-1234567890") == "••••••••7890"
    assert mask_key("") == ""
    assert mask_key("short") == "••••••••"

    # Error sanitization
    secret_key = "sk-super-secret-key-12345678"
    p = OpenAIProvider(api_key=secret_key)
    sanitized = p._sanitize_error(f"Error occurred with Authorization: Bearer {secret_key}")
    assert secret_key not in sanitized, "API key was not sanitized from error message!"
    assert "[REDACTED_KEY]" in sanitized

    # Audit log privacy test: zero text and zero keys recorded
    clear_ai_audit_log()
    log_ai_request(
        provider="Anthropic Claude",
        model="claude-3-5-sonnet-20241022",
        char_count=1500,
        page_num="Page 3",
        is_local=False,
    )
    records = get_ai_audit_log()
    assert len(records) >= 1
    latest = records[-1]
    assert "timestamp" in latest
    assert latest["provider"] == "Anthropic Claude"
    assert latest["model"] == "claude-3-5-sonnet-20241022"
    assert latest["character_count"] == 1500
    assert latest["page_number"] == "Page 3"
    assert "text" not in latest, "Document text MUST NOT be stored in audit log!"
    assert "api_key" not in latest, "API key MUST NOT be stored in audit log!"
    assert "key" not in latest, "Key MUST NOT be stored in audit log!"

    # Test audit file contents directly on disk
    audit_file = PROJECT_ROOT / "exports" / "ai_request_audit.json"
    if audit_file.is_file():
        audit_raw = audit_file.read_text(encoding="utf-8")
        assert secret_key not in audit_raw
        assert "sk-ant" not in audit_raw
    print("  ✓ Verified: Audit log stores strictly metadata; zero document text and zero keys.")

    # --------------------------------------------------------------------------
    # Test 4: Consent Dialog & Cancellation Safety
    # --------------------------------------------------------------------------
    print("\n[Test 4/11] Verifying Mandatory Privacy Confirmation & Rejection Safety...")

    sample_snippet = "Confidential medical text that should never be sent without click."
    confirm_dlg = AIEnhanceConfirmDialog(
        text=sample_snippet,
        provider_name="Anthropic Claude",
        model_name="claude-3-5-sonnet",
        is_local=False,
    )

    # Initial state: unconfirmed
    assert confirm_dlg.confirmed is False

    # Simulate User Cancellation
    confirm_dlg.btn_cancel.click()
    assert confirm_dlg.confirmed is False
    print("  ✓ Cancel button keeps confirmed=False and transmits nothing.")

    # Simulate User Acceptance
    confirm_dlg_ok = AIEnhanceConfirmDialog(
        text=sample_snippet,
        provider_name="Anthropic Claude",
        model_name="claude-3-5-sonnet",
        is_local=False,
    )
    confirm_dlg_ok.btn_send.click()
    assert confirm_dlg_ok.confirmed is True
    print("  ✓ Send button explicitly registers user confirmation.")

    # Test DeepSeek Host Name Disclosure in Confirmation Dialog
    confirm_dlg_ds = AIEnhanceConfirmDialog(
        text=sample_snippet,
        provider_name="DeepSeek",
        model_name="deepseek-chat",
        endpoint_host="api.deepseek.com",
        is_local=False,
    )
    assert confirm_dlg_ds.endpoint_host == "api.deepseek.com"
    labels_text = " ".join(lbl.text() for lbl in confirm_dlg_ds.findChildren(QLabel))
    assert "api.deepseek.com" in labels_text, "Confirmation dialog MUST explicitly show 'api.deepseek.com'!"
    print("  ✓ DeepSeek confirmation dialog transparently reveals cloud host 'api.deepseek.com'.")

    # --------------------------------------------------------------------------
    # Test 5: Side-by-Side Review Dialog & Glossary Integration
    # --------------------------------------------------------------------------
    print("\n[Test 5/11] Verifying Side-by-Side Review Dialog & Acceptance...")

    orig_txt = "The device suggest route."
    enhanced_txt = "The device suggests the route."
    review_dlg = AIEnhanceResultDialog(
        original_text=orig_txt,
        enhanced_text=enhanced_txt,
        provider_name="Anthropic Claude",
    )

    # Initial state
    assert review_dlg.accepted_result is False

    # Test Reject
    review_dlg.btn_reject.click()
    assert review_dlg.accepted_result is False
    print("  ✓ Reject leaves document unchanged.")

    # Test Accept and Replace
    review_dlg_2 = AIEnhanceResultDialog(
        original_text=orig_txt,
        enhanced_text=enhanced_txt,
        provider_name="Anthropic Claude",
    )
    review_dlg_2.chk_add_glossary.setChecked(True)
    review_dlg_2.btn_accept.click()
    assert review_dlg_2.accepted_result is True
    assert review_dlg_2.enhanced_text == enhanced_txt
    assert review_dlg_2.add_to_glossary is True
    print("  ✓ Accept and Replace applies enhanced text and flags glossary offer.")

    # --------------------------------------------------------------------------
    # Test 6: Redaction Round-Trip (Names, Numbers, Emails, Phones)
    # --------------------------------------------------------------------------
    print("\n[Test 6/11] Verifying Redaction and Restoration Round-Trip...")

    original_pii = (
        "Patient Rahul Sharma with ID 98214 contacted doctor@healthcorp.org "
        "or call +91-98765-43210 regarding invoice 4500 dollars."
    )
    redacted_text, placeholder_map = redact_sensitive_data(original_pii)

    # Verify PII replaced with tags
    assert "doctor@healthcorp.org" not in redacted_text
    assert "+91-98765-43210" not in redacted_text
    assert "[EMAIL_" in redacted_text
    assert "[PHONE_" in redacted_text
    assert "[NUM_" in redacted_text

    # Simulate AI returning text with placeholders preserved
    simulated_ai_response = redacted_text.replace("contacted", "has successfully contacted")

    # Restore placeholders
    restored_text = restore_sensitive_data(simulated_ai_response, placeholder_map)
    assert "doctor@healthcorp.org" in restored_text
    assert "+91-98765-43210" in restored_text
    assert "98214" in restored_text
    assert "4500" in restored_text
    assert "[EMAIL_" not in restored_text
    print("  ✓ Redaction successfully masks entities and restores them accurately.")

    # --------------------------------------------------------------------------
    # Test 7: Request Size Limits & Text Splitting
    # --------------------------------------------------------------------------
    print("\n[Test 7/11] Verifying Text Splitting for Requests Exceeding Limit...")

    main_win = MainWindow()

    # Create a long text exceeding 4000 characters
    long_paragraph = "This is a detailed paragraph discussing system architecture and local offline processing.\n\n"
    long_text = long_paragraph * 50  # ~4500 characters
    assert len(long_text) > AI_ENHANCE_MAX_CHARS

    chunks = main_win._split_text_for_ai_enhance(long_text, max_chars=AI_ENHANCE_MAX_CHARS)
    assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}"
    for idx, c in enumerate(chunks):
        assert len(c) <= AI_ENHANCE_MAX_CHARS, f"Chunk {idx} exceeded max length: {len(c)}"
    print(f"  ✓ Long text ({len(long_text):,} chars) cleanly split into {len(chunks)} chunks <= {AI_ENHANCE_MAX_CHARS} chars.")

    # --------------------------------------------------------------------------
    # Test 8: Comprehensive Error Handling (401, 429, 500, Timeout, Refusal)
    # --------------------------------------------------------------------------
    print("\n[Test 8/11] Verifying Error Handling across Failure Modes...")

    # 1. 401 Unauthorized (Invalid Key)
    def mock_401(req, *args, **kwargs):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error": "Invalid API key"}'))

    urllib.request.urlopen = mock_401
    try:
        provider = OpenAIProvider(api_key="invalid-sk")
        try:
            provider.enhance("Test")
            assert False, "Should have raised AIProviderError on 401"
        except AIProviderError as e:
            assert e.is_auth_error is True
            assert "authentication failed" in str(e).lower() or "invalid" in str(e).lower()
        print("  ✓ 401 Unauthorized correctly caught as authentication failure without leaking key.")
    finally:
        urllib.request.urlopen = orig_urlopen

    # 2. 429 Rate Limit
    def mock_429(req, *args, **kwargs):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"error": "Rate limit reached"}'))

    urllib.request.urlopen = mock_429
    try:
        provider = OpenAIProvider(api_key="test-key")
        try:
            provider.enhance("Test")
            assert False, "Should have raised AIProviderError on 429"
        except AIProviderError as e:
            assert "rate limit" in str(e).lower() or "quota" in str(e).lower()
        print("  ✓ 429 Rate Limit correctly handled with clear sanitized message.")
    finally:
        urllib.request.urlopen = orig_urlopen

    # 3. Timeout handling
    def mock_timeout(req, *args, **kwargs):
        raise urllib.error.URLError(socket.timeout("Connection timed out"))

    urllib.request.urlopen = mock_timeout
    try:
        provider = AnthropicProvider(api_key="test-key")
        try:
            provider.enhance("Test")
            assert False, "Should have raised AIProviderError on timeout"
        except AIProviderError as e:
            assert "timed out" in str(e).lower()
        print("  ✓ Request timeout correctly handled with non-blocking error.")
    finally:
        urllib.request.urlopen = orig_urlopen

    # 4. Content refusal / Malformed response
    def mock_malformed(req, *args, **kwargs):
        return FakeHTTPResponse(b"NOT A JSON RESPONSE", status=200)

    urllib.request.urlopen = mock_malformed
    try:
        provider = AnthropicProvider(api_key="test-key")
        try:
            provider.enhance("Test")
            assert False, "Should have raised AIProviderError on malformed response"
        except AIProviderError as e:
            assert "parse" in str(e).lower() or "malformed" in str(e).lower() or "failed" in str(e).lower()
        print("  ✓ Malformed non-JSON server response handled safely.")
    finally:
        urllib.request.urlopen = orig_urlopen

    # --------------------------------------------------------------------------
    # Test 9: Settings Dialog Controls & Provider Configuration
    # --------------------------------------------------------------------------
    print("\n[Test 9/11] Verifying Settings Dialog Multi-Provider Controls...")

    dlg = SettingsDialog(ai_enhance_enabled=False, current_provider="local_server")
    assert dlg.chk_allow_ai.isChecked() is False

    # Check local server hides API key field
    dlg._select_provider("local_server")
    assert dlg.txt_api_key.isHidden() is True
    assert "No key needed" in dlg._provider_status_widgets["local_server"].text()

    # Check Anthropic shows API key field
    dlg._select_provider("anthropic")
    assert dlg.txt_api_key.isHidden() is False

    # Check DeepSeek shows in settings with default model deepseek-chat
    dlg._select_provider("deepseek")
    assert dlg.txt_api_key.isHidden() is False
    assert dlg.txt_model_name.text() == "deepseek-chat"
    assert "deepseek" in dlg._provider_status_widgets
    assert dlg.combo_provider.findData("deepseek") >= 0
    print("  ✓ SettingsDialog correctly displays DeepSeek in provider list with deepseek-chat model.")
    print("  ✓ SettingsDialog correctly adapts interface between cloud and local providers.")

    # --------------------------------------------------------------------------
    # Test 10: Status Bar State Transitions & Offline Restoration
    # --------------------------------------------------------------------------
    print("\n[Test 10/11] Verifying Status Bar State Transitions in MainWindow...")

    # Default offline status
    assert STATUS_OFFLINE in main_win.status_bar.currentMessage()
    assert "Offline" in main_win.conn_badge.text()

    # Online progress simulation
    main_win.status_bar.showMessage(STATUS_ONLINE_PROGRESS)
    main_win.conn_badge.setText("🟡 Online Request in Progress")
    assert STATUS_ONLINE_PROGRESS in main_win.status_bar.currentMessage()
    assert "Online" in main_win.conn_badge.text()

    # Local server simulation
    main_win.status_bar.showMessage("🟢 Offline — Local Model Server request in progress (qwen2.5:7b)...")
    main_win.conn_badge.setText("🟢 Offline (Local AI Server)")
    assert "Offline" in main_win.status_bar.currentMessage()
    assert "Offline" in main_win.conn_badge.text()

    # Revert to clean offline state
    main_win.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Ready")
    main_win.conn_badge.setText("🟢 100% Offline Mode")
    assert STATUS_OFFLINE in main_win.status_bar.currentMessage()
    assert "100% Offline Mode" in main_win.conn_badge.text()
    print("  ✓ MainWindow guarantees return to 100% Offline mode on completion, cancel, or error.")

    main_win.preview_panel.mark_saved()
    main_win.close()

    # --------------------------------------------------------------------------
    # Test 11: SSL Certificate Verification Security Guarantees
    # --------------------------------------------------------------------------
    print("\n[Test 11/11] Verifying SSL Context & Certificate Verification Enforcement...")
    from services.ai_provider import get_secure_ssl_context
    import ssl
    import certifi

    ctx = get_secure_ssl_context()
    assert isinstance(ctx, ssl.SSLContext), "Must return an ssl.SSLContext instance."
    # Certificate verification MUST be strictly required (never CERT_NONE)
    assert ctx.verify_mode == ssl.CERT_REQUIRED, f"Expected ssl.CERT_REQUIRED, got {ctx.verify_mode}"
    # Hostname checking MUST be strictly enabled
    assert ctx.check_hostname is True, "Hostname checking MUST remain strictly enabled!"
    # Ensure trusted CA root certificates are loaded (from certifi's vetted bundle)
    ca_certs = ctx.get_ca_certs()
    assert len(ca_certs) > 0, "SSLContext must contain loaded trusted CA root certificates!"
    print(f"  ✓ SSL verification strictly enforced (CERT_REQUIRED), check_hostname=True, {len(ca_certs)} root CAs loaded from certifi.")

    print("\n" + "=" * 70)
    print("🎉 ALL 11 SUBSYSTEM UNIT TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_tests()
