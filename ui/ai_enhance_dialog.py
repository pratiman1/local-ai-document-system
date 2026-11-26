"""
ui/ai_enhance_dialog.py
-----------------------
Dialogs governing the optional Cloud & Local AI Enhancement feature:
1. AIEnhanceConfirmDialog: Mandatory privacy disclosure showing provider, model,
   exact scrollable text to be sent, transmission metrics, task preset selector,
   redaction toggle, and session bypass option.
2. AIEnhanceResultDialog: Side-by-side comparison (Original vs. Enhanced) with
   explicit Accept & Replace and Reject buttons, plus optional glossary addition.
3. AIAuditLogDialog: Viewer for metadata-only request audit log (no text/keys stored).
"""

from typing import Tuple, Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QFrame,
    QSplitter,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
)
from PySide6.QtCore import Qt
from config.settings import FONT_FAMILY_STACK
from services.redaction_manager import redact_sensitive_data, restore_sensitive_data
from services.audit_logger import get_ai_audit_log, clear_ai_audit_log


PRESET_TASKS = [
    (
        "Fix grammar",
        "Fix grammar, spelling, punctuation, and syntax while strictly preserving all numbers, proper names, section headings, and glossary terms. Do not add or remove content.",
    ),
    (
        "Fix doubtful translation using the source text",
        "Evaluate translation against source text. Fix mistranslated idioms, false friends, and awkward phrasing while preserving all numbers, names, headings, and glossary terms.",
    ),
    (
        "Rewrite more naturally",
        "Rewrite in natural, fluent, and idiomatic prose while strictly preserving the exact original meaning, numbers, names, headings, and glossary terms.",
    ),
    (
        "Custom instruction",
        "",
    ),
]


