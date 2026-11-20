"""
ui/upload_panel.py
------------------
Compact horizontal panel component for uploading, replacing, and removing PDF documents.
Supports native file browsing and drag-and-drop with informative hover tooltips.

Features:
- Dedicated 'Remove' button with close icon when a file is loaded.
- Reversible 'Open another file' (Replace) workflow.
- Clean visual states for empty vs loaded document.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from config.settings import FONT_FAMILY_STACK, CLOSE_ICON, CLOSE_HOVER_ICON


class UploadPanel(QWidget):
    """
    Compact horizontal document upload widget with drag-and-drop support,
    replace option, and file removal button.

    Signals:
        file_selected (str): Emitted when a PDF path is chosen or dropped.
        remove_requested (): Emitted when the user clicks the Remove button.
        browse_requested (): Emitted when user clicks Browse/Replace button.
    """

    file_selected = Signal(str)
    remove_requested = Signal()
    browse_requested = Signal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAcceptDrops(True)  # Enable drag and drop
        self._current_file_path: str = ""
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(0)

        # Sleek, compact horizontal drop frame with tooltip
        self.drop_frame = QFrame()
        self.drop_frame.setFixedHeight(56)
        self.drop_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.drop_frame.setToolTip("Drag and drop your PDF document here.")
        self.drop_frame.setStyleSheet("""
            QFrame {
                border: 1.5px dashed #94a3b8;
                border-radius: 6px;
                background-color: #f8fafc;
            }
            QFrame:hover {
                border-color: #2563eb;
                background-color: #eff6ff;
            }
        """)

        frame_layout = QHBoxLayout(self.drop_frame)
        frame_layout.setContentsMargins(12, 6, 12, 6)
        frame_layout.setSpacing(10)

        # Left Icon and Prompt
        self.drop_icon = QLabel("📄")
        self.drop_icon.setStyleSheet("font-size: 18px;")
        frame_layout.addWidget(self.drop_icon)

        self.drop_label = QLabel("<b>Drag & drop PDF</b> here or choose file:")
        self.drop_label.setStyleSheet(f"font-size: 11.5px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        self.drop_label.setToolTip("Drag and drop your PDF document here.")
        frame_layout.addWidget(self.drop_label)

        # Browse / Replace Button with tooltip
        self.browse_button = QPushButton("Browse Files")
        self.browse_button.setCursor(Qt.PointingHandCursor)
        self.browse_button.setToolTip("Select a PDF document from your computer.")
        self.browse_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 5px 14px;
                font-size: 11px;
                font-family: {FONT_FAMILY_STACK};
                min-width: 85px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
            QPushButton:pressed {{
                background-color: #1e40af;
            }}
        """)
        self.browse_button.clicked.connect(self._on_browse_clicked)
        frame_layout.addWidget(self.browse_button)

        frame_layout.addStretch()

        # Right-side Container: Document Metadata Badge + Remove (X) Button
        self.info_container = QWidget()
        info_layout = QHBoxLayout(self.info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(6)

        # Document Metadata Badge
        self.file_info_badge = QLabel("No document loaded")
        self.file_info_badge.setToolTip("Shows the currently loaded document name, page count, and file size.")
        self.file_info_badge.setStyleSheet(f"""
            QLabel {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                color: #475569;
                font-weight: 500;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        info_layout.addWidget(self.file_info_badge)

        # Small 'X' (Remove) button - Hidden when no file is loaded
        self.btn_remove = QPushButton()
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.setToolTip("Remove this file and load another")
        self.btn_remove.setVisible(False)
        self.btn_remove.setStyleSheet(f"""
            QPushButton {{
                image: url("{CLOSE_ICON}");
                background-color: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px;
                min-width: 22px;
                max-width: 22px;
                min-height: 22px;
                max-height: 22px;
            }}
            QPushButton:hover {{
                image: url("{CLOSE_HOVER_ICON}");
                background-color: #fee2e2;
                border-color: #f87171;
            }}
            QPushButton:pressed {{
                background-color: #fecaca;
            }}
        """)
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        info_layout.addWidget(self.btn_remove)

        frame_layout.addWidget(self.info_container)
        layout.addWidget(self.drop_frame)

    def _on_browse_clicked(self):
        """Notifies coordinator that user wants to browse or replace."""
        self.browse_requested.emit()

    def _on_remove_clicked(self):
        """Notifies coordinator that user clicked the Remove button."""
        self.remove_requested.emit()

    def set_file(self, file_path: str, emit_signal: bool = False):
        """Sets the selected file and reveals the Remove button."""
        if not file_path:
            self.reset_state()
            return

        self._current_file_path = file_path
        path = Path(file_path)
        size_kb = path.stat().st_size / 1024 if path.exists() else 0

        display_name = path.name if len(path.name) <= 30 else f"{path.name[:27]}..."
        self.file_info_badge.setText(f"📄 {display_name}  •  {size_kb:.1f} KB  •  Loading pages...")
        self.file_info_badge.setToolTip(f"Active file: {path.name}\nPath: {path}\nSize: {size_kb:.1f} KB")
        self.file_info_badge.setStyleSheet(f"""
            QLabel {{
                background-color: #eff6ff;
                border: 1px solid #93c5fd;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                color: #1e40af;
                font-weight: 600;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)

        # Update button to 'Open another file' (Replace)
        self.browse_button.setText("Open Another File")
        self.browse_button.setToolTip("Open another PDF document to replace the current one.")

        # Show the Remove button
        self.btn_remove.setVisible(True)

        if emit_signal:
            self.file_selected.emit(file_path)

    def update_page_count(self, page_count: int):
        """Updates the metadata display with the extracted page count."""
        if self._current_file_path:
            path = Path(self._current_file_path)
            size_kb = path.stat().st_size / 1024 if path.exists() else 0
            display_name = path.name if len(path.name) <= 30 else f"{path.name[:27]}..."
            self.file_info_badge.setText(f"📄 {display_name}  •  {page_count} Pages  •  {size_kb:.1f} KB")
            self.file_info_badge.setToolTip(f"Active file: {path.name}\nTotal Pages: {page_count}\nSize: {size_kb:.1f} KB")

    def reset_state(self):
        """Resets the upload panel back to its clean initial state."""
        self._current_file_path = ""
        self.file_info_badge.setText("No document loaded")
        self.file_info_badge.setToolTip("Shows the currently loaded document name, page count, and file size.")
        self.file_info_badge.setStyleSheet(f"""
            QLabel {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                color: #475569;
                font-weight: 500;
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        self.browse_button.setText("Browse Files")
        self.browse_button.setToolTip("Select a PDF document from your computer.")
        self.btn_remove.setVisible(False)

    def has_file_loaded(self) -> bool:
        """Returns True if a PDF is currently active."""
        return bool(self._current_file_path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(url.toLocalFile().lower().endswith(".pdf") for url in urls):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(".pdf"):
                main_win = self.window()
                if hasattr(main_win, "handle_incoming_file"):
                    main_win.handle_incoming_file(file_path)
                else:
                    self.set_file(file_path, emit_signal=True)
                event.acceptProposedAction()
                break
