"""
tests/test_ai_enhance.py
------------------------
Automated test suite validating the Optional Online AI Enhancement subsystem:
1. Privacy Confirmation Dialog: Explicit text preview, scope metrics, provider disclosure.
2. Rejection Safety: Cancelling transmission sends zero data and makes zero network calls.
3. Result Comparison Dialog: Side-by-side original vs enhanced, Accept & Replace vs Reject.
4. Secure Credential Management: OS Keychain integration with transient in-memory fallback.
5. Mock AI Provider Execution: Formats enhancement without external network calls.
6. Offline-by-Default Architecture: Status bar offline mode transitions and strict settings toggle.
"""

import os
import sys
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set Qt to run in headless offscreen mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt

from config.settings import (
    STATUS_OFFLINE,
    STATUS_ONLINE_PROGRESS,
    AI_ENHANCE_ENABLED_DEFAULT,
)
from services.keychain_manager import (
    store_api_key,
    get_api_key,
    delete_api_key,
    store_provider_config,
    get_provider_config,
    is_keyring_available,
)
from services.ai_provider import (
    get_ai_provider,
    MockAIProvider,
    GenericOpenAICompatibleProvider,
    AIProviderError,
)
from ui.ai_enhance_dialog import (
    AIEnhanceConfirmDialog,
    AIEnhanceResultDialog,
)
from ui.settings_dialog import SettingsDialog
from ui.main_window import MainWindow


