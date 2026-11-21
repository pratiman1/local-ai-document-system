"""
tests/test_security_remediations.py
------------------------------------
Comprehensive regression test suite verifying the 6 approved security remediations:
1. Digital PDF extraction regression check.
2. Scanned PDF OCR regression check.
3. OCR cancellation & recovery file deletion.
4. Translation cancellation & recovery file deletion.
5. Document removal while processing & recovery cleanup.
6. Application close during active processing.
7. Declining unsaved edits close confirmation.
8. Temporary image cleanup after subprocess timeout.
9. Temporary image cleanup after unexpected exception.
10. Git ignore rules for root document, image, temporary and recovery files.
11. Gemini API key redaction in simulated network exceptions.
12. Streamlit telemetry configuration verification.
"""

import os
import sys
import io
import time
import shutil
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# Force Qt offscreen platform for headless execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PIL import Image, ImageDraw
import pymupdf as fitz
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QCloseEvent

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from extractors.pdf_extractor import extract_text_from_pdf
from ocr.tesseract_engine import TesseractEngine, OCRError
from ocr.ocr_pipeline import (
    OCRWorkerThread,
    get_recovery_file_path,
    save_recovery_checkpoint,
    remove_recovery_checkpoint,
)
from translation.translation_pipeline import (
    TranslationWorkerThread,
    get_translation_recovery_path,
    save_translation_recovery,
    remove_translation_recovery,
)
from translation.language_detector import detect_script_from_scanned_page
from services.ai_provider import GeminiProvider, OpenAIProvider, AIProviderError
from ui.main_window import MainWindow


class MockSecTranslator:
    def get_name(self): return "MockSecTranslator"
    def is_available(self): return True
    def is_pair_supported(self, s, t): return True
    def translate(self, text, source, target):
        from translation.base_translator import TranslationOutput
        time.sleep(0.02)
        return TranslationOutput(
            translated_text="Translated " + text,
            source_language=source,
            target_language=target,
            was_pivoted=False,
            engine_name="MockSecTranslator",
        )
    def get_installation_instructions(self, pair): return "None"


def create_test_digital_pdf(file_path: Path, num_pages: int = 2) -> Path:
    """Creates a sample digital PDF with selectable text."""
    doc = fitz.open()
    for p in range(num_pages):
        page = doc.new_page(width=500, height=300)
        page.insert_text((40, 60), f"Digital Page {p + 1}: Selectable text for test extraction.")
    doc.save(str(file_path))
    doc.close()
    return file_path


