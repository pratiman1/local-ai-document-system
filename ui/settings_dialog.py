"""
ui/settings_dialog.py
---------------------
Application settings dialog governing offline defaults, local translation models,
and optional cloud AI enhancements.

Provides:
1. Offline Translation Models manager:
   - Scans models/argos/ folder automatically for .argosmodel packages.
   - View installed offline translation language pairs.
   - View dropdown target languages availability at a glance.
   - User-controlled import: copies chosen file into models/argos/ and scans.
   - Immediate cache refresh upon installation.
2. Strict master toggle: 'Allow online AI enhancement' (OFF by default).
3. Cloud AI provider selection (OpenAI, Google Gemini, OpenAI-Compatible).
4. Secure API key entry with OS keychain storage via keyring.
"""

import shutil
from pathlib import Path
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
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QWidget,
    QSpinBox,
)
from PySide6.QtCore import Qt
from config.settings import FONT_FAMILY_STACK, ARGOS_MODELS_DIR, INDICTRANS2_MODELS_DIR
from services.keychain_manager import (
    store_api_key,
    get_api_key,
    store_provider_config,
    get_provider_config,
    is_keyring_available,
)
from translation.argos_translator import ArgosTranslator
from translation.indictrans2_translator import IndicTrans2Translator
from translation.indictrans2_mapping import DIRECTION_NAMES


