"""
translation package
-------------------
Offline language detection and machine translation subsystem for the Local AI Document System.
"""

from translation.base_translator import (
    Translator,
    TranslationError,
    TranslatorNotAvailableError,
    LanguagePairNotSupportedError,
    TranslationOutput,
)
from translation.translator_factory import get_translator, list_available_translators
from translation.language_detector import (
    detect_language_from_text,
    detect_script_from_text,
    detect_document_language,
    DetectionResult,
    DocumentLanguageResult,
)
from translation.quality_checker import (
    evaluate_translation_sanity,
    compute_document_ocr_confidence,
    TranslationSanityReport,
)
from translation.translation_pipeline import (
    TranslationWorkerThread,
    run_translation_pipeline_sync,
    translate_page,
    chunk_text,
)

__all__ = [
    "Translator",
    "TranslationError",
    "TranslatorNotAvailableError",
    "LanguagePairNotSupportedError",
    "TranslationOutput",
    "get_translator",
    "list_available_translators",
    "detect_language_from_text",
    "detect_script_from_text",
    "detect_document_language",
    "DetectionResult",
    "DocumentLanguageResult",
    "evaluate_translation_sanity",
    "compute_document_ocr_confidence",
    "TranslationSanityReport",
    "TranslationWorkerThread",
    "run_translation_pipeline_sync",
    "translate_page",
    "chunk_text",
]
