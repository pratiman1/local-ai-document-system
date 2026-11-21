"""
ui/main_window.py
-----------------
The central desktop window for the Local AI Multilingual Document Processing System.
Assembles the modular panels:
- UploadPanel (compact horizontal document ingestion, replace option & remove button)
- LanguageSelector (left sidebar dropdown with visible arrow & tooltips)
- PreviewPanel (metrics, full text editor, page breakdown with dirty state tracking)
- ExportPanel (TXT export controls with dynamic enable/disable)
- SystemInfoPanel (dynamic cross-platform hardware and OS detection)

Coordinates remove/replace workflows with unsaved edits confirmation dialogs.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QFrame,
    QLabel,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QMessageBox,
    QFileDialog,
)
from PySide6.QtCore import Qt

from config.settings import (
    APP_NAME,
    APP_VERSION,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_DEFAULT_HEIGHT,
    GLOBAL_STYLESHEET,
    STATUS_OFFLINE,
    STATUS_ONLINE_PROGRESS,
    FONT_FAMILY_STACK,
    AI_ENHANCE_ENABLED_DEFAULT,
    AI_DEFAULT_PROVIDER,
    AI_ENHANCE_MAX_CHARS,
)
from ui.upload_panel import UploadPanel
from ui.language_selector import LanguageSelector
from ui.preview_panel import PreviewPanel
from ui.export_panel import ExportPanel
from ui.system_info_panel import SystemInfoPanel
from extractors.pdf_extractor import extract_text_from_pdf
from ocr.ocr_pipeline import OCRWorkerThread
from ocr.engine_factory import get_engine
from ocr.language_mapping import map_app_lang_to_tesseract, get_missing_language_instructions
from translation.language_detector import detect_document_language, DetectionResult
from translation.translator_factory import get_translator
from translation.translation_pipeline import TranslationWorkerThread
from services.ai_provider import get_ai_provider, AIProviderError
from services.keychain_manager import get_api_key, get_provider_config
from ui.ai_enhance_dialog import AIEnhanceConfirmDialog, AIEnhanceResultDialog
from ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """
    Main application window orchestrating the document processing pipeline.
    """

    def __init__(self):
        super().__init__()
        self._current_pdf_path: str = ""
        self._ocr_worker: Optional[OCRWorkerThread] = None
        self._trans_worker: Optional[TranslationWorkerThread] = None
        self._detected_source_lang: str = "eng"
        self._ai_enhance_enabled: bool = AI_ENHANCE_ENABLED_DEFAULT
        self._ai_provider_name: str = AI_DEFAULT_PROVIDER
        self._init_window()
        self._init_ui()
        self._connect_signals()

    def _init_window(self):
        self.setWindowTitle(f"{APP_NAME} (v{APP_VERSION}) — [100% Offline]")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        # Global modern stylesheet including QToolTip and QComboBox dropdown arrow
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: #f8fafc;
            }}
            QLabel {{
                color: #0f172a;
                font-family: {FONT_FAMILY_STACK};
            }}
            QStatusBar {{
                background-color: #ffffff;
                border-top: 1px solid #e2e8f0;
                color: #475569;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                padding-left: 8px;
            }}
            {GLOBAL_STYLESHEET}
        """)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main Splitter: Left Sidebar | Right Workspace
        splitter = QSplitter(Qt.Horizontal)

        # ----------------------------------------------------------------------
        # LEFT SIDEBAR: System Status & Language Selection
        # ----------------------------------------------------------------------
        sidebar = QFrame()
        sidebar.setMaximumWidth(280)
        sidebar.setMinimumWidth(240)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-right: 1px solid #e2e8f0;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 14)
        sidebar_layout.setSpacing(10)

        # App Brand Header
        brand_label = QLabel("🚀 Local AI DocSystem")
        brand_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #1e293b;")
        brand_label.setToolTip("Local AI Multilingual Document Processing Desktop Application")
        sidebar_layout.addWidget(brand_label)

        sub_label = QLabel("Multilingual Offline Document Processor")
        sub_label.setStyleSheet("font-size: 10.5px; color: #64748b;")
        sidebar_layout.addWidget(sub_label)

        # Connection Badge (Accurate Offline Status)
        self.conn_badge = QLabel("🟢 100% Offline Mode")
        self.conn_badge.setStyleSheet("""
            QLabel {
                background-color: #f0fdf4;
                color: #166534;
                border: 1px solid #bbf7d0;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 600;
            }
        """)
        self.conn_badge.setToolTip("Application is operating completely offline. No data leaves your computer.")
        sidebar_layout.addWidget(self.conn_badge)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #e2e8f0;")
        sidebar_layout.addWidget(sep)

        # Language Selector Component
        self.language_selector = LanguageSelector()
        sidebar_layout.addWidget(self.language_selector)

        sidebar_layout.addStretch()

        # Dynamic System Information Panel
        self.system_info_panel = SystemInfoPanel()
        sidebar_layout.addWidget(self.system_info_panel)

        splitter.addWidget(sidebar)

        # ----------------------------------------------------------------------
        # RIGHT WORKSPACE: Document Ingestion, Preview & Export
        # ----------------------------------------------------------------------
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(12, 10, 12, 10)
        workspace_layout.setSpacing(6)

        # Compact Horizontal Upload Panel with Remove & Replace capabilities
        self.upload_panel = UploadPanel()
        workspace_layout.addWidget(self.upload_panel)

        # Compact OCR Progress Bar & Cancel Control (Visible during processing)
        self.ocr_progress_container = QFrame()
        self.ocr_progress_container.setStyleSheet(f"""
            QFrame {{
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }}
        """)
        progress_layout = QHBoxLayout(self.ocr_progress_container)
        progress_layout.setContentsMargins(8, 4, 8, 4)
        progress_layout.setSpacing(8)

        self.lbl_progress_status = QLabel("Processing: Page 0 of 0")
        self.lbl_progress_status.setStyleSheet(f"font-size: 11px; font-weight: 500; color: #1e293b; font-family: {FONT_FAMILY_STACK};")
        self.lbl_progress_status.setToolTip("Current OCR page completion and estimated time remaining (ETA).")
        progress_layout.addWidget(self.lbl_progress_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setToolTip("Overall document page completion progress.")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #cbd5e1;
                border-radius: 3px;
                background-color: #ffffff;
                text-align: center;
                font-size: 9.5px;
                color: #1e293b;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 2px;
            }
        """)
        progress_layout.addWidget(self.progress_bar, stretch=1)

        self.btn_cancel_ocr = QPushButton("Cancel")
        self.btn_cancel_ocr.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_ocr.setToolTip("Cancel OCR processing and preserve all completed pages.")
        self.btn_cancel_ocr.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #991b1b;
                border: 1px solid #fca5a5;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #fecaca;
            }
        """)
        self.btn_cancel_ocr.clicked.connect(self._handle_cancel_ocr_clicked)
        progress_layout.addWidget(self.btn_cancel_ocr)

        self.ocr_progress_container.hide()
        workspace_layout.addWidget(self.ocr_progress_container)

        # Compact Translation Progress Bar & Cancel Control (Visible during translation)
        self.trans_progress_container = QFrame()
        self.trans_progress_container.setStyleSheet(f"""
            QFrame {{
                background-color: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 6px;
            }}
        """)
        trans_prog_layout = QHBoxLayout(self.trans_progress_container)
        trans_prog_layout.setContentsMargins(8, 4, 8, 4)
        trans_prog_layout.setSpacing(8)

        self.lbl_trans_status = QLabel("Translating: Page 0 of 0 • ETA: --")
        self.lbl_trans_status.setStyleSheet(f"font-size: 11px; font-weight: 500; color: #1e40af; font-family: {FONT_FAMILY_STACK};")
        self.lbl_trans_status.setToolTip("Current offline translation progress and estimated time remaining.")
        trans_prog_layout.addWidget(self.lbl_trans_status)

        self.trans_progress_bar = QProgressBar()
        self.trans_progress_bar.setRange(0, 100)
        self.trans_progress_bar.setValue(0)
        self.trans_progress_bar.setTextVisible(True)
        self.trans_progress_bar.setFixedHeight(14)
        self.trans_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bfdbfe;
                border-radius: 3px;
                background-color: #ffffff;
                text-align: center;
                font-size: 9.5px;
                color: #1e3a8a;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
                border-radius: 2px;
            }
        """)
        trans_prog_layout.addWidget(self.trans_progress_bar, stretch=1)

        self.btn_cancel_trans = QPushButton("Cancel")
        self.btn_cancel_trans.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_trans.setToolTip("Cancel translation and preserve all completed pages.")
        self.btn_cancel_trans.setStyleSheet("""
            QPushButton {
                background-color: #fee2e2;
                color: #991b1b;
                border: 1px solid #fca5a5;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #fecaca;
            }
        """)
        self.btn_cancel_trans.clicked.connect(self._handle_cancel_trans_clicked)
        trans_prog_layout.addWidget(self.btn_cancel_trans)

        self.trans_progress_container.hide()
        workspace_layout.addWidget(self.trans_progress_container)

        # AI Action Toolbar (Settings & AI Enhance)
        ai_toolbar = QWidget()
        ai_toolbar_layout = QHBoxLayout(ai_toolbar)
        ai_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        ai_toolbar_layout.setSpacing(6)

        self.lbl_offline_guarantee = QLabel("🔒 <b>100% Offline Processing Active</b>")
        self.lbl_offline_guarantee.setStyleSheet(f"font-size: 10.5px; color: #166534; font-family: {FONT_FAMILY_STACK};")
        self.lbl_offline_guarantee.setToolTip("All OCR, translation, and text editing operations run 100% locally on your machine.")
        ai_toolbar_layout.addWidget(self.lbl_offline_guarantee)

        ai_toolbar_layout.addStretch()

        self.btn_ai_enhance = QPushButton("✨ AI Enhance")
        self.btn_ai_enhance.setCursor(Qt.PointingHandCursor)
        self.btn_ai_enhance.setEnabled(False)
        self.btn_ai_enhance.setToolTip("Enhance active text using online AI (Disabled until allowed in Settings).")
        self.btn_ai_enhance.setStyleSheet(f"""
            QPushButton {{
                background-color: #7c3aed;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 3px 12px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                min-height: 22px;
            }}
            QPushButton:hover {{
                background-color: #6d28d9;
            }}
            QPushButton:disabled {{
                background-color: #e2e8f0;
                color: #94a3b8;
            }}
        """)
        self.btn_ai_enhance.clicked.connect(self._handle_ai_enhance_clicked)
        ai_toolbar_layout.addWidget(self.btn_ai_enhance)

        self.btn_settings = QPushButton("⚙️ Settings")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Configure application preferences, translation engines, and online AI permissions.")
        self.btn_settings.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                min-height: 22px;
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
        """)
        self.btn_settings.clicked.connect(self._handle_settings_clicked)
        ai_toolbar_layout.addWidget(self.btn_settings)

        workspace_layout.addWidget(ai_toolbar)

        # Text Preview & Correction Panel
        self.preview_panel = PreviewPanel()
        workspace_layout.addWidget(self.preview_panel, stretch=1)

        # Compact OCR Status Line (Engine, Language, Direct vs OCR count)
        self.lbl_ocr_info = QLabel("⚙️ Engine: Tesseract (LSTM) • Language: English (eng) • Ready")
        self.lbl_ocr_info.setStyleSheet(f"font-size: 10.5px; color: #64748b; font-family: {FONT_FAMILY_STACK}; padding: 0 2px;")
        self.lbl_ocr_info.setToolTip("Active OCR engine, target language, and extraction distribution across document pages.")
        workspace_layout.addWidget(self.lbl_ocr_info)

        # Export Panel (initially disabled until text is available)
        self.export_panel = ExportPanel()
        workspace_layout.addWidget(self.export_panel)

        splitter.addWidget(workspace)
        splitter.setSizes([260, 820])

        main_layout.addWidget(splitter)

        # Status Bar with Accurate Offline Status
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Ready — Select or drop a PDF to begin")

    def _connect_signals(self):
        """Connects Qt signals and slots across panels."""
        self.upload_panel.file_selected.connect(self._handle_file_selected)
        self.upload_panel.browse_requested.connect(self._handle_browse_requested)
        self.upload_panel.remove_requested.connect(self._handle_remove_requested)
        self.export_panel.export_completed.connect(self._handle_export_completed)
        self.language_selector.language_changed.connect(self._handle_language_changed)
        self.language_selector.translate_requested.connect(self._handle_translate_requested)
        self.preview_panel.language_corrected.connect(self._handle_language_corrected)

    def _confirm_unsaved_edits(self) -> bool:
        """
        Prompts the user if there are unsaved edits in the preview editor.
        Returns True if the action is approved (Remove/Proceed), False if user wants to Keep.
        """
        if self.preview_panel.has_unsaved_edits():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Unsaved Edits")
            msg_box.setText("You have unsaved edits. Remove this file anyway?")
            msg_box.setIcon(QMessageBox.Warning)
            btn_remove = msg_box.addButton("Remove", QMessageBox.DestructiveRole)
            btn_keep = msg_box.addButton("Keep", QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_keep)
            msg_box.exec()

            # Return True only if user explicitly confirmed Remove
            return msg_box.clickedButton() == btn_remove
        return True

    def _handle_remove_requested(self):
        """Handles user clicking the Remove (X) button."""
        if not self._confirm_unsaved_edits():
            return
        self.clear_document()

    def _handle_browse_requested(self):
        """Handles user clicking Browse Files or Open Another File."""
        # If a file is already loaded and there are unsaved edits, confirm first
        if self._current_pdf_path and self.preview_panel.has_unsaved_edits():
            if not self._confirm_unsaved_edits():
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF Document",
            "",
            "PDF Files (*.pdf);;All Files (*)",
        )
        if file_path:
            self._handle_file_selected(file_path)

    def handle_incoming_file(self, file_path: str):
        """Handles drag-and-drop replacement with unsaved-edits confirmation."""
        if self._current_pdf_path and self.preview_panel.has_unsaved_edits():
            if not self._confirm_unsaved_edits():
                return
        self._handle_file_selected(file_path)

    def _handle_cancel_ocr_clicked(self):
        """Cancels background OCR processing while preserving completed pages."""
        if self._ocr_worker and self._ocr_worker.isRunning():
            self.lbl_progress_status.setText("Cancelling... preserving completed pages...")
            self.btn_cancel_ocr.setEnabled(False)
            self._ocr_worker.cancel()

    def _handle_file_selected(self, file_path: str, sync: bool = False):
        """Processes the chosen PDF using the background OCR pipeline."""
        # Cancel any previous worker if still running
        if self._ocr_worker and self._ocr_worker.isRunning():
            self._ocr_worker.cancel()
            self._ocr_worker.wait()

        self._current_pdf_path = file_path
        self.status_bar.showMessage(f"Opening: {Path(file_path).name} locally...")

        # Update upload panel state safely without recursive signal emission
        self.upload_panel.set_file(file_path, emit_signal=False)
        self.export_panel.set_document_name(file_path)

        # Quick validation of PDF integrity & page count
        try:
            import pymupdf as fitz
            doc = fitz.open(file_path)
            total_pages = len(doc)
            doc.close()
        except Exception as e:
            self.preview_panel.display_extraction_result({"success": False, "error": str(e)})
            self.export_panel.set_export_enabled(False)
            self.status_bar.showMessage("Error: Invalid or corrupted PDF")
            QMessageBox.critical(
                self,
                "Extraction Error",
                f"Could not read the PDF document:\n\n{str(e)}",
            )
            return

        if total_pages == 0:
            self.preview_panel.display_extraction_result({
                "success": False,
                "page_count": 0,
                "pages": [],
                "full_text": "",
                "is_empty": True,
                "error": "The PDF document contains 0 pages (empty file).",
            })
            self.export_panel.set_export_enabled(False)
            return

        self.upload_panel.update_page_count(total_pages)

        # Target language mapping
        app_lang = self.language_selector.get_selected_language_code()
        tess_lang = map_app_lang_to_tesseract(app_lang)
        lang_name = self.language_selector.get_selected_language_name()

        # Update status line & progress container
        self.lbl_ocr_info.setText(f"⚙️ Engine: Tesseract (LSTM) • Language: {lang_name} ({tess_lang}) • Starting processing...")
        self.lbl_progress_status.setText(f"Page 0 of {total_pages} • Estimating time...")
        self.progress_bar.setRange(0, total_pages)
        self.progress_bar.setValue(0)
        self.btn_cancel_ocr.setEnabled(True)
        self.ocr_progress_container.show()

        # Start background worker thread
        self._ocr_worker = OCRWorkerThread(
            pdf_path=file_path,
            target_lang=tess_lang,
            parent=self,
        )
        self._ocr_worker.page_completed.connect(self._handle_ocr_page_completed)
        self._ocr_worker.pipeline_finished.connect(self._handle_ocr_pipeline_finished)
        self._ocr_worker.pipeline_cancelled.connect(self._handle_ocr_pipeline_cancelled)
        self._ocr_worker.pipeline_error.connect(self._handle_ocr_pipeline_error)
        self._ocr_worker.start()

        # In headless test environments, synchronize to allow direct unit assertions
        if sync or QApplication.platformName() == "offscreen":
            self._ocr_worker.wait()
            QApplication.processEvents()

    def _handle_ocr_page_completed(self, page_dict: Dict[str, Any], completed_count: int, total_pages: int, eta_sec: float):
        """Fires incrementally as each page completes, updating UI in real time."""
        self.progress_bar.setValue(completed_count)
        if eta_sec < 60:
            eta_str = f"{max(1, int(eta_sec))}s"
        else:
            eta_str = f"{int(eta_sec // 60)}m {int(eta_sec % 60)}s"
        self.lbl_progress_status.setText(f"Page {completed_count} of {total_pages} • ETA: {eta_str}")
        self.preview_panel.append_or_update_page(page_dict, total_pages)

    def _handle_ocr_pipeline_finished(self, result: Dict[str, Any]):
        """Fires when all pages finish successfully."""
        self.ocr_progress_container.hide()
        self.preview_panel.display_extraction_result(result)
        has_text = bool(result.get("full_text", "").strip())
        self.export_panel.set_export_enabled(has_text)

        total = result.get("page_count", 0)
        direct = result.get("direct_pages", 0)
        ocr = result.get("ocr_pages", 0)
        lang_name = self.language_selector.get_selected_language_name()
        tess_lang = map_app_lang_to_tesseract(self.language_selector.get_selected_language_code())

        # Automatic offline language detection across extracted pages
        pages = result.get("pages", [])
        if pages:
            doc_lang = detect_document_language(pages)
            self._detected_source_lang = doc_lang.primary_language_code
            det_res = DetectionResult(
                language_code=doc_lang.primary_language_code,
                language_name=doc_lang.primary_language_name,
                script_name="",
                confidence=doc_lang.overall_confidence,
                is_ambiguous=doc_lang.is_mixed or doc_lang.overall_confidence < 0.85 or doc_lang.primary_language_code in ("hin", "mar"),
                requires_user_confirmation=doc_lang.is_mixed or doc_lang.overall_confidence < 0.85 or doc_lang.primary_language_code in ("hin", "mar"),
                details=doc_lang.note,
            )
            self.preview_panel.set_detected_language(det_res)

        self.lbl_ocr_info.setText(
            f"⚙️ Engine: Tesseract (LSTM) • Language: {lang_name} ({tess_lang}) • Direct: {direct} | OCR: {ocr} | Total: {total}"
        )
        self.status_bar.showMessage(
            f"🟢 {STATUS_OFFLINE} • Extracted {total} pages ({direct} digital text, {ocr} OCR)"
        )

        # Enable translation and AI Enhance buttons
        self.language_selector.set_translate_enabled(has_text)
        self._update_ai_enhance_button_state()

    def _handle_language_corrected(self, lang_code: str):
        """Fires when user manually overrides the detected source language."""
        self._detected_source_lang = lang_code
        self.status_bar.showMessage(f"Source language manually set to: {lang_code}")

    def _handle_cancel_trans_clicked(self):
        """Cancels background translation while preserving completed pages."""
        if self._trans_worker and self._trans_worker.isRunning():
            self.lbl_trans_status.setText("Cancelling translation... preserving completed pages...")
            self.btn_cancel_trans.setEnabled(False)
            self._trans_worker.cancel()

    def _handle_translate_requested(self, sync: bool = False):
        """Executes offline translation across all pages using pluggable engine."""
        pages = self.preview_panel._pages_data
        if not pages:
            QMessageBox.warning(self, "Translation Warning", "Please load a document before translating.")
            return

        target_lang = self.language_selector.get_selected_language_code()
        source_lang = self._detected_source_lang

        # Same-language skip check
        if source_lang.lower() == target_lang.lower():
            target_name = self.language_selector.get_selected_language_name()
            QMessageBox.information(
                self,
                "Translation Skipped",
                f"Source and target languages are both '{target_name}'. Translation is not required.",
            )
            self.preview_panel.display_translation_result({
                "full_translated_text": self.preview_panel.get_current_text(),
                "translated_pages": pages,
                "was_pivoted": False,
                "skipped": True,
            })
            return

        translator = get_translator("argos")
        if not translator.is_available():
            inst = translator.get_installation_instructions((source_lang, target_lang))
            QMessageBox.warning(self, "Translation Engine Missing", inst)
            return

        total_pages = len(pages)
        self.trans_progress_bar.setRange(0, total_pages)
        self.trans_progress_bar.setValue(0)
        self.lbl_trans_status.setText(f"Translating Page 0 of {total_pages} • Estimating time...")
        self.btn_cancel_trans.setEnabled(True)
        self.trans_progress_container.show()

        doc_stem = Path(self._current_pdf_path).stem if self._current_pdf_path else "doc"
        self._trans_worker = TranslationWorkerThread(
            pages=pages,
            source_lang=source_lang,
            target_lang=target_lang,
            translator=translator,
            doc_id=doc_stem,
            parent=self,
        )
        self._trans_worker.page_translated.connect(self._handle_trans_page_completed)
        self._trans_worker.translation_finished.connect(self._handle_trans_pipeline_finished)
        self._trans_worker.translation_cancelled.connect(self._handle_trans_pipeline_cancelled)
        self._trans_worker.translation_error.connect(self._handle_trans_pipeline_error)
        self._trans_worker.start()

        if sync or QApplication.platformName() == "offscreen":
            self._trans_worker.wait()
            QApplication.processEvents()

    def _handle_trans_page_completed(self, page_dict: Dict[str, Any], completed: int, total: int, eta_sec: float):
        self.trans_progress_bar.setValue(completed)
        eta_str = f"{max(1, int(eta_sec))}s" if eta_sec < 60 else f"{int(eta_sec // 60)}m {int(eta_sec % 60)}s"
        self.lbl_trans_status.setText(f"Page {completed} of {total} • ETA: {eta_str}")
        self.preview_panel.update_translation_page(page_dict, total)

    def _handle_trans_pipeline_finished(self, result: Dict[str, Any]):
        self.trans_progress_container.hide()
        self.preview_panel.display_translation_result(result)
        pivot_msg = " (Pivoted via English)" if result.get("was_pivoted") else ""
        self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Translation completed{pivot_msg}")

    def _handle_trans_pipeline_cancelled(self, result: Dict[str, Any]):
        self.trans_progress_container.hide()
        self.preview_panel.display_translation_result(result)
        comp = result.get("completed_count", 0)
        total = result.get("page_count", 0)
        self.status_bar.showMessage(f"⚠️ Translation Cancelled • Preserved {comp} of {total} translated pages")

    def _handle_trans_pipeline_error(self, message: str, instructions: str):
        self.trans_progress_container.hide()
        msg = message
        if instructions:
            msg += f"\n\n{instructions}"
        QMessageBox.warning(self, "Translation Error", msg)

    # --------------------------------------------------------------------------
    # Cloud AI Enhancement Actions (Strictly OFF by default)
    # --------------------------------------------------------------------------
    def _update_ai_enhance_button_state(self):
        has_text = bool(self.preview_panel.get_current_text().strip())
        self.btn_ai_enhance.setEnabled(self._ai_enhance_enabled and has_text)

    def _handle_settings_clicked(self):
        dlg = SettingsDialog(
            ai_enhance_enabled=self._ai_enhance_enabled,
            current_provider=self._ai_provider_name,
            parent=self,
        )
        if dlg.exec():
            self._ai_enhance_enabled = dlg.ai_enhance_enabled
            self._ai_provider_name = dlg.selected_provider
            self._update_ai_enhance_button_state()
            mode_text = "✨ Online AI Allowed" if self._ai_enhance_enabled else "🔒 100% Offline Processing Active"
            self.lbl_offline_guarantee.setText(mode_text)

    def _handle_ai_enhance_clicked(self):
        if not self._ai_enhance_enabled:
            QMessageBox.information(
                self,
                "AI Enhancement Disabled",
                "Online AI Enhancement is currently disabled to ensure strict offline privacy.\n\n"
                "To enable it, open Settings (⚙️) and check 'Allow online AI enhancement'.",
            )
            return

        text_to_send, scope_desc, context_type = self.preview_panel.get_ai_enhance_target_text()
        text_to_send = text_to_send.strip()
        if not text_to_send:
            QMessageBox.warning(self, "Empty Text", "No text or page available to enhance.")
            return

        if len(text_to_send) > AI_ENHANCE_MAX_CHARS:
            text_to_send = text_to_send[:AI_ENHANCE_MAX_CHARS]

        # Get Provider Instance
        prov_config = get_provider_config(self._ai_provider_name)
        api_key = get_api_key(self._ai_provider_name) or ""
        try:
            provider = get_ai_provider(
                self._ai_provider_name,
                api_key=api_key,
                base_url=prov_config.get("base_url"),
                model_name=prov_config.get("model_name"),
            )
        except Exception as e:
            QMessageBox.critical(self, "Provider Error", f"Failed to initialize AI provider:\n{str(e)}")
            return

        # 1. Mandatory Privacy Confirmation Dialog
        confirm_dlg = AIEnhanceConfirmDialog(
            text=text_to_send,
            provider_name=provider.get_name(),
            parent=self,
        )
        if confirm_dlg.exec() != 1 or not confirm_dlg.confirmed:
            return

        # 2. Status Bar indicates Online Mode while request is running
        self.status_bar.showMessage(STATUS_ONLINE_PROGRESS)
        self.conn_badge.setText("🟡 Online Request in Progress")
        self.conn_badge.setStyleSheet("""
            QLabel {
                background-color: #fefce8;
                color: #854d0e;
                border: 1px solid #fef08a;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 600;
            }
        """)
        QApplication.processEvents()

        try:
            enhanced_output = provider.enhance_text(text_to_send)
        except Exception as e:
            QMessageBox.critical(self, "AI Enhancement Failed", f"External API request failed:\n\n{str(e)}")
            return
        finally:
            self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Ready")
            self.conn_badge.setText("🟢 100% Offline Mode")
            self.conn_badge.setStyleSheet("""
                QLabel {
                    background-color: #f0fdf4;
                    color: #166534;
                    border: 1px solid #bbf7d0;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 10px;
                    font-weight: 600;
                }
            """)

        # 3. Side-by-side Review Dialog (Accept & Replace vs Reject)
        review_dlg = AIEnhanceResultDialog(
            original_text=text_to_send,
            enhanced_text=enhanced_output,
            provider_name=provider.get_name(),
            parent=self,
        )
        if review_dlg.exec() == 1 and review_dlg.accepted_result:
            self.preview_panel.apply_enhanced_text(review_dlg.enhanced_text, context_type)
            self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Replaced text with AI enhanced result ({scope_desc})")

    def _handle_ocr_pipeline_cancelled(self, result: Dict[str, Any]):
        """Fires when user cancels processing, preserving all completed pages."""
        self.ocr_progress_container.hide()
        self.preview_panel.display_extraction_result(result)
        has_text = bool(result.get("full_text", "").strip())
        self.export_panel.set_export_enabled(has_text)

        completed = result.get("completed_count", 0)
        total = result.get("page_count", 0)
        lang_name = self.language_selector.get_selected_language_name()
        tess_lang = map_app_lang_to_tesseract(self.language_selector.get_selected_language_code())

        self.lbl_ocr_info.setText(
            f"⚙️ Engine: Tesseract (LSTM) • Language: {lang_name} ({tess_lang}) • [Cancelled: {completed}/{total} pages kept]"
        )
        self.status_bar.showMessage(
            f"⚠️ OCR Cancelled • Preserved {completed} of {total} completed pages"
        )

    def _handle_ocr_pipeline_error(self, error_message: str, instructions: str):
        """Handles pipeline errors cleanly without crashing."""
        self.ocr_progress_container.hide()
        self.status_bar.showMessage(f"❌ OCR Error: {error_message}")
        msg = error_message
        if instructions:
            msg += f"\n\n{instructions}"
        QMessageBox.warning(self, "OCR Warning", msg)

    def clear_document(self):
        """
        Clears the loaded document, extracted text, page views, and badges,
        returning the application to its clean ready state.
        """
        if self._ocr_worker and self._ocr_worker.isRunning():
            self._ocr_worker.cancel()
            self._ocr_worker.wait()

        if self._trans_worker and self._trans_worker.isRunning():
            self._trans_worker.cancel()
            self._trans_worker.wait()

        # Clean active document recovery checkpoints before clearing state
        if self._current_pdf_path:
            try:
                from ocr.ocr_pipeline import get_recovery_file_path, remove_recovery_checkpoint
                remove_recovery_checkpoint(get_recovery_file_path(self._current_pdf_path))
            except Exception:
                pass
            try:
                from translation.translation_pipeline import get_translation_recovery_path, remove_translation_recovery
                remove_translation_recovery(get_translation_recovery_path(self._current_pdf_path))
            except Exception:
                pass

        self._current_pdf_path = ""
        self.ocr_progress_container.hide()
        self.trans_progress_container.hide()
        self.upload_panel.reset_state()
        self.preview_panel.clear()
        self.language_selector.set_translate_enabled(False)
        self.btn_ai_enhance.setEnabled(False)
        self.export_panel.set_document_name("")
        self.export_panel.set_export_enabled(False)
        self.lbl_ocr_info.setText("⚙️ Engine: Tesseract (LSTM) • Language: English (eng) • Ready")
        self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Ready — Select or drop a PDF to begin")

    def _handle_export_completed(self, saved_path: str):
        """Marks text as saved once exported."""
        self.preview_panel.mark_saved()
        self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Saved to: {saved_path}")

    def _handle_language_changed(self, lang_code: str):
        lang_name = self.language_selector.get_selected_language_name()
        tess_code = map_app_lang_to_tesseract(lang_code)
        engine = get_engine("tesseract")
        if engine.is_available() and not engine.is_language_installed(tess_code):
            self.status_bar.showMessage(f"⚠️ Missing language pack for {lang_name} ({tess_code}.traineddata)")
            QMessageBox.information(
                self,
                f"Language Pack Missing: {lang_name}",
                get_missing_language_instructions(lang_code),
            )
        else:
            self.status_bar.showMessage(f"Target language set to: {lang_name} ({tess_code})")

        self.lbl_ocr_info.setText(
            f"⚙️ Engine: Tesseract (LSTM) • Language: {lang_name} ({tess_code}) • Ready"
        )

    def get_document_text(self) -> str:
        """Returns the current original document text."""
        return self.preview_panel.get_current_text()

    def get_translated_text(self) -> str:
        """Returns the current translated text."""
        return self.preview_panel.get_translated_text()

    def get_bilingual_text(self) -> str:
        """Returns side-by-side bilingual text."""
        return self.preview_panel.get_bilingual_side_by_side_text()

    def closeEvent(self, event):
        """
        Ensures safe application shutdown:
        1. Prompts user if there are unsaved edits.
        2. Cooperatively cancels and joins background worker threads.
        3. Cleans up any active document recovery checkpoints.
        """
        # 1. Unsaved edits check
        if self.preview_panel.has_unsaved_edits():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Unsaved Edits")
            msg_box.setText("You have unsaved edits. Discard edits and close application?")
            msg_box.setIcon(QMessageBox.Warning)
            btn_discard = msg_box.addButton("Discard and Exit", QMessageBox.DestructiveRole)
            btn_cancel = msg_box.addButton("Cancel", QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_cancel)
            msg_box.exec()

            if msg_box.clickedButton() != btn_discard:
                event.ignore()
                return

        # 2. Cooperatively cancel and wait for background workers
        for worker in (self._ocr_worker, self._trans_worker):
            if worker and worker.isRunning():
                worker.cancel()
                if not worker.wait(3000):
                    QMessageBox.warning(
                        self,
                        "Busy",
                        "Background processing could not be stopped safely. Please try again.",
                    )
                    event.ignore()
                    return

        # 3. Clean active document recovery files
        if self._current_pdf_path:
            try:
                from ocr.ocr_pipeline import get_recovery_file_path, remove_recovery_checkpoint
                remove_recovery_checkpoint(get_recovery_file_path(self._current_pdf_path))
            except Exception:
                pass
            try:
                from translation.translation_pipeline import get_translation_recovery_path, remove_translation_recovery
                remove_translation_recovery(get_translation_recovery_path(self._current_pdf_path))
            except Exception:
                pass

        event.accept()
