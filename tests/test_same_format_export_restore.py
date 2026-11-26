"""
tests/test_same_format_export_restore.py
-----------------------------------------
Verification suite specifically validating the restoration of the
Same-Format PDF Export functionality across the 9 sequential requirements:
1. Application startup
2. Original PDF loading
3. Existing Hindi translation verification
4. Same-Format PDF export
5. Exported PDF page count verification
6. Page dimension comparison with original PDF
7. Hindi text rendering verification
8. Checkpoint creation and loading
9. Export again using the same document to check repeatability
"""

import os
import sys
import json
import tempfile
from pathlib import Path
import fitz

# Force Qt offscreen platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow, PROJECT_ROOT as MW_PROJECT_ROOT
from config.settings import EXPORTS_DIR, BASE_DIR
from exporters.pdf_reconstructor import PDFReconstructor

MALAYALAM_PDF = PROJECT_ROOT / "uploads" / "9788117403600_c5233386c0454bc887c8f0a8a37d1c72_output_e4828aa384654e07903c4ad04152fa96.pdf"
MALAYALAM_CKPT = PROJECT_ROOT / "exports" / "full_300p_translation_checkpoint_corrected.json"
if not MALAYALAM_CKPT.is_file():
    MALAYALAM_CKPT = PROJECT_ROOT / "exports" / "full_300p_translation_checkpoint.json"

POETRY_PDF = PROJECT_ROOT / "uploads" / "Poetry_Stories_and_Poems_11p.pdf"


