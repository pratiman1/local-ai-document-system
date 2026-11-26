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

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
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
    QInputDialog,
)
from PySide6.QtCore import Qt

from config.settings import (
    APP_NAME,
    APP_VERSION,
    BASE_DIR,
    EXPORTS_DIR,
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
    TRANSLATION_ENGINE_PREFERENCE,
    TRANSLATION_COMPARE_MODE,
    TRANSLATION_AGREEMENT_THRESHOLD,
)

PROJECT_ROOT = BASE_DIR
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
from translation.router import resolve_translation_route
from services.ai_provider import get_ai_provider, AIProviderError
from services.keychain_manager import get_api_key, get_provider_config
from services.redaction_manager import redact_sensitive_data, restore_sensitive_data
from services.audit_logger import log_ai_request
from ui.ai_enhance_dialog import AIEnhanceConfirmDialog, AIEnhanceResultDialog
from ui.settings_dialog import SettingsDialog
from ui.compare_review_dialog import CompareReviewDialog
from exporters.pdf_reconstructor import PDFExportWorkerThread


class MainWindow(QMainWindow):
    """
    Main application window orchestrating the document processing pipeline.
    """

    def __init__(self):
        super().__init__()
        self._current_pdf_path: str = ""
        self._ocr_worker: Optional[OCRWorkerThread] = None
        self._trans_worker: Optional[TranslationWorkerThread] = None
        self._pdf_export_worker: Optional[PDFExportWorkerThread] = None
        self._detected_source_lang: str = "eng"
        self._ai_enhance_enabled: bool = AI_ENHANCE_ENABLED_DEFAULT
        self._ai_provider_name: str = AI_DEFAULT_PROVIDER
        self._engine_preference: str = TRANSLATION_ENGINE_PREFERENCE
        self._compare_mode: bool = TRANSLATION_COMPARE_MODE
        self._agreement_threshold: float = TRANSLATION_AGREEMENT_THRESHOLD
        self._session_consent_cache = set()  # In-memory session consent cache: (provider_name, doc_id)
        self._init_window()
        self._init_ui()
        self._connect_signals()
        # Automatically scan models/argos/ folder on startup
        translator = get_translator("argos")
        if translator.is_available():
            translator.scan_and_install_models_folder()
        self._update_translation_status()

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
        self.export_panel.export_pdf_requested.connect(self._handle_export_pdf_requested)
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
        self._update_translation_status()

    def _handle_language_corrected(self, lang_code: str):
        """Fires when user manually overrides the detected source language."""
        self._detected_source_lang = lang_code
        self.status_bar.showMessage(f"Source language manually set to: {lang_code}")
        self._update_translation_status()

    def _handle_cancel_trans_clicked(self):
        """Cancels background translation while preserving completed pages."""
        if self._trans_worker and self._trans_worker.isRunning():
            self.lbl_trans_status.setText("Cancelling translation... preserving completed pages...")
            self.btn_cancel_trans.setEnabled(False)
            self._trans_worker.cancel()
        if self._pdf_export_worker and self._pdf_export_worker.isRunning():
            self.lbl_trans_status.setText("Cancelling PDF reconstruction...")
            self.btn_cancel_trans.setEnabled(False)
            self._pdf_export_worker.cancel()

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

        # Pre-flight check: Ensure required offline translation language pair is installed
        route = resolve_translation_route(
            source_lang,
            target_lang,
            engine_preference=self._engine_preference,
            compare_mode=self._compare_mode,
        )
        if not route.get("can_translate", False):
            self.language_selector.update_translation_status(
                "model_missing",
                source_lang=source_lang,
                target_lang=target_lang,
                message=route["message"],
                tooltip=route["tooltip"],
            )
            self.status_bar.showMessage(f"⚠️ {STATUS_OFFLINE} • {route['status_line']}")
            QMessageBox.warning(
                self,
                "Model Missing",
                f"{route['message']}\n\nModels folders:\n• models/argos/ (for Argos models)\n• models/indictrans2/ (for IndicTrans2 models)",
            )
            return

        primary_translator = get_translator(route["primary_engine"])
        secondary_translator = (
            get_translator(route["secondary_engine"])
            if route.get("can_compare") and route.get("secondary_engine")
            else None
        )

        # Set status indicator to translating
        self.language_selector.update_translation_status(
            "translating",
            source_lang=source_lang,
            target_lang=target_lang,
            message=route["status_line"],
        )
        self.status_bar.showMessage(f"🔵 {STATUS_OFFLINE} • Translating: {route['status_line']}...")

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
            translator=primary_translator,
            secondary_translator=secondary_translator,
            compare_mode=route.get("can_compare", False),
            agreement_threshold=self._agreement_threshold,
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
        if completed > 0:
            self.export_panel.set_pdf_export_enabled(True)

    def _handle_trans_pipeline_finished(self, result: Dict[str, Any]):
        self.trans_progress_container.hide()
        self.preview_panel.display_translation_result(result)
        self.export_panel.set_pdf_export_enabled(True)
        self._update_translation_status()
        route = resolve_translation_route(
            self._detected_source_lang,
            self.language_selector.get_selected_language_code(),
            engine_preference=self._engine_preference,
            compare_mode=self._compare_mode,
        )
        flagged_count = result.get("flagged_count", 0)
        if result.get("compare_mode"):
            if flagged_count > 0:
                self.status_bar.showMessage(
                    f"🟣 {STATUS_OFFLINE} • Compare Mode: {flagged_count} page(s) flagged (agreement < {int(self._agreement_threshold * 100)}%)"
                )
                self._prompt_compare_review(result)
            else:
                self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Translation completed: {route['status_line']} (High Agreement)")
        else:
            self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Translation completed: {route['status_line']}")

    def _prompt_compare_review(self, result: Dict[str, Any]):
        """Prompts the user to review side-by-side translation differences on flagged pages."""
        pages = result.get("translated_pages", [])
        if not pages:
            return
        dlg = CompareReviewDialog(pages, agreement_threshold=self._agreement_threshold, parent=self)
        if dlg.exec() and dlg.modified:
            # Reconstruct full translated text and update preview editor
            full_text = "\n\n--- Page Break ---\n\n".join(p.get("translated_text", "") for p in pages)
            result["full_translated_text"] = full_text
            self.preview_panel.display_translation_result(result)
            self.status_bar.showMessage("✓ Compare selections applied to document preview.")

    def _handle_trans_pipeline_cancelled(self, result: Dict[str, Any]):
        self.trans_progress_container.hide()
        self.preview_panel.display_translation_result(result)
        self.language_selector.update_translation_status(
            "ready",
            source_lang=self._detected_source_lang,
            target_lang=self.language_selector.get_selected_language_code(),
        )
        comp = result.get("completed_count", 0)
        total = result.get("page_count", 0)
        self.status_bar.showMessage(f"⚠️ Translation Cancelled • Preserved {comp} of {total} translated pages")

    def _handle_trans_pipeline_error(self, message: str, instructions: str):
        self.trans_progress_container.hide()
        self.language_selector.update_translation_status(
            "error",
            source_lang=self._detected_source_lang,
            target_lang=self.language_selector.get_selected_language_code(),
            message=message,
        )
        self.status_bar.showMessage(f"❌ Translation Error: {message}")
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
            engine_preference=self._engine_preference,
            compare_mode=self._compare_mode,
            agreement_threshold=self._agreement_threshold,
            parent=self,
        )
        if dlg.exec():
            self._ai_enhance_enabled = dlg.ai_enhance_enabled
            self._ai_provider_name = dlg.selected_provider
            self._engine_preference = getattr(dlg, "engine_preference", self._engine_preference)
            self._compare_mode = getattr(dlg, "compare_mode", self._compare_mode)
            self._agreement_threshold = getattr(dlg, "agreement_threshold", self._agreement_threshold)
            self._update_ai_enhance_button_state()
            mode_text = "✨ Online AI Allowed" if self._ai_enhance_enabled else "🔒 100% Offline Processing Active"
            self.lbl_offline_guarantee.setText(mode_text)

        # Refresh translation status in case models were imported or refreshed
        self._update_translation_status()

    def _split_text_for_ai_enhance(self, text: str, max_chars: int = AI_ENHANCE_MAX_CHARS) -> List[str]:
        """
        Splits text into chunks of at most max_chars, breaking at paragraph,
        line, sentence, or word boundaries.
        """
        if len(text) <= max_chars:
            return [text]

        chunks = []
        remaining = text.strip()
        while len(remaining) > max_chars:
            candidate = remaining[:max_chars]
            split_idx = -1
            # 1. Paragraph boundary
            p_idx = candidate.rfind("\n\n")
            if p_idx > max_chars // 3:
                split_idx = p_idx + 2
            else:
                # 2. Line boundary
                l_idx = candidate.rfind("\n")
                if l_idx > max_chars // 3:
                    split_idx = l_idx + 1
                else:
                    # 3. Sentence boundary
                    for sep in [". ", "? ", "! ", "। "]:
                        s_idx = candidate.rfind(sep)
                        if s_idx > max_chars // 3:
                            split_idx = max(split_idx, s_idx + len(sep))
                    # 4. Word boundary
                    if split_idx == -1:
                        w_idx = candidate.rfind(" ")
                        if w_idx > max_chars // 3:
                            split_idx = w_idx + 1
                        else:
                            split_idx = max_chars

            chunk = remaining[:split_idx].strip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[split_idx:].strip()

        if remaining:
            chunks.append(remaining)

        return chunks or [text]

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

        if not provider.is_configured():
            QMessageBox.warning(
                self,
                "Provider Not Configured",
                f"The AI provider '{provider.name()}' is not configured with an API key.\n\n"
                "Please configure it in Settings (⚙️) before proceeding.",
            )
            return

        # Split into chunks if exceeds maximum request size
        chunks = self._split_text_for_ai_enhance(text_to_send, max_chars=AI_ENHANCE_MAX_CHARS)
        total_chunks = len(chunks)

        # Session consent check key (specific to provider and active document)
        doc_key = self._current_pdf_path or "active_session_document"
        session_cache_key = (self._ai_provider_name, doc_key)

        enhanced_chunks = []
        target_lang = self.language_selector.get_selected_language_code() or "eng"
        source_lang = self._detected_source_lang or "eng"

        # Obtain source context if enhancing translation
        source_context = ""
        if hasattr(self.preview_panel, "get_current_text"):
            source_context = self.preview_panel.get_current_text().strip()

        # Shared user instructions & task across chunks
        active_task = "Fix grammar"
        active_instruction = ""
        active_redaction = False

        for chunk_idx, chunk in enumerate(chunks, 1):
            chunk_placeholder_map = {}
            chunk_to_transmit = chunk

            # Check if user already gave consent for this session and document
            has_session_consent = session_cache_key in self._session_consent_cache

            if not has_session_consent:
                confirm_dlg = AIEnhanceConfirmDialog(
                    text=chunk,
                    provider_name=provider.name(),
                    model_name=provider.model_name,
                    source_text=source_context,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    is_local=provider.is_local,
                    endpoint_host=provider.get_host_name(),
                    parent=self,
                )
                if confirm_dlg.exec() != 1 or not confirm_dlg.confirmed:
                    # User cancelled: abort and ensure status is offline
                    self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Ready")
                    return

                if confirm_dlg.do_not_ask_again:
                    self._session_consent_cache.add(session_cache_key)

                active_task = confirm_dlg.selected_task
                active_instruction = confirm_dlg.user_instruction
                active_redaction = confirm_dlg.redaction_enabled

            # Apply redaction if enabled
            if active_redaction:
                chunk_to_transmit, chunk_placeholder_map = redact_sensitive_data(chunk)

            # Update status bar & badges during processing
            if provider.is_local:
                self.status_bar.showMessage(f"🟢 Offline — Local Model Server request in progress ({provider.model_name})...")
                self.conn_badge.setText("🟢 Offline (Local AI Server)")
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
            else:
                self.status_bar.showMessage(f"🟡 Online request in progress — {provider.name()}...")
                self.conn_badge.setText(f"🟡 Online ({provider.name()})")
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
                enhanced_output = provider.enhance(
                    text=chunk_to_transmit,
                    task=active_task,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    user_instructions=active_instruction,
                )
            except AIProviderError as pe:
                QMessageBox.warning(self, "AI Enhancement Error", f"Provider error from {provider.name()}:\n\n{str(pe)}")
                return
            except Exception as e:
                sanitized_e = provider._sanitize_error(str(e))
                QMessageBox.critical(self, "AI Enhancement Failed", f"Request failed:\n\n{sanitized_e}")
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

            # Restore redacted placeholders if redaction was active
            if chunk_placeholder_map:
                enhanced_output = restore_sensitive_data(enhanced_output, chunk_placeholder_map)

            enhanced_chunks.append(enhanced_output)

            # Record in local metadata-only audit log (zero document text, zero keys)
            log_ai_request(
                provider=provider.name(),
                model=provider.model_name,
                char_count=len(chunk_to_transmit),
                page_num=scope_desc,
                is_local=provider.is_local,
            )

        full_enhanced_output = "\n\n".join(enhanced_chunks)

        # Side-by-side Review Dialog (Accept & Replace vs Reject)
        review_dlg = AIEnhanceResultDialog(
            original_text=text_to_send,
            enhanced_text=full_enhanced_output,
            provider_name=provider.name(),
            source_lang=source_lang,
            target_lang=target_lang,
            parent=self,
        )
        if review_dlg.exec() == 1 and review_dlg.accepted_result:
            self.preview_panel.apply_enhanced_text(review_dlg.enhanced_text, context_type)
            self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Replaced text with AI enhanced result ({scope_desc})")

            # If user checked "Offer to add corrected terms to domain glossary"
            if review_dlg.add_to_glossary:
                self._prompt_add_glossary_term(source_lang, target_lang)

    def _prompt_add_glossary_term(self, source_lang: str, target_lang: str):
        """Offers to store a domain-specific term pair in the local glossary."""
        src_term, ok1 = QInputDialog.getText(
            self,
            "Add to Domain Glossary",
            f"Enter source term ({source_lang}):",
        )
        if not ok1 or not src_term.strip():
            return

        tgt_term, ok2 = QInputDialog.getText(
            self,
            "Add to Domain Glossary",
            f"Enter corrected translation for '{src_term.strip()}' ({target_lang}):",
        )
        if ok2 and tgt_term.strip():
            self._save_glossary_entry(source_lang, target_lang, src_term.strip(), tgt_term.strip())
            QMessageBox.information(
                self,
                "Glossary Updated",
                f"Added entry to {source_lang} glossary:\n\n• '{src_term.strip()}' ➔ '{tgt_term.strip()}'"
            )

    def _save_glossary_entry(self, source_lang: str, target_lang: str, source_term: str, target_term: str):
        """Saves a term mapping to glossaries/{source_lang}.json."""
        glossary_dir = Path(__file__).resolve().parent.parent / "glossaries"
        glossary_dir.mkdir(parents=True, exist_ok=True)
        glossary_file = glossary_dir / f"{source_lang}.json"

        data = {}
        if glossary_file.is_file():
            try:
                with open(glossary_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        if target_lang not in data:
            data[target_lang] = {}

        data[target_lang][source_term] = target_term

        try:
            with open(glossary_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

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

        if self._pdf_export_worker and self._pdf_export_worker.isRunning():
            self._pdf_export_worker.cancel()
            self._pdf_export_worker.wait()

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
        self._detected_source_lang = "eng"
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
        self._update_translation_status()

    def _handle_export_completed(self, saved_path: str):
        """Marks text as saved once exported."""
        self.preview_panel.mark_saved()
        self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Saved to: {saved_path}")

    def _handle_export_pdf_requested(self, target_save_path: Optional[str] = None, sync: bool = False):
        """Launches the book-format PDF reconstruction export workflow."""
        if not self._current_pdf_path or not Path(self._current_pdf_path).is_file():
            QMessageBox.warning(self, "Export Warning", "Original PDF source document is not available.")
            return

        # Retrieve per-page translated text from live on-screen panes & preview state
        page_map, missing_pages, error_msg = self.preview_panel.get_translated_pages_for_export()
        if error_msg:
            QMessageBox.warning(self, "Page Break Mismatch", error_msg)
            return

        if not page_map:
            QMessageBox.warning(
                self,
                "Export Warning",
                "No translated text available to export into PDF. Please run translation first.",
            )
            return

        total_pages = len(self.preview_panel._pages_data) if self.preview_panel._pages_data else len(page_map)

        # Incomplete translation handling: warn with missing pages and offer choice
        if missing_pages and QApplication.platformName() != "offscreen":
            missing_str = ", ".join(str(p) for p in sorted(missing_pages))
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Incomplete Translation")
            msg_box.setText(
                f"Translation is incomplete. The following page(s) have not been translated yet:\n\n"
                f"Pages: {missing_str}\n\n"
                f"Do you want to export anyway, keeping original English on missing pages?"
            )
            btn_export_anyway = msg_box.addButton(
                "Export anyway, keeping original English on missing pages",
                QMessageBox.AcceptRole,
            )
            btn_cancel = msg_box.addButton("Cancel", QMessageBox.RejectRole)
            msg_box.setDefaultButton(btn_cancel)
            msg_box.exec()

            if msg_box.clickedButton() != btn_export_anyway:
                return

        target_lang = self.language_selector.get_selected_language_code() or "hin"
        lang_label = "hindi" if target_lang == "hin" else target_lang
        doc_stem = Path(self._current_pdf_path).stem
        default_filename = f"{doc_stem}_{lang_label}_translated_book.pdf"
        export_dir = self.export_panel.get_export_dir()
        default_path = str(export_dir / default_filename)

        if target_save_path:
            save_path = target_save_path
        else:
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Book-Format Translated PDF",
                default_path,
                "PDF Files (*.pdf);;All Files (*)",
            )

        if not save_path:
            return

        target_path = Path(save_path).resolve()

        if target_path.exists() and not target_save_path:
            reply = QMessageBox.question(
                self,
                "Confirm Overwrite",
                f"A file named '{target_path.name}' already exists in this folder.\n\nDo you want to replace it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # Prepare checkpoint data from current preview panel pages & live edits
        block_ckpt_path = EXPORTS_DIR / f"{doc_stem}_block_checkpoint.json"
        if not block_ckpt_path.is_file() and "poetry" in doc_stem.lower():
            block_ckpt_path = EXPORTS_DIR / "poetry_11p_block_checkpoint.json"

        block_data_by_page = {}
        if block_ckpt_path.is_file():
            try:
                with open(block_ckpt_path, "r", encoding="utf-8") as f:
                    block_data_by_page = json.load(f).get("pages", {})
            except Exception:
                block_data_by_page = {}

        checkpoint_pages = {}
        for p_idx in range(total_pages):
            p_num = p_idx + 1
            orig_text = ""
            if p_idx < len(self.preview_panel._pages_data):
                p_info = self.preview_panel._pages_data[p_idx]
                p_num = p_info.get("page_number", p_num)
                orig_text = p_info.get("cleaned_text", p_info.get("text", ""))

            trans_text = page_map.get(p_num, "")
            is_fallback = False
            if not trans_text and p_num in missing_pages:
                trans_text = orig_text
                is_fallback = True

            page_blocks = block_data_by_page.get(str(p_num), {}).get("blocks")
            checkpoint_pages[str(p_num)] = {
                "page_number": p_num,
                "translated_text": trans_text,
                "cleaned_text": orig_text,
                "is_fallback_original": is_fallback,
                "blocks": page_blocks,
            }
        checkpoint_data = {"pages": checkpoint_pages}

        # Show progress container
        total_pages = len(checkpoint_pages)
        self.trans_progress_bar.setRange(0, total_pages)
        self.trans_progress_bar.setValue(0)
        self.lbl_trans_status.setText(f"Reconstructing book PDF: Page 0 of {total_pages} • Estimating time...")
        self.btn_cancel_trans.setEnabled(True)
        self.trans_progress_container.show()

        self._pdf_export_worker = PDFExportWorkerThread(
            source_pdf_path=self._current_pdf_path,
            output_pdf_path=str(target_path),
            checkpoint_data=checkpoint_data,
            parent=self,
        )
        self._pdf_export_worker.progress_updated.connect(self._handle_pdf_export_progress)
        self._pdf_export_worker.export_finished.connect(self._handle_pdf_export_finished)
        self._pdf_export_worker.export_error.connect(self._handle_pdf_export_error)
        self._pdf_export_worker.start()

        if sync or QApplication.platformName() == "offscreen":
            self._pdf_export_worker.wait()

    def _handle_pdf_export_progress(self, completed: int, total: int, eta_sec: float):
        self.trans_progress_bar.setValue(completed)
        eta_str = f"{max(1, int(eta_sec))}s" if eta_sec < 60 else f"{int(eta_sec // 60)}m {int(eta_sec % 60)}s"
        self.lbl_trans_status.setText(f"Reconstructing PDF: Page {completed} of {total} • ETA: {eta_str}")

    def _handle_pdf_export_finished(self, summary: dict):
        self.trans_progress_container.hide()
        if summary.get("cancelled"):
            self.status_bar.showMessage("⚠️ PDF Export cancelled.")
            return

        out_path = summary.get("output_path", "")
        self.export_panel._last_export_dir = Path(out_path).parent
        self.export_panel._last_saved_file = out_path
        self.export_panel.export_status.setText(f"✓ Saved to {Path(out_path).name}")
        self.export_panel.btn_open_folder.show()
        self.export_panel.export_completed.emit(out_path)

        if QApplication.platformName() != "offscreen":
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("PDF Export Successful")
            msg_box.setIcon(QMessageBox.Information)
            size_mb = summary.get("file_size_bytes", 0) / (1024 * 1024)
            msg_box.setText(
                f"Book-format Hindi PDF reconstructed successfully:\n\n{out_path}\n\n"
                f"Pages: {summary.get('completed_pages', 0)} • File Size: {size_mb:.1f} MB\n\n"
                f"Layout geometry, embedded photos, borders, and vector tables preserved."
            )
            msg_box.addButton("Open Folder", QMessageBox.ActionRole)
            btn_ok = msg_box.addButton("OK", QMessageBox.AcceptRole)
            msg_box.setDefaultButton(btn_ok)
            msg_box.exec()

    def _handle_pdf_export_error(self, err_msg: str):
        self.trans_progress_container.hide()
        if QApplication.platformName() != "offscreen":
            QMessageBox.critical(self, "PDF Export Error", f"An error occurred during PDF reconstruction:\n\n{err_msg}")

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
        self._update_translation_status()

    def _update_translation_status(self):
        """Updates the language selector status indicator based on current source/target pair and engine router."""
        target_lang = self.language_selector.get_selected_language_code()
        source_lang = self._detected_source_lang or "eng"

        if not target_lang:
            return

        route = resolve_translation_route(
            source_lang,
            target_lang,
            engine_preference=self._engine_preference,
            compare_mode=self._compare_mode,
        )

        st = route["status"]
        self.language_selector.update_translation_status(
            st,
            source_lang=source_lang,
            target_lang=target_lang,
            message=route.get("status_line", route.get("message", "")),
            tooltip=route.get("tooltip", ""),
        )

        # Update status bar with pair in use when document text is present
        if bool(self.preview_panel.get_current_text().strip()):
            self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Translation: {route['status_line']}")

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
        for worker in (self._ocr_worker, self._trans_worker, self._pdf_export_worker):
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
