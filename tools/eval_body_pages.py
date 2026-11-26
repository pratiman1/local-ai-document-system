"""
tools/eval_body_pages.py
-------------------------
Evaluates real body-text pages from user's 300-page hotel front office PDF.
Translates Malayalam to Hindi via IndicTrans2 with sentence chunking & glossary tags.
Saves results incrementally to tools/eval_results.json.
"""

import os
import sys
import json
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from extractors.pdf_extractor import extract_text_from_pdf
from translation.translator_factory import get_translator
from translation.translation_pipeline import translate_page
from translation.indic_text_processor import (
    split_into_sentences,
    clean_and_join_lines,
    GlossaryManager,
)

PDF_PATH = PROJECT_ROOT / "uploads" / "9788117403600_c5233386c0454bc887c8f0a8a37d1c72_output_e4828aa384654e07903c4ad04152fa96.pdf"
OUTPUT_FILE = PROJECT_ROOT / "tools" / "eval_results.json"

TARGET_PAGES = [10, 15, 20, 33, 40, 45]

def main():
    print("=" * 60)
    print("Starting Body-Text Translation Evaluation with IndicTrans2")
    print(f"Target Pages: {TARGET_PAGES}")
    print("=" * 60)

    if not PDF_PATH.exists():
        print(f"ERROR: PDF file not found at {PDF_PATH}")
        sys.exit(1)

    print("Extracting text from PDF...")
    doc_res = extract_text_from_pdf(str(PDF_PATH))
    total_pages = doc_res["page_count"]
    print(f"Extracted {total_pages} total pages successfully.")

    translator = get_translator("indictrans2")
    print(f"Initialized translator: {translator.get_name()}")

    existing_results = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_results = json.load(f)
            print(f"Loaded {len(existing_results)} previously translated pages.")
        except Exception:
            existing_results = {}

    for p_num in TARGET_PAGES:
        p_str = str(p_num)
        if p_str in existing_results and existing_results[p_str].get("completed", False):
            print(f"Page {p_num} already completed. Skipping.")
            continue

        print(f"\n>>> Processing Page {p_num} of {total_pages}...")
        t0 = time.time()
        page_dict = doc_res["pages"][p_num - 1]

        # Check raw text
        raw_text = page_dict.get("text", "")
        cleaned, mods = clean_and_join_lines(raw_text)
        print(f"Raw length: {len(raw_text)}, Cleaned length: {len(cleaned)}, Doubled-char mods: {mods}")

        if not cleaned.strip():
            print(f"Page {p_num} is blank (0 chars).")
            res_dict = {
                "page_number": p_num,
                "completed": True,
                "is_blank": True,
                "elapsed_sec": 0.0,
                "raw_text": "",
                "cleaned_text": "",
                "translated_text": "",
                "doubled_char_mods": [],
                "pairs": [],
            }
            existing_results[p_str] = res_dict
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_results, f, ensure_ascii=False, indent=2)
            continue

        gm = GlossaryManager()
        src_sents = split_into_sentences(cleaned)
        print(f"Translating {len(src_sents)} sentences for Page {p_num}...")

        pairs = []
        translated_sents = []

        for idx, sent in enumerate(src_sents):
            masked_sent, tag_map, matched_terms = gm.mask_terms(sent, "mal", "hin")
            if tag_map:
                out = translator.translate(masked_sent, source="mal", target="hin")
                restored, all_found = gm.restore_terms(out.translated_text, tag_map)
                if not all_found:
                    raw_out = translator.translate(sent, source="mal", target="hin")
                    restored = gm.apply_fallback_replacement(
                        raw_out.translated_text, "mal", "hin", matched_terms
                    )
                pairs.append({"mal": sent, "hin": restored})
                translated_sents.append(restored)
            else:
                out = translator.translate(sent, source="mal", target="hin")
                pairs.append({"mal": sent, "hin": out.translated_text})
                translated_sents.append(out.translated_text)

        elapsed = time.time() - t0
        print(f"Page {p_num} translated in {elapsed:.2f} seconds.")

        full_translated = " ".join(translated_sents).strip()

        res_dict = {
            "page_number": p_num,
            "completed": True,
            "is_blank": False,
            "elapsed_sec": round(elapsed, 2),
            "raw_text": raw_text,
            "cleaned_text": cleaned,
            "translated_text": full_translated,
            "doubled_char_mods": mods,
            "pairs": pairs,
        }

        existing_results[p_str] = res_dict
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_results, f, ensure_ascii=False, indent=2)
        print(f"Saved Page {p_num} results to {OUTPUT_FILE}")

    print("\n" + "=" * 60)
    print("ALL EVALUATION PAGES TRANSLATED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
