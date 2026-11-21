"""
tests/test_ocr.py
-----------------
Automated test suite validating the offline OCR subsystem:
1. Engine availability check (non-crashing, returns bool).
2. Language mapping across all 13 Indian languages + English.
3. Text-layer detection: digital selectable text vs. scanned image.
4. Parallel worker execution and strict page ordering.
5. Cancellation safety: preserves completed pages on cancel.
6. Graceful missing-dependency handling with actionable user guides.
7. Benchmark CER & WER calculation accuracy.
"""

import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, List

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set Qt to run in headless offscreen mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PIL import Image, ImageDraw
import pymupdf as fitz
from PySide6.QtWidgets import QApplication

from ocr.base_engine import OCREngine, EngineNotAvailableError, LanguageNotInstalledError
from ocr.engine_factory import get_engine, list_available_engines
from ocr.language_mapping import (
    APP_TO_TESSERACT_LANG,
    map_app_lang_to_tesseract,
    get_missing_language_instructions,
)
from ocr.ocr_pipeline import (
    page_has_selectable_text,
    preprocess_image,
    render_page_to_image,
    run_ocr_pipeline_sync,
    OCRWorkerThread,
    get_optimal_worker_count,
)
from tools.ocr_benchmark import calculate_cer_and_wer


# Mock OCR engine for simulating deterministic OCR recognition in tests
class MockOCREngine(OCREngine):
    def __init__(self, available: bool = True, installed_langs: List[str] = None):
        self._available = available
        self._installed_langs = installed_langs or ["eng", "hin", "tam", "tel", "mar", "ben"]

    def get_name(self) -> str:
        return "Mock OCR Engine"

    def is_available(self) -> bool:
        return self._available

    def supported_languages(self) -> List[str]:
        return self._installed_langs if self._available else []

    def is_language_installed(self, language: str) -> bool:
        return self._available and (language.lower() in self._installed_langs)

    def recognize(self, image: Image.Image, language: str = "eng") -> str:
        if not self._available:
            raise EngineNotAvailableError(
                "Mock engine unavailable",
                instructions=self.get_installation_instructions(),
            )
        if not self.is_language_installed(language):
            raise LanguageNotInstalledError(
                language=language,
                message=f"Language '{language}' not installed",
                instructions=self.get_installation_instructions(missing_lang=language),
            )
        return f"Recognized OCR text for {language} ({image.width}x{image.height})"

    def get_installation_instructions(self, missing_lang=None) -> str:
        if missing_lang:
            return get_missing_language_instructions(missing_lang)
        return "Run: brew install tesseract tesseract-lang"


class MockSlowOCREngine(MockOCREngine):
    """Simulates a non-instant OCR engine for cancellation testing."""
    def recognize(self, image: Image.Image, language: str = "eng") -> str:
        import time
        time.sleep(0.04)
        return super().recognize(image, language)


