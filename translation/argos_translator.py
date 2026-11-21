"""
translation/argos_translator.py
-------------------------------
Argos Translate offline translation engine implementation conforming to Translator.
Features:
1. Lightweight, 100% offline neural machine translation.
2. Direct language pair translation when direct models are installed.
3. Automatic pivot translation through English when no direct pair exists
   (e.g., Hindi -> English -> Tamil), notifying the user regarding potential quality loss.
4. Non-crashing dependency probing and clear instructions for downloading offline .argosmodel files.
"""

from typing import List, Tuple, Optional, Dict
from translation.base_translator import (
    Translator,
    TranslationError,
    TranslatorNotAvailableError,
    LanguagePairNotSupportedError,
    TranslationOutput,
)

# Probing for argostranslate
try:
    import argostranslate.package
    import argostranslate.translate
    _ARGOS_AVAILABLE = True
except ImportError:
    argostranslate = None
    _ARGOS_AVAILABLE = False


# Map 3-letter app codes to Argos 2-letter ISO 639-1 codes
APP_TO_ARGOS_LANG: Dict[str, str] = {
    "eng": "en",
    "hin": "hi",
    "tam": "ta",
    "tel": "te",
    "mar": "mr",
    "ben": "bn",
    "guj": "gu",
    "pan": "pa",
    "kan": "kn",
    "mal": "ml",
    "ori": "or",
    "asm": "as",
    "urd": "ur",
}

ARGOS_TO_APP_LANG: Dict[str, str] = {
    v: k for k, v in APP_TO_ARGOS_LANG.items()
}


class ArgosTranslator(OCREngine := Translator):
    """
    Offline neural translation powered by Argos Translate.
    Supports local .argosmodel weights with automatic English pivoting.
    """

    def __init__(self):
        self._cached_installed_langs = None

    def get_name(self) -> str:
        return "Argos Translate (Offline Open-Source Engine)"

    def is_available(self) -> bool:
        """Checks if argostranslate is importable and available in environment."""
        return _ARGOS_AVAILABLE

    def _get_argos_languages(self):
        if not self.is_available():
            return []
        try:
            return argostranslate.translate.get_installed_languages()
        except Exception:
            return []

    def supported_pairs(self) -> List[Tuple[str, str]]:
        """
        Returns all supported (source_app_code, target_app_code) pairs,
        including pivoted combinations through English.
        """
        if not self.is_available():
            return []

        installed = self._get_argos_languages()
        if not installed:
            return []

        direct_pairs: List[Tuple[str, str]] = []
        lang_dict = {lang.code: lang for lang in installed}

        for src_lang in installed:
            src_app = ARGOS_TO_APP_LANG.get(src_lang.code, src_lang.code)
            for tgt_lang in installed:
                if src_lang == tgt_lang:
                    continue
                try:
                    trans = src_lang.get_translation(tgt_lang)
                    if trans is not None:
                        tgt_app = ARGOS_TO_APP_LANG.get(tgt_lang.code, tgt_lang.code)
                        direct_pairs.append((src_app, tgt_app))
                except Exception:
                    pass

        # Also add pivoted pairs through 'en'
        all_pairs = list(direct_pairs)
        if "en" in lang_dict:
            en_lang = lang_dict["en"]
            sources_to_en = [src for src, tgt in direct_pairs if tgt == "eng"]
            targets_from_en = [tgt for src, tgt in direct_pairs if src == "eng"]

            for src in sources_to_en:
                for tgt in targets_from_en:
                    if src != tgt and (src, tgt) not in all_pairs:
                        all_pairs.append((src, tgt))

        return all_pairs

    def is_pair_supported(self, source: str, target: str) -> bool:
        """Checks if a translation route exists between source and target."""
        if source == target:
            return True
        pairs = self.supported_pairs()
        return (source.lower(), target.lower()) in pairs

    def translate(self, text: str, source: str, target: str) -> TranslationOutput:
        """
        Translates text from source to target language code.
        Automatically applies pivoting through English when no direct pair exists.
        """
        if not text or not text.strip():
            return TranslationOutput(
                translated_text="",
                source_language=source,
                target_language=target,
            )

        if source.lower() == target.lower():
            return TranslationOutput(
                translated_text=text,
                source_language=source,
                target_language=target,
                was_pivoted=False,
                notice=f"Source and target languages are both '{source}'. Translation skipped.",
            )

        if not self.is_available():
            raise TranslatorNotAvailableError(
                "Argos Translate engine is not installed in your Python environment.",
                instructions=self.get_installation_instructions((source, target)),
            )

        src_argos = APP_TO_ARGOS_LANG.get(source.lower(), source.lower())
        tgt_argos = APP_TO_ARGOS_LANG.get(target.lower(), target.lower())

        installed = self._get_argos_languages()
        lang_dict = {lang.code: lang for lang in installed}

        src_obj = lang_dict.get(src_argos)
        tgt_obj = lang_dict.get(tgt_argos)

        if not src_obj or not tgt_obj:
            raise LanguagePairNotSupportedError(
                source, target,
                message=f"Missing language model for '{source}' or '{target}'.",
                instructions=self.get_installation_instructions((source, target)),
            )

        # 1. Attempt Direct Translation
        try:
            direct_trans = src_obj.get_translation(tgt_obj)
            if direct_trans is not None:
                translated_str = direct_trans.translate(text)
                return TranslationOutput(
                    translated_text=translated_str,
                    source_language=source,
                    target_language=target,
                    was_pivoted=False,
                )
        except Exception:
            pass

        # 2. Attempt Pivot Translation through English ('en')
        en_obj = lang_dict.get("en")
        if en_obj and src_obj != en_obj and tgt_obj != en_obj:
            try:
                to_en = src_obj.get_translation(en_obj)
                from_en = en_obj.get_translation(tgt_obj)

                if to_en is not None and from_en is not None:
                    intermediate_en = to_en.translate(text)
                    final_translated = from_en.translate(intermediate_en)
                    notice_msg = f"Pivoted through English ({source} ➔ eng ➔ {target}). Translation quality may be lower."
                    return TranslationOutput(
                        translated_text=final_translated,
                        source_language=source,
                        target_language=target,
                        was_pivoted=True,
                        pivot_language="eng",
                        notice=notice_msg,
                    )
            except Exception as e:
                raise TranslationError(f"Pivot translation failed: {str(e)}")

        # Neither direct nor pivot path available
        raise LanguagePairNotSupportedError(
            source, target,
            instructions=self.get_installation_instructions((source, target)),
        )

    def get_installation_instructions(self, missing_pair: Optional[Tuple[str, str]] = None) -> str:
        """
        Returns copy-pasteable instructions for installing Argos Translate and downloading models.
        """
        pair_hint = ""
        if missing_pair:
            src, tgt = missing_pair
            pair_hint = f" for '{src}' to '{tgt}'"

        return (
            f"Argos Translate language model{pair_hint} is not installed.\n\n"
            "To install Argos Translate in your local virtual environment, run:\n"
            "  pip install argostranslate\n\n"
            "To download and install the required language model packages locally:\n"
            "1. Download the '.argosmodel' package file for your language pair from:\n"
            "   https://www.argosopentech.com/argospm/index/\n"
            "2. Install the package using Python in Terminal:\n"
            "   python -c \"import argostranslate.package; argostranslate.package.install_from_path('path/to/model.argosmodel')\"\n\n"
            "All models run 100% offline with zero cloud API dependency."
        )
