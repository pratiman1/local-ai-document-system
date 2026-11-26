"""
tools/test_list_translation.py
--------------------------------
Translates Page 15 and Page 20 using IndicTrans2 to verify:
1. List/heading/bullet formatting (no '5 • • • • •', clean 1.3.2 heading, clean bullet items).
2. 'ഡിപ്പാർച്ചർ എറാൻഡ്' translation using 'प्रस्थान कार्य' in context.
Saves results to tools/list_translation_results.json.
"""

import sys
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from extractors.pdf_extractor import extract_text_from_pdf
from translation.translator_factory import get_translator
from translation.indic_text_processor import (
    clean_and_join_lines,
    split_into_sentences,
    GlossaryManager,
)

PDF_PATH = PROJECT_ROOT / "uploads" / "9788117403600_c5233386c0454bc887c8f0a8a37d1c72_output_e4828aa384654e07903c4ad04152fa96.pdf"
OUTPUT_FILE = PROJECT_ROOT / "tools" / "list_translation_results.json"

TARGET_PAGES = [15, 20]

def main():
    print("=" * 60)
    print("Evaluating List Formatting & Departure Errand on Pages 15 & 20")
    print("=" * 60)

    doc_res = extract_text_from_pdf(str(PDF_PATH))
    translator = get_translator("indictrans2")
    gm = GlossaryManager()

    results = {}

    for p_num in TARGET_PAGES:
        print(f"\n>>> Processing Page {p_num}...")
        t0 = time.time()
        raw_text = doc_res["pages"][p_num - 1]["text"]

        cleaned_text, mods = clean_and_join_lines(raw_text)
        sentences = split_into_sentences(cleaned_text)
        print(f"Page {p_num} cleaned into {len(sentences)} distinct sentences/units.")

        pairs = []
        translated_sents = []

        for idx, sent in enumerate(sentences):
            masked_sent, tag_map, matched_terms = gm.mask_terms(sent, "mal", "hin")
            if tag_map:
                out = translator.translate(masked_sent, source="mal", target="hin")
                restored, all_found = gm.restore_terms(out.translated_text, tag_map)
                if not all_found:
                    raw_out = translator.translate(sent, source="mal", target="hin")
                    restored = gm.apply_fallback_replacement(
                        raw_out.translated_text, "mal", "hin", matched_terms
                    )
                pairs.append({"mal": sent, "hin": restored, "matched": matched_terms})
                translated_sents.append(restored)
            else:
                out = translator.translate(sent, source="mal", target="hin")
                pairs.append({"mal": sent, "hin": out.translated_text, "matched": []})
                translated_sents.append(out.translated_text)

            print(f"  [{idx+1}/{len(sentences)}] MAL: {sent[:60]}... -> HIN: {pairs[-1]['hin'][:60]}...")

        elapsed = time.time() - t0
        print(f"Page {p_num} finished in {elapsed:.2f}s.")

        results[str(p_num)] = {
            "page_number": p_num,
            "elapsed_sec": round(elapsed, 2),
            "sentence_count": len(sentences),
            "cleaned_text": cleaned_text,
            "translated_text": " ".join(translated_sents).strip(),
            "pairs": pairs,
        }

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"RESULTS SAVED TO {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
