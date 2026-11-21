"""
ui/settings_dialog.py
---------------------
Application settings dialog governing offline defaults and optional cloud AI enhancements.
Provides:
1. Strict master toggle: 'Allow online AI enhancement' (OFF by default).
2. Cloud AI provider selection (OpenAI, Google Gemini).
3. Secure API key entry with OS keychain storage via keyring.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QFrame,
    QMessageBox,
)
from PySide6.QtCore import Qt
from config.settings import FONT_FAMILY_STACK
from services.keychain_manager import (
    store_api_key,
    get_api_key,
    store_provider_config,
    get_provider_config,
    is_keyring_available,
)


class SettingsDialog(QDialog):
    """
    Application preferences and privacy settings dialog.
    """

    def __init__(self, ai_enhance_enabled: bool, current_provider: str = "openai", parent=None):
        super().__init__(parent)
        self.ai_enhance_enabled = ai_enhance_enabled
        self.selected_provider = current_provider
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Settings & AI Preferences")
        self.setMinimumSize(480, 360)
        self.resize(500, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # Header
        title = QLabel("⚙️ <b>Application Settings & Privacy</b>")
        title.setStyleSheet(f"font-size: 14px; color: #1e293b; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(title)

        # Section 1: Online AI Enhancement Master Toggle
        ai_frame = QFrame()
        ai_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        ai_layout = QVBoxLayout(ai_frame)
        ai_layout.setContentsMargins(10, 10, 10, 10)
        ai_layout.setSpacing(8)

        self.chk_allow_ai = QCheckBox("Allow online AI enhancement (Default: Off)")
        self.chk_allow_ai.setChecked(self.ai_enhance_enabled)
        self.chk_allow_ai.setStyleSheet(f"font-weight: bold; font-size: 12px; color: #0f172a; font-family: {FONT_FAMILY_STACK};")
        self.chk_allow_ai.stateChanged.connect(self._on_toggle_ai_allowed)
        ai_layout.addWidget(self.chk_allow_ai)

        ai_desc = QLabel(
            "When disabled, the application is strictly 100% offline. "
            "Enabling this allows you to voluntarily send selected document snippets to external cloud AI providers."
        )
        ai_desc.setWordWrap(True)
        ai_desc.setStyleSheet(f"font-size: 10.5px; color: #64748b; font-family: {FONT_FAMILY_STACK};")
        ai_layout.addWidget(ai_desc)

        # Provider Selector
        prov_layout = QHBoxLayout()
        prov_lbl = QLabel("AI Provider:")
        prov_lbl.setStyleSheet(f"font-size: 11.5px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        prov_layout.addWidget(prov_lbl)

        self.combo_provider = QComboBox()
        self.combo_provider.addItem("OpenAI (GPT-4o / GPT-4o-mini)", "openai")
        self.combo_provider.addItem("Google Gemini (Gemini 1.5 Flash)", "gemini")
        self.combo_provider.addItem("OpenAI-Compatible API (e.g. Qwen / Ollama / Local)", "openai_compatible")

        # Set default index
        idx = 0
        if self.selected_provider == "gemini":
            idx = 1
        elif self.selected_provider in ("openai_compatible", "generic"):
            idx = 2
        self.combo_provider.setCurrentIndex(idx)
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        prov_layout.addWidget(self.combo_provider, stretch=1)
        ai_layout.addLayout(prov_layout)

        # Custom Endpoint & Model Name for Generic OpenAI-Compatible
        saved_cfg = get_provider_config("openai_compatible")
        self.lbl_base_url = QLabel("API Base Address:")
        self.lbl_base_url.setStyleSheet(f"font-size: 11.5px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        ai_layout.addWidget(self.lbl_base_url)

        self.txt_base_url = QLineEdit()
        self.txt_base_url.setPlaceholderText("e.g. http://localhost:11434/v1 or https://api.together.xyz/v1")
        self.txt_base_url.setText(saved_cfg.get("base_url", "http://localhost:11434/v1"))
        ai_layout.addWidget(self.txt_base_url)

        self.lbl_model_name = QLabel("Model Name:")
        self.lbl_model_name.setStyleSheet(f"font-size: 11.5px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        ai_layout.addWidget(self.lbl_model_name)

        self.txt_model_name = QLineEdit()
        self.txt_model_name.setPlaceholderText("e.g. qwen2.5:7b or Qwen/Qwen2.5-72B-Instruct")
        self.txt_model_name.setText(saved_cfg.get("model_name", "qwen2.5:7b"))
        ai_layout.addWidget(self.txt_model_name)

        # API Key Field
        key_lbl = QLabel("API Key:")
        key_lbl.setStyleSheet(f"font-size: 11.5px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        ai_layout.addWidget(key_lbl)

        self.txt_api_key = QLineEdit()
        self.txt_api_key.setEchoMode(QLineEdit.Password)
        self.txt_api_key.setPlaceholderText("Enter API Key (Optional for local Ollama, never saved to git)")
        # Load existing key if stored
        existing_key = get_api_key(self.selected_provider)
        if existing_key:
            self.txt_api_key.setText(existing_key)
        ai_layout.addWidget(self.txt_api_key)

        # Keyring Security Status Note
        keyring_status = (
            "🔒 Protected by OS Secure Keychain (keyring available)."
            if is_keyring_available()
            else "ℹ️ Session-only in-memory storage (keyring not available; not saved to disk)."
        )
        self.lbl_key_status = QLabel(keyring_status)
        self.lbl_key_status.setStyleSheet(f"font-size: 10px; color: #059669; font-family: {FONT_FAMILY_STACK};")
        ai_layout.addWidget(self.lbl_key_status)

        layout.addWidget(ai_frame)
        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save Settings")
        btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
                border-radius: 5px;
                padding: 6px 16px;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
        """)
        btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)
        self._on_provider_changed()
        self._update_controls_state()

    def _on_toggle_ai_allowed(self):
        self._update_controls_state()

    def _update_controls_state(self):
        enabled = self.chk_allow_ai.isChecked()
        self.combo_provider.setEnabled(enabled)
        self.txt_api_key.setEnabled(enabled)
        self.txt_base_url.setEnabled(enabled)
        self.txt_model_name.setEnabled(enabled)

    def _on_provider_changed(self):
        prov = self.combo_provider.currentData()
        is_generic = prov in ("openai_compatible", "generic")
        self.lbl_base_url.setVisible(is_generic)
        self.txt_base_url.setVisible(is_generic)
        self.lbl_model_name.setVisible(is_generic)
        self.txt_model_name.setVisible(is_generic)

        existing_key = get_api_key(prov)
        self.txt_api_key.setText(existing_key or "")

    def _on_save_clicked(self):
        self.ai_enhance_enabled = self.chk_allow_ai.isChecked()
        self.selected_provider = self.combo_provider.currentData()

        if self.ai_enhance_enabled:
            api_key = self.txt_api_key.text().strip()
            if api_key:
                store_api_key(self.selected_provider, api_key)

            if self.selected_provider in ("openai_compatible", "generic"):
                store_provider_config("openai_compatible", {
                    "base_url": self.txt_base_url.text().strip() or "http://localhost:11434/v1",
                    "model_name": self.txt_model_name.text().strip() or "qwen2.5:7b",
                })

        self.accept()
