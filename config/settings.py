"""
config/settings.py
------------------
Central application configuration, paths, and cross-platform UI styles.
Designed for portable execution across macOS, Windows 10/11, and Linux.

Supports both standard Python development and PyInstaller bundled environments.
"""

import os
import sys
from pathlib import Path

# Application Metadata
APP_NAME = "Local AI Multilingual Document Processing System"
APP_VERSION = "1.0.0"
ORGANIZATION_NAME = "LocalAI"

# Status Constants (Clear Offline / Online status)
STATUS_OFFLINE = "100% Offline — No External AI Requests"
STATUS_ONLINE = "Online Mode — User-Authorized AI Request"

# Portable Base Directory Resolution
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS).resolve()
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

UPLOADS_DIR = BASE_DIR / "uploads"
EXPORTS_DIR = BASE_DIR / "exports"
MODELS_DIR = BASE_DIR / "models"
ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"

# Ensure essential runtime directories exist
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)

# Icon Paths: Using as_posix() ensures forward slashes in Qt stylesheets across Windows, Linux, and macOS
CHEVRON_DOWN_ICON = (ICONS_DIR / "chevron_down.svg").as_posix()
CHEVRON_DOWN_HOVER_ICON = (ICONS_DIR / "chevron_down_hover.svg").as_posix()
CLOSE_ICON = (ICONS_DIR / "close.svg").as_posix()
CLOSE_HOVER_ICON = (ICONS_DIR / "close_hover.svg").as_posix()

# Compact, Responsive Desktop UI Dimensions
WINDOW_MIN_WIDTH = 880
WINDOW_MIN_HEIGHT = 580
WINDOW_DEFAULT_WIDTH = 1080
WINDOW_DEFAULT_HEIGHT = 680

# OCR Processing Configuration (High-performance, memory-bounded offline processing)
OCR_DEFAULT_DPI = 300
OCR_MIN_TEXT_CHARS = 10  # Minimum digital characters to consider a page having direct selectable text
OCR_DEFAULT_OEM = 3      # Tesseract LSTM engine mode
OCR_DEFAULT_PSM = 3      # Fully automatic page segmentation without OSD
OCR_MAX_WORKERS = min(4, max(1, (os.cpu_count() or 2) - 1))  # Default worker pool size
OCR_RECOVERY_INTERVAL = 10  # Checkpoint partial recovery every N completed pages
OCR_CONFIDENCE_THRESHOLD = 80.0  # Quality threshold: highlight pages below 80% average confidence
RECOVERY_DIR = UPLOADS_DIR   # Temporary recovery storage (ignored by git)

# Offline Translation Configuration
TRANSLATION_RECOVERY_INTERVAL = 10
TRANSLATION_CHUNK_SIZE = 500   # Max characters per translation chunk to maintain low memory
TRANSLATION_DEFAULT_ENGINE = "argos"

# Optional Cloud AI Enhancement Configuration (Strictly OFF by default)
AI_ENHANCE_ENABLED_DEFAULT = False
AI_ENHANCE_MAX_CHARS = 4000     # Maximum characters sent per authorized request
AI_DEFAULT_PROVIDER = "openai"  # Options: 'openai', 'gemini'
STATUS_ONLINE_PROGRESS = "Online request in progress — Sending authorized snippet..."

# Supported Document File Extensions
SUPPORTED_DOCUMENT_TYPES = [".pdf"]
SUPPORTED_IMAGE_TYPES = [".png", ".jpg", ".jpeg"]

# Universal Cross-Platform Font Family Stack
FONT_FAMILY_STACK = '"Segoe UI", -apple-system, BlinkMacSystemFont, "Ubuntu", "Cantarell", "DejaVu Sans", "Helvetica Neue", Arial, sans-serif'

# Universal Cross-Platform Stylesheet
GLOBAL_STYLESHEET = f"""
    /* Universal Cross-Platform ToolTip Styling */
    QToolTip {{
        background-color: #1e293b;
        color: #ffffff;
        border: 1px solid #334155;
        border-radius: 4px;
        padding: 5px 9px;
        font-size: 11px;
        font-family: {FONT_FAMILY_STACK};
    }}

    /* Global QComboBox Styling with Visible Right-Aligned Dropdown Arrow */
    QComboBox {{
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 5px 30px 5px 10px;
        background-color: #ffffff;
        color: #0f172a;
        font-size: 12px;
        font-family: {FONT_FAMILY_STACK};
        min-height: 26px;
    }}
    QComboBox:hover {{
        border-color: #3b82f6;
        background-color: #f8fafc;
    }}
    QComboBox:focus {{
        border: 1.5px solid #2563eb;
    }}
    QComboBox:disabled {{
        background-color: #f1f5f9;
        color: #94a3b8;
        border-color: #e2e8f0;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 26px;
        border-left: 1px solid #e2e8f0;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }}
    QComboBox::down-arrow {{
        image: url("{CHEVRON_DOWN_ICON}");
        width: 12px;
        height: 12px;
    }}
    QComboBox::down-arrow:hover {{
        image: url("{CHEVRON_DOWN_HOVER_ICON}");
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        background-color: #ffffff;
        selection-background-color: #dbeafe;
        selection-color: #1e40af;
        padding: 4px;
        font-size: 12px;
        font-family: {FONT_FAMILY_STACK};
    }}
"""
