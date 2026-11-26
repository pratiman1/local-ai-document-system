"""
ui/export_panel.py
------------------
Panel component handling document exports.
Provides:
- Native system save dialog (macOS, Windows, Linux) targeting user's Documents folder.
- Dynamic persistence of user's last chosen export directory.
- Pre-filled filename pattern: <original_name>_extracted.txt.
- Overwrite protection prompt before replacing existing files.
- Confirmation modal with full file path and an 'Open Folder' button.
- Clean cancellation handling without false errors.
- One-click export to plain text (.txt) files with full UTF-8 multilingual script support.
- DOCX and PDF export buttons permanently disabled with 'Coming soon' tooltips.
"""

import platform
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Union

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QComboBox,
)
from PySide6.QtCore import Signal, Qt, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices

from exporters.txt_exporter import export_to_txt
from config.settings import FONT_FAMILY_STACK


def get_default_documents_folder() -> Path:
    """
    Retrieves the user's Documents directory in a portable manner across
    macOS, Windows, and Linux using QStandardPaths with filesystem fallbacks.
    """
    doc_loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    if doc_loc:
        return Path(doc_loc)
    return Path.home() / "Documents"


def open_file_folder(file_path: Union[str, Path]):
    """
    Reveals the file in the operating system's native file manager:
    - macOS: Highlights item in Finder (open -R)
    - Windows: Highlights item in File Explorer (explorer /select,)
    - Linux: Opens parent directory via xdg-open or QDesktopServices
    """
    path = Path(file_path).resolve()
    folder = path.parent if path.is_file() else path
    system = platform.system()

    try:
        if system == "Darwin":
            if path.exists():
                subprocess.run(["open", "-R", str(path)], check=False)
            else:
                subprocess.run(["open", str(folder)], check=False)
        elif system == "Windows":
            if path.exists():
                subprocess.run(["explorer", f"/select,{str(path)}"], check=False)
            else:
                subprocess.run(["explorer", str(folder)], check=False)
        else:  # Linux / Unix
            if shutil.which("xdg-open"):
                subprocess.run(["xdg-open", str(folder)], check=False)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
    except Exception:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


