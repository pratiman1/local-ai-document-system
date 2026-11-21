"""
translation/language_detector.py
--------------------------------
Offline language and script detection for multilingual documents.
Specialized for Indian languages (Hindi, Marathi, Tamil, Telugu, Bengali, Gujarati,
Punjabi, Kannada, Malayalam, Odia, Assamese, Urdu) and English.

Key Capabilities:
1. Fast, offline Unicode script classification.
2. Devanagari disambiguation: lexical discrimination between Hindi and Marathi.
3. Confidence estimation: never silently trusts low-confidence or ambiguous guesses.
4. Per-page script detection for scanned pages to choose optimal OCR language models.
5. Multi-page document aggregation and mixed-language detection.
"""

import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from PIL import Image

# Unicode Block Ranges for Indic Scripts & Latin
SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F),
    "Bengali":    (0x0980, 0x09FF),  # Also covers Assamese
    "Gurmukhi":   (0x0A00, 0x0A7F),  # Punjabi
    "Gujarati":   (0x0A80, 0x0AFF),
    "Odia":       (0x0B00, 0x0B7F),
    "Tamil":      (0x0B80, 0x0BFF),
    "Telugu":     (0x0C00, 0x0C7F),
    "Kannada":    (0x0C80, 0x0CFF),
    "Malayalam":  (0x0D00, 0x0D7F),
    "Arabic":     (0x0600, 0x06FF),  # Urdu
    "Latin":      (0x0041, 0x007A),  # English
}

# Mapping from Script to default application language code
SCRIPT_TO_DEFAULT_LANG = {
    "Devanagari": "hin",  # Hindi (or Marathi if disambiguated)
    "Bengali":    "ben",  # Bengali
    "Gurmukhi":   "pan",  # Punjabi
    "Gujarati":   "guj",  # Gujarati
    "Odia":       "ori",  # Odia
    "Tamil":      "tam",  # Tamil
    "Telugu":     "tel",  # Telugu
    "Kannada":    "kan",  # Kannada
    "Malayalam":  "mal",  # Malayalam
    "Arabic":     "urd",  # Urdu
    "Latin":      "eng",  # English
}

# Lexical markers for Devanagari script disambiguation (Hindi vs Marathi)
MARATHI_SPECIFIC_CHAR = "\u0933"  # 'ळ' (Lla) - heavily used in Marathi, rare in standard Hindi

MARATHI_STOPWORDS = {
    "आहे", "आणि", "नाही", "झाला", "केले", "होते", "करणे", "या", "च्या",
    "मध्ये", "तो", "ती", "ते", "एक", "म्हणून", "काही", "आपण", "त्यांना",
    "झाली", "केली", "असेल", "होती", "आहेत", "त्याच्या", "झाले", "तर"
}

HINDI_STOPWORDS = {
    "है", "हैं", "और", "नहीं", "किया", "था", "थी", "थे", "के", "की", "को",
    "का", "में", "से", "पर", "यह", "वह", "होता", "होती", "होते", "एक",
    "कुछ", "अपने", "उनके", "हुआ", "हुई", "हुए", "गया", "गई", "गए", "लेकिन"
}

ASSAMESE_SPECIFIC_CHARS = {"\u09F0", "\u09F1"}  # Ra (ৰ), Va (ৱ)


@dataclass
class DetectionResult:
    """Detailed result of language and script detection."""
    language_code: str          # e.g., 'hin', 'mar', 'tam', 'eng'
    language_name: str          # e.g., 'Hindi', 'Marathi', 'English'
    script_name: str            # e.g., 'Devanagari', 'Tamil', 'Latin'
    confidence: float           # 0.0 to 1.0 (e.g. 0.92 for 92%)
    is_ambiguous: bool          # True if confidence < 0.65 or shared script
    requires_user_confirmation: bool  # True for low-confidence or Hindi/Marathi
    details: str = ""

    def get_display_str(self) -> str:
        conf_pct = int(round(self.confidence * 100))
        if self.requires_user_confirmation:
            return f"Detected: {self.language_name} ({conf_pct}% confidence — please verify)"
        return f"Detected: {self.language_name} ({conf_pct}% confidence)"


@dataclass
class DocumentLanguageResult:
    """Aggregated language detection result across a multi-page document."""
    primary_language_code: str
    primary_language_name: str
    overall_confidence: float
    is_mixed: bool
    page_languages: List[DetectionResult] = field(default_factory=list)
    note: str = ""


