"""
ui/preview_panel.py
-------------------
Panel component for viewing and manually editing extracted text.
Supports:
- Distinct modern dashboard metric pills with tooltips.
- Tab bar with generous sizing and tooltips.
- Full document editor with cross-platform typography and editing tooltips.
- Resizable page-by-page inspector with unclipped page list items.
- Unsaved edits state tracking and complete reset capabilities.
"""

from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QTabWidget,
    QFrame,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from config.settings import FONT_FAMILY_STACK


class PreviewPanel(QWidget):
    """
    Text preview widget allowing inspection and manual correction of extracted text.
    Tracks unsaved edits and supports resetting all view states.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._pages_data: List[Dict[str, Any]] = []
        self._original_text: str = ""
        self._is_dirty: bool = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        # ----------------------------------------------------------------------
        # Top Metrics & Status Ribbon
        # ----------------------------------------------------------------------
        metrics_frame = QFrame()
        metrics_frame.setStyleSheet("""
            QFrame {
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
        """)
        metrics_layout = QHBoxLayout(metrics_frame)
        metrics_layout.setContentsMargins(8, 4, 8, 4)
        metrics_layout.setSpacing(8)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"font-weight: bold; color: #1e293b; font-size: 11px; font-family: {FONT_FAMILY_STACK};")
        self.status_label.setToolTip("Current document processing and extraction status.")
        metrics_layout.addWidget(self.status_label)

        metrics_layout.addStretch()

        # Modern metric pills with tooltips
        pill_style = f"""
            QLabel {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                color: #334155;
                font-weight: 500;
                font-family: {FONT_FAMILY_STACK};
            }}
        """

        self.pages_metric = QLabel("Pages: 0")
        self.pages_metric.setStyleSheet(pill_style)
        self.pages_metric.setToolTip("Total number of pages in the loaded document.")
        metrics_layout.addWidget(self.pages_metric)

        self.words_metric = QLabel("Words: 0")
        self.words_metric.setStyleSheet(pill_style)
        self.words_metric.setToolTip("Total word count of the current document text.")
        metrics_layout.addWidget(self.words_metric)

        self.chars_metric = QLabel("Characters: 0")
        self.chars_metric.setStyleSheet(pill_style)
        self.chars_metric.setToolTip("Total character count including punctuation and spaces.")
        metrics_layout.addWidget(self.chars_metric)

        layout.addWidget(metrics_frame)

        # ----------------------------------------------------------------------
        # Tabs: Full Document vs Page-by-Page Breakdown
        # ----------------------------------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background-color: #ffffff;
            }}
            QTabBar::tab {{
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-bottom: none;
                padding: 6px 16px;
                margin-right: 3px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-size: 11.5px;
                font-family: {FONT_FAMILY_STACK};
                color: #475569;
                min-width: 130px;
            }}
            QTabBar::tab:selected {{
                background-color: #ffffff;
                font-weight: bold;
                color: #2563eb;
                border-bottom: 2px solid #2563eb;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #f1f5f9;
                color: #1e293b;
            }}
        """)

        # Tab 1: Full Document Editor with cross-platform typography
        self.text_editor = QTextEdit()
        self.text_editor.setPlaceholderText(
            "Extracted text will appear here. You can manually edit or correct any text in-place."
        )
        self.text_editor.setToolTip("Editable text area. You can manually edit, clean up, or correct text in-place.")
        self.text_editor.setStyleSheet(f"""
            QTextEdit {{
                font-family: {FONT_FAMILY_STACK};
                font-size: 13px;
                line-height: 1.6;
                padding: 12px;
                border: none;
                background-color: #ffffff;
                color: #0f172a;
            }}
        """)
        self.text_editor.textChanged.connect(self._on_text_edited)
        self.tabs.addTab(self.text_editor, "📝 Full Document")
        self.tabs.setTabToolTip(0, "View and manually edit the complete extracted document text.")

        # Tab 2: Page-by-Page Inspector
        page_widget = QWidget()
        page_layout = QHBoxLayout(page_widget)
        page_layout.setContentsMargins(6, 6, 6, 6)
        page_layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # Page List with tooltip
        self.page_list = QListWidget()
        self.page_list.setMinimumWidth(160)
        self.page_list.setMaximumWidth(210)
        self.page_list.setToolTip("Click a page to inspect its specific extracted text.")
        self.page_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #e2e8f0;
                border-radius: 5px;
                font-size: 11.5px;
                font-family: {FONT_FAMILY_STACK};
                background-color: #f8fafc;
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid #f1f5f9;
            }}
            QListWidget::item:selected {{
                background-color: #dbeafe;
                color: #1e40af;
                font-weight: bold;
                border-radius: 4px;
            }}
        """)
        self.page_list.currentRowChanged.connect(self._on_page_selected)
        splitter.addWidget(self.page_list)

        # Single Page Inspector View
        single_page_container = QWidget()
        single_page_layout = QVBoxLayout(single_page_container)
        single_page_layout.setContentsMargins(0, 0, 0, 0)
        single_page_layout.setSpacing(4)

        self.single_page_header = QLabel("Page Content")
        self.single_page_header.setStyleSheet(f"font-size: 11px; font-weight: bold; color: #64748b; font-family: {FONT_FAMILY_STACK}; padding-left: 2px;")
        single_page_layout.addWidget(self.single_page_header)

        self.single_page_editor = QTextEdit()
        self.single_page_editor.setReadOnly(True)
        self.single_page_editor.setToolTip("Read-only view of text on the selected page.")
        self.single_page_editor.setStyleSheet(f"""
            QTextEdit {{
                font-family: {FONT_FAMILY_STACK};
                font-size: 12.5px;
                line-height: 1.5;
                padding: 10px;
                border: 1px solid #e2e8f0;
                border-radius: 5px;
                background-color: #ffffff;
                color: #0f172a;
            }}
        """)
        single_page_layout.addWidget(self.single_page_editor)

        splitter.addWidget(single_page_container)
        splitter.setSizes([170, 680])

        page_layout.addWidget(splitter)
        self.tabs.addTab(page_widget, "📑 Page-by-Page")
        self.tabs.setTabToolTip(1, "Inspect and navigate through individual pages of the document.")

        layout.addWidget(self.tabs)

    def display_extraction_result(self, result: Dict[str, Any]):
        """Populates the preview panel with extracted text and metrics."""
        if not result.get("success", False):
            self.status_label.setText(f"❌ Error: {result.get('error', 'Unknown extraction error')}")
            self.clear()
            return

        if result.get("is_empty", False):
            self.status_label.setText("⚠️ Scanned Image or Blank PDF (No digital text found)")
            empty_msg = (
                "No digital text layer found in this document.\n\n"
                "This document is likely a scanned image or photo.\n"
                "OCR processing for scanned documents will be available in an upcoming update."
            )
            self.text_editor.setPlainText(empty_msg)
            self._original_text = empty_msg
            self._is_dirty = False
            total_pages = result.get("page_count", 0)
            self.pages_metric.setText(f"Pages: {total_pages}")
            self.words_metric.setText("Words: 0")
            self.chars_metric.setText("Characters: 0")
            return

        full_text = result.get("full_text", "")
        total_pages = result.get("page_count", 0)
        self._pages_data = result.get("pages", [])
        self._original_text = full_text
        self._is_dirty = False

        # Update text view
        self.text_editor.setPlainText(full_text)
        self.status_label.setText("✅ Text Extracted Successfully")

        # Update metrics
        self.pages_metric.setText(f"Pages: {total_pages}")
        self._update_word_char_counts(full_text)

        # Populate page list tab
        self.page_list.clear()
        for page in self._pages_data:
            item = QListWidgetItem(f"Page {page['page_number']}  ({page.get('word_count', 0)} words)")
            self.page_list.addItem(item)

        if self._pages_data:
            self.page_list.setCurrentRow(0)

    def _on_page_selected(self, row: int):
        if 0 <= row < len(self._pages_data):
            page_info = self._pages_data[row]
            page_num = page_info.get("page_number", row + 1)
            page_text = page_info.get("text", "")
            word_count = page_info.get("word_count", 0)

            self.single_page_header.setText(f"Page {page_num} of {len(self._pages_data)} • {word_count} words")
            self.single_page_editor.setPlainText(page_text if page_text else "(No extractable digital text on this page)")

    def _on_text_edited(self):
        text = self.text_editor.toPlainText()
        self._update_word_char_counts(text)
        # Mark dirty if edited text differs from original
        self._is_dirty = (text != self._original_text)

    def _update_word_char_counts(self, text: str):
        char_count = len(text)
        word_count = len(text.split())
        self.words_metric.setText(f"Words: {word_count:,}")
        self.chars_metric.setText(f"Characters: {char_count:,}")

    def get_current_text(self) -> str:
        """Returns the current (potentially edited) text from the editor."""
        return self.text_editor.toPlainText()

    def has_unsaved_edits(self) -> bool:
        """Returns True if the text in editor was modified since last extraction or export."""
        return self._is_dirty

    def mark_saved(self):
        """Marks current text as saved, resetting the dirty flag."""
        self._original_text = self.text_editor.toPlainText()
        self._is_dirty = False

    def clear(self):
        """Resets all preview panel state, text editors, page lists, and metric badges."""
        self._pages_data = []
        self._original_text = ""
        self._is_dirty = False
        self.text_editor.setPlainText("")
        self.page_list.clear()
        self.single_page_editor.setPlainText("")
        self.single_page_header.setText("Page Content")
        self.status_label.setText("Ready")
        self.pages_metric.setText("Pages: 0")
        self.words_metric.setText("Words: 0")
        self.chars_metric.setText("Characters: 0")
        self.tabs.setCurrentIndex(0)
