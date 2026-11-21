"""
ocr/base_engine.py
------------------
Abstract base class definition for pluggable offline OCR engines.
Provides a unified interface enabling drop-in engine substitution
(e.g., Tesseract OCR, future PaddleOCR, etc.) without altering the
document processing pipeline.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from PIL import Image


class OCRError(Exception):
    """Base exception for all OCR-related errors."""
    pass


class EngineNotAvailableError(OCRError):
    """Raised when the underlying OCR binary or Python wrapper is not found."""
    def __init__(self, message: str, instructions: str = ""):
        super().__init__(message)
        self.instructions = instructions


class LanguageNotInstalledError(OCRError):
    """Raised when the requested OCR language pack is not installed."""
    def __init__(self, language: str, message: str, instructions: str = ""):
        super().__init__(message)
        self.language = language
        self.instructions = instructions


class OCREngine(ABC):
    """
    Abstract interface for OCR engines.
    Any concrete OCR engine (e.g., TesseractEngine, future PaddleOCREngine)
    must implement these methods.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Returns the human-readable display name of the engine."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Checks whether the OCR engine is installed, executable, and ready for use.
        Returns True if available, False otherwise. Must never raise an unhandled exception.
        """
        pass

    @abstractmethod
    def supported_languages(self) -> List[str]:
        """
        Returns a list of language codes currently installed and supported by this engine.
        Example: ['eng', 'hin', 'tam']
        """
        pass

    @abstractmethod
    def is_language_installed(self, language: str) -> bool:
        """
        Checks if the specified language code is supported and installed.
        """
        pass

    @abstractmethod
    def recognize(self, image: Image.Image, language: str = "eng") -> str:
        """
        Performs optical character recognition on a PIL Image for the specified language.

        Parameters:
            image (PIL.Image.Image): The preprocessed page image to recognize.
            language (str): Target OCR language code (e.g., 'eng', 'hin').

        Returns:
            str: Extracted plain text.

        Raises:
            EngineNotAvailableError: If engine executable is missing.
            LanguageNotInstalledError: If language data pack is missing.
            OCRError: If recognition fails.
        """
        pass

    @abstractmethod
    def get_installation_instructions(self, missing_lang: Optional[str] = None) -> str:
        """
        Returns clear, platform-specific installation instructions for the user
        when the engine or a required language pack is missing.
        """
        pass
