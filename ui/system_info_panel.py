"""
ui/system_info_panel.py
-----------------------
Dynamic, cross-platform system information panel.
Detects and displays host operating system, processor architecture,
installed system RAM, and application version.

Works natively on macOS, Windows, and Linux without hardcoded values.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QHBoxLayout,
)
from config.settings import APP_VERSION, FONT_FAMILY_STACK
from utils.system_info import get_system_summary


class SystemInfoPanel(QWidget):
    """
    Compact, dynamic hardware and system information card.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main Info Card Frame
        self.card = QFrame()
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 8px;
            }}
            QLabel {{
                font-family: {FONT_FAMILY_STACK};
            }}
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        # Header
        header = QLabel("💻 <b>System Information</b>")
        header.setStyleSheet("font-size: 11px; color: #334155;")
        header.setToolTip("Dynamic hardware and OS specifications detected on this computer.")
        card_layout.addWidget(header)

        # Fetch live detected system summary
        sys_data = get_system_summary()

        # OS Row
        os_display = sys_data["os_version"] if sys_data["os_version"] else sys_data["os_name"]
        self.lbl_os = QLabel(f"• <b>OS:</b> {os_display}")
        self.lbl_os.setStyleSheet("font-size: 10px; color: #475569;")
        self.lbl_os.setToolTip(f"Host Operating System: {sys_data['os_name']}\nRelease/Kernel: {sys_data['os_version']}")
        card_layout.addWidget(self.lbl_os)

        # Architecture Row
        self.lbl_arch = QLabel(f"• <b>Arch:</b> {sys_data['arch']}")
        self.lbl_arch.setStyleSheet("font-size: 10px; color: #475569;")
        self.lbl_arch.setToolTip(f"Processor Architecture: {sys_data['arch']}\nProcessor Details: {sys_data.get('processor', 'Standard')}")
        card_layout.addWidget(self.lbl_arch)

        # RAM Row
        self.lbl_ram = QLabel(f"• <b>RAM:</b> {sys_data['ram']}")
        self.lbl_ram.setStyleSheet("font-size: 10px; color: #475569;")
        self.lbl_ram.setToolTip("Total physical installed memory detected on this machine.")
        card_layout.addWidget(self.lbl_ram)

        # App Version Row
        self.lbl_ver = QLabel(f"• <b>App Version:</b> v{APP_VERSION}")
        self.lbl_ver.setStyleSheet("font-size: 10px; color: #2563eb; font-weight: 500;")
        self.lbl_ver.setToolTip(f"Local AI Document Processing System v{APP_VERSION}")
        card_layout.addWidget(self.lbl_ver)

        layout.addWidget(self.card)
