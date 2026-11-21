"""
ocr/language_mapping.py
-----------------------
Bridges application language codes (from config/languages.py) to OCR engine
language codes (Tesseract 3-letter codes) without modifying config/languages.py.

Provides actionable, OS-aware installation guides for missing language packs
across macOS, Windows, and Linux.
"""

import platform
from typing import Dict, Optional


# Application language code -> Tesseract language identifier
APP_TO_TESSERACT_LANG: Dict[str, str] = {
    "eng": "eng",  # English
    "hin": "hin",  # Hindi (हिन्दी)
    "tam": "tam",  # Tamil (தமிழ்)
    "tel": "tel",  # Telugu (తెలుగు)
    "mar": "mar",  # Marathi (मराठी)
    "ben": "ben",  # Bengali (বাংলা)
    "guj": "guj",  # Gujarati (ગુજરાતી)
    "pan": "pan",  # Punjabi (ਪੰਜਾਬੀ)
    "kan": "kan",  # Kannada (ಕನ್ನಡ)
    "mal": "mal",  # Malayalam (മലയാളം)
    "ori": "ori",  # Odia (ଓଡ଼ିଆ)
    "asm": "asm",  # Assamese (অসমীয়া)
    "urd": "urd",  # Urdu (اردو)
}

# Human-readable language names for messaging
TESSERACT_LANG_NAMES: Dict[str, str] = {
    "eng": "English",
    "hin": "Hindi",
    "tam": "Tamil",
    "tel": "Telugu",
    "mar": "Marathi",
    "ben": "Bengali",
    "guj": "Gujarati",
    "pan": "Punjabi",
    "kan": "Kannada",
    "mal": "Malayalam",
    "ori": "Odia",
    "asm": "Assamese",
    "urd": "Urdu",
}

# Reverse mapping: Tesseract code -> App code
TESSERACT_TO_APP_LANG: Dict[str, str] = {
    v: k for k, v in APP_TO_TESSERACT_LANG.items()
}


def map_app_lang_to_tesseract(app_code: str) -> str:
    """
    Maps an application language code (e.g. 'hin', 'tam') to its Tesseract OCR code.
    Defaults to 'eng' if unmapped.
    """
    if not app_code:
        return "eng"
    return APP_TO_TESSERACT_LANG.get(app_code.lower().strip(), "eng")


def map_tesseract_to_app_lang(tess_code: str) -> str:
    """
    Maps a Tesseract OCR language code back to the application language code.
    """
    if not tess_code:
        return "eng"
    return TESSERACT_TO_APP_LANG.get(tess_code.lower().strip(), "eng")


def get_language_display_name(tess_code: str) -> str:
    """
    Returns the English display name for a Tesseract code.
    """
    return TESSERACT_LANG_NAMES.get(tess_code.lower().strip(), tess_code)


def get_missing_language_instructions(lang_code: str, os_name: Optional[str] = None) -> str:
    """
    Generates tailored, copy-pasteable installation instructions for missing language data
    based on the host operating system.
    """
    if os_name is None:
        raw_sys = platform.system()
        if raw_sys == "Darwin":
            os_name = "macOS"
        elif raw_sys == "Windows":
            os_name = "Windows"
        else:
            os_name = "Linux"

    tess_code = map_app_lang_to_tesseract(lang_code) if lang_code in APP_TO_TESSERACT_LANG else lang_code
    lang_name = get_language_display_name(tess_code)
    traineddata_file = f"{tess_code}.traineddata"

    if os_name == "macOS":
        return (
            f"The Tesseract language pack for '{lang_name}' ({traineddata_file}) is not installed.\n\n"
            f"To install all Indian language packs on macOS using Homebrew, run in Terminal:\n"
            f"  brew install tesseract-lang\n\n"
            f"Alternatively, download '{traineddata_file}' from the official tessdata_fast repository:\n"
            f"  https://github.com/tesseract-ocr/tessdata_fast/raw/main/{traineddata_file}\n"
            f"and place it into:\n"
            f"  /opt/homebrew/share/tessdata/ (Apple Silicon) or /usr/local/share/tessdata/ (Intel)"
        )
    elif os_name == "Windows":
        return (
            f"The Tesseract language pack for '{lang_name}' ({traineddata_file}) is not installed.\n\n"
            f"To install on Windows:\n"
            f"1. Download '{traineddata_file}' directly from:\n"
            f"   https://github.com/tesseract-ocr/tessdata_fast/raw/main/{traineddata_file}\n"
            f"2. Copy the file into your Tesseract 'tessdata' folder:\n"
            f"   C:\\Program Files\\Tesseract-OCR\\tessdata\\\n"
            f"3. Restart the application."
        )
    else:  # Linux
        return (
            f"The Tesseract language pack for '{lang_name}' ({traineddata_file}) is not installed.\n\n"
            f"To install on Ubuntu / Debian / Linux Mint, run in Terminal:\n"
            f"  sudo apt-get update && sudo apt-get install -y tesseract-ocr-{tess_code}\n\n"
            f"On Fedora / RHEL:\n"
            f"  sudo dnf install -y tesseract-langpack-{tess_code}\n\n"
            f"On Arch Linux:\n"
            f"  sudo pacman -S tesseract-data-{tess_code}"
        )