class ExportPanel(QWidget):
    """
    Document export controls widget with hover tooltips, remembered save location,
    and native file revealing.

    Signals:
        export_completed (str): Emitted with the path of the successfully exported file.
        export_pdf_requested (): Emitted when user clicks Export PDF.
    """

    export_completed = Signal(str)
    export_pdf_requested = Signal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._current_doc_name: str = ""
        self._last_export_dir: Optional[Path] = None
        self._last_saved_file: str = ""
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
        self.btn_export_txt.setToolTip("Save document text as a UTF-8 text file.")
        self.btn_export_txt.setEnabled(False)  # Disabled by default until file loaded
        self.btn_export_txt.setStyleSheet(f"""
            QPushButton {{
                background-color: #059669;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 11.5px;
                font-family: {FONT_FAMILY_STACK};
                min-width: 95px;
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

        # Export Scope Selector: Original, Translated, or Both
        self.combo_export_scope = QComboBox()
        self.combo_export_scope.addItem("Original Text", "original")
        self.combo_export_scope.addItem("Translated Text", "translated")
        self.combo_export_scope.addItem("Both Side-by-Side", "both")
        self.combo_export_scope.setToolTip("Choose whether to export Original text, Translated text, or Both side-by-side.")
        self.combo_export_scope.setStyleSheet(f"""
            QComboBox {{
                font-size: 11px;
                padding: 2px 24px 2px 8px;
                min-height: 26px;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        layout.addWidget(self.combo_export_scope)

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

        # PDF Export Button (active when translated text exists)
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
        self.btn_export_pdf.clicked.connect(self._on_export_pdf_clicked)
        layout.addWidget(self.btn_export_pdf)

        layout.addStretch()

        # Inline "Open Folder" button (reveals file location after export)
        self.btn_open_folder = QPushButton("📂 Open Folder")
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.setToolTip("Open the folder containing the exported file.")
        self.btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: #1e293b;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }}
        """)
        self.btn_open_folder.clicked.connect(self._on_open_folder_clicked)
        self.btn_open_folder.hide()
        layout.addWidget(self.btn_open_folder)

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
        # DOCX remains permanently disabled
        self.btn_export_docx.setEnabled(False)
        if not enabled:
            self.set_pdf_export_enabled(False)
            self.export_status.setText("")
            self.btn_open_folder.hide()
            self._last_saved_file = ""

    def set_pdf_export_enabled(self, enabled: bool):
        """Enables or disables book-format PDF export."""
        self.btn_export_pdf.setEnabled(enabled)
        if enabled:
            self.btn_export_pdf.setText("📕 Export PDF")
            self.btn_export_pdf.setToolTip("Export translated document as a book-format PDF preserving layout and graphics.")
            self.btn_export_pdf.setStyleSheet(f"""
                QPushButton {{
                    background-color: #dc2626;
                    color: #ffffff;
                    font-weight: bold;
                    border: none;
                    border-radius: 5px;
                    padding: 6px 14px;
                    font-size: 11.5px;
                    font-family: {FONT_FAMILY_STACK};
                    min-width: 95px;
                    min-height: 28px;
                }}
                QPushButton:hover {{
                    background-color: #b91c1c;
                }}
                QPushButton:pressed {{
                    background-color: #991b1b;
                }}
                QPushButton:disabled {{
                    background-color: #cbd5e1;
                    color: #94a3b8;
                }}
            """)
        else:
            self.btn_export_pdf.setText("📕 PDF (Coming Soon)")
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

    def _on_export_pdf_clicked(self):
        """Emits signal requesting PDF reconstruction export."""
        self.export_pdf_requested.emit()

    def get_export_dir(self) -> Path:
        """
        Returns the directory to open the save dialog in:
        The last folder chosen by the user, or the user's Documents folder by default.
        """
        if self._last_export_dir:
            return self._last_export_dir
        return get_default_documents_folder()

    def _on_open_folder_clicked(self):
        """Reveals the last saved export file in the OS file manager."""
        if self._last_saved_file:
            open_file_folder(self._last_saved_file)

    def _on_export_txt_clicked(self):
        main_win = self.window()
        if not hasattr(main_win, "get_document_text"):
            return

        scope = self.combo_export_scope.currentData()
        doc_base = self._current_doc_name if self._current_doc_name else "document"

        if scope == "translated":
            text = main_win.get_translated_text() if hasattr(main_win, "get_translated_text") else ""
            default_filename = f"{doc_base}_translated.txt"
            if not text.strip():
                QMessageBox.warning(self, "Export Warning", "No translated text available yet. Please run translation first, or select 'Original Text'.")
                return
        elif scope == "both":
            text = main_win.get_bilingual_text() if hasattr(main_win, "get_bilingual_text") else ""
            default_filename = f"{doc_base}_bilingual.txt"
            if not text.strip():
                text = main_win.get_document_text()
        else:  # "original"
            text = main_win.get_document_text()
            default_filename = f"{doc_base}_extracted.txt"

        if not text or not text.strip():
            QMessageBox.warning(self, "Export Warning", "There is no text to export. Please load a PDF document first.")
            return

        export_dir = self.get_export_dir()
        default_path = str(export_dir / default_filename)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Extracted Text",
            default_path,
            "Text Files (*.txt);;All Files (*)",
        )

        # Requirement 4: If user cancels, do nothing and show no error
        if not save_path:
            return

        target_path = Path(save_path).resolve()

        # Requirement 6: Overwrite protection - ask before replacing an existing file
        if target_path.exists():
            reply = QMessageBox.question(
                self,
                "Confirm Overwrite",
                f"A file named '{target_path.name}' already exists in this folder.\n\nDo you want to replace it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        result = export_to_txt(text=text, output_path=target_path, overwrite=True)
        if result["success"]:
            # Requirement 3: Remember the last folder chosen
            self._last_export_dir = target_path.parent
            self._last_saved_file = str(target_path)

            self.export_status.setText(f"✓ Saved to {target_path.name}")
            self.btn_open_folder.show()
            self.export_completed.emit(str(target_path))

            # Requirement 5: Show full file path and an "Open Folder" button in confirmation dialog
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Export Successful")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText(
                f"Text document saved successfully to:\n\n{target_path}\n\n"
                f"(Original PDF remains untouched)."
            )
            btn_open_folder = msg_box.addButton("Open Folder", QMessageBox.ActionRole)
            btn_ok = msg_box.addButton("OK", QMessageBox.AcceptRole)
            msg_box.setDefaultButton(btn_ok)
            msg_box.exec()

            if msg_box.clickedButton() == btn_open_folder:
                open_file_folder(target_path)
        else:
            QMessageBox.critical(self, "Export Failed", f"Could not save file: {result['error']}")
