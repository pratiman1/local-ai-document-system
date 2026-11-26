"""
tools/run_full_translation_300p.py
-----------------------------------
Full 300-page Malayalam to Hindi document translation runner using AI4Bharat IndicTrans2.
Features:
1. Strict 100% offline execution on CPU (float32, micro-batches).
2. Uses the updated indic_text_processor (clean list formatting, protected numbering).
3. Uses the updated glossaries/mal.json including 'ഡിപ്പാർച്ചർ എറാൻഡ്' -> 'प्रस्थान कार्य'.
4. Auto-saves checkpoint after every single page to exports/full_300p_translation_checkpoint.json.
5. Continuously updates exports/full_300p_hindi_translation.txt.
6. Auto-resumes from last completed page if interrupted.
7. Low memory footprint with garbage collection per page.
"""

import os
import sys
import json
import time
import gc
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from extractors.pdf_extractor import extract_text_from_pdf
from translation.translator_factory import get_translator
from translation.translation_pipeline import translate_page
from translation.indic_text_processor import GlossaryManager

PDF_PATH = PROJECT_ROOT / "uploads" / "9788117403600_c5233386c0454bc887c8f0a8a37d1c72_output_e4828aa384654e07903c4ad04152fa96.pdf"
EXPORTS_DIR = PROJECT_ROOT / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

CHECKPOINT_JSON = EXPORTS_DIR / "full_300p_translation_checkpoint.json"
OUTPUT_TXT = EXPORTS_DIR / "full_300p_hindi_translation.txt"

def format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"

def save_atomic_json(filepath: Path, data: dict):
    tmp_path = filepath.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(filepath)

def update_output_txt(filepath: Path, pages_dict: dict, total_pages: int):
    tmp_path = filepath.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("OFFLINE TRANSLATION: MALAYALAM TO HINDI\n")
        f.write("Document: Front Office Management (300 pages)\n")
        f.write("Engine: AI4Bharat IndicTrans2 (Offline)\n")
        f.write("=" * 60 + "\n\n")

        for p_num in range(1, total_pages + 1):
            p_str = str(p_num)
            p_data = pages_dict.get(p_str)
            if not p_data:
                continue

            f.write(f"\n--- Page {p_num} ---\n\n")
            if p_data.get("is_blank"):
                f.write("[Blank Page]\n")
            else:
                f.write(p_data.get("translated_text", "") + "\n")

    tmp_path.replace(filepath)