def detect_script_from_text(text: str) -> Tuple[str, float]:
    """
    Analyzes character Unicode ranges and returns the dominant script and its ratio.
    """
    if not text or not text.strip():
        return "Latin", 0.0

    script_counts: Dict[str, int] = {s: 0 for s in SCRIPT_RANGES}
    total_analyzed = 0

    for ch in text:
        code = ord(ch)
        # Skip ASCII punctuation, whitespace, and digits
        if ch.isspace() or ch.isdigit() or code < 0x0041:
            continue

        for script, (start, end) in SCRIPT_RANGES.items():
            if start <= code <= end:
                script_counts[script] += 1
                total_analyzed += 1
                break

    if total_analyzed == 0:
        return "Latin", 0.0

    dominant_script, max_count = max(script_counts.items(), key=lambda item: item[1])
    ratio = max_count / total_analyzed
    return dominant_script, ratio


def disambiguate_devanagari(text: str) -> Tuple[str, str, float]:
    """
    Disambiguates between Hindi and Marathi in Devanagari text using character
    and lexical stopwords analysis.

    Returns:
        (lang_code, lang_name, confidence)
    """
    # 1. Check for Marathi-specific character 'ळ'
    marathi_char_count = text.count(MARATHI_SPECIFIC_CHAR)

    # 2. Tokenize words (alphabetic characters in Devanagari range)
    tokens = re.findall(r"[\u0900-\u097F]+", text)
    if not tokens:
        return "hin", "Hindi", 0.50

    marathi_hits = sum(1 for tok in tokens if tok in MARATHI_STOPWORDS)
    hindi_hits = sum(1 for tok in tokens if tok in HINDI_STOPWORDS)

    if marathi_char_count > 0:
        marathi_hits += marathi_char_count * 2

    total_hits = marathi_hits + hindi_hits

    if total_hits == 0:
        # No stopwords found (e.g. short names or numbers): ambiguous
        return "hin", "Hindi", 0.55

    if marathi_hits > hindi_hits:
        conf = min(0.95, 0.65 + (marathi_hits / total_hits) * 0.30)
        return "mar", "Marathi", conf
    elif hindi_hits > marathi_hits:
        conf = min(0.95, 0.65 + (hindi_hits / total_hits) * 0.30)
        return "hin", "Hindi", conf
    else:
        # Equal hits: 50% tie
        return "hin", "Hindi", 0.50


def detect_language_from_text(text: str) -> DetectionResult:
    """
    Performs fast, accurate offline language detection on digital text.
    """
    stripped = text.strip() if text else ""
    if not stripped:
        return DetectionResult(
            language_code="eng",
            language_name="English",
            script_name="Latin",
            confidence=0.0,
            is_ambiguous=True,
            requires_user_confirmation=True,
            details="Empty text provided",
        )

    dominant_script, script_ratio = detect_script_from_text(stripped)

    # 1. Devanagari: Hindi vs Marathi
    if dominant_script == "Devanagari":
        lang_code, lang_name, lex_conf = disambiguate_devanagari(stripped)
        combined_conf = script_ratio * lex_conf
        # Devanagari always benefits from user confirmation if confidence < 0.85
        requires_confirm = combined_conf < 0.85
        return DetectionResult(
            language_code=lang_code,
            language_name=lang_name,
            script_name="Devanagari",
            confidence=round(combined_conf, 2),
            is_ambiguous=requires_confirm,
            requires_user_confirmation=requires_confirm,
            details=f"Devanagari script ({int(script_ratio*100)}%), lexical confidence {int(lex_conf*100)}%",
        )

    # 2. Bengali vs Assamese
    if dominant_script == "Bengali":
        is_assamese = any(ch in stripped for ch in ASSAMESE_SPECIFIC_CHARS)
        if is_assamese:
            return DetectionResult(
                language_code="asm",
                language_name="Assamese",
                script_name="Bengali",
                confidence=round(script_ratio * 0.90, 2),
                is_ambiguous=False,
                requires_user_confirmation=False,
                details="Assamese character markers detected",
            )
        return DetectionResult(
            language_code="ben",
            language_name="Bengali",
            script_name="Bengali",
            confidence=round(script_ratio * 0.95, 2),
            is_ambiguous=False,
            requires_user_confirmation=False,
            details="Bengali script detected",
        )

    # 3. Direct 1:1 Indic Script Mappings
    lang_names = {
        "Tamil": ("tam", "Tamil"),
        "Telugu": ("tel", "Telugu"),
        "Kannada": ("kan", "Kannada"),
        "Malayalam": ("mal", "Malayalam"),
        "Gujarati": ("guj", "Gujarati"),
        "Gurmukhi": ("pan", "Punjabi"),
        "Odia": ("ori", "Odia"),
        "Arabic": ("urd", "Urdu"),
        "Latin": ("eng", "English"),
    }

    if dominant_script in lang_names:
        code, name = lang_names[dominant_script]
        conf = round(script_ratio * 0.95, 2)
        requires_confirm = conf < 0.70
        return DetectionResult(
            language_code=code,
            language_name=name,
            script_name=dominant_script,
            confidence=conf,
            is_ambiguous=requires_confirm,
            requires_user_confirmation=requires_confirm,
            details=f"{dominant_script} script detected with {int(script_ratio*100)}% coverage",
        )

    # Default fallback
    return DetectionResult(
        language_code="eng",
        language_name="English",
        script_name="Latin",
        confidence=0.50,
        is_ambiguous=True,
        requires_user_confirmation=True,
        details="Fallback default",
    )