def create_test_scanned_pdf(file_path: Path, num_pages: int = 2) -> Path:
    """Creates a sample scanned PDF without selectable text."""
    doc = fitz.open()
    for p in range(num_pages):
        img = Image.new("RGB", (500, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((30, 40), f"Scanned Document Page {p + 1}", fill=(0, 0, 0))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        page = doc.new_page(width=500, height=300)
        page.insert_image(page.rect, stream=img_bytes.getvalue())
    doc.save(str(file_path))
    doc.close()
    return file_path


def run_tests():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    test_dir = PROJECT_ROOT / "_test_sec_remed_scratch"
    test_dir.mkdir(exist_ok=True)

    print("\n" + "=" * 65)
    print("🔒 RUNNING 12 TARGETED SECURITY REMEDIATION TESTS")
    print("=" * 65)

    try:
        # =============================================================
        # Test 1: Digital PDF Extraction Regression
        # =============================================================
        print("\n[1/12] Digital PDF Extraction Regression...")
        dig_pdf = test_dir / "regress_digital.pdf"
        create_test_digital_pdf(dig_pdf, num_pages=2)
        res = extract_text_from_pdf(str(dig_pdf))
        assert res["success"] is True, "Digital extraction should succeed"
        assert res["page_count"] == 2, f"Expected 2 pages, got {res['page_count']}"
        assert "Digital Page 1" in res["full_text"], "Digital text should be preserved"
        print("  ✓ Digital PDF extraction functions correctly without regression.")

        # =============================================================
        # Test 2: Scanned PDF OCR Regression
        # =============================================================
        print("\n[2/12] Scanned PDF OCR Regression...")
        tess = TesseractEngine()
        if tess.is_available():
            test_img = Image.new("RGB", (400, 150), color=(255, 255, 255))
            draw = ImageDraw.Draw(test_img)
            draw.text((20, 30), "SECURITY AUDIT TEST", fill=(0, 0, 0))
            text, conf = tess.recognize_with_confidence(test_img, language="eng")
            assert "SECURITY" in text.upper(), f"Expected 'SECURITY' in OCR output, got '{text}'"
            assert conf > 0.0, "Expected positive confidence score"
            print(f"  ✓ OCR recognized '{text.strip()}' with confidence {conf}%.")
        else:
            print("  ✓ Tesseract engine gracefully detected as unavailable (skipped live OCR).")

        # =============================================================
        # Test 3: OCR Cancellation & Recovery File Deletion
        # =============================================================
        print("\n[3/12] OCR Cancellation & Recovery File Deletion...")
        sample_pdf = test_dir / "ocr_cancel_test.pdf"
        create_test_scanned_pdf(sample_pdf, num_pages=4)
        rec_path = get_recovery_file_path(str(sample_pdf))

        # Simulate checkpoint creation
        save_recovery_checkpoint(rec_path, {
            "current_page": 1,
            "total_pages": 4,
            "completed_pages": [{"page_num": 1, "text": "Partial text"}],
        })
        assert os.path.isfile(rec_path), f"Checkpoint should exist at {rec_path}"

        # Run OCR worker and immediately cancel
        worker = OCRWorkerThread(pdf_path=str(sample_pdf), max_workers=1)
        worker.cancel()
        worker.start()
        worker.wait(5000)
        app.processEvents()

        assert not os.path.isfile(rec_path), (
            f"Security Violation: Recovery file {rec_path} was NOT deleted upon cancellation!"
        )
        print("  ✓ OCR cancellation cleanly deleted active recovery checkpoint.")

        # =============================================================
        # Test 4: Translation Cancellation & Recovery File Deletion
        # =============================================================
        print("\n[4/12] Translation Cancellation & Recovery File Deletion...")
        trans_pdf = test_dir / "trans_cancel_test.pdf"
        trans_rec_path = get_translation_recovery_path(str(trans_pdf))

        # Simulate translation recovery creation
        save_translation_recovery(trans_rec_path, {
            "current_page": 1,
            "total_pages": 3,
            "translated_pages": [{"page_num": 1, "translated_text": "अनुवाद"}],
        })
        assert os.path.isfile(trans_rec_path), "Translation recovery file should exist"

        pages_payload = [
            {"page_num": 1, "text": "Page one text"},
            {"page_num": 2, "text": "Page two text"},
            {"page_num": 3, "text": "Page three text"},
        ]
        trans_worker = TranslationWorkerThread(
            pages=pages_payload,
            source_lang="eng",
            target_lang="hin",
            translator=MockSecTranslator(),
            doc_id=str(trans_pdf),
        )
        trans_worker.cancel()
        trans_worker.start()
        trans_worker.wait(5000)
        app.processEvents()

        assert not os.path.isfile(trans_rec_path), (
            f"Security Violation: Translation recovery file {trans_rec_path} was NOT deleted upon cancellation!"
        )
        print("  ✓ Translation cancellation cleanly deleted active recovery checkpoint.")

        # =============================================================
        # Test 5: Document Removal While Processing & Recovery Cleanup
        # =============================================================
        print("\n[5/12] Document Removal While Processing & Recovery Cleanup...")
        main_win = MainWindow()
        doc_path = str(test_dir / "active_doc.pdf")
        main_win._current_pdf_path = doc_path

        # Create both OCR and translation checkpoints for this active document
        doc_ocr_rec = get_recovery_file_path(doc_path)
        doc_trans_rec = get_translation_recovery_path(doc_path)
        save_recovery_checkpoint(doc_ocr_rec, {"current_page": 2, "total_pages": 5, "completed_pages": [{"page_num": 1, "text": "Page 1"}]})
        save_translation_recovery(doc_trans_rec, {"current_page": 1, "total_pages": 5, "translated_pages": [{"page_num": 1, "translated_text": "Trans 1"}]})
        assert os.path.isfile(doc_ocr_rec), "OCR recovery file must exist"
        assert os.path.isfile(doc_trans_rec), "Translation recovery file must exist"

        # Calling clear_document must cancel workers and remove checkpoints
        main_win.clear_document()
        assert main_win._current_pdf_path == "", "Document path must be reset"
        assert not os.path.isfile(doc_ocr_rec), "OCR recovery file should be removed on clear_document"
        assert not os.path.isfile(doc_trans_rec), "Translation recovery file should be removed on clear_document"
        print("  ✓ clear_document() successfully wiped active document recovery checkpoints.")

        # =============================================================
        # Test 6: Application Close During Active Processing
        # =============================================================
        print("\n[6/12] Application Close During Active Processing...")
        main_win._current_pdf_path = doc_path
        save_recovery_checkpoint(doc_ocr_rec, {"current_page": 1, "total_pages": 3, "completed_pages": [{"page_num": 1, "text": "Text"}]})
        save_translation_recovery(doc_trans_rec, {"current_page": 1, "total_pages": 3, "translated_pages": [{"page_num": 1, "translated_text": "T1"}]})

        # Ensure no unsaved edits prevent closing
        main_win.preview_panel.mark_saved()

        close_evt = QCloseEvent()
        main_win.closeEvent(close_evt)

        assert close_evt.isAccepted(), "Close event should be accepted"
        assert not os.path.isfile(doc_ocr_rec), "OCR recovery file must be cleaned on closeEvent"
        assert not os.path.isfile(doc_trans_rec), "Translation recovery file must be cleaned on closeEvent"
        print("  ✓ closeEvent() cleanly shut down workers and wiped recovery checkpoints.")

        # =============================================================
        # Test 7: Declining Unsaved Edits Close Confirmation
        # =============================================================
        print("\n[7/12] Declining Unsaved Edits Close Confirmation...")
        main_win.preview_panel.text_editor.setPlainText("Unsaved edit text")
        assert main_win.preview_panel.has_unsaved_edits() is True, "Preview panel should have unsaved edits"

        close_evt_cancel = QCloseEvent()
        # Mock QMessageBox so user clicks 'Cancel' (not btn_discard)
        with patch.object(QMessageBox, "exec", return_value=0):
            with patch.object(QMessageBox, "clickedButton", return_value=None):
                main_win.closeEvent(close_evt_cancel)

        assert not close_evt_cancel.isAccepted(), "Close event MUST be ignored when user cancels"

        # Now test accepting discard
        close_evt_discard = QCloseEvent()
        original_init = QMessageBox.__init__

        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self._discard_btn = None
            orig_add = self.addButton

            def patched_add(text, role):
                btn = orig_add(text, role)
                if "Discard" in text:
                    self._discard_btn = btn
                return btn

            self.addButton = patched_add
            self.exec = lambda: 0
            self.clickedButton = lambda: self._discard_btn

        with patch.object(QMessageBox, "__init__", patched_init):
            main_win.closeEvent(close_evt_discard)

        assert close_evt_discard.isAccepted(), "Close event should be accepted when user discards"
        main_win.preview_panel.mark_saved()
        print("  ✓ User confirmation dialog on closeEvent accurately guards unsaved edits.")

        # =============================================================
        # Test 8: Temporary Image Cleanup After Subprocess Timeout
        # =============================================================
        print("\n[8/12] Temporary Image Cleanup After Subprocess Timeout...")
        tess = TesseractEngine()
        dummy_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        captured_temp_files = []

        orig_sub_run = subprocess.run

        def mock_timeout_run(cmd, *args, **kwargs):
            if any(arg in cmd for arg in ("--version", "--list-langs")):
                return orig_sub_run(cmd, *args, **kwargs)
            # cmd[1] is the temporary image path
            img_path = cmd[1]
            captured_temp_files.append(img_path)
            assert os.path.isfile(img_path), f"Temp file {img_path} should exist when subprocess is called"
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

        # Test Tesseract timeout cleanup (force fallback CLI branch)
        with patch("ocr.tesseract_engine._PYTESSERACT_AVAILABLE", False):
            with patch("subprocess.run", side_effect=mock_timeout_run):
                try:
                    tess.recognize_with_confidence(dummy_img, language="eng")
                except OCRError as err:
                    assert "timed out" in str(err).lower() or "error" in str(err).lower()

        assert len(captured_temp_files) >= 1, "Should have attempted subprocess execution"
        tess_temp_file = captured_temp_files[0]
        assert not os.path.isfile(tess_temp_file), (
            f"Security Leak: Temporary image {tess_temp_file} leaked after Subprocess Timeout!"
        )

        # Test language detector OSD timeout cleanup
        captured_osd_files = []
        def mock_osd_timeout(cmd, *args, **kwargs):
            if any(arg in cmd for arg in ("--version", "--list-langs")):
                return orig_sub_run(cmd, *args, **kwargs)
            img_path = cmd[1]
            captured_osd_files.append(img_path)
            assert os.path.isfile(img_path), f"OSD temp file {img_path} should exist"
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

        with patch("subprocess.run", side_effect=mock_osd_timeout):
            script = detect_script_from_scanned_page(dummy_img, tesseract_cmd="/usr/bin/tesseract")
            assert script == "Latin", "Should fall back to Latin on timeout"

        assert len(captured_osd_files) >= 1
        osd_temp_file = captured_osd_files[0]
        assert not os.path.isfile(osd_temp_file), (
            f"Security Leak: OSD Temporary image {osd_temp_file} leaked after Subprocess Timeout!"
        )
        print("  ✓ Temporary image files strictly removed even on subprocess.TimeoutExpired.")

        # =============================================================
        # Test 9: Temporary Image Cleanup After Unexpected Exception
        # =============================================================
        print("\n[9/12] Temporary Image Cleanup After Unexpected Exception...")
        captured_exc_files = []
        def mock_crash_run(cmd, *args, **kwargs):
            if any(arg in cmd for arg in ("--version", "--list-langs")):
                return orig_sub_run(cmd, *args, **kwargs)
            img_path = cmd[1]
            captured_exc_files.append(img_path)
            raise RuntimeError("Simulated unexpected OS kernel fault")

        with patch("ocr.tesseract_engine._PYTESSERACT_AVAILABLE", False):
            with patch("subprocess.run", side_effect=mock_crash_run):
                try:
                    tess.recognize_with_confidence(dummy_img, language="eng")
                except OCRError:
                    pass

        assert len(captured_exc_files) >= 1
        crash_temp_file = captured_exc_files[0]
        assert not os.path.isfile(crash_temp_file), (
            f"Security Leak: Temporary image {crash_temp_file} leaked after unexpected exception!"
        )
        print("  ✓ Temporary image files strictly removed via try/finally on unexpected exceptions.")

        # =============================================================
        # Test 10: Git Ignore Rules For Document and Image Extensions
        # =============================================================
        print("\n[10/12] Git Ignore Rules For Document and Image Extensions...")
        # Test items that MUST be ignored at root
        must_ignore = [
            "sample.pdf",
            "contract.docx",
            "notes.txt",
            "photo.png",
            "scan.jpg",
            "figure.jpeg",
            "banner.webp",
            "diagram.tiff",
            "raw.bmp",
            "data.tmp",
            ".recovery_ocr_123.json",
            ".recovery_trans_456.json",
            "doc.recovery.json",
        ]

        for item in must_ignore:
            res = subprocess.run(
                ["git", "check-ignore", "-v", item],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"Git should ignore '{item}', but check-ignore returned {res.returncode}"

        # Test items that MUST NOT be ignored
        must_not_ignore = [
            "requirements.txt",
            "assets/icons/chevron_down.svg",
            "ocr/ocr_pipeline.py",
        ]
        for item in must_not_ignore:
            res = subprocess.run(
                ["git", "check-ignore", "-v", item],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
            )
            assert res.returncode == 1, f"Git should NOT ignore '{item}', but it was ignored: {res.stdout}"

        print("  ✓ Git ignore rules strictly protect root documents/images while preserving assets.")

        # =============================================================
        # Test 11: Gemini API Key Redaction In Simulated Network Exceptions
        # =============================================================
        print("\n[11/12] Gemini API Key Redaction In Simulated Network Exceptions...")
        secret_key = "AIzaSyTestSecretKey_1234567890abcdef"
        gemini = GeminiProvider(api_key=secret_key)

        # Test 11a: Direct sanitizer unit test
        raw_err_with_query = f"urllib.error.HTTPError: HTTP 403 Forbidden: https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={secret_key}"
        sanitized = gemini._sanitize_error(raw_err_with_query)
        assert secret_key not in sanitized, "Secret key was not redacted from query string"
        assert "[REDACTED_KEY]" in sanitized, "Expected [REDACTED_KEY] in sanitized string"

        raw_err_with_token = f"Bad request: API key {secret_key} was rejected."
        sanitized_tok = gemini._sanitize_error(raw_err_with_token)
        assert secret_key not in sanitized_tok, "Secret key was not redacted from body text"
        assert "[REDACTED_KEY]" in sanitized_tok

        # Test 11b: enhance_text exception handling
        def mock_gemini_urlopen(req, *args, **kwargs):
            raise io.BytesIO(b"dummy") # trigger exception

        with patch("urllib.request.urlopen", side_effect=Exception(f"Failed to connect: ?key={secret_key}")):
            try:
                gemini.enhance_text("Test document content")
                assert False, "Should have raised AIProviderError"
            except AIProviderError as err:
                err_str = str(err)
                assert secret_key not in err_str, f"Security Leak: Raw API key found in exception: {err_str}"
                assert "[REDACTED_KEY]" in err_str, f"Expected [REDACTED_KEY] placeholder in exception: {err_str}"

        # Test 11c: OpenAI provider sanitization
        openai_key = "sk-test-openai-secret-key-1234567890"
        openai_prov = OpenAIProvider(api_key=openai_key)
        with patch("urllib.request.urlopen", side_effect=Exception(f"Connection error sk-test-openai-secret-key-1234567890")):
            try:
                openai_prov.enhance_text("Test text")
                assert False, "Should have raised AIProviderError"
            except AIProviderError as err:
                err_str = str(err)
                assert openai_key not in err_str
                assert "[REDACTED_KEY]" in err_str

        print("  ✓ API keys strictly sanitized and replaced with [REDACTED_KEY] in all provider errors.")

        # =============================================================
        # Test 12: Streamlit Telemetry Configuration Verification
        # =============================================================
        print("\n[12/12] Streamlit Telemetry Configuration Verification...")
        config_path = PROJECT_ROOT / ".streamlit" / "config.toml"
        assert config_path.is_file(), f"Expected config file at {config_path}"

        content = config_path.read_text(encoding="utf-8")
        assert "[browser]" in content, "Expected [browser] section in config.toml"
        assert "gatherUsageStats = false" in content, (
            f"Expected gatherUsageStats = false in config.toml, found:\n{content}"
        )
        print("  ✓ .streamlit/config.toml verified: gatherUsageStats is strictly false.")

        print("\n" + "=" * 65)
        print("🎉 ALL 12 TARGETED SECURITY REMEDIATION TESTS PASSED!")
        print("=" * 65 + "\n")

    finally:
        # Cleanup scratch test files
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    run_tests()
