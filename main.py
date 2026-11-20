"""
main.py
-------
Desktop Application Entry Point for the Local AI Multilingual Document Processing System.

Initializes the PySide6 (Qt) application event loop, applies modern styling,
and displays the MainWindow.

How Qt applications work (for beginners):
1. QApplication manages GUI application control flow and main settings.
2. The event loop (app.exec()) waits for user interactions (clicks, keypresses, drops)
   and routes them to the proper widgets via Signals and Slots.
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path so modules can import from config, ui, extractors, etc.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from config.settings import APP_NAME, APP_VERSION, ORGANIZATION_NAME
from ui.main_window import MainWindow


def main():
    """Main application routine."""
    # Ensure High-DPI screen support (Retina displays on Mac)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORGANIZATION_NAME)

    # Instantiate the central window
    window = MainWindow()
    window.show()

    # Start the Qt Event Loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
