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
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #f0fdf4;
                border: 1px solid #bbf7d0;
                border-radius: 5px;
                padding: 6px;
            }
        """)
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(6, 4, 6, 4)

        info_text = QLabel("🌐 <b>Offline Translation:</b> Ready (Argos Translate). Fast local neural translation with automatic English pivoting.")
        info_text.setWordWrap(True)
        info_text.setStyleSheet(f"font-size: 10px; color: #166534; font-family: {FONT_FAMILY_STACK};")
        info_frame.setToolTip("Offline machine translation is active. Runs 100% locally on your computer.")
        info_layout.addWidget(info_text)

        layout.addWidget(info_frame)
        layout.addStretch()

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
