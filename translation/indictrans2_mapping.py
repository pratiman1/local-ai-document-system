"""
translation/indictrans2_mapping.py
----------------------------------
Language code mapping and script resolution for AI4Bharat IndicTrans2.
Converts application 3-letter ISO language codes (e.g. 'hin', 'tam', 'eng')
to IndicTrans2 Flores-200 style format ('hin_Deva', 'tam_Taml', 'eng_Latn').
Determines model direction: 'en-indic', 'indic-en', 'indic-indic'.

Does not modify config/languages.py.
"""

from typing import Dict, Optional, Tuple, Set


# Map application 3-letter codes to IndicTrans2 Flores-200 codes (lang_Script)
APP_TO_INDICTRANS_LANG: Dict[str, str] = {
    "eng": "eng_Latn",
    "hin": "hin_Deva",
    "tam": "tam_Taml",
    "tel": "tel_Telu",
    "mar": "mar_Deva",
    "ben": "ben_Beng",
    "guj": "guj_Gujr",
    "pan": "pan_Guru",
    "kan": "kan_Knda",
    "mal": "mal_Mlym",
    "ori": "ory_Orya",  # Flores-200 uses 'ory_Orya' for Odia
    "asm": "asm_Beng",
    "urd": "urd_Arab",
}

# Reverse mapping from IndicTrans2 Flores-200 code to application 3-letter code
INDICTRANS_TO_APP_LANG: Dict[str, str] = {
    v: k for k, v in APP_TO_INDICTRANS_LANG.items()
}

# Set of all Indic 3-letter codes supported in the application
INDIC_APP_LANGS: Set[str] = {
    "hin", "tam", "tel", "mar", "ben",
    "guj", "pan", "kan", "mal", "ori", "asm", "urd"
}

# Human-readable labels for the 3 model directions
DIRECTION_NAMES: Dict[str, str] = {
    "en-indic": "English to Indic (22 languages)",
    "indic-en": "Indic to English (22 languages)",
    "indic-indic": "Indic to Indic (Direct Indian Language Translation)",
}

# Approximate download and disk sizes for IndicTrans2 distilled models
MODEL_SIZES_INFO: Dict[str, Dict[str, str]] = {
    "en-indic": {
        "params": "200M (distilled)",
        "download_size": "~800 MB - 1 GB",
        "disk_size": "~850 MB",
        "huggingface_repo": "ai4bharat/indictrans2-en-indic-dist-200M",
    },
    "indic-en": {
        "params": "200M (distilled)",
        "download_size": "~800 MB - 1 GB",
        "disk_size": "~850 MB",
        "huggingface_repo": "ai4bharat/indictrans2-indic-en-dist-200M",
    },
    "indic-indic": {
        "params": "320M (distilled)",
        "download_size": "~1.2 GB - 1.5 GB",
        "disk_size": "~1.4 GB",
        "huggingface_repo": "ai4bharat/indictrans2-indic-indic-dist-320M",
    },
}


def app_code_to_indictrans(code: str) -> Optional[str]:
    """Converts a 3-letter application code (e.g. 'hin') to IndicTrans2 Flores-200 code ('hin_Deva')."""
    return APP_TO_INDICTRANS_LANG.get(code.lower().strip())


def indictrans_to_app_code(flores_code: str) -> Optional[str]:
    """Converts a Flores-200 code (e.g. 'hin_Deva') to application 3-letter code ('hin')."""
    return INDICTRANS_TO_APP_LANG.get(flores_code.strip())


def is_indic_language(code: str) -> bool:
    """Returns True if the 3-letter language code is a scheduled Indian language."""
    return code.lower().strip() in INDIC_APP_LANGS


def get_model_direction(source: str, target: str) -> Optional[str]:
    """
    Determines which IndicTrans2 model direction is required for a given language pair.

    Returns:
        'en-indic'     if English -> Indic
        'indic-en'     if Indic -> English
        'indic-indic'  if Indic -> Indic (and source != target)
        'same_language' if source == target
        None           if pair is not supported by IndicTrans2
    """
    src = source.lower().strip()
    tgt = target.lower().strip()

    if src == tgt:
        return "same_language"

    src_is_indic = is_indic_language(src)
    tgt_is_indic = is_indic_language(tgt)

    if src == "eng" and tgt_is_indic:
        return "en-indic"
    elif src_is_indic and tgt == "eng":
        return "indic-en"
    elif src_is_indic and tgt_is_indic:
        return "indic-indic"

    return None


def get_direction_display_name(direction: str) -> str:
    """Returns a friendly description for a model direction."""
    return DIRECTION_NAMES.get(direction, direction)
