"""
ui/preview_panel.py
-------------------
Panel component providing dual-pane inspection, manual correction, and honest quality validation:
1. Split View: Original text on the left, Translated text on the right with clear headings.
2. Dual-tab support: Full Document and Page-by-Page inspector with matching dual text alignment.
3. Unsaved-edits tracking for both Original and Translated text.
4. Honest Quality Indicators:
   - Real Tesseract word-confidence average across pages (flagging pages < 80%).
   - Automated translation heuristic sanity check (length plausibility, script conversion).
   - Source language detection badge with low-confidence / Hindi-Marathi correction dropdown.
"""

from typing import List, Dict, Any, Optional
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
    QComboBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from config.settings import FONT_FAMILY_STACK, OCR_CONFIDENCE_THRESHOLD
from translation.language_detector import DetectionResult
from translation.quality_checker import (
    evaluate_translation_sanity,
    compute_document_ocr_confidence,
    TranslationSanityReport,
)


class PreviewPanel(QWidget):
    """
    Dual-pane text preview widget allowing inspection, manual correction,
    and quality monitoring across Original and Translated document text.
    """

    language_corrected = Signal(str)  # Emitted when user overrides detected source language

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._pages_data: List[Dict[str, Any]] = []
        self._translated_pages: List[Dict[str, Any]] = []
        self._original_text: str = ""
        self._original_trans_text: str = ""
        self._is_dirty_orig: bool = False
        self._is_dirty_trans: bool = False
        self._detected_lang_result: Optional[DetectionResult] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        # ----------------------------------------------------------------------
        # 1. Top Metrics, Detection & Honest Quality Ribbon
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
        metrics_layout.setSpacing(6)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"font-weight: bold; color: #1e293b; font-size: 11px; font-family: {FONT_FAMILY_STACK};")
        self.status_label.setToolTip("Current document processing and extraction status.")
        metrics_layout.addWidget(self.status_label)

        # Source Language Detection Badge with Tooltip
        self.lang_badge = QLabel("🌐 Source: Auto")
        self.lang_badge.setStyleSheet(f"""
            QLabel {{
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10.5px;
                color: #334155;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        self.lang_badge.setToolTip("Detected source document language. Based on offline script and lexical analysis.")
        metrics_layout.addWidget(self.lang_badge)

        # Disambiguation / Correction dropdown (visible for low-confidence or Hindi/Marathi)
        self.combo_correct_lang = QComboBox()
        self.combo_correct_lang.setToolTip("Correct the detected source language if inaccurate.")
        self.combo_correct_lang.addItem("Hindi", "hin")
        self.combo_correct_lang.addItem("Marathi", "mar")
        self.combo_correct_lang.addItem("English", "eng")
        self.combo_correct_lang.addItem("Tamil", "tam")
        self.combo_correct_lang.addItem("Telugu", "tel")
        self.combo_correct_lang.addItem("Bengali", "ben")
        self.combo_correct_lang.setStyleSheet(f"""
            QComboBox {{
                font-size: 10.5px;
                padding: 1px 4px;
                min-height: 20px;
                max-width: 90px;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        self.combo_correct_lang.currentIndexChanged.connect(self._on_language_correction_changed)
        self.combo_correct_lang.hide()
        metrics_layout.addWidget(self.combo_correct_lang)

        # Honest Quality Badges (OCR & Translation)
        self.ocr_quality_badge = QLabel("🔍 OCR Conf: --")
        self.ocr_quality_badge.setStyleSheet(f"""
            QLabel {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10.5px;
                color: #0f766e;
                font-weight: 600;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        self.ocr_quality_badge.setToolTip(
            "Honest OCR Confidence: Aggregated word-level confidence reported directly by Tesseract. "
            "Pages below 80% are flagged in the page list. This is a heuristic confidence indicator, not guaranteed accuracy."
        )
        metrics_layout.addWidget(self.ocr_quality_badge)

        self.trans_quality_badge = QLabel("✓ Basic Check: --")
        self.trans_quality_badge.setStyleSheet(f"""
            QLabel {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10.5px;
                color: #1e40af;
                font-weight: 600;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        self.trans_quality_badge.setToolTip(
            "Translation Basic Check: Evaluates output completeness, character length ratio, "
            "and script conversion. This is an automated heuristic check, not a linguistic accuracy score."
        )
        metrics_layout.addWidget(self.trans_quality_badge)

        metrics_layout.addStretch()

        # Document Metrics Pills
        pill_style = f"""
            QLabel {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10.5px;
                color: #334155;
                font-weight: 500;
                font-family: {FONT_FAMILY_STACK};
            }}
        """
        self.pages_metric = QLabel("Pages: 0")
        self.pages_metric.setStyleSheet(pill_style)
        metrics_layout.addWidget(self.pages_metric)

        self.words_metric = QLabel("Words: 0")
        self.words_metric.setStyleSheet(pill_style)
        metrics_layout.addWidget(self.words_metric)

        self.chars_metric = QLabel("Characters: 0")
        self.chars_metric.setStyleSheet(pill_style)
        metrics_layout.addWidget(self.chars_metric)

        layout.addWidget(metrics_frame)

        # ----------------------------------------------------------------------
        # 2. Main Tabbed Split View: Full Document vs Page-by-Page Breakdown
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
        """)

        # ----------------------------------------------------------------------
        # Tab 1: Full Document Split View (Original | Translated)
        # ----------------------------------------------------------------------
        full_doc_container = QWidget()
        full_doc_layout = QVBoxLayout(full_doc_container)
        full_doc_layout.setContentsMargins(4, 4, 4, 4)
        full_doc_layout.setSpacing(4)

        full_splitter = QSplitter(Qt.Horizontal)

        # Left: Original Document Editor
        orig_box = QFrame()
        orig_layout = QVBoxLayout(orig_box)
        orig_layout.setContentsMargins(4, 4, 4, 4)
        orig_layout.setSpacing(4)
        self.lbl_orig_header = QLabel("📄 <b>Original Document Text</b>")
        self.lbl_orig_header.setStyleSheet(f"font-size: 11.5px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        orig_layout.addWidget(self.lbl_orig_header)

        self.text_editor = QTextEdit()
        self.text_editor.setPlaceholderText("Extracted text will appear here. Editable in-place.")
        self.text_editor.setStyleSheet(f"font-family: {FONT_FAMILY_STACK}; font-size: 12.5px; line-height: 1.5; padding: 8px; border: 1px solid #e2e8f0; border-radius: 4px;")
        self.text_editor.textChanged.connect(self._on_orig_text_edited)
        orig_layout.addWidget(self.text_editor)
        full_splitter.addWidget(orig_box)

        # Right: Translated Document Editor
        trans_box = QFrame()
        trans_layout = QVBoxLayout(trans_box)
        trans_layout.setContentsMargins(4, 4, 4, 4)
        trans_layout.setSpacing(4)
        self.lbl_trans_header = QLabel("🌐 <b>Translated Text</b>")
        self.lbl_trans_header.setStyleSheet(f"font-size: 11.5px; color: #1e40af; font-family: {FONT_FAMILY_STACK};")
        trans_layout.addWidget(self.lbl_trans_header)

        self.trans_editor = QTextEdit()
        self.trans_editor.setPlaceholderText("Offline translation will appear here. Editable in-place.")
        self.trans_editor.setStyleSheet(f"font-family: {FONT_FAMILY_STACK}; font-size: 12.5px; line-height: 1.5; padding: 8px; border: 1px solid #bfdbfe; border-radius: 4px;")
        self.trans_editor.textChanged.connect(self._on_trans_text_edited)
        trans_layout.addWidget(self.trans_editor)
        full_splitter.addWidget(trans_box)

        full_splitter.setSizes([450, 450])
        full_doc_layout.addWidget(full_splitter)
        self.tabs.addTab(full_doc_container, "📝 Full Document")

        # ----------------------------------------------------------------------
        # Tab 2: Page-by-Page Split Inspector (List | Original Page | Translated Page)
        # ----------------------------------------------------------------------
        page_widget = QWidget()
        page_layout = QHBoxLayout(page_widget)
        page_layout.setContentsMargins(4, 4, 4, 4)
        page_layout.setSpacing(4)

        page_splitter = QSplitter(Qt.Horizontal)

        # Page List (Left)
        self.page_list = QListWidget()
        self.page_list.setMinimumWidth(160)
        self.page_list.setMaximumWidth(220)
        self.page_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid #e2e8f0;
                border-radius: 5px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                background-color: #f8fafc;
            }}
            QListWidget::item {{
                padding: 5px 6px;
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
        page_splitter.addWidget(self.page_list)

        # Middle: Single Page Original
        single_orig_container = QWidget()
        single_orig_layout = QVBoxLayout(single_orig_container)
        single_orig_layout.setContentsMargins(2, 2, 2, 2)
        single_orig_layout.setSpacing(4)

        self.single_page_header = QLabel("Page Content")
        self.single_page_header.setStyleSheet(f"font-size: 11px; font-weight: bold; color: #475569; font-family: {FONT_FAMILY_STACK};")
        single_orig_layout.addWidget(self.single_page_header)

        self.single_page_editor = QTextEdit()
        self.single_page_editor.setReadOnly(True)
        self.single_page_editor.setStyleSheet(f"font-family: {FONT_FAMILY_STACK}; font-size: 12px; border: 1px solid #e2e8f0; border-radius: 4px;")
        single_orig_layout.addWidget(self.single_page_editor)
        page_splitter.addWidget(single_orig_container)

        # Right: Single Page Translated
        single_trans_container = QWidget()
        single_trans_layout = QVBoxLayout(single_trans_container)
        single_trans_layout.setContentsMargins(2, 2, 2, 2)
        single_trans_layout.setSpacing(4)

        self.single_page_trans_header = QLabel("Translated Page Content")
        self.single_page_trans_header.setStyleSheet(f"font-size: 11px; font-weight: bold; color: #1e40af; font-family: {FONT_FAMILY_STACK};")
        single_trans_layout.addWidget(self.single_page_trans_header)

        self.single_page_trans_editor = QTextEdit()
        self.single_page_trans_editor.setStyleSheet(f"font-family: {FONT_FAMILY_STACK}; font-size: 12px; border: 1px solid #bfdbfe; border-radius: 4px;")
        self.single_page_trans_editor.textChanged.connect(self._on_single_page_trans_edited)
        single_trans_layout.addWidget(self.single_page_trans_editor)
        page_splitter.addWidget(single_trans_container)

        page_splitter.setSizes([180, 360, 360])
        page_layout.addWidget(page_splitter)
        self.tabs.addTab(page_widget, "📑 Page-by-Page")

        layout.addWidget(self.tabs)

    # --------------------------------------------------------------------------
    # Incremental Updates & State Population
    # --------------------------------------------------------------------------
    def append_or_update_page(self, page_data: Dict[str, Any], total_pages: int):
        page_num = page_data.get("page_number", 1)

        # Update or insert page
        existing_idx = next((i for i, p in enumerate(self._pages_data) if p.get("page_number") == page_num), None)
        if existing_idx is not None:
            self._pages_data[existing_idx] = page_data
        else:
            self._pages_data.append(page_data)
            self._pages_data.sort(key=lambda p: p.get("page_number", 0))

        self._refresh_page_list()
        full_text = "\n\n--- Page Break ---\n\n".join(p.get("text", "") for p in self._pages_data)
        self.text_editor.setPlainText(full_text)
        self._original_text = full_text
        self._is_dirty_orig = False

        self.pages_metric.setText(f"Pages: {len(self._pages_data)} / {total_pages}")
        self._update_word_char_counts(full_text)
        self.status_label.setText(f"Processing Page {len(self._pages_data)} of {total_pages}...")

    def update_translation_page(self, page_data: Dict[str, Any], total_pages: int):
        """Incrementally updates translated page data as translation progresses."""
        p_num = page_data.get("page_number", 1)
        existing_idx = next((i for i, p in enumerate(self._translated_pages) if p.get("page_number") == p_num), None)
        if existing_idx is not None:
            self._translated_pages[existing_idx] = page_data
        else:
            self._translated_pages.append(page_data)
            self._translated_pages.sort(key=lambda p: p.get("page_number", 0))

        full_trans = "\n\n--- Page Break ---\n\n".join(p.get("translated_text", "") for p in self._translated_pages)
        self.trans_editor.setPlainText(full_trans)
        self._original_trans_text = full_trans
        self._is_dirty_trans = False

        # Update current page editor if selected
        curr_row = self.page_list.currentRow()
        if 0 <= curr_row < len(self._translated_pages):
            if self._translated_pages[curr_row].get("page_number") == p_num:
                self.single_page_trans_editor.setPlainText(page_data.get("translated_text", ""))

        # Update sanity check badge
        last_sanity: TranslationSanityReport = page_data.get("sanity_report")
        if last_sanity:
            icon = "✓" if last_sanity.status == "Passed" else "⚠️"
            self.trans_quality_badge.setText(f"{icon} {last_sanity.summary}")

    def display_extraction_result(self, result: Dict[str, Any]):
        if not result.get("success", False):
            self.status_label.setText(f"❌ Error: {result.get('error', 'Unknown extraction error')}")
            self.clear()
            return

        full_text = result.get("full_text", "")
        total_pages = result.get("page_count", 0)
        self._pages_data = result.get("pages", [])
        self._original_text = full_text
        self._is_dirty_orig = False

        self.text_editor.setPlainText(full_text)
        direct_count = result.get("direct_pages", 0)
        ocr_count = result.get("ocr_pages", 0)
        if direct_count > 0 or ocr_count > 0:
            self.status_label.setText(f"✅ Extracted {total_pages} Pages ({direct_count} Direct, {ocr_count} OCR)")
        else:
            self.status_label.setText("✅ Text Extracted Successfully")

        self.pages_metric.setText(f"Pages: {total_pages}")
        self._update_word_char_counts(full_text)
        self._refresh_page_list()

        # Update aggregate OCR confidence
        ocr_summary = compute_document_ocr_confidence(self._pages_data)
        if ocr_summary["has_ocr"]:
            conf_val = int(round(ocr_summary["document_confidence"]))
            warn = " ⚠️" if ocr_summary["low_confidence_pages"] else ""
            self.ocr_quality_badge.setText(f"🔍 OCR Conf: {conf_val}%{warn}")
            self.ocr_quality_badge.setToolTip(ocr_summary["display_str"])
        else:
            self.ocr_quality_badge.setText("⚡ 100% Digital Text")
            self.ocr_quality_badge.setToolTip("Document contains digital selectable text layers. Zero OCR needed.")

        if self._pages_data:
            self.page_list.setCurrentRow(0)

    def display_translation_result(self, result: Dict[str, Any]):
        """Populates the complete translation result."""
        full_trans = result.get("full_translated_text", "")
        self._translated_pages = result.get("translated_pages", [])
        self._original_trans_text = full_trans
        self._is_dirty_trans = False
        self.trans_editor.setPlainText(full_trans)

        was_pivoted = result.get("was_pivoted", False)
        skipped = result.get("skipped", False)

        if skipped:
            self.trans_quality_badge.setText("ℹ️ Same Language (Skipped)")
        elif was_pivoted:
            self.trans_quality_badge.setText("⚠️ Pivoted (via English)")
        else:
            self.trans_quality_badge.setText("✓ Translated (Direct)")

        # Sync current page
        curr_row = self.page_list.currentRow()
        if 0 <= curr_row < len(self._translated_pages):
            self.single_page_trans_editor.setPlainText(self._translated_pages[curr_row].get("translated_text", ""))

    def set_detected_language(self, det: DetectionResult):
        """Displays honest source language detection and activates correction dropdown if needed."""
        self._detected_lang_result = det
        self.lang_badge.setText(det.get_display_str())
        if det.requires_user_confirmation:
            # Show correction dropdown for ambiguous or Hindi/Marathi results
            idx = self.combo_correct_lang.findData(det.language_code)
            if idx >= 0:
                self.combo_correct_lang.blockSignals(True)
                self.combo_correct_lang.setCurrentIndex(idx)
                self.combo_correct_lang.blockSignals(False)
            self.combo_correct_lang.show()
        else:
            self.combo_correct_lang.hide()

    def _on_language_correction_changed(self):
        new_code = self.combo_correct_lang.currentData()
        new_name = self.combo_correct_lang.currentText()
        self.lang_badge.setText(f"User Selected: {new_name}")
        self.language_corrected.emit(new_code)

    def _refresh_page_list(self):
        self.page_list.clear()
        for page in self._pages_data:
            p_no = page.get("page_number", 1)
            p_words = page.get("word_count", 0)
            p_src = "⚡" if page.get("source") == "direct" else "🔍"
            conf = page.get("ocr_confidence", 100.0)
            low_warn = " ⚠️" if (page.get("source") == "ocr" and conf < OCR_CONFIDENCE_THRESHOLD) else ""
            item = QListWidgetItem(f"Page {p_no} ({p_words}w) [{p_src}]{low_warn}")
            if low_warn:
                item.setToolTip(f"Low OCR confidence ({int(conf)}%). Please review this page carefully.")
            self.page_list.addItem(item)

    def _on_page_selected(self, row: int):
        if 0 <= row < len(self._pages_data):
            p_info = self._pages_data[row]
            p_num = p_info.get("page_number", row + 1)
            p_text = p_info.get("text", "")
            w_count = p_info.get("word_count", 0)
            self.single_page_header.setText(f"Page {p_num} of {len(self._pages_data)} • {w_count} words")
            self.single_page_editor.setPlainText(p_text if p_text else "(No extractable digital text on this page)")

        if 0 <= row < len(self._translated_pages):
            trans_info = self._translated_pages[row]
            t_text = trans_info.get("translated_text", "")
            tw_count = trans_info.get("word_count", 0)
            self.single_page_trans_header.setText(f"Translated Page {row + 1} • {tw_count} words")
            self.single_page_trans_editor.setPlainText(t_text if t_text else "(No translation available for this page)")
        else:
            self.single_page_trans_header.setText("Translated Page Content")
            self.single_page_trans_editor.setPlainText("")

    def _on_orig_text_edited(self):
        text = self.text_editor.toPlainText()
        self._update_word_char_counts(text)
        self._is_dirty_orig = (text != self._original_text)

    def _on_trans_text_edited(self):
        text = self.trans_editor.toPlainText()
        self._is_dirty_trans = (text != self._original_trans_text)

    def _on_single_page_trans_edited(self):
        curr_row = self.page_list.currentRow()
        if 0 <= curr_row < len(self._translated_pages):
            self._translated_pages[curr_row]["translated_text"] = self.single_page_trans_editor.toPlainText()
            # Sync full document translated editor
            full = "\n\n--- Page Break ---\n\n".join(p.get("translated_text", "") for p in self._translated_pages)
            self.trans_editor.setPlainText(full)
            self._is_dirty_trans = True

    def _update_word_char_counts(self, text: str):
        self.words_metric.setText(f"Words: {len(text.split()):,}")
        self.chars_metric.setText(f"Characters: {len(text):,}")

    def get_current_text(self) -> str:
        return self.text_editor.toPlainText()

    def get_ai_enhance_target_text(self) -> Tuple[str, str, str]:
        """
        Retrieves text for AI Enhancement according to user selection / active page:
        Returns: (text_snippet, scope_description, context_type)
        - Selected text has priority.
        - Otherwise, currently viewed page in Page-by-Page tab.
        - Otherwise, active page or visible text. Never silently transmits entire document.
        """
        # 1. Check user highlighted selection in Full Document tab
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            sel = cursor.selectedText().replace("\u2029", "\n").strip()
            if sel:
                return sel, "Highlighted Text Selection (Full Doc)", "selection_full"

        # 2. Check user highlighted selection in Page-by-Page tab
        p_cursor = self.single_page_editor.textCursor()
        if p_cursor.hasSelection():
            sel = p_cursor.selectedText().replace("\u2029", "\n").strip()
            if sel:
                return sel, "Highlighted Text Selection (Single Page)", "selection_single"

        # 3. Check active page in Page-by-Page tab
        if self.tabs.currentIndex() == 1 and self._pages_data:
            curr_row = self.page_list.currentRow()
            if 0 <= curr_row < len(self._pages_data):
                p_text = self._pages_data[curr_row].get("text", "").strip()
                p_num = self._pages_data[curr_row].get("page_number", curr_row + 1)
                return p_text, f"Page {p_num} (Selected Page)", "page_single"

        # 4. In Full Document tab, if multi-page, return page 1
        if self._pages_data:
            p1_text = self._pages_data[0].get("text", "").strip()
            p1_num = self._pages_data[0].get("page_number", 1)
            return p1_text, f"Page {p1_num} (Selected Page)", "page_single"

        full_txt = self.get_current_text().strip()
        return full_txt, "Current Document View", "document"

    def apply_enhanced_text(self, enhanced_text: str, context_type: str):
        """
        Safely applies approved AI enhanced text back to the editor according to the original scope.
        """
        if context_type == "selection_full":
            cursor = self.text_editor.textCursor()
            if cursor.hasSelection():
                cursor.insertText(enhanced_text)
                self._is_dirty_orig = True
                self._update_word_char_counts(self.text_editor.toPlainText())
                return

        if context_type == "selection_single":
            p_cursor = self.single_page_editor.textCursor()
            if p_cursor.hasSelection():
                p_cursor.insertText(enhanced_text)
                self._on_single_page_edited()
                return

        if context_type == "page_single":
            curr_row = self.page_list.currentRow()
            if curr_row < 0:
                curr_row = 0
            if 0 <= curr_row < len(self._pages_data):
                self._pages_data[curr_row]["text"] = enhanced_text
                self.single_page_editor.blockSignals(True)
                self.single_page_editor.setPlainText(enhanced_text)
                self.single_page_editor.blockSignals(False)
                # Rebuild full document text
                full_rebuilt = "\n\n--- Page Break ---\n\n".join(p.get("text", "") for p in self._pages_data)
                self.text_editor.blockSignals(True)
                self.text_editor.setPlainText(full_rebuilt)
                self.text_editor.blockSignals(False)
                self._is_dirty_orig = True
                self._update_word_char_counts(full_rebuilt)
                return

        # Fallback: document
        self.text_editor.setPlainText(enhanced_text)
        self._is_dirty_orig = True
        self._update_word_char_counts(enhanced_text)

    def get_translated_text(self) -> str:
        return self.trans_editor.toPlainText()

    def get_bilingual_side_by_side_text(self) -> str:
        """Generates clean dual-column or alternating bilingual text for export."""
        orig_paragraphs = self.get_current_text().split("\n\n")
        trans_paragraphs = self.get_translated_text().split("\n\n")
        combined = []
        max_len = max(len(orig_paragraphs), len(trans_paragraphs))
        for i in range(max_len):
            orig_p = orig_paragraphs[i] if i < len(orig_paragraphs) else ""
            trans_p = trans_paragraphs[i] if i < len(trans_paragraphs) else ""
            combined.append(f"[Original]\n{orig_p}\n\n[Translation]\n{trans_p}")
        return "\n\n" + ("=" * 50) + "\n\n".join(combined)

    def has_unsaved_edits(self) -> bool:
        return self._is_dirty_orig or self._is_dirty_trans

    def mark_saved(self):
        self._original_text = self.text_editor.toPlainText()
        self._original_trans_text = self.trans_editor.toPlainText()
        self._is_dirty_orig = False
        self._is_dirty_trans = False

    def clear(self):
        self._pages_data = []
        self._translated_pages = []
        self._original_text = ""
        self._original_trans_text = ""
        self._is_dirty_orig = False
        self._is_dirty_trans = False
        self._detected_lang_result = None
        self.text_editor.setPlainText("")
        self.trans_editor.setPlainText("")
        self.page_list.clear()
        self.single_page_editor.setPlainText("")
        self.single_page_trans_editor.setPlainText("")
        self.status_label.setText("Ready")
        self.lang_badge.setText("🌐 Source: Auto")
        self.combo_correct_lang.hide()
        self.ocr_quality_badge.setText("🔍 OCR Conf: --")
        self.trans_quality_badge.setText("✓ Basic Check: --")
        self.pages_metric.setText("Pages: 0")
        self.words_metric.setText("Words: 0")
        self.chars_metric.setText("Characters: 0")
        self.tabs.setCurrentIndex(0)
