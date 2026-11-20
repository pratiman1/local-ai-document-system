"""
tests/test_txt_exporter.py
--------------------------
Unit tests for the TXT document exporter.
Validates:
1. Writing UTF-8 encoded text including Indian scripts (Devanagari, Tamil).
2. Rejecting empty text exports.
3. Preserving existing files when overwrite=False.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from exporters.txt_exporter import export_to_txt


def test_multilingual_txt_export():
    print("Running Test 1: Multilingual UTF-8 TXT export...")
    test_content = (
        "English: Local Multilingual Document System\n"
        "Hindi (हिन्दी): स्थानीय बहुभाषी दस्तावेज़ प्रसंस्करण प्रणाली\n"
        "Tamil (தமிழ்): உள்ளூர் பலமொழி ஆவண செயலாக்க அமைப்பு\n"
    )
    test_file = PROJECT_ROOT / "exports" / "_test_sample.txt"

    try:
        result = export_to_txt(text=test_content, output_path=test_file, overwrite=True)
        assert result["success"] is True, f"Export failed: {result['error']}"
        assert test_file.exists(), "Exported file was not found on disk"

        # Verify UTF-8 reading matches written content
        read_back = test_file.read_text(encoding="utf-8")
        assert "हिन्दी" in read_back, "Hindi script corrupted during export"
        assert "தமிழ்" in read_back, "Tamil script corrupted during export"
        print("  ✅ Passed: Multilingual text written and verified accurately.")
    finally:
        if test_file.exists():
            test_file.unlink()  # Clean up test artifact


def test_empty_text_rejection():
    print("Running Test 2: Rejecting empty text export...")
    test_file = PROJECT_ROOT / "exports" / "_test_empty.txt"
    result = export_to_txt(text="   \n  ", output_path=test_file)
    assert result["success"] is False, "Empty text should not succeed"
    assert "empty" in result["error"].lower(), "Expected error message about empty text"
    assert not test_file.exists(), "Empty file should not be created"
    print("  ✅ Passed: Gracefully rejected empty text.")


def test_overwrite_protection():
    print("Running Test 3: Overwrite protection check...")
    test_file = PROJECT_ROOT / "exports" / "_test_overwrite.txt"
    try:
        test_file.write_text("Original content", encoding="utf-8")
        result = export_to_txt(text="New content", output_path=test_file, overwrite=False)
        assert result["success"] is False, "Should fail when overwrite=False"
        assert "already exists" in result["error"], "Expected already exists error"
        assert test_file.read_text(encoding="utf-8") == "Original content", "Original file modified!"
        print("  ✅ Passed: Prevented overwriting when overwrite=False.")
    finally:
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🧪 EXPORTER TEST SUITE")
    print("=" * 50 + "\n")
    test_multilingual_txt_export()
    test_empty_text_rejection()
    test_overwrite_protection()
    print("\n" + "=" * 50)
    print("🎉 ALL EXPORTER TESTS PASSED!")
    print("=" * 50 + "\n")
