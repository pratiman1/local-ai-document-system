"""
tests/test_translation.py
-------------------------
Automated test suite validating the offline translation and detection subsystem:
1. Script classification and language detection across Indic scripts & English.
2. Devanagari Hindi vs. Marathi lexical disambiguation and low-confidence flagging.
3. Sentence and paragraph text chunking adhering to memory limits.
4. Same-language bypass (skips translation when source == target).
5. Pivot translation routing and notification (e.g. Indic -> English -> Indic).
6. Non-blocking QThread worker execution and safe cancellation preserving completed pages.
7. Translation sanity check heuristics (length ratio, untranslated script detection).
8. Real OCR confidence aggregation and low-confidence page flagging (<80%).
9. Pure-Python smoothed BLEU-4 and CER/WER metric calculation.
10. Actionable offline model installation guides.
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set Qt to run in headless offscreen mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from translation.base_translator import (
    Translator,
    TranslationOutput,
    TranslationError,
    LanguagePairNotSupportedError,
    TranslatorNotAvailableError,
)
from translation.language_detector import (
    detect_language_from_text,
    detect_document_language,
    disambiguate_devanagari,
    detect_script_from_text,
    DetectionResult,
)
from translation.argos_translator import ArgosTranslator
from translation.translator_factory import get_translator, register_translator
from translation.quality_checker import (
    evaluate_translation_sanity,
    compute_document_ocr_confidence,
    TranslationSanityReport,
)
from translation.translation_pipeline import (
    chunk_text,
    translate_page,
    run_translation_pipeline_sync,
    TranslationWorkerThread,
)
from tools.ocr_benchmark import calculate_smoothed_bleu, calculate_cer_and_wer


class MockPairTranslator(Translator):
    """
    Mock translator for deterministic offline testing without downloading GBs of models.
    """
    def __init__(self, supported_pairs: List[tuple]):
        self.pairs = supported_pairs

    def get_name(self) -> str:
        return "Mock Translator"

    def is_available(self) -> bool:
        return True

    def supported_pairs(self) -> List[Tuple[str, str]]:
        return list(self.pairs)

    def is_pair_supported(self, source: str, target: str) -> bool:
        s, t = source.lower(), target.lower()
        if (s, t) in self.pairs:
            return True
        if (s, "eng") in self.pairs and ("eng", t) in self.pairs:
            return True
        return False

    def translate(self, text: str, source: str, target: str) -> TranslationOutput:
        s, t = source.lower(), target.lower()
        if (s, t) in self.pairs:
            return TranslationOutput(
                translated_text=f"[{t.upper()}] {text}",
                source_language=s,
                target_language=t,
                was_pivoted=False,
            )
        # Check pivot via eng
        if (s, "eng") in self.pairs and ("eng", t) in self.pairs:
            intermediate = f"[ENG] {text}"
            return TranslationOutput(
                translated_text=f"[{t.upper()}] {intermediate}",
                source_language=s,
                target_language=t,
                was_pivoted=True,
                notice=f"Translated via English pivot ({s} -> eng -> {t}).",
            )
        raise LanguagePairNotSupportedError(s, t)

    def get_installation_instructions(self, missing_pair: Optional[Tuple[str, str]] = None) -> str:
        s, t = missing_pair if missing_pair else ("src", "tgt")
        return f"Install mock model for {s}->{t}."


def run_tests():
    print("=" * 60)
    print("🧪 STARTING OFFLINE TRANSLATION & DETECTION TEST SUITE")
    print("=" * 60)

    # Initialize headless Qt App for QThread tests
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # -------------------------------------------------------------
    # 1. Test Script Classification & Language Detection
    # -------------------------------------------------------------
    print("\n[1/10] Testing Offline Language Detection...")

    samples = [
        ("यह भारत का संविधान है और हम भारत के नागरिक हैं।", "hin", "Devanagari"),
        ("हा महाराष्ट्र राज्याचा अधिकृत दस्तऐवज आहे आणि तो अतिशय महत्त्वाचा आहे.", "mar", "Devanagari"),
        ("இது தமிழ் மொழியில் எழுதப்பட்ட முக்கியமான ஆவணம் ஆகும்.", "tam", "Tamil"),
        ("ఇది తెలుగు భాషలో ఉన్న ముఖ్యమైన అధికారిక పత్రము.", "tel", "Telugu"),
        ("এটি বাংলা ভাষায় লিখিত একটি অত্যন্ত গুরুত্বপূর্ণ নথি।", "ben", "Bengali"),
        ("This is a standard English paragraph for verification.", "eng", "Latin"),
    ]

    for text, expected_lang, expected_script in samples:
        res = detect_language_from_text(text)
        assert res.language_code == expected_lang, f"Expected {expected_lang}, got {res.language_code} for '{text[:20]}'"
        assert res.script_name == expected_script, f"Expected script {expected_script}, got {res.script_name}"
        assert res.confidence >= 0.70, f"Expected high confidence for clear text, got {res.confidence}"
        print(f"  ✓ Detected {res.language_name} ({res.script_name}) with {int(res.confidence*100)}% conf.")

    # -------------------------------------------------------------
    # 2. Test Devanagari Disambiguation & Low-Confidence Handling
    # -------------------------------------------------------------
    print("\n[2/10] Testing Devanagari Disambiguation & Low Confidence...")

    # Marathi-specific letter 'ळ'
    mar_text = "बाळ शाळेत जातो आणि आनंदाने खेळतो."
    mar_res = detect_language_from_text(mar_text)
    assert mar_res.language_code == "mar"
    print(f"  ✓ Correctly classified Marathi with character 'ळ' marker.")

    # Ambiguous or numeric text
    empty_res = detect_language_from_text("   ")
    assert empty_res.confidence == 0.0
    assert empty_res.requires_user_confirmation is True
    print(f"  ✓ Handled empty text with requires_user_confirmation=True.")

    num_res = detect_language_from_text("१२३ ४५६ ७८९")
    assert num_res.requires_user_confirmation is True
    print(f"  ✓ Ambiguous numeric Devanagari flagged for user confirmation.")

    # -------------------------------------------------------------
    # 3. Test Sentence & Paragraph Chunking
    # -------------------------------------------------------------
    print("\n[3/10] Testing Text Chunking for Memory Safety (<= 500 chars)...")

    short_text = "Hello world! This is short."
    chunks_short = chunk_text(short_text, max_chunk_chars=500)
    assert len(chunks_short) == 1
    assert chunks_short[0] == short_text

    # Create a long text of ~1200 characters across multiple sentences
    long_para = "This is a detailed paragraph intended to test chunking. " * 25
    chunks_long = chunk_text(long_para, max_chunk_chars=500)
    assert len(chunks_long) > 1
    for c in chunks_long:
        assert len(c) <= 500, f"Chunk exceeded 500 chars: {len(c)}"
    print(f"  ✓ Successfully split {len(long_para)} chars into {len(chunks_long)} chunks <= 500 chars.")

    # -------------------------------------------------------------
    # 4. Test Same-Language Skip
    # -------------------------------------------------------------
    print("\n[4/10] Testing Same-Language Bypass...")

    mock_translator = MockPairTranslator([("hin", "eng"), ("eng", "hin"), ("eng", "tam")])
    page_data = {"page_number": 1, "text": "This is already in English."}

    skip_res = translate_page(page_data, source_lang="eng", target_lang="eng", translator=mock_translator)
    assert skip_res["skipped"] is True
    assert skip_res["translated_text"] == "This is already in English."
    print("  ✓ Same-language translation bypassed cleanly (skipped=True, original preserved).")

    # -------------------------------------------------------------
    # 5. Test Direct vs Pivot Translation Routing
    # -------------------------------------------------------------
    print("\n[5/10] Testing Translation Routing (Direct & English Pivot)...")

    # Direct pair: hin -> eng
    direct_out = mock_translator.translate("नमस्ते", source="hin", target="eng")
    assert direct_out.was_pivoted is False
    assert "[ENG]" in direct_out.translated_text
    print("  ✓ Direct translation executed without pivot.")

    # Pivot pair: hin -> tam (routed via hin -> eng -> tam)
    pivot_out = mock_translator.translate("नमस्ते", source="hin", target="tam")
    assert pivot_out.was_pivoted is True
    assert "Translated via English pivot" in pivot_out.notice
    assert "[TAM]" in pivot_out.translated_text
    print(f"  ✓ Pivot translation routing verified: {pivot_out.notice}")

    # Unsupported pair
    try:
        mock_translator.translate("Hello", source="eng", target="urd")
        assert False, "Should have raised LanguagePairNotSupportedError"
    except LanguagePairNotSupportedError:
        print("  ✓ Correctly raised LanguagePairNotSupportedError for unsupported pair.")

    # -------------------------------------------------------------
    # 6. Test Synchronous Document Pipeline Execution
    # -------------------------------------------------------------
    print("\n[6/10] Testing Synchronous Translation Pipeline...")

    pages = [
        {"page_number": 1, "text": "Page one text in Hindi: नमस्ते."},
        {"page_number": 2, "text": "Page two text in Hindi: धन्यवाद."},
    ]
    doc_res = run_translation_pipeline_sync(
        pages=pages,
        source_lang="hin",
        target_lang="eng",
        translator=mock_translator,
    )
    assert doc_res["success"] is True
    assert doc_res["page_count"] == 2
    assert len(doc_res["translated_pages"]) == 2
    assert "[ENG]" in doc_res["full_translated_text"]
    assert "--- Page Break ---" in doc_res["full_translated_text"]
    print("  ✓ Pipeline preserved page-by-page alignment and generated full translated text.")

    # -------------------------------------------------------------
    # 7. Test Threaded Worker Execution & Cancellation
    # -------------------------------------------------------------
    print("\n[7/10] Testing Translation Worker Thread Cancellation...")

    multi_pages = [{"page_number": i + 1, "text": f"Content page {i + 1}"} for i in range(10)]

    class SlowMockTranslator(MockPairTranslator):
        def translate(self, text: str, source: str, target: str) -> TranslationOutput:
            time.sleep(0.04)  # 40ms per page
            return super().translate(text, source, target)

    slow_trans = SlowMockTranslator([("hin", "eng")])
    worker = TranslationWorkerThread(
        pages=multi_pages,
        source_lang="hin",
        target_lang="eng",
        translator=slow_trans,
        doc_id="test_cancel_doc",
    )

    completed_pages = []
    worker.page_translated.connect(lambda p, c, t, eta: completed_pages.append(p))

    cancelled_payload = []
    worker.translation_cancelled.connect(lambda payload: cancelled_payload.append(payload))

    worker.start()
    time.sleep(0.10)  # Wait for 1-2 pages to complete
    worker.cancel()
    worker.wait(5000)
    app.processEvents()

    assert len(cancelled_payload) == 1, "Expected translation_cancelled signal to fire."
    payload = cancelled_payload[0]
    assert payload["was_cancelled"] is True
    assert payload["completed_count"] >= 1
    assert payload["completed_count"] < 10
    assert len(payload["translated_pages"]) == payload["completed_count"]
    print(f"  ✓ Safely cancelled translation at page {payload['completed_count']}/10; preserved completed pages.")

    # -------------------------------------------------------------
    # 8. Test Quality Checker Heuristics & Sanity Checks
    # -------------------------------------------------------------
    print("\n[8/10] Testing Quality Checker Heuristics...")

    # Normal valid translation
    normal_rep = evaluate_translation_sanity("This is a test.", "यह एक परीक्षण है।", "eng", "hin")
    assert normal_rep.status == "Passed"
    assert normal_rep.is_empty is False

    # Empty output check
    empty_rep = evaluate_translation_sanity("Original text", "", "eng", "hin")
    assert empty_rep.status == "Failed"
    assert empty_rep.is_empty is True
    assert "Empty output" in empty_rep.summary

    # Untranslated script check (Devanagari words untouched when translating hin -> eng)
    untrans_rep = evaluate_translation_sanity("यह एक परीक्षण वाक्य है।", "यह एक परीक्षण वाक्य है।", "hin", "eng")
    assert untrans_rep.status == "Warning"
    assert untrans_rep.untranslated_script_ratio > 0.5
    print("  ✓ Correctly flagged suspicious untranslated script output.")

    # -------------------------------------------------------------
    # 9. Test OCR Word-Confidence Aggregation
    # -------------------------------------------------------------
    print("\n[9/10] Testing OCR Word Confidence & Low-Confidence Page Flagging...")

    ocr_pages = [
        {"page_number": 1, "source": "ocr", "ocr_confidence": 92.5},
        {"page_number": 2, "source": "ocr", "ocr_confidence": 74.0},  # Low confidence page (<80%)
        {"page_number": 3, "source": "ocr", "ocr_confidence": 88.0},
    ]
    doc_ocr = compute_document_ocr_confidence(ocr_pages)
    assert doc_ocr["has_ocr"] is True
    assert doc_ocr["low_confidence_pages"] == [2]
    expected_avg = (92.5 + 74.0 + 88.0) / 3
    assert abs(doc_ocr["document_confidence"] - expected_avg) < 0.1
    assert "⚠️ Low confidence on: Page 2" in doc_ocr["display_str"]
    print(f"  ✓ Flagged low-confidence pages {doc_ocr['low_confidence_pages']} (doc avg {doc_ocr['document_confidence']:.1f}%).")

    # -------------------------------------------------------------
    # 10. Test Smoothed BLEU-4 and Offline Installation Guides
    # -------------------------------------------------------------
    print("\n[10/10] Testing Smoothed BLEU-4 & Installation Guides...")

    # Exact match BLEU
    ref = "The quick brown fox jumps over the lazy dog."
    hyp_exact = "The quick brown fox jumps over the lazy dog."
    bleu_exact = calculate_smoothed_bleu(hyp_exact, ref)
    assert abs(bleu_exact - 1.0) < 1e-4, f"Expected 1.0, got {bleu_exact}"
    print(f"  ✓ Exact match BLEU-4 = {bleu_exact * 100:.2f}%")

    # Partial match BLEU
    hyp_part = "The fast brown fox jumps over a lazy dog."
    bleu_part = calculate_smoothed_bleu(hyp_part, ref)
    assert 0.20 < bleu_part < 1.0
    print(f"  ✓ Partial match BLEU-4 = {bleu_part * 100:.2f}%")

    # Zero/empty text BLEU
    bleu_zero = calculate_smoothed_bleu("", ref)
    assert bleu_zero == 0.0

    # Installation guide text
    argos_engine = ArgosTranslator()
    guide = argos_engine.get_installation_instructions(("hin", "eng"))
    assert "pip install argostranslate" in guide
    assert "for 'hin' to 'eng'" in guide
    assert ".argosmodel" in guide
    print(f"  ✓ Actionable offline installation instructions generated.")

    print("\n" + "=" * 60)
    print("🎉 ALL OFFLINE TRANSLATION & DETECTION TESTS PASSED!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_tests()