def create_synthetic_scanned_pdf(file_path: Path, num_pages: int = 3) -> Path:
    """
    Creates a synthetic scanned PDF by rendering text into PIL images
    and embedding them as pure image pages with NO digital text layer.
    """
    doc = fitz.open()
    for p in range(num_pages):
        img = Image.new("RGB", (600, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((30, 40), f"Synthetic Scanned Document - Page {p + 1}", fill=(0, 0, 0))
        draw.text((30, 90), "This page has NO digital text layer.", fill=(50, 50, 50))
        draw.text((30, 140), "Optical Character Recognition is required.", fill=(80, 80, 80))

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        png_data = img_byte_arr.getvalue()

        page = doc.new_page(width=600, height=300)
        page.insert_image(page.rect, stream=png_data)

    doc.save(str(file_path))
    doc.close()
    return file_path


def create_synthetic_digital_pdf(file_path: Path, num_pages: int = 3) -> Path:
    """Creates a PDF with real selectable digital text layer."""
    doc = fitz.open()
    for p in range(num_pages):
        page = doc.new_page(width=600, height=300)
        page.insert_text(
            (50, 80),
            f"Digital Document Page {p + 1}\nThis page contains selectable digital text.",
            fontsize=12,
        )
    doc.save(str(file_path))
    doc.close()
    return file_path


def run_tests():
    print("\n" + "=" * 60)
    print("🧪 OFFLINE OCR SUBSYSTEM TEST SUITE")
    print("=" * 60 + "\n")

    app = QApplication.instance()
    if not app:
        app = QApplication(["-platform", "offscreen"])

    # --------------------------------------------------------------------------
    # Test 1: Engine Availability & Safe Non-Crashing Check
    # --------------------------------------------------------------------------
    print("Test 1: Engine availability check...")
    engine = get_engine("tesseract")
    is_avail = engine.is_available()
    print(f"  • Host Tesseract Available: {is_avail}")
    assert isinstance(is_avail, bool), "is_available() must return a boolean"

    # Even if Tesseract is not installed on this host, calling methods must not crash
    langs = engine.supported_languages()
    assert isinstance(langs, list), "supported_languages() must return a list"
    inst = engine.get_installation_instructions()
    assert "brew install" in inst or "apt-get" in inst or "Tesseract" in inst, "Instructions must contain OS package commands"
    print("  ✅ Passed: Engine availability check behaves safely without crashing.")

    # --------------------------------------------------------------------------
    # Test 2: Language Mapping (13 Indian Languages + English)
    # --------------------------------------------------------------------------
    print("\nTest 2: Validating language mappings...")
    assert len(APP_TO_TESSERACT_LANG) >= 13, "Must cover all supported languages"
    expected_mappings = {
        "eng": "eng",
        "hin": "hin",
        "tam": "tam",
        "tel": "tel",
        "mar": "mar",
        "ben": "ben",
    }
    for app_code, tess_code in expected_mappings.items():
        assert map_app_lang_to_tesseract(app_code) == tess_code, f"Mismatch for {app_code}"

    # Missing language instruction test
    missing_hin_help = get_missing_language_instructions("hin", os_name="macOS")
    assert "hin.traineddata" in missing_hin_help
    assert "brew install tesseract-lang" in missing_hin_help
    print("  ✅ Passed: Language mappings and missing language instructions verified.")

    # --------------------------------------------------------------------------
    # Test 3: Text-Layer Detection (Digital Selectable vs Scanned Image)
    # --------------------------------------------------------------------------
    print("\nTest 3: Testing text-layer detection on digital vs scanned pages...")
    digital_pdf = PROJECT_ROOT / "uploads" / "_test_digital.pdf"
    scanned_pdf = PROJECT_ROOT / "uploads" / "_test_scanned.pdf"

    create_synthetic_digital_pdf(digital_pdf, num_pages=2)
    create_synthetic_scanned_pdf(scanned_pdf, num_pages=2)

    try:
        # Check Digital PDF
        doc_dig = fitz.open(str(digital_pdf))
        has_text_dig, text_dig = page_has_selectable_text(doc_dig[0])
        doc_dig.close()
        assert has_text_dig is True, "Digital page should be recognized as having selectable text"
        assert "Digital Document Page 1" in text_dig

        # Check Scanned PDF
        doc_scan = fitz.open(str(scanned_pdf))
        has_text_scan, text_scan = page_has_selectable_text(doc_scan[0])
        doc_scan.close()
        assert has_text_scan is False, "Scanned image page should NOT have selectable text"
        assert text_scan == ""
        print("  ✅ Passed: Correctly differentiates digital selectable text from scanned pages.")

        # ----------------------------------------------------------------------
        # Test 4: Page Ordering with Parallel Workers (Mock Engine)
        # ----------------------------------------------------------------------
        print("\nTest 4: Verifying parallel execution and strict page ordering...")
        mock_eng = MockOCREngine(available=True)
        res_sync = run_ocr_pipeline_sync(
            pdf_path=str(scanned_pdf),
            target_lang="hin",
            dpi=150,
            max_workers=4,
            engine=mock_eng,
        )
        assert res_sync["success"] is True
        assert res_sync["page_count"] == 2
        assert len(res_sync["pages"]) == 2
        # Check exact page order: page 1 then page 2
        assert res_sync["pages"][0]["page_number"] == 1
        assert res_sync["pages"][1]["page_number"] == 2
        assert res_sync["pages"][0]["source"] == "ocr"
        assert "Recognized OCR text for hin" in res_sync["pages"][0]["text"]
        print("  ✅ Passed: Parallel workers processed pages in strict sequential order.")

        # ----------------------------------------------------------------------
        # Test 5: Graceful Missing Engine / Dependency Handling
        # ----------------------------------------------------------------------
        print("\nTest 5: Testing graceful handling when OCR engine is unavailable...")
        unavail_engine = MockOCREngine(available=False)
        res_unavail = run_ocr_pipeline_sync(
            pdf_path=str(scanned_pdf),
            target_lang="eng",
            dpi=150,
            max_workers=2,
            engine=unavail_engine,
        )
        assert res_unavail["success"] is True
        assert res_unavail["pages"][0]["source"] == "ocr_unavailable"
        assert "OCR Engine Not Available" in res_unavail["pages"][0]["text"]
        assert "brew install" in res_unavail["pages"][0]["text"]
        print("  ✅ Passed: Graceful fallback and user install guide generated without crashing.")

        # ----------------------------------------------------------------------
        # Test 6: Background QThread Cancellation with Partial Results
        # ----------------------------------------------------------------------
        print("\nTest 6: Testing worker cancellation preserving partial results...")
        multi_page_pdf = PROJECT_ROOT / "uploads" / "_test_multi_page.pdf"
        create_synthetic_scanned_pdf(multi_page_pdf, num_pages=8)

        cancelled_result = []

        def on_cancelled(payload):
            cancelled_result.append(payload)

        slow_eng = MockSlowOCREngine(available=True)
        worker = OCRWorkerThread(
            pdf_path=str(multi_page_pdf),
            target_lang="eng",
            dpi=150,
            max_workers=1,  # Serial execution
            engine=slow_eng,
        )
        worker.pipeline_cancelled.connect(on_cancelled)

        worker.start()
        # Allow worker to start and process the first page, then cancel
        import time
        time.sleep(0.06)
        worker.cancel()
        worker.wait()
        app.processEvents()

        assert len(cancelled_result) == 1, "Expected cancellation callback to fire"
        assert cancelled_result[0]["was_cancelled"] is True
        assert cancelled_result[0]["completed_count"] >= 1
        assert len(cancelled_result[0]["pages"]) >= 1
        print(f"  ✅ Passed: Worker cancelled cleanly, keeping {cancelled_result[0]['completed_count']} completed pages intact.")

        # ----------------------------------------------------------------------
        # Test 7: Benchmark Accuracy Metric Calculations (CER & WER)
        # ----------------------------------------------------------------------
        print("\nTest 7: Validating CER & WER accuracy score calculations...")
        # Exact match
        acc_exact = calculate_cer_and_wer("नमस्ते भारत Hello World", "नमस्ते भारत Hello World")
        assert acc_exact["cer"] == 0.0
        assert acc_exact["wer"] == 0.0
        assert acc_exact["char_accuracy"] == 1.0

        # Partial errors
        acc_err = calculate_cer_and_wer("Hello Wurld", "Hello World")
        assert acc_err["char_distance"] == 1
        assert 0.0 < acc_err["cer"] < 0.2
        assert acc_err["wer"] == 0.5  # 1 word wrong out of 2 words
        print("  ✅ Passed: CER and WER calculation verified for multilingual text.")

    finally:
        # Cleanup temporary test PDFs
        for temp_p in [digital_pdf, scanned_pdf, PROJECT_ROOT / "uploads" / "_test_multi_page.pdf"]:
            try:
                if temp_p.is_file():
                    temp_p.unlink()
            except OSError:
                pass

    print("\n" + "=" * 60)
    print("🎉 ALL OCR SUBSYSTEM TESTS PASSED SUCCESSFULLY!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_tests()
