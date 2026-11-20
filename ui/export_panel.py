"""
ui/export_panel.py
------------------
Panel component handling document exports.
Provides:
- One-click export to plain text (.txt) files with full UTF-8 Indian script support.
- Native system save dialog (macOS, Windows, Linux).
- TXT export is dynamically enabled/disabled based on document presence.
- Explicit minimum widths and concise labels prevent text truncation.
- DOCX and PDF export buttons are permanently disabled with 'Coming soon' tooltips.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Signal, Qt
from exporters.txt_exporter import export_to_txt
from config.settings import EXPORTS_DIR, FONT_FAMILY_STACK


class ExportPanel(QWidget):
    """
    Document export controls widget with hover tooltips and unclipped buttons.

    Signals:
        export_completed (str): Emitted with the path of the successfully exported file.
    """

    export_completed = Signal(str)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._current_doc_name: str = ""
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(10)

        # Label with tooltip
        export_label = QLabel("💾 <b>Export Document:</b>")
        export_label.setStyleSheet(f"font-size: 12px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        export_label.setToolTip("Export the current document text locally to your computer.")
        layout.addWidget(export_label)

        # Export as TXT Button (Active when document is loaded)
        self.btn_export_txt = QPushButton("📄 Export TXT")
        self.btn_export_txt.setCursor(Qt.PointingHandCursor)
        self.btn_export_txt.setToolTip("Save extracted text as a UTF-8 text file.")
        self.btn_export_txt.setEnabled(False)  # Disabled by default until file loaded
        self.btn_export_txt.setStyleSheet(f"""
            QPushButton {{
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 6px 16px;
                font-size: 11.5px;
                font-family: {FONT_FAMILY_STACK};
                min-width: 105px;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: #047857;
            }}
            QPushButton:pressed {{
                background-color: #065f46;
            }}
            QPushButton:disabled {{
                background-color: #cbd5e1;
                color: #94a3b8;
            }}
        """)
        self.btn_export_txt.clicked.connect(self._on_export_txt_clicked)
        layout.addWidget(self.btn_export_txt)

        # Inactive DOCX Export Button (Permanently disabled for now, tooltip 'Coming soon')
        self.btn_export_docx = QPushButton("📘 DOCX (Coming Soon)")
        self.btn_export_docx.setEnabled(False)
        self.btn_export_docx.setToolTip("Coming soon")
        self.btn_export_docx.setStyleSheet(f"""
            QPushButton {{
                padding: 5px 12px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                color: #94a3b8;
                border: 1px dashed #cbd5e1;
                border-radius: 5px;
                background-color: #f8fafc;
                min-width: 130px;
                min-height: 26px;
            }}
        """)
        layout.addWidget(self.btn_export_docx)

        # Inactive PDF Export Button (Permanently disabled for now, tooltip 'Coming soon')
        self.btn_export_pdf = QPushButton("📕 PDF (Coming Soon)")
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_pdf.setToolTip("Coming soon")
        self.btn_export_pdf.setStyleSheet(f"""
            QPushButton {{
                padding: 5px 12px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                color: #94a3b8;
                border: 1px dashed #cbd5e1;
                border-radius: 5px;
                background-color: #f8fafc;
                min-width: 120px;
                min-height: 26px;
            }}
        """)
        layout.addWidget(self.btn_export_pdf)

        layout.addStretch()

        # Status text
        self.export_status = QLabel("")
        self.export_status.setStyleSheet(f"font-size: 11px; color: #059669; font-weight: 600; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(self.export_status)

    def set_document_name(self, file_path: str):
        """Sets base document name for default export naming."""
        if file_path:
            self._current_doc_name = Path(file_path).stem
        else:
            self._current_doc_name = ""

    def set_export_enabled(self, enabled: bool):
        """Enables or disables TXT export depending on document presence."""
        self.btn_export_txt.setEnabled(enabled)
        # DOCX and PDF remain permanently disabled
        self.btn_export_docx.setEnabled(False)
        self.btn_export_pdf.setEnabled(False)
        if not enabled:
            self.export_status.setText("")

    def _on_export_txt_clicked(self):
        main_win = self.window()
        if not hasattr(main_win, "get_document_text"):
            return

        text = main_win.get_document_text()
        if not text or not text.strip():
            QMessageBox.warning(self, "Export Warning", "There is no text to export. Please load a PDF document first.")
            return

        doc_base = self._current_doc_name if self._current_doc_name else "document"
        default_filename = f"{doc_base}_extracted.txt"
        default_path = str(EXPORTS_DIR / default_filename)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Extracted Text",
            default_path,
            "Text Files (*.txt);;All Files (*)",
        )

        if save_path:
            result = export_to_txt(text=text, output_path=save_path, overwrite=True)
            if result["success"]:
                self.export_status.setText(f"✓ Saved to {Path(save_path).name}")
                self.export_completed.emit(save_path)
                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Text document saved successfully to:\n\n{save_path}\n\n(Original PDF remains untouched).",
                )
            else:
                QMessageBox.critical(self, "Export Failed", f"Could not save file: {result['error']}")
