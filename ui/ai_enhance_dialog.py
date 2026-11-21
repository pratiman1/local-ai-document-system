"""
ui/ai_enhance_dialog.py
-----------------------
Dialogs governing the optional Cloud AI Enhancement feature:
1. AIEnhanceConfirmDialog: Mandatory privacy disclosure showing exact text, provider,
   and estimated payload size with explicit Send and Cancel buttons.
2. AIEnhanceResultDialog: Side-by-side comparison (Original vs. Enhanced) with
   explicit Accept & Replace and Reject buttons.
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QFrame,
    QSplitter,
)
from PySide6.QtCore import Qt
from config.settings import FONT_FAMILY_STACK


class AIEnhanceConfirmDialog(QDialog):
    """
    Mandatory privacy confirmation dialog before transmitting any document text.
    """

    def __init__(self, text: str, provider_name: str, parent=None):
        super().__init__(parent)
        self.text_to_send = text
        self.provider_name = provider_name
        self.confirmed = False
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Confirm Online AI Enhancement")
        self.setMinimumSize(560, 420)
        self.resize(600, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Warning Card
        warning_card = QFrame()
        warning_card.setStyleSheet("""
            QFrame {
                background-color: #fffbeb;
                border: 1px solid #fde68a;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        w_layout = QVBoxLayout(warning_card)
        w_layout.setContentsMargins(8, 8, 8, 8)
        w_layout.setSpacing(4)

        w_title = QLabel("⚠️ <b>Privacy Warning: Text Will Leave Your Computer</b>")
        w_title.setStyleSheet(f"color: #92400e; font-size: 13px; font-family: {FONT_FAMILY_STACK}; font-weight: bold;")
        w_layout.addWidget(w_title)

        w_desc = QLabel(
            f"You are about to transmit the document snippet below to external servers operated by <b>{self.provider_name}</b>. "
            "Only the approved text displayed below will be sent. Nothing leaves your machine without your explicit click."
        )
        w_desc.setWordWrap(True)
        w_desc.setStyleSheet(f"color: #78350f; font-size: 11px; font-family: {FONT_FAMILY_STACK};")
        w_layout.addWidget(w_desc)

        layout.addWidget(warning_card)

        # Payload Statistics
        char_count = len(self.text_to_send)
        word_count = len(self.text_to_send.split())
        est_kb = round(char_count / 1024, 2)
        stats_label = QLabel(
            f"<b>Transmission Scope:</b> {word_count:,} words • {char_count:,} characters • Approx {est_kb} KB"
        )
        stats_label.setStyleSheet(f"font-size: 11px; color: #475569; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(stats_label)

        # Exact Text Preview (Read-only)
        preview_box = QTextEdit()
        preview_box.setReadOnly(True)
        preview_box.setPlainText(self.text_to_send)
        preview_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                font-family: {FONT_FAMILY_STACK};
                font-size: 12px;
                padding: 8px;
                color: #0f172a;
            }}
        """)
        layout.addWidget(preview_box, stretch=1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 6px 16px;
                font-size: 12px;
                font-family: {FONT_FAMILY_STACK};
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_send = QPushButton(f"🚀 Send to {self.provider_name}")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 18px;
                font-size: 12px;
                font-family: {FONT_FAMILY_STACK};
                font-weight: bold;
                min-width: 140px;
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
        """)
        self.btn_send.clicked.connect(self._on_send_clicked)
        btn_layout.addWidget(self.btn_send)

        layout.addLayout(btn_layout)

    def _on_send_clicked(self):
        self.confirmed = True
        self.accept()


class AIEnhanceResultDialog(QDialog):
    """
    Side-by-side comparison modal allowing the user to review original vs. enhanced text,
    and explicitly Accept & Replace or Reject the result.
    """

    def __init__(self, original_text: str, enhanced_text: str, provider_name: str, parent=None):
        super().__init__(parent)
        self.original_text = original_text
        self.enhanced_text = enhanced_text
        self.provider_name = provider_name
        self.accepted_result = False
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Review AI Enhanced Text")
        self.setMinimumSize(780, 520)
        self.resize(850, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_label = QLabel(f"✨ <b>AI Enhancement Review</b> ({self.provider_name})")
        header_label.setStyleSheet(f"font-size: 14px; color: #1e293b; font-family: {FONT_FAMILY_STACK}; font-weight: bold;")
        layout.addWidget(header_label)

        sub_label = QLabel("Compare the original text on the left with the AI enhanced result on the right before accepting.")
        sub_label.setStyleSheet(f"font-size: 11px; color: #64748b; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(sub_label)

        # Splitter comparing Original vs Enhanced
        splitter = QSplitter(Qt.Horizontal)

        # Left: Original Text
        left_widget = QFrame()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_header = QLabel("📄 Original Text")
        left_header.setStyleSheet(f"font-size: 11.5px; font-weight: bold; color: #475569; font-family: {FONT_FAMILY_STACK};")
        left_layout.addWidget(left_header)
        left_editor = QTextEdit()
        left_editor.setReadOnly(True)
        left_editor.setPlainText(self.original_text)
        left_editor.setStyleSheet(f"font-family: {FONT_FAMILY_STACK}; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 5px;")
        left_layout.addWidget(left_editor)
        splitter.addWidget(left_widget)

        # Right: Enhanced Text
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_header = QLabel("✨ Enhanced Result")
        right_header.setStyleSheet(f"font-size: 11.5px; font-weight: bold; color: #2563eb; font-family: {FONT_FAMILY_STACK};")
        right_layout.addWidget(right_header)
        self.right_editor = QTextEdit()
        self.right_editor.setPlainText(self.enhanced_text)
        self.right_editor.setStyleSheet(f"font-family: {FONT_FAMILY_STACK}; font-size: 12px; border: 1px solid #93c5fd; border-radius: 5px;")
        right_layout.addWidget(self.right_editor)
        splitter.addWidget(right_widget)

        splitter.setSizes([400, 400])
        layout.addWidget(splitter, stretch=1)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_reject = QPushButton("Reject & Keep Original")
        self.btn_reject.setCursor(Qt.PointingHandCursor)
        self.btn_reject.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 6px 16px;
                font-size: 12px;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #fee2e2;
                color: #991b1b;
            }}
        """)
        self.btn_reject.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_reject)

        self.btn_accept = QPushButton("✓ Accept and Replace")
        self.btn_accept.setCursor(Qt.PointingHandCursor)
        self.btn_accept.setStyleSheet(f"""
            QPushButton {{
                background-color: #059669;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 20px;
                font-size: 12px;
                font-weight: bold;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #047857;
            }}
        """)
        self.btn_accept.clicked.connect(self._on_accept_clicked)
        btn_layout.addWidget(self.btn_accept)

        layout.addLayout(btn_layout)

    def _on_accept_clicked(self):
        self.accepted_result = True
        self.enhanced_text = self.right_editor.toPlainText()
        self.accept()
