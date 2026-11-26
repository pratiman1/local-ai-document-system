"""
tools/test_sections_6_and_7.py
------------------------------
Re-runs offline translation only for Section 6 and Section 7.
Verifies:
1. Punctuation following glossary tags is kept (specifically the comma after 'two-factor authentication,' in Section 6).
2. 'पैदल चलना' is translated as 'walking' in Section 7.
Updates the exported txt and json files for sections 6 and 7.
"""

import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from translation.translator_factory import get_translator
from translation.translation_pipeline import translate_page
from translation.indic_text_processor import GlossaryManager
from tools.run_hindi_to_english_10sections import PAGES_DATA

OUTPUT_JSON = PROJECT_ROOT / "exports" / "hindi_to_english_10sections_translated.json"
OUTPUT_TXT = PROJECT_ROOT / "exports" / "hindi_to_english_10sections_translated.txt"

def main():
    print("=" * 70)
    print("🚀 RE-RUNNING TRANSLATION FOR SECTIONS 6 & 7")
    print("=" * 70)

    translator = get_translator("indictrans2")
    gm = GlossaryManager()

    # Load existing JSON
    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Translate Section 6 (index 5)
    print("\n--- Translating Section 6 ---")
    p6_raw = PAGES_DATA[5]
    res6 = translate_page(
        page_data={"page_number": 6, "text": p6_raw, "page_index": 5},
        source_lang="hin",
        target_lang="eng",
        translator=translator,
        glossary_manager=gm,
    )
    data["sections"][5] = res6
    print("Section 6 translation complete.")

    # Translate Section 7 (index 6)
    print("\n--- Translating Section 7 ---")
    p7_raw = PAGES_DATA[6]
    res7 = translate_page(
        page_data={"page_number": 7, "text": p7_raw, "page_index": 6},
        source_lang="hin",
        target_lang="eng",
        translator=translator,
        glossary_manager=gm,
    )
    data["sections"][6] = res7
    print("Section 7 translation complete.")

    # Save updated JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    # Save updated TXT
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("HINDI TO ENGLISH TRANSLATION: 10 SECTIONS\n")
        f.write("=" * 70 + "\n\n")
        for r in data["sections"]:
            f.write(f"\n--- PAGE / SECTION {r['page_number']} ---\n\n")
            f.write(r["translated_text"] + "\n")

    print("\n" + "=" * 70)
    print("🔍 VERIFYING TARGET SENTENCES")
    print("=" * 70)

    # Verify Section 6 sentence
    sec6_text = res6["translated_text"]
    assert "two-factor authentication," in sec6_text, "Comma missing after 'two-factor authentication'!"
    print("✅ Section 6 target sentence verified: Comma after 'two-factor authentication,' preserved!")

    # Verify Section 7 sentence
    sec7_text = res7["translated_text"]
    assert "walking" in sec7_text.lower(), "'walking' not found in Section 7!"
    print("✅ Section 7 target sentence verified: 'walking' used for 'पैदल चलना'!")
    print("=" * 70)

if __name__ == "__main__":
    main()