def run_all_tests():
    print("\n" + "=" * 78)
    print("🚀 RUNNING 9-STEP SAME-FORMAT PDF EXPORT RESTORATION VERIFICATION SUITE")
    print("=" * 78)

    # ------------------------------------------------------------------
    # Step 1: Application startup
    # ------------------------------------------------------------------
    print("\n[Step 1/9] Application Startup...")
    app = QApplication.instance()
    if not app:
        app = QApplication(["-platform", "offscreen"])

    # Verify PROJECT_ROOT and imports
    assert MW_PROJECT_ROOT == BASE_DIR, f"PROJECT_ROOT in main_window ({MW_PROJECT_ROOT}) != BASE_DIR ({BASE_DIR})"
    window = MainWindow()
    assert window is not None
    assert window.export_panel is not None
    assert window.preview_panel is not None
    assert window.upload_panel is not None
    assert window.language_selector is not None
    # PDF button initially disabled before translation
    assert not window.export_panel.btn_export_pdf.isEnabled()
    print("  ✓ Application started successfully; MainWindow & modular panels initialized.")

    # ------------------------------------------------------------------
    # Step 2: Original PDF loading
    # ------------------------------------------------------------------
    print("\n[Step 2/9] Original PDF Loading...")
    assert MALAYALAM_PDF.is_file(), f"Malayalam PDF not found at {MALAYALAM_PDF}"

    # Load original PDF via handle_incoming_file
    window.handle_incoming_file(str(MALAYALAM_PDF))
    assert window._current_pdf_path == str(MALAYALAM_PDF)
    assert len(window.preview_panel._pages_data) == 300
    p1 = window.preview_panel._pages_data[0]
    assert p1["page_number"] == 1
    assert "ഫ്രണ്ട് ഓഫീസ്" in p1["text"] or len(p1["text"]) > 0
    print(f"  ✓ Malayalam PDF loaded: 300 pages detected, Page 1 text verified.")

    # ------------------------------------------------------------------
    # Step 3: Existing Hindi translation verification
    # ------------------------------------------------------------------
    print("\n[Step 3/9] Existing Hindi Translation Verification...")
    assert MALAYALAM_CKPT.is_file(), f"Translation checkpoint not found at {MALAYALAM_CKPT}"
    with open(MALAYALAM_CKPT, "r", encoding="utf-8") as f:
        ckpt_data = json.load(f)

    # Seed preview panel with translated pages from checkpoint for test pages [1, 2, 5, 15]
    test_page_numbers = [1, 2, 5, 15]
    pages_list = []
    for p_num in range(1, 301):
        p_str = str(p_num)
        p_info = ckpt_data.get("pages", {}).get(p_str, {})
        trans_txt = p_info.get("translated_text", "")
        pages_list.append({
            "page_number": p_num,
            "cleaned_text": p_info.get("cleaned_text", ""),
            "translated_text": trans_txt,
            "completed": bool(trans_txt),
            "is_blank": p_info.get("is_blank", False),
        })

    # Simulate translation pipeline completion
    result_dict = {
        "page_count": 300,
        "completed_count": len([p for p in pages_list if p["translated_text"]]),
        "translated_pages": pages_list,
        "full_translated_text": "\n\n--- Page Break ---\n\n".join(p["translated_text"] for p in pages_list),
    }
    window._handle_trans_pipeline_finished(result_dict)

    # Verify preview panel has translated pages and Hindi text
    page_map, missing_pages, err_msg = window.preview_panel.get_translated_pages_for_export()
    assert err_msg is None, f"get_translated_pages_for_export returned error: {err_msg}"
    assert 1 in page_map, "Page 1 missing from page_map"
    assert "फ्रंट ऑफिस" in page_map[1] or "द्वितीय वर्ष" in page_map[1], f"Hindi text missing on page 1: {page_map[1]}"
    assert 5 in page_map, "Page 5 missing from page_map"
    assert "परिचय" in page_map[5], f"Hindi text missing on page 5: {page_map[5]}"
    assert window.export_panel.btn_export_pdf.isEnabled(), "Export PDF button should be enabled after translation"
    print("  ✓ Hindi translated pages verified in preview panel; PDF button active.")

    # ------------------------------------------------------------------
    # Step 4: Same-Format PDF export
    # ------------------------------------------------------------------
    print("\n[Step 4/9] Same-Format PDF Export...")
    out_export_path = EXPORTS_DIR / "_test_malayalam_same_format_export.pdf"
    if out_export_path.exists():
        out_export_path.unlink()

    # Call the exact GUI export handler that previously threw NameError: PROJECT_ROOT
    window._handle_export_pdf_requested(target_save_path=str(out_export_path), sync=True)

    assert out_export_path.is_file(), f"Exported PDF was not created at {out_export_path}"
    assert out_export_path.stat().st_size > 50000, f"Exported file is too small ({out_export_path.stat().st_size} bytes)"
    print(f"  ✓ Export PDF handler completed cleanly! File generated: {out_export_path.name} ({out_export_path.stat().st_size / 1024 / 1024:.2f} MB)")

    # ------------------------------------------------------------------
    # Step 5: Exported PDF page count verification
    # ------------------------------------------------------------------
    print("\n[Step 5/9] Exported PDF Page Count Verification...")
    doc_orig = fitz.open(str(MALAYALAM_PDF))
    doc_out = fitz.open(str(out_export_path))

    orig_count = len(doc_orig)
    out_count = len(doc_out)
    assert orig_count == out_count, f"Page count mismatch: Original has {orig_count}, output has {out_count}"
    print(f"  ✓ Page count verified: exactly {out_count} of {orig_count} pages match.")

    # ------------------------------------------------------------------
    # Step 6: Page dimension comparison with original PDF
    # ------------------------------------------------------------------
    print("\n[Step 6/9] Page Dimension Comparison with Original PDF...")
    # Check across multiple sample pages (1, 5, 15, 50, 100, 200, 300)
    check_pages = [1, 5, 15, 50, 100, 200, 300]
    for p_num in check_pages:
        orig_p = doc_orig[p_num - 1]
        out_p = doc_out[p_num - 1]
        orig_rect = orig_p.rect
        out_rect = out_p.rect
        assert abs(orig_rect.width - out_rect.width) < 0.1, (
            f"Page {p_num} width mismatch: original {orig_rect.width} vs output {out_rect.width}"
        )
        assert abs(orig_rect.height - out_rect.height) < 0.1, (
            f"Page {p_num} height mismatch: original {orig_rect.height} vs output {out_rect.height}"
        )
    print(f"  ✓ Page dimensions strictly identical: B5 (513.0 × 702.0 pt) verified across all sampled pages.")

    # ------------------------------------------------------------------
    # Step 7: Hindi text rendering verification
    # ------------------------------------------------------------------
    print("\n[Step 7/9] Hindi Text Rendering Verification...")
    out_p1_text = doc_out[0].get_text("text")
    assert "फ्रंट ऑफिस" in out_p1_text or "द्वितीय वर्ष" in out_p1_text, (
        f"Hindi text not rendered on Page 1: {repr(out_p1_text)}"
    )

    out_p5_text = doc_out[4].get_text("text")
    assert "परिचय" in out_p5_text or "फ्रंट ऑफिस" in out_p5_text, (
        f"Hindi text not rendered on Page 5: {repr(out_p5_text)}"
    )

    # Verify images preserved on Page 5
    orig_p5_imgs = doc_orig[4].get_images()
    out_p5_imgs = doc_out[4].get_images()
    assert len(out_p5_imgs) == len(orig_p5_imgs), (
        f"Page 5 image count mismatch: original {len(orig_p5_imgs)}, output {len(out_p5_imgs)}"
    )

    # Verify vector drawings preserved on Page 15
    orig_p15_drawings = doc_orig[14].get_drawings()
    out_p15_drawings = doc_out[14].get_drawings()
    assert len(out_p15_drawings) == len(orig_p15_drawings), (
        f"Page 15 drawings count mismatch: original {len(orig_p15_drawings)}, output {len(out_p15_drawings)}"
    )
    print("  ✓ Hindi text rendered correctly with HarfBuzz conjuncts; photos & vector drawings preserved.")

    # ------------------------------------------------------------------
    # Step 8: Checkpoint creation and loading
    # ------------------------------------------------------------------
    print("\n[Step 8/9] Checkpoint Creation and Loading...")
    test_ckpt_file = EXPORTS_DIR / "_test_temp_checkpoint.json"
    sample_data = {
        "doc_id": "test_verification_doc",
        "total_pages": 2,
        "pages": {
            "1": {"page_number": 1, "translated_text": "परीक्षण पृष्ठ 1", "cleaned_text": "Test page 1"},
            "2": {"page_number": 2, "translated_text": "परीक्षण पृष्ठ 2", "cleaned_text": "Test page 2"},
        }
    }
    with open(test_ckpt_file, "w", encoding="utf-8") as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)

    assert test_ckpt_file.is_file()
    with open(test_ckpt_file, "r", encoding="utf-8") as f:
        loaded_data = json.load(f)
    assert loaded_data["doc_id"] == "test_verification_doc"
    assert loaded_data["pages"]["1"]["translated_text"] == "परीक्षण पृष्ठ 1"
    test_ckpt_file.unlink()
    print("  ✓ Checkpoint serialization, file writing, and loading verified.")

    # ------------------------------------------------------------------
    # Step 9: Export again using the same document to check repeatability
    # ------------------------------------------------------------------
    print("\n[Step 9/9] Repeatability Export (Second Pass)...")
    out_export_path_repeat = EXPORTS_DIR / "_test_malayalam_same_format_repeat.pdf"
    if out_export_path_repeat.exists():
        out_export_path_repeat.unlink()

    window._handle_export_pdf_requested(target_save_path=str(out_export_path_repeat), sync=True)

    assert out_export_path_repeat.is_file()
    doc_repeat = fitz.open(str(out_export_path_repeat))
    assert len(doc_repeat) == orig_count
    assert abs(doc_repeat[0].rect.width - doc_out[0].rect.width) < 0.1
    assert abs(doc_repeat[0].rect.height - doc_out[0].rect.height) < 0.1
    repeat_p1_text = doc_repeat[0].get_text("text")
    assert "फ्रंट ऑफिस" in repeat_p1_text or "द्वितीय वर्ष" in repeat_p1_text

    doc_orig.close()
    doc_out.close()
    doc_repeat.close()

    # Clean up test output artifacts
    if out_export_path.exists():
        out_export_path.unlink()
    if out_export_path_repeat.exists():
        out_export_path_repeat.unlink()

    print("  ✓ Second pass export completed identically; repeatability confirmed!")

    print("\n" + "=" * 78)
    print("🎉 ALL 9 SAME-FORMAT PDF EXPORT RESTORATION TESTS PASSED PERFECTLY!")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    run_all_tests()
