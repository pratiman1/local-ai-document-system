"""
ui/language_selector.py
-----------------------
Panel component for selecting target translation languages.
Focuses on Indian languages (Hindi, Tamil, Telugu, Marathi, Bengali, etc.) and English.

Features:
- Visible, cleanly aligned downward arrow indicator on the dropdown across macOS, Windows, Linux.
- Informative hover tooltips for accessibility.
- Production-ready styling without internal development tags.
- Preserves Qt signal emission (language_changed) when selection changes.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFrame,
    QHBoxLayout,
)
from PySide6.QtCore import Signal, Qt
from config.languages import get_language_dropdown_items, DEFAULT_TARGET_LANGUAGE
from config.settings import CHEVRON_DOWN_ICON, CHEVRON_DOWN_HOVER_ICON, FONT_FAMILY_STACK


class LanguageSelector(QWidget):
    """
    Language selection panel widget with hover tooltips and visible dropdown arrow.

    Signals:
        language_changed (str): Emitted when the selected language changes.
        translate_requested (): Emitted when the user requests translation.
    """

    language_changed = Signal(str)
    translate_requested = Signal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Section Header with tooltip
        title_label = QLabel("🌐 <b>Target Language</b>")
        title_label.setStyleSheet(f"font-size: 13px; color: #1e293b; font-family: {FONT_FAMILY_STACK};")
        title_label.setToolTip("Select your preferred target language for document translation.")
        layout.addWidget(title_label)

        # Dropdown description
        desc_label = QLabel("Select desired output language:")
        desc_label.setStyleSheet(f"font-size: 11px; color: #64748b; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(desc_label)

        # Language ComboBox with visible downward arrow and clear padding
        self.combo = QComboBox()
        self.combo.setCursor(Qt.PointingHandCursor)
        self.combo.setToolTip("Select your preferred target language.")
        self.combo.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 32px 6px 10px;
                background-color: #ffffff;
                color: #0f172a;
                font-size: 12.5px;
                font-family: {FONT_FAMILY_STACK};
                min-height: 28px;
            }}
            QComboBox:hover {{
                border-color: #3b82f6;
                background-color: #f8fafc;
            }}
            QComboBox:focus {{
                border: 1.5px solid #2563eb;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 26px;
                border-left: 1px solid #e2e8f0;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
            QComboBox::down-arrow {{
                image: url("{CHEVRON_DOWN_ICON}");
                width: 12px;
                height: 12px;
            }}
            QComboBox::down-arrow:hover {{
                image: url("{CHEVRON_DOWN_HOVER_ICON}");
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
                selection-background-color: #dbeafe;
                selection-color: #1e40af;
                padding: 4px;
                font-size: 12px;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)

        # Populate with Indian languages from config
        languages = get_language_dropdown_items()
        default_index = 0
        for index, item in enumerate(languages):
            self.combo.addItem(item["label"], item["code"])
            if item["code"] == DEFAULT_TARGET_LANGUAGE:
                default_index = index

        self.combo.setCurrentIndex(default_index)
        self.combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self.combo)

        # Translate Action Button (Active when document is loaded)
        self.btn_translate = QPushButton("🔄 Translate Document")
        self.btn_translate.setCursor(Qt.PointingHandCursor)
        self.btn_translate.setEnabled(False)
        self.btn_translate.setToolTip("Translate extracted text to the chosen target language using local neural engines.")
        self.btn_translate.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 6px 12px;
                font-size: 11.5px;
                font-family: {FONT_FAMILY_STACK};
                min-height: 26px;
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
            QPushButton:pressed {{
                background-color: #1e40af;
            }}
            QPushButton:disabled {{
                background-color: #cbd5e1;
                color: #94a3b8;
            }}
        """)
        self.btn_translate.clicked.connect(self._on_translate_clicked)
        layout.addWidget(self.btn_translate)

        # Production-grade Informational Badge reflecting real offline translation state
        self.info_frame = QFrame()
        self.info_frame.setStyleSheet("""
            QFrame {
                background-color: #fefce8;
                border: 1px solid #fef08a;
                border-radius: 5px;
                padding: 6px;
            }
        """)
        info_layout = QHBoxLayout(self.info_frame)
        info_layout.setContentsMargins(6, 4, 6, 4)

        self.info_text = QLabel("🟡 <b>Status:</b> Model Missing • English to Hindi offline translation model is not installed.")
        self.info_text.setWordWrap(True)
        self.info_text.setStyleSheet(f"font-size: 10px; color: #854d0e; font-family: {FONT_FAMILY_STACK};")
        self.info_frame.setToolTip("Offline translation model is not installed. Open Settings (⚙️) to import an .argosmodel file.")
        info_layout.addWidget(self.info_text)

        layout.addWidget(self.info_frame)
        layout.addStretch()

        self._status_state = "model_missing"

    def _on_translate_clicked(self):
        self.translate_requested.emit()

    def set_translate_enabled(self, enabled: bool):
        """Enables or disables the Translate button based on document presence."""
        self.btn_translate.setEnabled(enabled)

    def _on_language_changed(self, index: int):
        code = self.combo.itemData(index)
        self.language_changed.emit(code)

    def get_selected_language_code(self) -> str:
        """Returns the currently selected language code (e.g. 'hin')."""
        return self.combo.currentData()

    def get_selected_language_name(self) -> str:
        """Returns the currently selected language display name."""
        return self.combo.currentText()

    def get_language_name(self, code: str) -> str:
        """Returns the human-readable language name for a 3-letter code."""
        from config.languages import SUPPORTED_LANGUAGES
        info = SUPPORTED_LANGUAGES.get(code.lower())
        if info:
            return info.name
        return code.upper()

    def get_translation_status(self) -> str:
        """Returns the current translation status string ('ready', 'model_missing', 'translating', 'error')."""
        return getattr(self, "_status_state", "ready")

    def update_translation_status(
        self,
        state: str,
        source_lang: str = "eng",
        target_lang: str = "hin",
        message: str = "",
        tooltip: str = "",
    ):
        """
        Updates the offline translation status indicator badge.
        Supported states:
        - 'ready' / 'ready_direct': Direct offline translation model ready.
        - 'ready_pivot': Pivot translation through English ready.
        - 'model_missing': Required language pair unavailable.
        - 'translating': Translation currently running.
        - 'error': Translation failed.
        """
        state_key = state.lower().strip()
        self._status_state = state_key
        src_name = self.get_language_name(source_lang)
        tgt_name = self.get_language_name(target_lang)

        if state_key in ("ready_compare", "compare_mode", "compare"):
            self._status_state = "ready_compare"
            details = message or f"{src_name} to {tgt_name} (IndicTrans2 vs Argos)"
            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #faf5ff;
                    border: 1px solid #d8b4fe;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #6b21a8; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🟣 <b>Status:</b> Compare Mode • {details}")
            self.info_frame.setToolTip(tooltip or "Compare Mode active: Translates with primary & secondary engines sequentially to check agreement.")

        elif state_key in ("ready_indictrans2", "indictrans2"):
            self._status_state = "ready_indictrans2"
            details = message or f"{src_name} to {tgt_name}: IndicTrans2 (direct)"
            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #f0fdf4;
                    border: 1px solid #86efac;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #166534; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🟢 <b>Status:</b> Ready (IndicTrans2) • {details}")
            self.info_frame.setToolTip(tooltip or f"Direct AI4Bharat IndicTrans2 model ready for {src_name} to {tgt_name}.")

        elif state_key in ("ready_direct", "direct"):
            self._status_state = "ready_direct"
            details = message or f"{src_name} to {tgt_name} (direct)"
            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #f0fdf4;
                    border: 1px solid #bbf7d0;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #166534; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🟢 <b>Status:</b> Ready (direct) • {details}")
            self.info_frame.setToolTip(tooltip or f"Direct offline translation model installed and ready for {src_name} to {tgt_name}.")

        elif state_key in ("ready_pivot", "pivot"):
            self._status_state = "ready_pivot"
            details = message or f"{src_name} to {tgt_name} (via English)"
            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #f0fdf4;
                    border: 1px solid #86efac;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #15803d; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🟢 <b>Status:</b> Ready via English • {details}")
            self.info_frame.setToolTip(tooltip or f"Translation will pivot through English ({src_name} ➔ English ➔ {tgt_name}). Translation quality may be lower.")

        elif state_key == "ready":
            self._status_state = "ready"
            details = message or f"{src_name} to {tgt_name} model ready"
            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #f0fdf4;
                    border: 1px solid #bbf7d0;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #166534; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🟢 <b>Status:</b> Ready • {details}")
            self.info_frame.setToolTip(tooltip or "Offline translation model is installed and ready for translation.")

        elif state_key in ("model_missing", "missing", "unavailable", "unavailable_in_argos"):
            self._status_state = "model_missing"
            if message:
                details = message
            else:
                if source_lang.lower() == "eng" and target_lang.lower() == "hin":
                    details = "English to Hindi offline translation model is not installed. Place translate-en_hi.argosmodel in models/argos/"
                else:
                    details = f"{src_name} to {tgt_name} offline translation model is missing. Place .argosmodel in models/argos/"

            if "models/argos" not in details.lower() and "online ai" not in details.lower():
                details = f"{details}. Place .argosmodel in models/argos/"

            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #fefce8;
                    border: 1px solid #fef08a;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #854d0e; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🟡 <b>Status:</b> Model Missing • {details}")
            self.info_frame.setToolTip(tooltip or f"{details}\nPlace required .argosmodel files in models/argos/")

        elif state_key in ("translating", "running", "in_progress"):
            self._status_state = "translating"
            details = message or f"Translating document ({src_name} ➔ {tgt_name})..."
            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #eff6ff;
                    border: 1px solid #bfdbfe;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #1e40af; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🔵 <b>Status:</b> Translating • {details}")
            self.info_frame.setToolTip("Offline translation is currently running in background.")

        elif state_key in ("error", "failed"):
            self._status_state = "error"
            details = message or "Translation failed."
            self.info_frame.setStyleSheet("""
                QFrame {
                    background-color: #fef2f2;
                    border: 1px solid #fecaca;
                    border-radius: 5px;
                    padding: 6px;
                }
            """)
            self.info_text.setStyleSheet(f"font-size: 10px; color: #991b1b; font-family: {FONT_FAMILY_STACK};")
            self.info_text.setText(f"🔴 <b>Status:</b> Error • {details}")
            self.info_frame.setToolTip(f"Translation error: {details}")
