"""
translation/base_translator.py
------------------------------
Abstract base class definition for pluggable offline machine translation engines.
Enables drop-in engine substitution (e.g., Argos Translate now, AI4Bharat IndicTrans2 later)
without modifying document pipeline logic or UI components.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from dataclasses import dataclass


class TranslationError(Exception):
    """Base exception for all translation-related failures."""
    pass


class TranslatorNotAvailableError(TranslationError):
    """Raised when the translation package or engine runtime is missing."""
    def __init__(self, message: str, instructions: str = ""):
        super().__init__(message)
        self.instructions = instructions


class LanguagePairNotSupportedError(TranslationError):
    """Raised when the requested (source, target) language pair is not available."""
    def __init__(self, source: str, target: str, message: str = "", instructions: str = ""):
        msg = message or f"Translation from '{source}' to '{target}' is not supported."
        super().__init__(msg)
        self.source = source
        self.target = target
        self.instructions = instructions


@dataclass
class TranslationOutput:
    """Detailed output for a translated chunk or page."""
    translated_text: str
    source_language: str
    target_language: str
    was_pivoted: bool = False
    pivot_language: str = "eng"
    notice: str = ""


class Translator(ABC):
    """
    Abstract interface for offline translation engines.
    Concrete implementations (ArgosTranslator, future IndicTrans2Translator)
    must implement these methods.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Returns the human-readable engine name, e.g. 'Argos Translate (Offline)'."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Checks whether the engine packages and runtime dependencies are installed.
        Returns True if ready to translate, False otherwise. Must never raise an unhandled exception.
        """
        pass

    @abstractmethod
    def supported_pairs(self) -> List[Tuple[str, str]]:
        """
        Returns a list of supported (source_code, target_code) tuples.
        Example: [('eng', 'hin'), ('hin', 'eng'), ('eng', 'tam')]
        """
        pass

    @abstractmethod
    def is_pair_supported(self, source: str, target: str) -> bool:
        """
        Checks if a direct or pivoted translation pair is available.
        """
        pass

    @abstractmethod
    def translate(self, text: str, source: str, target: str) -> TranslationOutput:
        """
        Translates text from source language code to target language code.

        Parameters:
            text (str): Input text chunk.
            source (str): Source ISO/app language code (e.g. 'eng', 'hin').
            target (str): Target ISO/app language code (e.g. 'hin', 'tam').

        Returns:
            TranslationOutput: Containing translated text, pivot notice, etc.

        Raises:
            TranslatorNotAvailableError: If engine dependencies are missing.
            LanguagePairNotSupportedError: If language pair cannot be routed.
            TranslationError: If translation fails during execution.
        """
        pass

    @abstractmethod
    def get_installation_instructions(self, missing_pair: Optional[Tuple[str, str]] = None) -> str:
        """
        Returns actionable, OS-specific installation instructions for packages and language models.
        """
        pass
