"""
translation/quality_checker.py
------------------------------
Honest, un-faked quality and heuristic sanity check indicators for offline processing.
Neither OCR nor Translation can know true accuracy without ground-truth reference text.

Provides:
1. OCR word-level confidence aggregation from Tesseract.
2. Threshold-based page flagging (e.g., < 80% confidence highlighted for review).
3. Translation heuristic sanity checks: output presence, script conversion ratio, length plausibility.
4. Transparent labeling and tooltips informing the user that these are heuristics, not guaranteed accuracy.
"""

from dataclasses import dataclass
from typing import Dict, Any, List
from translation.language_detector import detect_script_from_text, SCRIPT_RANGES


@dataclass
class TranslationSanityReport:
    """Honest heuristic validation of translation output."""
    status: str                 # 'Passed', 'Warning', 'Failed'
    is_empty: bool
    length_ratio: float         # len(translated) / max(1, len(original))
    untranslated_script_ratio: float  # Fraction of characters remaining in source script
    target_script_ratio: float        # Fraction of characters matching target script
    summary: str
    details: str
    tooltip: str = (
        "Basic heuristic sanity check verifying output completeness, script conversion, "
        "and character length ratio. This does NOT guarantee linguistic accuracy."
    )


def evaluate_translation_sanity(
    original_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
) -> TranslationSanityReport:
    """
    Evaluates translation output honestly using automated heuristic checks:
    1. Output is non-empty.
    2. Length ratio is plausible (typically 0.3x to 3.0x).
    3. Source script characters do not overwhelmingly dominate the output.
    """
    orig_clean = original_text.strip() if original_text else ""
    trans_clean = translated_text.strip() if translated_text else ""

    if not trans_clean:
        return TranslationSanityReport(
            status="Failed",
            is_empty=True,
            length_ratio=0.0,
            untranslated_script_ratio=0.0,
            target_script_ratio=0.0,
            summary="Basic check: Empty output",
            details="Translation produced zero characters.",
        )

    # 1. Length ratio check
    len_ratio = len(trans_clean) / max(1, len(orig_clean))

    # 2. Script conversion check
    orig_script, _ = detect_script_from_text(orig_clean)
    trans_script, trans_script_ratio = detect_script_from_text(trans_clean)

    # Calculate remaining characters in source script
    source_script_range = SCRIPT_RANGES.get(orig_script)
    untranslated_chars = 0
    total_letters = 0

    if source_script_range and orig_script != "Latin":
        start, end = source_script_range
        for ch in trans_clean:
            if not ch.isspace() and not ch.isdigit():
                total_letters += 1
                if start <= ord(ch) <= end:
                    untranslated_chars += 1

    untranslated_ratio = untranslated_chars / max(1, total_letters)

    # Evaluation Rules
    warnings = []
    if len_ratio < 0.25:
        warnings.append(f"Output is unusually short ({len_ratio:.2f}x of original)")
    elif len_ratio > 3.5:
        warnings.append(f"Output is unusually long ({len_ratio:.2f}x of original)")

    if untranslated_ratio > 0.40 and orig_script != "Latin":
        warnings.append(f"High untranslated source script remaining ({int(untranslated_ratio*100)}%)")

    if not warnings:
        status = "Passed"
        summary = f"Basic check: Passed ({len_ratio:.1f}x length, script converted)"
        details = f"Output length ratio: {len_ratio:.2f}x. Dominant script: {trans_script}."
    else:
        status = "Warning"
        summary = f"Basic check: Review Recommended"
        details = " • ".join(warnings)

    return TranslationSanityReport(
        status=status,
        is_empty=False,
        length_ratio=round(len_ratio, 2),
        untranslated_script_ratio=round(untranslated_ratio, 2),
        target_script_ratio=round(trans_script_ratio, 2),
        summary=summary,
        details=details,
    )


def compute_document_ocr_confidence(pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes real aggregate OCR confidence across all pages and identifies
    pages falling below the quality threshold for user inspection.
    """
    ocr_pages = [p for p in pages if p.get("source") == "ocr"]
    if not ocr_pages:
        return {
            "has_ocr": False,
            "document_confidence": 100.0,
            "display_str": "All digital text (100% digital extraction)",
            "low_confidence_pages": [],
        }

    total_conf = 0.0
    valid_count = 0
    low_conf_pages: List[int] = []

    for p in ocr_pages:
        conf = p.get("ocr_confidence", 0.0)
        p_num = p.get("page_number", 1)
        if conf > 0:
            total_conf += conf
            valid_count += 1
        if conf < 80.0:
            low_conf_pages.append(p_num)

    avg_conf = total_conf / max(1, valid_count)
    conf_pct = int(round(avg_conf))

    if low_conf_pages:
        low_list_str = ", ".join(f"Page {n}" for n in low_conf_pages[:5])
        if len(low_conf_pages) > 5:
            low_list_str += f" (+{len(low_conf_pages)-5} more)"
        display_str = f"OCR Confidence: {conf_pct}% (⚠️ Low confidence on: {low_list_str})"
    else:
        display_str = f"OCR Confidence: {conf_pct}% (All pages ≥ 80%)"

    return {
        "has_ocr": True,
        "document_confidence": avg_conf,
        "display_str": display_str,
        "low_confidence_pages": low_conf_pages,
    }
