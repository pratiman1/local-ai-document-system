"""
test_extractor.py
-----------------
Automated test script to verify that pdf_extractor.py works correctly.
It tests:
1. Valid multi-page PDF text extraction.
2. Accurate total page count.
3. Empty file error handling.
4. Corrupted file error handling.
5. Blank page / empty text detection.
"""

import sys
from pathlib import Path

# Add project root to sys.path so we can import from extractors
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pymupdf as fitz  # PyMuPDF
    from extractors.pdf_extractor import extract_text_from_pdf
except ImportError as e:
    print(f"❌ Dependency missing: {e}")
    print("Please install PyMuPDF first: pip install pymupdf")
    sys.exit(1)


def create_sample_pdf(num_pages: int = 2) -> bytes:
    """Creates a sample PDF in memory using PyMuPDF for testing."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        text = f"Sample document page {i + 1}.\nTesting local extraction on Mac M1."
        page.insert_text((50, 72), text)
    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


def test_valid_extraction():
    print("Running Test 1: Valid 2-page PDF text extraction...")
    sample_pdf = create_sample_pdf(num_pages=2)
    result = extract_text_from_pdf(sample_pdf)

    assert result["success"] is True, f"Extraction failed: {result['error']}"
    assert result["page_count"] == 2, f"Expected 2 pages, got {result['page_count']}"
    assert "page 1" in result["full_text"], "Text from page 1 missing"
    assert "page 2" in result["full_text"], "Text from page 2 missing"
    assert result["is_empty"] is False, "Document was falsely marked as empty"
    print("  ✅ Passed: Successfully extracted text and counted 2 pages.")


def test_empty_bytes():
    print("Running Test 2: Handling 0-byte empty file...")
    result = extract_text_from_pdf(b"")
    assert result["success"] is False, "Empty file should not succeed"
    assert "empty" in result["error"].lower(), "Expected error message about empty file"
    print("  ✅ Passed: Gracefully handled 0-byte input.")


def test_corrupted_file():
    print("Running Test 3: Handling corrupted/invalid file...")
    result = extract_text_from_pdf(b"This is completely invalid PDF data")
    assert result["success"] is False, "Corrupted data should not succeed"
    assert result["error"] is not None, "Error message should be populated"
    print("  ✅ Passed: Gracefully handled corrupted file.")


def test_blank_pdf():
    print("Running Test 4: Handling PDF with no text (blank pages)...")
    doc = fitz.open()
    doc.new_page()  # Blank page with no text
    blank_bytes = doc.write()
    doc.close()

    result = extract_text_from_pdf(blank_bytes)
    assert result["success"] is True, "Blank PDF should open successfully"
    assert result["page_count"] == 1, "Page count should be 1"
    assert result["is_empty"] is True, "Document should be flagged as is_empty"
    print("  ✅ Passed: Detected blank page without crashing.")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🧪 LOCAL AI DOCUMENT SYSTEM - PHASE 1 TEST SUITE")
    print("=" * 50 + "\n")

    try:
        test_valid_extraction()
        test_empty_bytes()
        test_corrupted_file()
        test_blank_pdf()
        print("\n" + "=" * 50)
        print("🎉 ALL TESTS PASSED SUCCESSFULLY!")
        print("=" * 50 + "\n")
    except AssertionError as e:
        print(f"\n❌ Test Failed: {e}")
        sys.exit(1)
