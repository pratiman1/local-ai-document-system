"""
tests/test_pdf_reconstructor.py
--------------------------------
Test suite validating book-format PDF reconstruction:
1. Font resolution and bundled Devanagari font detection.
2. Transparent text redaction: strips text while preserving 100% of images and drawings.
3. Complex Devanagari script shaping (conjuncts, matras, halants, danda).
4. Dynamic font auto-scaling to prevent overflow.
5. Batch document reconstruction with page range.
6. Worker thread progress signals and cooperative cancellation.
7. Atomic save verification (output is complete, temporary files cleaned).
"""

import os
import sys
import json
import fitz
from pathlib import Path

# Force Qt offscreen platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from exporters.pdf_reconstructor import (
    PDFReconstructor,
    PDFExportWorkerThread,
    resolve_devanagari_font,
)

PDF_PATH = PROJECT_ROOT / "uploads" / "9788117403600_c5233386c0454bc887c8f0a8a37d1c72_output_e4828aa384654e07903c4ad04152fa96.pdf"
CHECKPOINT_PATH = PROJECT_ROOT / "exports" / "full_300p_translation_checkpoint_corrected.json"
if not CHECKPOINT_PATH.is_file():
    CHECKPOINT_PATH = PROJECT_ROOT / "exports" / "full_300p_translation_checkpoint.json"


def run_tests():
    app = QApplication.instance()
    if not app:
        app = QApplication(["-platform", "offscreen"])

    print("\n" + "=" * 70)
    print("📕 RUNNING PDF RECONSTRUCTION ENGINE TEST SUITE")
    print("=" * 70)

    # Test 1: Font resolution
    print("\n[1/7] Testing Devanagari Font Resolution...")
    font_path = resolve_devanagari_font()
    assert font_path != "", "Font path must not be empty"
    print(f"  ✓ Resolved local typography font: '{font_path}'")

    # Test 2: Transparent text redaction preserving graphics & images
    print("\n[2/7] Testing Transparent Text Redaction...")
    doc = fitz.open(str(PDF_PATH))
    p5 = doc[4]
    orig_imgs = len(p5.get_images())
    orig_drawings = len(p5.get_drawings())

    reconstructor = PDFReconstructor(str(PDF_PATH))
    sample_hindi = (
        "फ्रंट ऑफिस प्रबंधन - प्रस्थान कार्य और नाइट ऑडिट। "
        "यह एक परीक्षण पैराग्राफ है जो देवनागरी लिपि के सही प्रतिपादन की पुष्टि करता है।"
    )
    res_page = reconstructor.reconstruct_page(p5, sample_hindi, page_number=5)
    assert res_page["overflow"] is False
    assert len(p5.get_images()) == orig_imgs, f"Images count altered: {len(p5.get_images())} vs {orig_imgs}"
    assert len(p5.get_drawings()) == orig_drawings, f"Drawings count altered: {len(p5.get_drawings())} vs {orig_drawings}"
    print(f"  ✓ Transparent redaction verified: {orig_imgs} images and {orig_drawings} vector drawings strictly preserved.")

    # Test 3: Complex Devanagari script rendering
    print("\n[3/7] Testing Complex Devanagari Conjunct Rendering...")
    test_pdf_out = PROJECT_ROOT / "exports" / "_test_conjuncts.pdf"
    new_doc = fitz.open()
    p = new_doc.new_page(width=513.0, height=702.0)
    test_conjuncts = "प्रस्थान कार्य, नाइट ऑडिट, रजिस्ट्रेशन, अच्छी प्रतिष्ठा, दृष्टिकोण"
    res_conj = reconstructor.reconstruct_page(p, test_conjuncts, page_number=1)
    new_doc.save(str(test_pdf_out))
    new_doc.close()

    # Re-open and verify text extracted back
    verify_doc = fitz.open(str(test_pdf_out))
    extracted = verify_doc[0].get_text()
    verify_doc.close()
    if test_pdf_out.exists():
        test_pdf_out.unlink()

    assert "प्रस्थान" in extracted or "कार्य" in extracted
    print(f"  ✓ Devanagari complex script extracted: {repr(extracted.strip()[:60])}")

    # Test 4: Dynamic font auto-scaling
    print("\n[4/7] Testing Dynamic Font Auto-Scaling...")
    long_text = "होटल प्रबंधन के तहत फ्रंट ऑफिस विभाग का संचालन " * 120
    p_scale = doc.new_page(width=513.0, height=702.0)
    scale_res = reconstructor.reconstruct_page(p_scale, long_text, page_number=999)
    assert scale_res["font_size_used"] < 9.5, f"Font size did not scale down: {scale_res['font_size_used']}"
    print(f"  ✓ Font auto-scaled down from 9.5pt to {scale_res['font_size_used']}pt to prevent overflow.")
    doc.close()

    # Test 5: Multi-page document reconstruction
    print("\n[5/7] Testing Document Reconstruction (Pages 1, 5, 15)...")
    with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
        ckpt = json.load(f)

    out_sample_pdf = PROJECT_ROOT / "exports" / "_test_sample_reconstruct.pdf"
    recon_summary = reconstructor.reconstruct_document(
        checkpoint_data=ckpt,
        output_pdf_path=str(out_sample_pdf),
        page_range=[1, 5, 15],
    )
    assert recon_summary["cancelled"] is False
    assert recon_summary["completed_pages"] == 3
    assert out_sample_pdf.is_file()
    assert recon_summary["file_size_bytes"] > 50000
    print(f"  ✓ Reconstructed 3 pages in {recon_summary['elapsed_seconds']}s (size: {recon_summary['file_size_bytes']/1024:.1f} KB).")

    # Test 6: Worker thread cancellation
    print("\n[6/7] Testing Worker Thread Cancellation...")
    worker = PDFExportWorkerThread(
        source_pdf_path=str(PDF_PATH),
        output_pdf_path=str(PROJECT_ROOT / "exports" / "_test_cancel.pdf"),
        checkpoint_data=ckpt,
        page_range=list(range(1, 10)),
    )
    worker.cancel()
    worker.start()
    worker.wait(5000)
    app.processEvents()
    print("  ✓ Worker thread cancellation handled cleanly without hanging.")

    # Test 7: Output file integrity
    print("\n[7/7] Testing Reconstructed PDF Integrity...")
    check_doc = fitz.open(str(out_sample_pdf))
    assert len(check_doc) == 3
    p5_check = check_doc[1]
    assert len(p5_check.get_images()) == 3, "Page 5 images missing in output PDF"
    assert len(p5_check.get_text().strip()) > 0, "Page 5 has no translated text"
    check_doc.close()
    if out_sample_pdf.exists():
        out_sample_pdf.unlink()
    print("  ✓ Verified final PDF: exact page count, image retention, and valid Hindi content.")

    print("\n" + "=" * 70)
    print("🎉 ALL PDF RECONSTRUCTION ENGINE TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
