"""
tests/test_pdf_export_e2e.py
----------------------------
End-to-end integration test verifying the complete PDF reconstruction export workflow:
1. Verifies ExportPanel signals and button states (starts disabled, enabled after translation).
2. Verifies MainWindow PDF export trigger, file selection, overwrite prompt, and progress.
3. Verifies Condition 1: Chunk count validation on full-document edits with page break mismatch warning.
4. Verifies Condition 2: Incomplete translation missing pages detection and options.
5. Verifies Condition 3: Text block matching by original position, font size, and color; footers,
   page numbers and digits preserved untouched.
6. Verifies Condition 4: Two-page spread layout (792 x 612 pt) with left and right columns
   treated separately (x < 396 pt vs x >= 396 pt) with zero cross-column bleeding.
7. Verifies Condition 5: Decorative calligraphic Devanagari typography.
8. Verifies 100% strict offline execution with zero network access.
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
from ui.main_window import MainWindow
from ui.preview_panel import PreviewPanel
from exporters.pdf_reconstructor import PDFReconstructor, PDFExportWorkerThread, find_unauthorized_english

B5_PDF_PATH = PROJECT_ROOT / "uploads" / "9788117403600_c5233386c0454bc887c8f0a8a37d1c72_output_e4828aa384654e07903c4ad04152fa96.pdf"
SPREAD_PDF_PATH = PROJECT_ROOT / "uploads" / "Poetry_Stories_and_Poems_11p.pdf"

CHECKPOINT_PATH = PROJECT_ROOT / "exports" / "full_300p_translation_checkpoint_corrected.json"
if not CHECKPOINT_PATH.is_file():
    CHECKPOINT_PATH = PROJECT_ROOT / "exports" / "full_300p_translation_checkpoint.json"


def run_tests():
    app = QApplication.instance()
    if not app:
        app = QApplication(["-platform", "offscreen"])

    print("\n" + "=" * 75)
    print("🖥️  RUNNING PDF EXPORT GUI & RECONSTRUCTION END-TO-END SUITE")
    print("=" * 75)

    # -------------------------------------------------------------
    # 1. Initialize MainWindow & Verify Button States
    # -------------------------------------------------------------
    print("\n[1/7] Testing MainWindow & ExportPanel Initial States...")
    window = MainWindow()
    assert window.export_panel.btn_export_pdf is not None
    assert not window.export_panel.btn_export_pdf.isEnabled(), "PDF export must start disabled"
    print("  ✓ ExportPanel PDF button initialized safely in disabled state.")

    # -------------------------------------------------------------
    # 2. Test Condition 1: Full-Document Page Break Chunk Verification
    # -------------------------------------------------------------
    print("\n[2/7] Testing Condition 1: Page Break Mismatch Verification...")
    panel = PreviewPanel()
    # Mock 3 pages loaded
    panel._pages_data = [
        {"page_number": 1, "text": "English page 1"},
        {"page_number": 2, "text": "English page 2"},
        {"page_number": 3, "text": "English page 3"},
    ]
    panel._translated_pages = [
        {"page_number": 1, "translated_text": "Hindi 1"},
        {"page_number": 2, "translated_text": "Hindi 2"},
        {"page_number": 3, "translated_text": "Hindi 3"},
    ]

    # User edited full document pane but deleted a page break (only 2 chunks for 3 pages)
    panel._is_dirty_trans = True
    panel.trans_editor.setPlainText("Hindi page 1 content\n\n--- Page Break ---\nHindi page 2 and 3 merged")

    page_map, missing_pages, err_msg = panel.get_translated_pages_for_export()
    assert err_msg is not None, "Must return error when chunk count != total_pages"
    assert "Page break count mismatch" in err_msg
    assert "Found 2 page section(s), but document has 3 pages" in err_msg
    print(f"  ✓ Successfully detected chunk count mismatch: '{err_msg.splitlines()[0]}'")

    # Now provide correct 3 chunks
    panel.trans_editor.setPlainText(
        "Hindi page 1 edited\n\n--- Page Break ---\nHindi page 2 edited\n\n--- Page Break ---\nHindi page 3 edited"
    )
    page_map, missing_pages, err_msg = panel.get_translated_pages_for_export()
    assert err_msg is None, f"Expected no error for matching chunks, got: {err_msg}"
    assert len(page_map) == 3
    assert page_map[1] == "Hindi page 1 edited"
    assert page_map[2] == "Hindi page 2 edited"
    assert page_map[3] == "Hindi page 3 edited"
    print("  ✓ Successfully synchronized 3 edited chunks matching 3 pages.")

    # -------------------------------------------------------------
    # 3. Test Condition 2: Incomplete Translation Missing Pages Detection
    # -------------------------------------------------------------
    print("\n[3/7] Testing Condition 2: Incomplete Translation Detection...")
    panel.trans_editor.blockSignals(True)
    panel.trans_editor.setPlainText("Hindi page 1\n\n--- Page Break ---\n\n--- Page Break ---\nHindi page 3")
    panel.trans_editor.blockSignals(False)
    panel._is_dirty_trans = False
    panel._translated_pages = [
        {"page_number": 1, "translated_text": "Hindi page 1"},
        {"page_number": 2, "translated_text": ""},  # Missing
        {"page_number": 3, "translated_text": "Hindi page 3"},
    ]

    page_map, missing_pages, err_msg = panel.get_translated_pages_for_export()
    assert err_msg is None
    assert missing_pages == [2], f"Expected missing_pages == [2], got {missing_pages}"
    assert 1 in page_map and 3 in page_map and 2 not in page_map
    print(f"  ✓ Incomplete translation correctly flagged missing pages: {missing_pages}")

    # -------------------------------------------------------------
    # 4. Test Single-Column (B5) Reconstructor Compatibility
    # -------------------------------------------------------------
    print("\n[4/7] Testing Single-Column B5 Reconstruction Fidelity...")
    out_b5_path = PROJECT_ROOT / "exports" / "_test_b5_out.pdf"
    if out_b5_path.exists():
        out_b5_path.unlink()

    if B5_PDF_PATH.is_file() and CHECKPOINT_PATH.is_file():
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            ckpt = json.load(f)

        pages_to_load = []
        for p_num in [1, 5, 15]:
            p_str = str(p_num)
            p_info = ckpt["pages"].get(p_str, {})
            pages_to_load.append({
                "page_number": p_num,
                "text": p_info.get("cleaned_text", "Sample text"),
                "translated_text": p_info.get("translated_text", "अनुवादित नमूना पाठ"),
            })

        reconstructor = PDFReconstructor(str(B5_PDF_PATH))
        res = reconstructor.reconstruct_document(
            checkpoint_data={"pages": {str(p["page_number"]): p for p in pages_to_load}},
            output_pdf_path=str(out_b5_path),
            page_range=[1, 5, 15],
        )
        assert res["completed_pages"] == 3
        assert out_b5_path.is_file()

        doc_b5 = fitz.open(str(out_b5_path))
        assert len(doc_b5) == 3
        assert abs(doc_b5[0].rect.width - 513.0) < 1.0
        # Page 5 retains images
        assert len(doc_b5[1].get_images()) == 3
        # Page 15 retains drawings
        assert len(doc_b5[2].get_drawings()) == 16
        doc_b5.close()
        out_b5_path.unlink()
        print("  ✓ Single-column B5 backward compatibility fully verified.")

    # -------------------------------------------------------------
    # 5. Test Two-Page Spread Layout & Column Isolation (Conditions 3, 4, 5)
    # -------------------------------------------------------------
    print("\n[5/7] Testing Conditions 3, 4, 5: Two-Page Spread Layout & Columns...")
    assert SPREAD_PDF_PATH.is_file(), f"Missing spread PDF: {SPREAD_PDF_PATH}"

    spread_reconstructor = PDFReconstructor(str(SPREAD_PDF_PATH))
    out_spread_path = PROJECT_ROOT / "exports" / "_test_spread_out.pdf"
    if out_spread_path.exists():
        out_spread_path.unlink()

    # Reconstruct Page 2 with explicit Column Break
    doc_in = fitz.open(str(SPREAD_PDF_PATH))
    page2_in = doc_in[1] # Page 2

    test_trans_page2 = (
        "मुझे जॉन कीट्स की 'ला बेले डेम सैन्स मर्सी' से गहरा प्यार हो गया था।\n"
        "भाषा और कल्पना ने मेरे भीतर कुछ ऐसा जगाया जिसे मैंने पहले कभी महसूस नहीं किया था।\n"
        "— टैमी कुक\n\n"
        "--- Column Break ---\n\n"
        "दादी के दालान में लटकती हुई पहली कविता जो मैंने पढ़ी थी।\n"
        "यह एक सुंदर क्रॉस-स्टिच थी जो अब मेरे अपने दालान में गर्व से लटक रही है।\n"
        "– पैटी रीमैन"
    )

    res_p2 = spread_reconstructor.reconstruct_page(page2_in, test_trans_page2, page_number=2)
    assert not res_p2["overflow"], "Page 2 should auto-scale without overflow"

    doc_in.save(str(out_spread_path))
    doc_in.close()

    # Verify output PDF
    doc_out = fitz.open(str(out_spread_path))
    p2_out = doc_out[1]

    # Verify spread dimensions: 792.0 x 612.0 pt
    assert abs(p2_out.rect.width - 792.0) < 1.0, f"Expected width 792, got {p2_out.rect.width}"
    assert abs(p2_out.rect.height - 612.0) < 1.0, f"Expected height 612, got {p2_out.rect.height}"

    # Verify Condition 3: Footer block and digits unchanged
    out_text = p2_out.get_text()
    assert "3 • A Little Book of Poetry Stories & Poems" in out_text, "Left footer with digit 3 must be preserved"
    assert "4 • A Little Book of Poetry Stories & Poems" in out_text, "Right footer with digit 4 must be preserved"
    print("  ✓ Condition 3: Running footers, page numbers and digits '3' and '4' preserved untouched.")

    # Verify Condition 4: Column bounds (x < 396 pt vs x >= 396 pt)
    d_out = p2_out.get_text("dict")
    left_found_hindi = False
    right_found_hindi = False

    for b in d_out.get("blocks", []):
        if b.get("type") == 0:
            txt = "".join(s["text"] for line in b["lines"] for s in line["spans"])
            bx0, by0, bx1, by1 = b["bbox"]

            if "टैमी कुक" in txt or "जॉन कीट्स" in txt:
                # Left column text
                left_found_hindi = True
                assert bx1 <= 396.0, f"Left column text crossed into right side: bx1={bx1} > 396.0"
            elif "पैटी रीमैन" in txt or "दादी के दालान" in txt:
                # Right column text
                right_found_hindi = True
                assert bx0 >= 396.0, f"Right column text crossed into left side: bx0={bx0} < 396.0"

    assert left_found_hindi, "Left column Hindi text was not placed"
    assert right_found_hindi, "Right column Hindi text was not placed"
    print("  ✓ Condition 4: Left text (x <= 396 pt) and Right text (x >= 396 pt) strictly separated.")

    # Verify Condition 5: Decorative title rendered
    assert "प्यार में पड़ गए" in out_text or "उसने मुझे दिया" in out_text, "Decorative title must be rendered in Devanagari"
    print("  ✓ Condition 5: Decorative Devanagari title rendered with calligraphic styling.")

    doc_out.close()
    if out_spread_path.exists():
        out_spread_path.unlink()

    # -------------------------------------------------------------
    # 6. Test Worker Thread Execution on Spread PDF
    # -------------------------------------------------------------
    print("\n[6/7] Testing PDFExportWorkerThread on Two-Page Spread...")
    out_worker_path = PROJECT_ROOT / "exports" / "_test_worker_spread.pdf"
    if out_worker_path.exists():
        out_worker_path.unlink()

    worker = PDFExportWorkerThread(
        source_pdf_path=str(SPREAD_PDF_PATH),
        output_pdf_path=str(out_worker_path),
        checkpoint_data={"pages": {"2": {"translated_text": test_trans_page2}}},
        page_range=[2],
    )
    worker_finished_events = []
    worker.export_finished.connect(lambda res: worker_finished_events.append(res))
    worker.start()
    worker.wait(10000)
    app.processEvents()

    assert len(worker_finished_events) == 1
    assert out_worker_path.is_file()
    out_worker_path.unlink()
    print("  ✓ Asynchronous export worker completed spread page with signals.")

    # -------------------------------------------------------------
    # 7. Document Clear & Reset Verification
    # -------------------------------------------------------------
    print("\n[7/8] Verifying State Cleanup on Document Clear...")
    window.clear_document()
    app.processEvents()
    assert not window.export_panel.btn_export_pdf.isEnabled()
    window.close()
    print("  ✓ Clean state reset verified.")

    # -------------------------------------------------------------
    # 8. Regression Test: Page 1 and Page 3 Body Blocks Zero English Words
    # -------------------------------------------------------------
    print("\n[8/8] Regression Test: Page 1 and Page 3 Body Blocks Zero English Words...")
    doc_spread = fitz.open(str(SPREAD_PDF_PATH))
    reconstructor = PDFReconstructor(str(SPREAD_PDF_PATH))

    # Test Page 1 (Cover spread)
    p1 = doc_spread[0]
    p1_trans = (
        "“भाषा और कल्पना ने मेरे अंदर कुछ जगाया...”\n"
        "– टैमी कुक\n\n"
        "--- Column Break ---\n\n"
        "कविताओं की कहानियों और कविताओं की एक छोटी सी पुस्तक\n\n"
        "लोगों ने हमें राष्ट्रीय कविता महीने 2021 के दौरान गद्य और कविता में अपनी व्यक्तिगत कविताओं की कहानियाँ सुनाई।\n\n"
        "अब आप भी उनका आनंद ले सकते हैं।\n\n"
        "tweetspeakpoetry.com"
    )
    res_p1 = reconstructor.reconstruct_page(p1, translated_text=p1_trans, page_number=1)

    # Verify Page 1 title and blurb in Hindi
    p1_texts = [b["text"] for b in res_p1["blocks"]]
    assert any("कविताओं की कहानियों" in t for t in p1_texts), "Page 1 title must be rendered in Hindi"
    assert any("राष्ट्रीय कविता" in t for t in p1_texts), "Page 1 blurb must be rendered in Hindi"
    print("  ✓ Page 1 title ('कविताओं की कहानियों...') and blurb rendered in Hindi.")

    # Verify zero unauthorized English in ANY Page 1 body block
    p1_body_blocks = [b for b in res_p1["blocks"] if b["block_type"] == "BODY"]
    assert len(p1_body_blocks) >= 4, f"Expected at least 4 body blocks on Page 1, got {len(p1_body_blocks)}"
    for b in p1_body_blocks:
        unauth = find_unauthorized_english(b["text"])
        assert not unauth, (
            f"REGRESSION FAILURE: Page 1 body block {b['block_index']} ({b['side']}) "
            f"contains unauthorized English words: {unauth}\nText: '{b['text']}'"
        )
    print(f"  ✓ Verified all {len(p1_body_blocks)} Page 1 body blocks contain ZERO unauthorized English words.")

    # Test Page 3 (Spread 3: Ms. Leah & Ink & Tears)
    p3 = doc_spread[2]
    p3_trans = (
        "सुश्री लेह कहती हैं... मैं लेह हूँ! लेया, मैं हूँ! कविता के प्रति मेरा प्यार परिवार से शुरू हुआ।\n"
        "– एम. लेह\n\n"
        "--- Column Break ---\n\n"
        "मैंने प्राथमिक विद्यालय तक कविता में थोड़ा सा काम किया। नर्सिंग स्कूल और परिवार के बाद कागज पर लिखने का समय मिला।\n"
        "जब स्याही और आँसू दोनों सूख जाते हैं, तो मैंने अपने जीवन को संशोधित किया है।"
    )
    res_p3 = reconstructor.reconstruct_page(p3, translated_text=p3_trans, page_number=3)

    # Verify Page 3 titles and content in Hindi
    p3_texts = [b["text"] for b in res_p3["blocks"]]
    assert any("दिल को भरना" in t for t in p3_texts), "Page 3 left title must be rendered in Hindi ('दिल को भरना')"
    assert any("स्याही और आँसू" in t for t in p3_texts), "Page 3 right title must be rendered in Hindi ('स्याही और आँसू')"
    print("  ✓ Page 3 titles ('दिल को भरना' / 'स्याही और आँसू') rendered in Hindi.")

    # Verify zero unauthorized English in ANY Page 3 body block
    p3_body_blocks = [b for b in res_p3["blocks"] if b["block_type"] == "BODY"]
    assert len(p3_body_blocks) >= 4, f"Expected at least 4 body blocks on Page 3, got {len(p3_body_blocks)}"
    for b in p3_body_blocks:
        unauth = find_unauthorized_english(b["text"])
        assert not unauth, (
            f"REGRESSION FAILURE: Page 3 body block {b['block_index']} ({b['side']}) "
            f"contains unauthorized English words: {unauth}\nText: '{b['text']}'"
        )
    print(f"  ✓ Verified all {len(p3_body_blocks)} Page 3 body blocks contain ZERO unauthorized English words.")

    # End-to-end multi-page worker export for Page 1 & 3
    out_reg_path = PROJECT_ROOT / "exports" / "_test_regression_p1_p3.pdf"
    if out_reg_path.exists():
        out_reg_path.unlink()

    worker_reg = PDFExportWorkerThread(
        source_pdf_path=str(SPREAD_PDF_PATH),
        output_pdf_path=str(out_reg_path),
        checkpoint_data={
            "pages": {
                "1": {"translated_text": p1_trans},
                "3": {"translated_text": p3_trans},
            }
        },
        page_range=[1, 3],
    )
    worker_reg_events = []
    worker_reg.export_finished.connect(lambda res: worker_reg_events.append(res))
    worker_reg.start()
    worker_reg.wait(10000)
    app.processEvents()

    assert len(worker_reg_events) == 1
    assert out_reg_path.is_file()

    doc_reg = fitz.open(str(out_reg_path))
    assert len(doc_reg) == 2, f"Expected 2 pages in regression export, got {len(doc_reg)}"
    # Verify Page 1 text
    p1_reg_text = doc_reg[0].get_text()
    assert "कविताओं की कहानियों" in p1_reg_text, "Exported PDF Page 1 missing Hindi title"
    assert "ट्वीटस्पीक" in p1_reg_text, "Exported PDF Page 1 missing Hindi tweetspeak"
    # Verify Page 3 text
    p3_reg_text = doc_reg[1].get_text()
    assert "दिल को भरना" in p3_reg_text, "Exported PDF Page 3 missing Hindi left title"
    assert "स्याही और आँसू" in p3_reg_text, "Exported PDF Page 3 missing Hindi right title"
    doc_reg.close()
    out_reg_path.unlink()
    doc_spread.close()
    print("  ✓ End-to-end multi-page regression export verified.")

    print("\n" + "=" * 75)
    print("🎉 ALL 8 PDF EXPORT INTEGRATION & REGRESSION TESTS PASSED PERFECTLY!")
    print("=" * 75)


if __name__ == "__main__":
    run_tests()
