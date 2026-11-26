"""
tools/translate_poetry_11p.py
-----------------------------
Translates all 11 pages of the English Poetry spread PDF to Hindi
using the offline IndicTrans2 neural model, saving the translation
checkpoint to exports/poetry_11p_translated_checkpoint.json.
"""

import json
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from extractors.pdf_extractor import extract_text_from_pdf
from translation.translator_factory import get_translator
from translation.translation_pipeline import translate_page

PDF_PATH = PROJECT_ROOT / "uploads" / "Poetry_Stories_and_Poems_11p.pdf"
CHECKPOINT_PATH = PROJECT_ROOT / "exports" / "poetry_11p_translated_checkpoint.json"

def main():
    print(f"Reading {PDF_PATH}...")
    doc_res = extract_text_from_pdf(str(PDF_PATH))
    total_pages = doc_res["page_count"]
    pages = doc_res["pages"]
    print(f"Extracted {total_pages} pages.")

    # Load existing checkpoint if partially done
    checkpoint_data = {"pages": {}}
    if CHECKPOINT_PATH.is_file():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)
            print(f"Loaded existing checkpoint with {len(checkpoint_data.get('pages', {}))} pages.")
        except Exception:
            checkpoint_data = {"pages": {}}

    t = get_translator("indictrans2")
    t0 = time.time()

    for idx, p in enumerate(pages):
        p_num = p["page_number"]
        p_str = str(p_num)

        if p_str in checkpoint_data["pages"] and checkpoint_data["pages"][p_str].get("translated_text", "").strip():
            print(f"Page {p_num}/{total_pages} already translated, skipping.")
            continue

        print(f"Translating Page {p_num}/{total_pages} ({len(p['text'])} chars)...")
        p_start = time.time()
        res = translate_page(p, "eng", "hin", t)
        p_elapsed = time.time() - p_start

        checkpoint_data["pages"][p_str] = {
            "page_number": p_num,
            "text": p["text"],
            "cleaned_text": p["text"],
            "translated_text": res["translated_text"],
        }

        # Save checkpoint periodically
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

        print(f"✓ Page {p_num}/{total_pages} done in {p_elapsed:.1f}s.")

    total_time = time.time() - t0
    print(f"All {total_pages} pages translated in {total_time:.1f}s.")
    print(f"Checkpoint saved to: {CHECKPOINT_PATH}")

if __name__ == "__main__":
    main()