def detect_script_from_scanned_page(image: Image.Image, tesseract_cmd: Optional[str] = None) -> str:
    """
    Attempts to detect script from a scanned page image using Tesseract OSD
    (Orientation & Script Detection: psm 0) if available.
    Falls back to Latin/Devanagari if OSD is unavailable.
    """
    if not tesseract_cmd:
        from ocr.tesseract_engine import TesseractEngine
        tesseract_cmd = TesseractEngine._locate_binary()

    if not tesseract_cmd:
        return "Latin"

    tmp_path = None
    try:
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
            tmp_path = tmp_img.name
            # Downsample thumbnail for fast OSD check
            thumb = image.copy()
            thumb.thumbnail((1200, 1200))
            thumb.save(tmp_path, format="PNG")

        cmd = [tesseract_cmd, tmp_path, "stdout", "--psm", "0"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)

        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if "Script:" in line:
                    script_val = line.split("Script:")[1].strip()
                    # Normalize script names
                    for known_script in SCRIPT_RANGES:
                        if known_script.lower() in script_val.lower():
                            return known_script
    except Exception:
        pass
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return "Latin"


def detect_document_language(pages: List[Dict[str, Any]]) -> DocumentLanguageResult:
    """
    Aggregates language detection across all pages of a document.
    Detects if the document has mixed languages and produces summary statistics.
    """
    if not pages:
        res = detect_language_from_text("")
        return DocumentLanguageResult(
            primary_language_code=res.language_code,
            primary_language_name=res.language_name,
            overall_confidence=0.0,
            is_mixed=False,
            page_languages=[res],
            note="Empty document",
        )

    page_results: List[DetectionResult] = []
    lang_counts: Dict[str, int] = {}
    lang_names: Dict[str, str] = {}
    conf_scores: Dict[str, List[float]] = {}

    for page in pages:
        text = page.get("text", "")
        res = detect_language_from_text(text)
        page_results.append(res)

        code = res.language_code
        lang_counts[code] = lang_counts.get(code, 0) + 1
        lang_names[code] = res.language_name
        if code not in conf_scores:
            conf_scores[code] = []
        conf_scores[code].append(res.confidence)

    # Dominant language by page count
    primary_code, dominant_page_count = max(lang_counts.items(), key=lambda item: item[1])
    primary_name = lang_names[primary_code]
    avg_conf = sum(conf_scores[primary_code]) / len(conf_scores[primary_code])

    # Check for mixed languages (any other language with >= 20% of pages)
    is_mixed = False
    note = ""
    other_langs = [f"{lang_names[c]} ({cnt} pgs)" for c, cnt in lang_counts.items() if c != primary_code and cnt > 0]

    if len(lang_counts) > 1 and len(other_langs) > 0:
        is_mixed = True
        summary_others = ", ".join(other_langs)
        note = f"Mixed document: {dominant_page_count} pgs {primary_name}, {summary_others}."

    return DocumentLanguageResult(
        primary_language_code=primary_code,
        primary_language_name=primary_name,
        overall_confidence=round(avg_conf, 2),
        is_mixed=is_mixed,
        page_languages=page_results,
        note=note,
    )