class SettingsDialog(QDialog):
    """
    Application preferences, offline models, and privacy settings dialog.
    """

    def __init__(
        self,
        ai_enhance_enabled: bool,
        current_provider: str = "openai",
        engine_preference: str = "automatic",
        compare_mode: bool = False,
        agreement_threshold: float = 0.60,
        parent=None,
    ):
        super().__init__(parent)
        self.ai_enhance_enabled = ai_enhance_enabled
        self.selected_provider = current_provider
        self.engine_preference = engine_preference
        self.compare_mode = compare_mode
        self.agreement_threshold = agreement_threshold
        self.models_updated = False
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Settings & Preferences")
        self.setSizeGripEnabled(True)
        self.setMinimumSize(540, 580)
        self.resize(580, 680)

        main_dialog_layout = QVBoxLayout(self)
        main_dialog_layout.setContentsMargins(16, 16, 16, 16)
        main_dialog_layout.setSpacing(12)

        # Header Title
        title = QLabel("⚙️ <b>Application Settings & Preferences</b>")
        title.setStyleSheet(f"font-size: 15px; color: #1e293b; font-family: {FONT_FAMILY_STACK}; margin-bottom: 2px;")
        main_dialog_layout.addWidget(title)

        # Scroll Area to prevent any vertical clipping across screens and DPI scalings
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 4, 0)
        scroll_layout.setSpacing(14)

        # ==============================================================================
        # Section 1: Translation Engine Choice & Compare Mode
        # ==============================================================================
        engine_frame = QFrame()
        engine_frame.setObjectName("engine_frame")
        engine_frame.setStyleSheet("""
            QFrame#engine_frame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
        """)
        engine_layout = QVBoxLayout(engine_frame)
        engine_layout.setContentsMargins(14, 14, 14, 14)
        engine_layout.setSpacing(9)

        engine_title = QLabel("⚡ <b>Translation Engine Routing & Compare Mode</b>")
        engine_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: #0f172a; font-family: {FONT_FAMILY_STACK};")
        engine_layout.addWidget(engine_title)

        pref_layout = QHBoxLayout()
        pref_lbl = QLabel("Engine Priority:")
        pref_lbl.setStyleSheet(f"font-size: 11.5px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        pref_layout.addWidget(pref_lbl)

        self.combo_engine_pref = QComboBox()
        self.combo_engine_pref.addItem("Automatic (IndicTrans2 direct > Argos direct > Pivot)", "automatic")
        self.combo_engine_pref.addItem("Argos Translate Only", "argos_only")
        self.combo_engine_pref.addItem("IndicTrans2 Only", "indictrans2_only")

        pref_idx = 0
        if self.engine_preference == "argos_only":
            pref_idx = 1
        elif self.engine_preference == "indictrans2_only":
            pref_idx = 2
        self.combo_engine_pref.setCurrentIndex(pref_idx)
        pref_layout.addWidget(self.combo_engine_pref)
        engine_layout.addLayout(pref_layout)

        # Compare Mode Checkbox & Threshold
        self.chk_compare_mode = QCheckBox("Enable Engine Compare Mode (Sequential consensus check)")
        self.chk_compare_mode.setChecked(self.compare_mode)
        self.chk_compare_mode.setStyleSheet(f"font-weight: 600; font-size: 11.5px; color: #0f172a; font-family: {FONT_FAMILY_STACK};")
        self.chk_compare_mode.setToolTip("Translates each page sequentially with both engines. Highlights pages where agreement is below threshold.")
        engine_layout.addWidget(self.chk_compare_mode)

        thresh_layout = QHBoxLayout()
        thresh_lbl = QLabel("Agreement Flag Threshold:")
        thresh_lbl.setStyleSheet(f"font-size: 11px; color: #475569; font-family: {FONT_FAMILY_STACK};")
        thresh_layout.addWidget(thresh_lbl)

        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(10, 95)
        self.spin_threshold.setValue(int(self.agreement_threshold * 100))
        self.spin_threshold.setSuffix("%")
        self.spin_threshold.setToolTip("Pages with engine agreement below this threshold will be flagged for review.")
        thresh_layout.addWidget(self.spin_threshold)
        thresh_layout.addStretch()
        engine_layout.addLayout(thresh_layout)

        compare_note = QLabel(
            "<i>Notice: Agreement indicator is not an accuracy score; two models can agree and still be wrong.</i>"
        )
        compare_note.setWordWrap(True)
        compare_note.setStyleSheet(f"font-size: 10px; color: #64748b; font-family: {FONT_FAMILY_STACK};")
        engine_layout.addWidget(compare_note)

        scroll_layout.addWidget(engine_frame)

        # ==============================================================================
        # Section 2: AI4Bharat IndicTrans2 Models (models/indictrans2/)
        # ==============================================================================
        indic_frame = QFrame()
        indic_frame.setObjectName("indic_frame")
        indic_frame.setStyleSheet("""
            QFrame#indic_frame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
        """)
        indic_layout = QVBoxLayout(indic_frame)
        indic_layout.setContentsMargins(14, 14, 14, 14)
        indic_layout.setSpacing(9)

        indic_title = QLabel("🇮🇳 <b>IndicTrans2 Offline Models (AI4Bharat)</b>")
        indic_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: #0f172a; font-family: {FONT_FAMILY_STACK};")
        indic_layout.addWidget(indic_title)

        indic_desc = QLabel(
            "Direct 100% offline translation across 22 Indian languages and English. "
            "Place downloaded distilled model folders in <b>models/indictrans2/</b>."
        )
        indic_desc.setWordWrap(True)
        indic_desc.setStyleSheet(f"font-size: 11px; color: #64748b; font-family: {FONT_FAMILY_STACK};")
        indic_layout.addWidget(indic_desc)

        self.list_indic_directions = QListWidget()
        self.list_indic_directions.setFixedHeight(80)
        self.list_indic_directions.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: #f8fafc;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                color: #1e293b;
            }}
            QListWidget::item {{
                padding: 3px 6px;
            }}
        """)
        indic_layout.addWidget(self.list_indic_directions)

        indic_btn_layout = QHBoxLayout()
        self.btn_indic_guide = QPushButton("📖 IndicTrans2 Setup Guide...")
        self.btn_indic_guide.setCursor(Qt.PointingHandCursor)
        self.btn_indic_guide.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
        """)
        self.btn_indic_guide.clicked.connect(self._on_indictrans2_guide_clicked)
        indic_btn_layout.addWidget(self.btn_indic_guide)
        indic_btn_layout.addStretch()
        indic_layout.addLayout(indic_btn_layout)

        scroll_layout.addWidget(indic_frame)

        # ==============================================================================
        # Section 3: Offline Translation Models (Argos Translate)
        # ==============================================================================
        trans_frame = QFrame()
        trans_frame.setObjectName("trans_frame")
        trans_frame.setStyleSheet("""
            QFrame#trans_frame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
        """)
        trans_layout = QVBoxLayout(trans_frame)
        trans_layout.setContentsMargins(14, 14, 14, 14)
        trans_layout.setSpacing(9)

        trans_title = QLabel("🌐 <b>Offline Translation Models (Argos Translate)</b>")
        trans_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: #0f172a; font-family: {FONT_FAMILY_STACK};")
        trans_layout.addWidget(trans_title)

        trans_desc = QLabel(
            "Offline translation runs 100% locally on your computer with zero network traffic. "
            "Place downloaded <code>.argosmodel</code> files in <b>models/argos/</b>; "
            "they are detected and installed automatically."
        )
        trans_desc.setWordWrap(True)
        trans_desc.setStyleSheet(f"font-size: 11px; color: #64748b; font-family: {FONT_FAMILY_STACK}; line-height: 1.4;")
        trans_layout.addWidget(trans_desc)

        # 1A. Installed Models List
        self.lbl_installed_summary = QLabel("Installed Model Packages (models/argos/):")
        self.lbl_installed_summary.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: #1e293b; font-family: {FONT_FAMILY_STACK}; margin-top: 4px;")
        trans_layout.addWidget(self.lbl_installed_summary)

        self.list_installed_pairs = QListWidget()
        self.list_installed_pairs.setFixedHeight(85)
        self.list_installed_pairs.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: #f8fafc;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                color: #1e293b;
            }}
            QListWidget::item {{
                padding: 3px 6px;
            }}
        """)
        trans_layout.addWidget(self.list_installed_pairs)

        # 1B. Target Languages Availability in Dropdown
        self.lbl_targets_summary = QLabel("Target Languages Availability (from English):")
        self.lbl_targets_summary.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: #1e293b; font-family: {FONT_FAMILY_STACK}; margin-top: 4px;")
        trans_layout.addWidget(self.lbl_targets_summary)

        self.list_target_availability = QListWidget()
        self.list_target_availability.setFixedHeight(95)
        self.list_target_availability.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: #f8fafc;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                color: #1e293b;
            }}
            QListWidget::item {{
                padding: 3px 6px;
            }}
        """)
        trans_layout.addWidget(self.list_target_availability)

        # Model Action Buttons
        model_btn_layout = QHBoxLayout()
        self.btn_import_model = QPushButton("📦 Import Offline Model (.argosmodel)...")
        self.btn_import_model.setCursor(Qt.PointingHandCursor)
        self.btn_import_model.setToolTip("Select a downloaded .argosmodel file; copies it into models/argos/ and installs automatically.")
        self.btn_import_model.setStyleSheet(f"""
            QPushButton {{
                background-color: #f0fdf4;
                color: #166534;
                border: 1px solid #86efac;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11.5px;
                font-weight: 600;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #dcfce7;
            }}
        """)
        self.btn_import_model.clicked.connect(self._on_import_model_clicked)
        model_btn_layout.addWidget(self.btn_import_model)

        self.btn_refresh_models = QPushButton("🔄 Refresh")
        self.btn_refresh_models.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_models.setToolTip("Re-scan models/argos/ for newly added model files.")
        self.btn_refresh_models.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
        """)
        self.btn_refresh_models.clicked.connect(self._refresh_installed_pairs_list)
        model_btn_layout.addWidget(self.btn_refresh_models)
        model_btn_layout.addStretch()

        trans_layout.addLayout(model_btn_layout)
        scroll_layout.addWidget(trans_frame)

        # ==============================================================================
        # Section 2: Online AI Enhancement Master Toggle (Strictly Optional)
        # ==============================================================================
        ai_frame = QFrame()
        ai_frame.setObjectName("ai_frame")
        ai_frame.setStyleSheet("""
            QFrame#ai_frame {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
        """)
        ai_layout = QVBoxLayout(ai_frame)
        ai_layout.setContentsMargins(14, 14, 14, 14)
        ai_layout.setSpacing(9)

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
        key_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: #334155; font-family: {FONT_FAMILY_STACK}; margin-top: 4px;")
        ai_layout.addWidget(key_lbl)

        self.txt_api_key = QLineEdit()
        self.txt_api_key.setEchoMode(QLineEdit.Password)
        self.txt_api_key.setPlaceholderText("Enter API Key (Optional for local Ollama, never saved to git)")
        existing_key = get_api_key(self.selected_provider)
        if existing_key:
            self.txt_api_key.setText(existing_key)
        ai_layout.addWidget(self.txt_api_key)

        keyring_status = (
            "🔒 Protected by OS Secure Keychain (keyring available)."
            if is_keyring_available()
            else "ℹ️ Session-only in-memory storage (keyring not available; not saved to disk)."
        )
        self.lbl_key_status = QLabel(keyring_status)
        self.lbl_key_status.setStyleSheet(f"font-size: 10px; color: #059669; font-family: {FONT_FAMILY_STACK};")
        ai_layout.addWidget(self.lbl_key_status)

        scroll_layout.addWidget(ai_frame)
        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        main_dialog_layout.addWidget(scroll_area, stretch=1)

        # Bottom Action Buttons
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

        main_dialog_layout.addLayout(btn_layout)
        self._on_provider_changed()
        self._update_controls_state()
        self._refresh_installed_pairs_list()

    def _refresh_installed_pairs_list(self):
        """Scans models/argos/ and refreshes the list of installed and available language pairs."""
        self.list_installed_pairs.clear()
        self.list_target_availability.clear()

        translator = ArgosTranslator()
        # Automatically scan models/argos/ on refresh
        translator.scan_and_install_models_folder()
        translator.refresh_installed_languages()
        pairs = translator.get_installed_pairs_info()

        # Update Installed Models List
        if not pairs:
            self.lbl_installed_summary.setText("Installed Model Packages: 0 models installed")
            item = QListWidgetItem("⚠️ No offline translation models installed in models/argos/.")
            item.setToolTip("Place .argosmodel files in models/argos/ or click 'Import Offline Model'.")
            self.list_installed_pairs.addItem(item)
        else:
            self.lbl_installed_summary.setText(f"Installed Model Packages: {len(pairs)} direct model(s) installed")
            for p in pairs:
                label = f"• {p['source_name']} ({p['source_code']}) ➔ {p['target_name']} ({p['target_code']}) [Direct Model]"
                item = QListWidgetItem(label)
                self.list_installed_pairs.addItem(item)

        # Update Target Languages Availability List (from English)
        target_avail = translator.get_target_languages_availability(source="eng")
        ready_count = sum(1 for t in target_avail if t["can_translate"])
        self.lbl_targets_summary.setText(
            f"Target Languages in Dropdown (from English): {ready_count}/{len(target_avail)} ready"
        )

        for t in target_avail:
            if t["can_translate"]:
                if t["route_type"] == "direct":
                    label = f"✓ {t['name']} ({t['code']}) — Ready (direct model)"
                else:
                    label = f"✓ {t['name']} ({t['code']}) — Ready (via English pivot)"
                item = QListWidgetItem(label)
                item.setForeground(Qt.darkGreen)
            else:
                if t["status"] == "unavailable_in_argos":
                    label = f"✗ {t['name']} ({t['code']}) — Unavailable in Argos (Use Online AI)"
                    item = QListWidgetItem(label)
                    item.setForeground(Qt.darkGray)
                    item.setToolTip(t["message"])
                else:
                    label = f"✗ {t['name']} ({t['code']}) — Missing (.argosmodel needed in models/argos/)"
                    item = QListWidgetItem(label)
                    item.setForeground(Qt.darkRed)
                    item.setToolTip(t["message"])
            self.list_target_availability.addItem(item)

        # Refresh IndicTrans2 model directions status
        self._refresh_indictrans2_list()

    def _refresh_indictrans2_list(self):
        """Refreshes status of IndicTrans2 model directions in models/indictrans2/."""
        self.list_indic_directions.clear()
        translator = IndicTrans2Translator()
        directions = [
            ("en-indic", "English to Indic", "ai4bharat/indictrans2-en-indic-dist-200M (~800 MB)"),
            ("indic-en", "Indic to English", "ai4bharat/indictrans2-indic-en-dist-200M (~800 MB)"),
            ("indic-indic", "Indic to Indic", "ai4bharat/indictrans2-indic-indic-dist-320M (~1.2 GB)"),
        ]
        installed_set = set(translator.get_installed_directions())
        for dir_key, label, hf_info in directions:
            is_inst = dir_key in installed_set
            if is_inst:
                item = QListWidgetItem(f"✓ {label} — Installed in models/indictrans2/{dir_key}/")
                item.setForeground(Qt.darkGreen)
            else:
                item = QListWidgetItem(f"✗ {label} — Missing in models/indictrans2/{dir_key}/")
                item.setForeground(Qt.darkRed)
                item.setToolTip(f"Download from Hugging Face: {hf_info}")
            self.list_indic_directions.addItem(item)

    def _on_indictrans2_guide_clicked(self):
        """Displays IndicTrans2 setup instructions and Hugging Face model details."""
        translator = IndicTrans2Translator()
        guide = translator.get_installation_instructions()
        QMessageBox.information(self, "AI4Bharat IndicTrans2 Setup Guide", guide)

    def _on_import_model_clicked(self):
        """Opens a file dialog for the user to select an .argosmodel file, copies it to models/argos/, and scans."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Argos Translation Model (.argosmodel)",
            "",
            "Argos Translation Models (*.argosmodel);;Zip Archives (*.zip);;All Files (*)",
        )
        if not file_path:
            return

        src_p = Path(file_path)
        translator = ArgosTranslator()

        # 1. Strictly validate the model package before copying
        is_valid, val_msg, meta = translator.validate_model_file(src_p)
        if not is_valid:
            QMessageBox.critical(
                self,
                "Invalid Model File",
                f"The selected file failed model validation:\n\n{val_msg}\n\nPlease select a valid .argosmodel package."
            )
            return

        # 2. Copy the chosen file into models/argos/
        target_folder = Path(ARGOS_MODELS_DIR)
        target_folder.mkdir(parents=True, exist_ok=True)
        dest_p = target_folder / src_p.name

        try:
            if src_p.resolve() != dest_p.resolve():
                shutil.copy2(src_p, dest_p)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Copy Failed",
                f"Could not copy model file to models/argos/:\n\n{str(e)}"
            )
            return

        # 3. Trigger the folder scan to install the newly copied model
        scan_res = translator.scan_and_install_models_folder()
        self.models_updated = True
        self._refresh_installed_pairs_list()

        from_name = meta.get("from_name", meta["from_code"])
        to_name = meta.get("to_name", meta["to_code"])
        QMessageBox.information(
            self,
            "Model Imported Successfully",
            f"Copied '{src_p.name}' into models/argos/ and installed successfully:\n\n"
            f"• {from_name} to {to_name}\n\n"
            f"The language pair is now ready for 100% offline translation."
        )

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
        self.engine_preference = self.combo_engine_pref.currentData()
        self.compare_mode = self.chk_compare_mode.isChecked()
        self.agreement_threshold = self.spin_threshold.value() / 100.0

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
