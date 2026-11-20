"""
config/languages.py
-------------------
Language registry for the multilingual document processing system.
Focuses on scheduled Indian languages and English.

In Phase 1, this acts as the configuration source for the UI language dropdown.
In Phase 3, these language codes will map directly to offline translation engines
such as AI4Bharat IndicTrans2 and Argos Translate.
"""

from typing import Dict, List, NamedTuple


class LanguageInfo(NamedTuple):
    code: str           # ISO 639-1 / IndicTrans2 language code
    name: str           # English name
    native_name: str    # Native script name
    is_indic: bool      # Flag identifying Indian languages


# Master catalog of supported languages
SUPPORTED_LANGUAGES: Dict[str, LanguageInfo] = {
    "eng": LanguageInfo(code="eng", name="English", native_name="English", is_indic=False),
    "hin": LanguageInfo(code="hin", name="Hindi", native_name="हिन्दी", is_indic=True),
    "tam": LanguageInfo(code="tam", name="Tamil", native_name="தமிழ்", is_indic=True),
    "tel": LanguageInfo(code="tel", name="Telugu", native_name="తెలుగు", is_indic=True),
    "mar": LanguageInfo(code="mar", name="Marathi", native_name="मराठी", is_indic=True),
    "ben": LanguageInfo(code="ben", name="Bengali", native_name="বাংলা", is_indic=True),
    "guj": LanguageInfo(code="guj", name="Gujarati", native_name="ગુજરાતી", is_indic=True),
    "pan": LanguageInfo(code="pan", name="Punjabi", native_name="ਪੰਜਾਬੀ", is_indic=True),
    "kan": LanguageInfo(code="kan", name="Kannada", native_name="ಕನ್ನಡ", is_indic=True),
    "mal": LanguageInfo(code="mal", name="Malayalam", native_name="മലയാളം", is_indic=True),
    "ori": LanguageInfo(code="ori", name="Odia", native_name="ଓଡ଼ିଆ", is_indic=True),
    "asm": LanguageInfo(code="asm", name="Assamese", native_name="অসমীয়া", is_indic=True),
    "urd": LanguageInfo(code="urd", name="Urdu", native_name="اردو", is_indic=True),
}

DEFAULT_SOURCE_LANGUAGE = "eng"
DEFAULT_TARGET_LANGUAGE = "hin"


def get_language_dropdown_items() -> List[Dict[str, str]]:
    """
    Returns formatted language entries suitable for display in PySide6 QComboBox.
    Example label: "Hindi (हिन्दी)"
    """
    items = []
    for code, info in SUPPORTED_LANGUAGES.items():
        items.append({
            "code": code,
            "label": f"{info.name} ({info.native_name})" if info.name != info.native_name else info.name,
            "is_indic": info.is_indic,
        })
    return items