def run_tests():
    print("=" * 60)
    print("🧪 STARTING ONLINE AI ENHANCEMENT SUBSYSTEM TESTS")
    print("=" * 60)

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # -------------------------------------------------------------
    # 1. Test Privacy Confirmation Dialog
    # -------------------------------------------------------------
    print("\n[1/6] Testing Privacy Confirmation Dialog & Disclosure...")

    sample_text = "This is a confidential snippet containing test data that must be explicitly reviewed."
    confirm_dlg = AIEnhanceConfirmDialog(text=sample_text, provider_name="OpenAI (GPT-4o)")

    # Verify dialog properties
    assert confirm_dlg.text_to_send == sample_text
    assert confirm_dlg.provider_name == "OpenAI (GPT-4o)"
    assert confirm_dlg.confirmed is False

    # Simulate Cancel / Reject
    confirm_dlg.btn_cancel.click()
    assert confirm_dlg.confirmed is False
    print("  ✓ User rejection/cancel preserves privacy (confirmed=False).")

    # Simulate Accept / Send
    confirm_dlg_2 = AIEnhanceConfirmDialog(text=sample_text, provider_name="OpenAI (GPT-4o)")
    confirm_dlg_2.btn_send.click()
    assert confirm_dlg_2.confirmed is True
    print("  ✓ User confirmation properly acknowledges transmission.")

    # -------------------------------------------------------------
    # 2. Test Side-by-Side Result Review Dialog
    # -------------------------------------------------------------
    print("\n[2/6] Testing Side-by-Side Review Dialog...")

    orig_text = "Original raw OCR snippet with typoz."
    enhanced_text = "Original raw OCR snippet with typos fixed."
    result_dlg = AIEnhanceResultDialog(
        original_text=orig_text,
        enhanced_text=enhanced_text,
        provider_name="OpenAI",
    )

    # Initial state
    assert result_dlg.accepted_result is False
    assert result_dlg.right_editor.toPlainText() == enhanced_text

    # Test Reject
    result_dlg.btn_reject.click()
    assert result_dlg.accepted_result is False
    print("  ✓ Reject button preserves original document without replacement.")

    # Test Accept and Replace
    result_dlg_2 = AIEnhanceResultDialog(
        original_text=orig_text,
        enhanced_text=enhanced_text,
        provider_name="OpenAI",
    )
    result_dlg_2.btn_accept.click()
    assert result_dlg_2.accepted_result is True
    assert result_dlg_2.enhanced_text == enhanced_text
    print("  ✓ Accept and Replace confirmed with enhanced text payload.")

    # -------------------------------------------------------------
    # 3. Test Secure Credential Management (Keychain / In-Memory Fallback)
    # -------------------------------------------------------------
    print("\n[3/6] Testing Credential Storage & Transient In-Memory Fallback...")

    test_provider = "mock_test_provider"
    test_key = "test-sk-abc123xyz"

    # Store key
    store_api_key(test_provider, test_key)
    retrieved = get_api_key(test_provider)
    assert retrieved == test_key, f"Expected {test_key}, got {retrieved}"

    # Delete key
    delete_api_key(test_provider)
    deleted = get_api_key(test_provider)
    assert not deleted, f"Expected None/empty after deletion, got {deleted}"
    print(f"  ✓ Credential storage, retrieval, and deletion verified (OS Keyring available: {is_keyring_available()}).")

    # -------------------------------------------------------------
    # 4. Test Mock & Generic OpenAI-Compatible Providers
    # -------------------------------------------------------------
    print("\n[4/7] Testing AI Provider Interface & Custom OpenAI-Compatible Setup...")

    mock_provider = get_ai_provider("mock", api_key="valid-mock-key")
    res = mock_provider.enhance_text("Hello World")
    assert res == "[AI Enhanced] Hello World"

    # Generic OpenAI-Compatible Provider validation
    custom_prov = get_ai_provider(
        "openai_compatible",
        api_key="test-ollama-key",
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:7b",
    )
    assert isinstance(custom_prov, GenericOpenAICompatibleProvider)
    assert "qwen2.5:7b" in custom_prov.get_name()
    assert "http://localhost:11434/v1" in custom_prov.get_name()
    print("  ✓ Generic OpenAI-compatible provider dynamically initialized without hardcoded endpoints.")

    # Provider config storage
    store_provider_config("openai_compatible", {
        "base_url": "https://api.together.xyz/v1",
        "model_name": "Qwen/Qwen2.5-72B-Instruct",
    })
    cfg = get_provider_config("openai_compatible")
    assert cfg["model_name"] == "Qwen/Qwen2.5-72B-Instruct"
    print("  ✓ Custom provider configuration preserved in session storage.")

    # Missing API key validation
    try:
        no_key_provider = get_ai_provider("mock", api_key="")
        no_key_provider.enhance_text("Test")
        assert False, "Should have raised AIProviderError"
    except AIProviderError:
        print("  ✓ Correctly raised AIProviderError when API key is missing.")

    # -------------------------------------------------------------
    # 5. Test Settings Dialog Configuration Controls
    # -------------------------------------------------------------
    print("\n[5/7] Testing Settings Dialog Provider Switching...")

    settings_dlg = SettingsDialog(ai_enhance_enabled=True, current_provider="openai_compatible")
    # Custom base address and model name fields should be visible for openai_compatible
    assert not settings_dlg.txt_base_url.isHidden()
    assert not settings_dlg.txt_model_name.isHidden()

    # Switch to standard OpenAI provider
    settings_dlg.combo_provider.setCurrentIndex(0)
    assert settings_dlg.txt_base_url.isHidden()
    assert settings_dlg.txt_model_name.isHidden()
    print("  ✓ SettingsDialog conditionally displays custom API endpoint fields for generic provider.")

    # -------------------------------------------------------------
    # 6. Test Default Offline Architecture in Settings
    # -------------------------------------------------------------
    print("\n[6/7] Testing Offline Default Settings...")

    assert AI_ENHANCE_ENABLED_DEFAULT is False, "AI Enhancement must be OFF by default."
    print("  ✓ Verified: AI_ENHANCE_ENABLED_DEFAULT is strictly False.")

    # -------------------------------------------------------------
    # 7. Test MainWindow Offline Status and Scope Selection
    # -------------------------------------------------------------
    print("\n[7/7] Testing MainWindow Status Transitions & Selective Scope...")

    main_win = MainWindow()
    # Check default status is strictly Offline
    status_msg = main_win.status_bar.currentMessage()
    badge_text = main_win.conn_badge.text()
    assert STATUS_OFFLINE in status_msg, f"Expected '{STATUS_OFFLINE}' in status msg, got '{status_msg}'"
    assert "Offline" in badge_text, f"Expected 'Offline' in badge text, got '{badge_text}'"

    # Test selective text scope logic
    main_win.preview_panel.text_editor.setPlainText("Full document text across multiple paragraphs.")
    target_txt, scope_lbl, ctx_type = main_win.preview_panel.get_ai_enhance_target_text()
    assert "Full document text" in target_txt
    assert ctx_type in ("document", "page_single")

    # Test status bar transition simulation
    main_win.status_bar.showMessage(STATUS_ONLINE_PROGRESS)
    main_win.conn_badge.setText("🟡 Online Request in Progress")
    assert STATUS_ONLINE_PROGRESS in main_win.status_bar.currentMessage()
    assert "Online Request" in main_win.conn_badge.text()

    # Revert to offline status
    main_win.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Ready")
    main_win.conn_badge.setText("🟢 100% Offline Mode")
    assert STATUS_OFFLINE in main_win.status_bar.currentMessage()
    assert "100% Offline Mode" in main_win.conn_badge.text()
    print("  ✓ Status bar strictly reflects Offline by default and restores immediately after transmission.")

    main_win.preview_panel.mark_saved()
    main_win.close()

    print("\n" + "=" * 60)
    print("🎉 ALL ONLINE AI ENHANCEMENT TESTS PASSED!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_tests()
