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
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QFrame,
    QLabel,
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
    FONT_FAMILY_STACK,
)
from ui.upload_panel import UploadPanel
from ui.language_selector import LanguageSelector
from ui.preview_panel import PreviewPanel
from ui.export_panel import ExportPanel
from ui.system_info_panel import SystemInfoPanel
from extractors.pdf_extractor import extract_text_from_pdf


class MainWindow(QMainWindow):
    """
    Main application window orchestrating the document processing pipeline.
    """

    def __init__(self):
        super().__init__()
        self._current_pdf_path: str = ""
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

        # Text Preview & Correction Panel
        self.preview_panel = PreviewPanel()
        workspace_layout.addWidget(self.preview_panel, stretch=1)

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

    def _handle_file_selected(self, file_path: str):
        """Processes the chosen PDF using the PyMuPDF extractor."""
        self._current_pdf_path = file_path
        self.status_bar.showMessage(f"Processing: {Path(file_path).name} locally...")

        # Update upload panel state safely without recursive signal emission
        self.upload_panel.set_file(file_path, emit_signal=False)

        # Local extraction
        result = extract_text_from_pdf(file_path)

        if result.get("success", False):
            page_count = result.get("page_count", 0)
            self.upload_panel.update_page_count(page_count)
            self.preview_panel.display_extraction_result(result)
            self.export_panel.set_document_name(file_path)

            has_text = bool(result.get("full_text", "").strip())
            self.export_panel.set_export_enabled(has_text)
            self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Extracted {page_count} pages from {Path(file_path).name}")
        else:
            self.preview_panel.display_extraction_result(result)
            self.export_panel.set_export_enabled(False)
            self.status_bar.showMessage("Error: Extraction failed")
            QMessageBox.critical(
                self,
                "Extraction Error",
                f"Could not read the PDF document:\n\n{result.get('error', 'Unknown error')}",
            )

    def clear_document(self):
        """
        Clears the loaded document, extracted text, page views, and badges,
        returning the application to its clean ready state.
        """
        self._current_pdf_path = ""
        self.upload_panel.reset_state()
        self.preview_panel.clear()
        self.export_panel.set_document_name("")
        self.export_panel.set_export_enabled(False)
        self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Ready — Select or drop a PDF to begin")

    def _handle_export_completed(self, saved_path: str):
        """Marks text as saved once exported."""
        self.preview_panel.mark_saved()
        self.status_bar.showMessage(f"🟢 {STATUS_OFFLINE} • Saved to {Path(saved_path).name}")

    def _handle_language_changed(self, lang_code: str):
        lang_name = self.language_selector.get_selected_language_name()
        self.status_bar.showMessage(f"Target language set to: {lang_name} (Offline translation will connect in an upcoming update)")

    def get_document_text(self) -> str:
        """Returns the current document text from the preview editor."""
        return self.preview_panel.get_current_text()