def main():
    print("=" * 70)
    print("🚀 STARTING FULL 300-PAGE MALAYALAM TO HINDI TRANSLATION")
    print(f"📄 PDF Source: {PDF_PATH}")
    print(f"💾 Checkpoint: {CHECKPOINT_JSON}")
    print(f"📝 Text Export: {OUTPUT_TXT}")
    print("=" * 70)

    if not PDF_PATH.is_file():
        print(f"❌ ERROR: PDF file not found at {PDF_PATH}")
        sys.exit(1)

    print("\n1. Extracting PDF document text...")
    doc_res = extract_text_from_pdf(str(PDF_PATH))
    total_pages = doc_res["page_count"]
    print(f"   ✓ Extracted {total_pages} total pages successfully.")

    print("\n2. Initializing IndicTrans2 translation engine...")
    translator = get_translator("indictrans2")
    print(f"   ✓ Engine: {translator.get_name()}")
    gm = GlossaryManager()
    print("   ✓ GlossaryManager initialized with updated terms.")

    # Load existing checkpoint if available (Resume capability)
    checkpoint = {
        "doc_id": "9788117403600_c5233386c0454bc887c8f0a8a37d1c72",
        "total_pages": total_pages,
        "completed_count": 0,
        "pages": {},
    }

    if CHECKPOINT_JSON.is_file():
        try:
            with open(CHECKPOINT_JSON, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if saved.get("total_pages") == total_pages:
                    checkpoint = saved
                    print(f"   ✓ Loaded existing checkpoint: {len(checkpoint['pages'])}/{total_pages} pages previously completed.")
        except Exception as e:
            print(f"   ⚠️ Could not load previous checkpoint ({e}). Starting fresh.")

    pages_dict = checkpoint["pages"]
    start_time = time.time()
    session_translated = 0
    total_non_blank_seconds = 0.0
    non_blank_count = 0

    print("\n3. Processing pages...")
    for idx, raw_page in enumerate(doc_res["pages"]):
        p_num = idx + 1
        p_str = str(p_num)

        # Check if already completed in checkpoint
        if p_str in pages_dict and pages_dict[p_str].get("completed"):
            continue

        raw_text = raw_page.get("text", "")
        t0 = time.time()

        if not raw_text.strip():
            # Blank page
            pages_dict[p_str] = {
                "page_number": p_num,
                "completed": True,
                "is_blank": True,
                "elapsed_sec": 0.0,
                "cleaned_text": "",
                "translated_text": "",
                "char_count": 0,
                "word_count": 0,
            }
            elapsed = 0.0
            status_str = "Blank (0 chars)"
        else:
            try:
                page_res = translate_page(
                    page_data=raw_page,
                    source_lang="mal",
                    target_lang="hin",
                    translator=translator,
                    glossary_manager=gm,
                )
                elapsed = time.time() - t0
                total_non_blank_seconds += elapsed
                non_blank_count += 1
                session_translated += 1

                pages_dict[p_str] = {
                    "page_number": p_num,
                    "completed": True,
                    "is_blank": False,
                    "elapsed_sec": round(elapsed, 2),
                    "cleaned_text": page_res.get("cleaned_text", ""),
                    "translated_text": page_res.get("translated_text", ""),
                    "modified_words": page_res.get("modified_words", []),
                    "char_count": len(page_res.get("translated_text", "")),
                    "word_count": len(page_res.get("translated_text", "").split()),
                }
                status_str = f"Done in {elapsed:.1f}s ({pages_dict[p_str]['word_count']} words)"
            except Exception as e:
                elapsed = time.time() - t0
                print(f"   ❌ Error on Page {p_num}: {e}")
                pages_dict[p_str] = {
                    "page_number": p_num,
                    "completed": False,
                    "error": str(e),
                    "elapsed_sec": round(elapsed, 2),
                }
                status_str = f"FAILED: {e}"

        # Update checkpoint count and save
        completed_so_far = sum(1 for p in pages_dict.values() if p.get("completed"))
        checkpoint["completed_count"] = completed_so_far

        # Estimate ETA
        if non_blank_count > 0:
            avg_per_page = total_non_blank_seconds / non_blank_count
            remaining_pages = total_pages - completed_so_far
            eta_seconds = remaining_pages * avg_per_page
            eta_str = format_eta(eta_seconds)
        else:
            eta_str = "Calculating..."

        pct = (completed_so_far / total_pages) * 100
        print(f"   [Page {p_num:>3}/{total_pages}] {status_str:<28} | Progress: {completed_so_far:>3}/{total_pages} ({pct:5.1f}%) | ETA: {eta_str}")

        # Save checkpoint atomically after every page
        save_atomic_json(CHECKPOINT_JSON, checkpoint)
        update_output_txt(OUTPUT_TXT, pages_dict, total_pages)

        # Force GC to keep memory bounded on 8 GB machine
        if p_num % 2 == 0:
            gc.collect()

    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("🎉 FULL DOCUMENT TRANSLATION COMPLETE!")
    print(f"⏱️ Total Execution Time: {format_eta(total_time)}")
    print(f"💾 Checkpoint Data: {CHECKPOINT_JSON}")
    print(f"📝 Full Hindi Text: {OUTPUT_TXT}")
    print("=" * 70)

if __name__ == "__main__":
    main()