class AIEnhanceConfirmDialog(QDialog):
    """
    Mandatory privacy confirmation dialog before transmitting any document text.
    Strictly requires user click to proceed.
    """

    def __init__(
        self,
        text: str,
        provider_name: str,
        model_name: str = "",
        source_text: str = "",
        source_lang: str = "eng",
        target_lang: str = "eng",
        is_local: bool = False,
        endpoint_host: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.raw_text = text
        self.provider_name = provider_name
        self.model_name = model_name
        self.source_text = source_text
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.is_local = is_local
        self.endpoint_host = endpoint_host

        self.confirmed = False
        self.redaction_enabled = False
        self.placeholder_map: Dict[str, str] = {}
        self.do_not_ask_again = False
        self.selected_task = "Fix grammar"
        self.user_instruction = ""
        self.final_text_to_send = text

        self._init_ui()

    def _init_ui(self):
        title = "Confirm AI Enhancement (Local Server)" if self.is_local else "Confirm Online AI Enhancement (Privacy Warning)"
        self.setWindowTitle(title)
        self.setMinimumSize(620, 560)
        self.resize(680, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # 1. Warning / Notice Card
        warning_card = QFrame()
        if self.is_local:
            warning_card.setStyleSheet("""
                QFrame {
                    background-color: #f0fdf4;
                    border: 1px solid #bbf7d0;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
            w_layout = QVBoxLayout(warning_card)
            w_layout.setContentsMargins(8, 8, 8, 8)
            w_layout.setSpacing(4)
            w_title = QLabel("🟢 <b>Local Model Server: Text Does NOT Leave Your Computer</b>")
            w_title.setStyleSheet(f"color: #166534; font-size: 12.5px; font-family: {FONT_FAMILY_STACK}; font-weight: bold;")
            w_layout.addWidget(w_title)
            w_desc = QLabel(
                f"The text will be processed on-device by <b>{self.provider_name}</b> using model <b>{self.model_name or 'default'}</b>. "
                "No external network calls are made. Processing stays 100% private and offline."
            )
            w_desc.setWordWrap(True)
            w_desc.setStyleSheet(f"color: #14532d; font-size: 11px; font-family: {FONT_FAMILY_STACK};")
            w_layout.addWidget(w_desc)
        else:
            warning_card.setStyleSheet("""
                QFrame {
                    background-color: #fffbeb;
                    border: 1px solid #fde68a;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
            w_layout = QVBoxLayout(warning_card)
            w_layout.setContentsMargins(8, 8, 8, 8)
            w_layout.setSpacing(4)
            w_title = QLabel("⚠️ <b>Privacy Warning: Text Will Leave Your Computer</b>")
            w_title.setStyleSheet(f"color: #92400e; font-size: 12.5px; font-family: {FONT_FAMILY_STACK}; font-weight: bold;")
            w_layout.addWidget(w_title)
            host_note = f" at cloud host <b>{self.endpoint_host}</b>" if self.endpoint_host else ""
            w_desc = QLabel(
                f"You are about to transmit the snippet below to external servers operated by <b>{self.provider_name}</b>{host_note} "
                f"using model <b>{self.model_name or 'default'}</b>. "
                "Only the approved text displayed below will be sent. Nothing leaves your machine without your explicit click."
            )
            w_desc.setWordWrap(True)
            w_desc.setStyleSheet(f"color: #78350f; font-size: 11px; font-family: {FONT_FAMILY_STACK};")
            w_layout.addWidget(w_desc)

        layout.addWidget(warning_card)

        # 2. Task Preset Selection & Custom Instruction
        task_frame = QFrame()
        task_frame.setStyleSheet("QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px; }")
        t_layout = QVBoxLayout(task_frame)
        t_layout.setContentsMargins(8, 6, 8, 6)
        t_layout.setSpacing(6)

        t_row = QHBoxLayout()
        t_row.addWidget(QLabel("<b>Task Preset:</b>"))
        self.combo_task = QComboBox()
        for name, _ in PRESET_TASKS:
            self.combo_task.addItem(name)
        self.combo_task.currentIndexChanged.connect(self._on_task_preset_changed)
        t_row.addWidget(self.combo_task, stretch=1)
        t_layout.addLayout(t_row)

        self.txt_instruction = QLineEdit()
        self.txt_instruction.setPlaceholderText("Enter or customize the prompt instruction to the AI...")
        self.txt_instruction.setText(PRESET_TASKS[0][1])
        t_layout.addWidget(self.txt_instruction)

        layout.addWidget(task_frame)

        # 3. Redaction / Masking Control
        self.chk_redact = QCheckBox("🔒 Mask personal data (names, numbers, emails, phone numbers) before sending")
        self.chk_redact.setStyleSheet(f"font-size: 11.5px; font-family: {FONT_FAMILY_STACK}; font-weight: 600; color: #0f172a;")
        self.chk_redact.toggled.connect(self._on_redact_toggled)
        layout.addWidget(self.chk_redact)

        # 4. Scope Statistics
        self.lbl_stats = QLabel()
        self.lbl_stats.setStyleSheet(f"font-size: 11px; color: #475569; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(self.lbl_stats)

        # 5. Exact Text Preview (Read-only, scrollable)
        lbl_preview = QLabel("<b>Exact Text To Be Sent (Scrollable Preview):</b>")
        lbl_preview.setStyleSheet(f"font-size: 11px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(lbl_preview)

        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                font-family: {FONT_FAMILY_STACK};
                font-size: 12px;
                padding: 6px;
                color: #0f172a;
            }}
        """)
        layout.addWidget(self.preview_box, stretch=1)

        # 6. Session Consent Bypass (expires on close, strictly never saved to disk)
        self.chk_session_bypass = QCheckBox(
            "Do not ask again for this session (for this provider and document only — expires when app closes)"
        )
        self.chk_session_bypass.setStyleSheet(f"font-size: 10.5px; color: #64748b; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(self.chk_session_bypass)

        # 7. Action Buttons
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
            QPushButton:hover {{ background-color: #e2e8f0; }}
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        send_label = f"🚀 Send to {self.provider_name}" if not self.is_local else "⚡ Run on Local Server"
        self.btn_send = QPushButton(send_label)
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 5px;
                padding: 6px 20px;
                font-size: 12px;
                font-family: {FONT_FAMILY_STACK};
                font-weight: bold;
                min-width: 140px;
            }}
            QPushButton:hover {{ background-color: #1d4ed8; }}
        """)
        self.btn_send.clicked.connect(self._on_send_clicked)
        btn_layout.addWidget(self.btn_send)

        layout.addLayout(btn_layout)

        # Initialize text display
        self._refresh_preview()

    def _on_task_preset_changed(self, idx: int):
        if 0 <= idx < len(PRESET_TASKS):
            self.txt_instruction.setText(PRESET_TASKS[idx][1])
            self.selected_task = PRESET_TASKS[idx][0]

    def _on_redact_toggled(self, checked: bool):
        self.redaction_enabled = checked
        self._refresh_preview()

    def _refresh_preview(self):
        if self.redaction_enabled:
            redacted_txt, p_map = redact_sensitive_data(self.raw_text)
            self.final_text_to_send = redacted_txt
            self.placeholder_map = p_map
        else:
            self.final_text_to_send = self.raw_text
            self.placeholder_map = {}

        self.preview_box.setPlainText(self.final_text_to_send)

        chars = len(self.final_text_to_send)
        tokens = max(1, chars // 4)
        words = len(self.final_text_to_send.split())
        est_kb = round(chars / 1024, 2)
        redact_note = f" • Masked {len(self.placeholder_map)} entities" if self.redaction_enabled else ""

        self.lbl_stats.setText(
            f"<b>Scope:</b> {words:,} words • {chars:,} characters • ~{tokens:,} tokens (~{est_kb} KB){redact_note} "
            f"• <i>No prices claimed (check provider rates).</i>"
        )

    def _on_send_clicked(self):
        self.confirmed = True
        self.do_not_ask_again = self.chk_session_bypass.isChecked()
        self.user_instruction = self.txt_instruction.text().strip()
        self.selected_task = self.combo_task.currentText()
        self.accept()


class AIEnhanceResultDialog(QDialog):
    """
    Side-by-side comparison modal allowing the user to review original vs. enhanced text,
    explicitly Accept & Replace or Reject the result, and optionally add glossary terms.
    """

    def __init__(
        self,
        original_text: str,
        enhanced_text: str,
        provider_name: str,
        source_lang: str = "eng",
        target_lang: str = "eng",
        parent=None,
    ):
        super().__init__(parent)
        self.original_text = original_text
        self.enhanced_text = enhanced_text
        self.provider_name = provider_name
        self.source_lang = source_lang
        self.target_lang = target_lang

        self.accepted_result = False
        self.add_to_glossary = False
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Review AI Enhanced Text")
        self.setMinimumSize(820, 540)
        self.resize(880, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_label = QLabel(f"✨ <b>AI Enhancement Review</b> ({self.provider_name})")
        header_label.setStyleSheet(f"font-size: 14px; color: #1e293b; font-family: {FONT_FAMILY_STACK}; font-weight: bold;")
        layout.addWidget(header_label)

        sub_label = QLabel(
            "Compare the original text on the left with the enhanced result on the right. "
            "You can edit the result directly before accepting."
        )
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

        # Right: Enhanced Text (editable)
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_header = QLabel("✨ Enhanced Result (Editable)")
        right_header.setStyleSheet(f"font-size: 11.5px; font-weight: bold; color: #2563eb; font-family: {FONT_FAMILY_STACK};")
        right_layout.addWidget(right_header)
        self.right_editor = QTextEdit()
        self.right_editor.setPlainText(self.enhanced_text)
        self.right_editor.setStyleSheet(f"font-family: {FONT_FAMILY_STACK}; font-size: 12px; border: 1px solid #93c5fd; border-radius: 5px;")
        right_layout.addWidget(self.right_editor)
        splitter.addWidget(right_widget)

        splitter.setSizes([420, 420])
        layout.addWidget(splitter, stretch=1)

        # Glossary addition checkbox
        self.chk_add_glossary = QCheckBox("📖 Add a corrected term from this change to the domain glossary")
        self.chk_add_glossary.setStyleSheet(f"font-size: 11px; color: #334155; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(self.chk_add_glossary)

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
        self.add_to_glossary = self.chk_add_glossary.isChecked()
        self.accept()


class AIAuditLogDialog(QDialog):
    """
    Viewer dialog for the metadata-only AI request audit log.
    Guaranteed: Contains zero document text and zero API keys.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Request Audit Log")
        self.setMinimumSize(640, 420)
        self.resize(700, 460)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QLabel("📋 <b>Local AI Request Audit Log</b>")
        header.setStyleSheet(f"font-size: 13.5px; color: #0f172a; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(header)

        sub = QLabel("Strict privacy log: Records only timestamp, provider, model, character count, and page number. Contains zero document text and zero keys.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 11px; color: #64748b; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(sub)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Timestamp (UTC)", "Provider", "Model", "Characters", "Approx Tokens", "Page / Target"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet(f"font-size: 11px; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(self.table, stretch=1)

        self._populate_table()

        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("🗑️ Clear Audit Log")
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _populate_table(self):
        records = get_ai_audit_log()
        self.table.setRowCount(len(records))
        for row, rec in enumerate(reversed(records)):
            self.table.setItem(row, 0, QTableWidgetItem(rec.get("timestamp", "")))
            self.table.setItem(row, 1, QTableWidgetItem(rec.get("provider", "")))
            self.table.setItem(row, 2, QTableWidgetItem(rec.get("model", "")))
            self.table.setItem(row, 3, QTableWidgetItem(str(rec.get("character_count", 0))))
            self.table.setItem(row, 4, QTableWidgetItem(str(rec.get("approx_tokens", 0))))
            self.table.setItem(row, 5, QTableWidgetItem(str(rec.get("page_number", ""))))

    def _on_clear_clicked(self):
        if QMessageBox.question(self, "Clear Audit Log", "Are you sure you want to clear the local AI request audit log?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            clear_ai_audit_log()
            self._populate_table()
