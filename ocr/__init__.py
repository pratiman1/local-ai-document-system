"""
ocr package
-----------
Offline Optical Character Recognition (OCR) module designed for high-accuracy,
memory-efficient, streaming document processing across macOS, Windows, and Linux.
"""

from ocr.base_engine import OCREngine, OCRError, LanguageNotInstalledError, EngineNotAvailableError
from ocr.engine_factory import get_engine, list_available_engines
from ocr.language_mapping import map_app_lang_to_tesseract, get_missing_language_instructions

__all__ = [
    "OCREngine",
    "OCRError",
    "LanguageNotInstalledError",
    "EngineNotAvailableError",
    "get_engine",
    "list_available_engines",
    "map_app_lang_to_tesseract",
    "get_missing_language_instructions",
]
