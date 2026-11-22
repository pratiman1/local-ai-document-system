"""
ui/compare_review_dialog.py
---------------------------
Side-by-side comparison and review dialog for Compare Mode.
Allows users to compare primary vs secondary engine translations (e.g. IndicTrans2 vs Argos)
on flagged pages and select their preferred output.

Notice:
"Agreement indicator, not an accuracy score; two models can agree and still be wrong."
"""

from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QComboBox,
    QFrame,
    QSplitter,
    QWidget,
)
from PySide6.QtCore import Qt
from config.settings import FONT_FAMILY_STACK


class CompareReviewDialog(QDialog):
    """
    Side-by-side comparison and review interface for multi-engine translation consensus.
    """

    def __init__(self, translated_pages: List[Dict[str, Any]], agreement_threshold: float = 0.60, parent=None):
        super().__init__(parent)
        self.translated_pages = translated_pages
        self.agreement_threshold = agreement_threshold
        self.modified = False
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Translation Consensus & Compare Review")
        self.resize(880, 600)
        self.setMinimumSize(700, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header Title
        title = QLabel("🔍 <b>Translation Engine Comparison & Review</b>")
        title.setStyleSheet(f"font-size: 14px; color: #1e293b; font-family: {FONT_FAMILY_STACK};")
        layout.addWidget(title)

        # Honest Disclosure Notice
        notice_frame = QFrame()
        notice_frame.setStyleSheet("""
            QFrame {
                background-color: #faf5ff;
                border: 1px solid #e9d5ff;
                border-radius: 5px;
                padding: 6px;
            }
        """)
        n_layout = QVBoxLayout(notice_frame)
        n_layout.setContentsMargins(8, 6, 8, 6)
        lbl_notice = QLabel(
            "<b>Consensus Notice:</b> Agreement indicator is not an accuracy score; "
            "two models can agree and still be wrong. Review differences and choose your preferred translation."
        )
        lbl_notice.setWordWrap(True)
        lbl_notice.setStyleSheet(f"font-size: 11px; color: #6b21a8; font-family: {FONT_FAMILY_STACK};")
        n_layout.addWidget(lbl_notice)
        layout.addWidget(notice_frame)

        # Page Selection Controls
        sel_layout = QHBoxLayout()
        sel_lbl = QLabel("Select Page to Review:")
        sel_lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 600; color: #334155; font-family: {FONT_FAMILY_STACK};")
        sel_layout.addWidget(sel_lbl)

        self.combo_pages = QComboBox()
        self.combo_pages.setStyleSheet(f"font-size: 12px; font-family: {FONT_FAMILY_STACK}; min-width: 200px;")
        
        # Populate pages
        for idx, page in enumerate(self.translated_pages):
            p_num = page.get("page_number", idx + 1)
            comp = page.get("comparison")
            if comp:
                flag = "⚠️ Low Agreement" if comp.get("is_flagged") else "✓ Consensus"
                pct = comp.get("score_percent", 0.0)
                label = f"Page {p_num} — {flag} ({pct:.1f}%)"
            else:
                label = f"Page {p_num}"
            self.combo_pages.addItem(label, idx)

        self.combo_pages.currentIndexChanged.connect(self._on_page_selected)
        sel_layout.addWidget(self.combo_pages)

        self.lbl_agreement_badge = QLabel("")
        self.lbl_agreement_badge.setStyleSheet(f"font-size: 11px; font-weight: bold; font-family: {FONT_FAMILY_STACK};")
        sel_layout.addWidget(self.lbl_agreement_badge)
        sel_layout.addStretch()

        layout.addLayout(sel_layout)

        # Side-by-Side Text Splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left: Primary Engine
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_primary_engine = QLabel("<b>Primary Engine Output:</b>")
        self.lbl_primary_engine.setStyleSheet(f"font-size: 11.5px; color: #1e293b; font-family: {FONT_FAMILY_STACK};")
        left_layout.addWidget(self.lbl_primary_engine)

        self.txt_primary = QPlainTextEdit()
        self.txt_primary.setReadOnly(True)
        self.txt_primary.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: #ffffff;
                font-size: 12px;
                font-family: {FONT_FAMILY_STACK};
                padding: 6px;
            }}
        """)
        left_layout.addWidget(self.txt_primary)
        splitter.addWidget(left_widget)

        # Right: Secondary Engine
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_secondary_engine = QLabel("<b>Secondary Engine Output:</b>")
        self.lbl_secondary_engine.setStyleSheet(f"font-size: 11.5px; color: #1e293b; font-family: {FONT_FAMILY_STACK};")
        right_layout.addWidget(self.lbl_secondary_engine)

        self.txt_secondary = QPlainTextEdit()
        self.txt_secondary.setReadOnly(True)
        self.txt_secondary.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: #ffffff;
                font-size: 12px;
                font-family: {FONT_FAMILY_STACK};
                padding: 6px;
            }}
        """)
        right_layout.addWidget(self.txt_secondary)
        splitter.addWidget(right_widget)

        layout.addWidget(splitter, 1)

        # Switch / Select Action Buttons
        page_action_layout = QHBoxLayout()
        self.btn_keep_primary = QPushButton("✓ Keep Primary Engine Text")
        self.btn_keep_primary.setCursor(Qt.PointingHandCursor)
        self.btn_keep_primary.setStyleSheet(f"""
            QPushButton {{
                background-color: #f1f5f9;
                color: #1e293b;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #e2e8f0;
            }}
        """)
        self.btn_keep_primary.clicked.connect(self._on_keep_primary)
        page_action_layout.addWidget(self.btn_keep_primary)

        self.btn_switch_secondary = QPushButton("⇄ Use Secondary Engine Text for this Page")
        self.btn_switch_secondary.setCursor(Qt.PointingHandCursor)
        self.btn_switch_secondary.setStyleSheet(f"""
            QPushButton {{
                background-color: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #93c5fd;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 600;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #dbeafe;
            }}
        """)
        self.btn_switch_secondary.clicked.connect(self._on_switch_secondary)
        page_action_layout.addWidget(self.btn_switch_secondary)
        page_action_layout.addStretch()

        layout.addLayout(page_action_layout)

        # Dialog Bottom Buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.btn_close = QPushButton("Done Reviewing")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 11.5px;
                font-family: {FONT_FAMILY_STACK};
            }}
            QPushButton:hover {{
                background-color: #1d4ed8;
            }}
        """)
        self.btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(self.btn_close)

        layout.addLayout(bottom_layout)

        # Initialize view on first page
        if self.translated_pages:
            self._on_page_selected(0)

    def _on_page_selected(self, index: int):
        if not (0 <= index < len(self.translated_pages)):
            return

        page = self.translated_pages[index]
        primary_text = page.get("translated_text", "")
        self.txt_primary.setPlainText(primary_text)

        comp = page.get("comparison")
        if comp:
            p_eng = comp.get("primary_engine", "Primary Engine")
            s_eng = comp.get("secondary_engine", "Secondary Engine")
            s_text = comp.get("secondary_text", "")
            pct = comp.get("score_percent", 0.0)
            flagged = comp.get("is_flagged", False)

            self.lbl_primary_engine.setText(f"<b>Primary ({p_eng}):</b>")
            self.lbl_secondary_engine.setText(f"<b>Secondary ({s_eng}):</b>")
            self.txt_secondary.setPlainText(s_text)

            color = "#b91c1c" if flagged else "#15803d"
            status_txt = "⚠️ Flagged (Below threshold)" if flagged else "✓ Consensus"
            self.lbl_agreement_badge.setText(f"<font color='{color}'>{status_txt}: {pct:.1f}% Agreement</font>")
        else:
            self.lbl_primary_engine.setText("<b>Primary Engine:</b>")
            self.lbl_secondary_engine.setText("<b>Secondary Engine:</b>")
            self.txt_secondary.setPlainText("(No comparison available for this page)")
            self.lbl_agreement_badge.setText("")

    def _on_keep_primary(self):
        """Keeps primary output."""
        idx = self.combo_pages.currentData()
        if 0 <= idx < len(self.translated_pages):
            self.lbl_agreement_badge.setText("<font color='#15803d'>✓ Primary engine selected for this page</font>")

    def _on_switch_secondary(self):
        """Replaces translated_text with secondary engine's translation."""
        idx = self.combo_pages.currentData()
        if 0 <= idx < len(self.translated_pages):
            page = self.translated_pages[idx]
            comp = page.get("comparison")
            if comp and comp.get("secondary_text"):
                page["translated_text"] = comp["secondary_text"]
                self.txt_primary.setPlainText(comp["secondary_text"])
                self.modified = True
                self.lbl_agreement_badge.setText("<font color='#2563eb'>✓ Switched to secondary engine for this page</font>")
