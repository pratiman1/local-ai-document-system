"""
tools/reprocess_flagged_pages.py
---------------------------------
Selectively reprocesses pages from the 300-page Malayalam-to-Hindi book that
contained untranslated Malayalam words (e.g. glued list markers like 'c.റിസപ്ഷൻ',
'd.മുകളിൽ') or repetition artifacts.

Safety & Integrity Rules:
1. NEVER overwrites or modifies exports/full_300p_translation_checkpoint.json.
2. Reads from full_300p_translation_checkpoint.json, clones to
   exports/full_300p_translation_checkpoint_corrected.json, and updates only the
   flagged pages.
3. Writes updated full text to exports/full_300p_hindi_translation_corrected.txt.
4. 100% offline execution on CPU with garbage collection per page.
"""

import os
import sys
import json
import time
import gc
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fitz  # PyMuPDF
from translation.translator_factory import get_translator
from translation.translation_pipeline import translate_page
from translation.indic_text_processor import GlossaryManager

PDF_PATH = PROJECT_ROOT / "uploads" / "9788117403600_c5233386c0454bc887c8f0a8a37d1c72_output_e4828aa384654e07903c4ad04152fa96.pdf"
EXPORTS_DIR = PROJECT_ROOT / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

ORIGINAL_CHECKPOINT = EXPORTS_DIR / "full_300p_translation_checkpoint.json"
CORRECTED_CHECKPOINT = EXPORTS_DIR / "full_300p_translation_checkpoint_corrected.json"
CORRECTED_TXT = EXPORTS_DIR / "full_300p_hindi_translation_corrected.txt"

MALAYALAM_RE = re.compile(r"[\u0D00-\u0D7F]+")


def save_atomic_json(filepath: Path, data: dict):
    tmp_path = filepath.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(filepath)


def update_output_txt(filepath: Path, pages_dict: dict, total_pages: int):
    tmp_path = filepath.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("OFFLINE TRANSLATION: MALAYALAM TO HINDI (CORRECTED)\n")
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


def get_flagged_pages(checkpoint_data: dict) -> list[int]:
    """Finds all page numbers containing untranslated Malayalam text."""
    pages = checkpoint_data.get("pages", {})
    flagged = []
    for p_str, p_info in pages.items():
        txt = p_info.get("translated_text", "")
        if MALAYALAM_RE.search(txt):
            flagged.append(int(p_str))
    flagged.sort()
    return flagged


def main(target_pages: list[int] = None):
    print("=" * 70)
    print("🔍 REPROCESSING FLAGGED TRANSLATION PAGES")
    print(f"📄 Source PDF: {PDF_PATH}")
    print(f"💾 Original Checkpoint: {ORIGINAL_CHECKPOINT}")
    print(f"💾 Target Corrected Checkpoint: {CORRECTED_CHECKPOINT}")
    print("=" * 70)

    if not ORIGINAL_CHECKPOINT.is_file():
        print(f"❌ Original checkpoint not found: {ORIGINAL_CHECKPOINT}")
        sys.exit(1)

    # Initialize or load corrected checkpoint
    if not CORRECTED_CHECKPOINT.is_file():
        print("📋 Initializing corrected checkpoint from original...")
        shutil.copy2(ORIGINAL_CHECKPOINT, CORRECTED_CHECKPOINT)

    with open(CORRECTED_CHECKPOINT, "r", encoding="utf-8") as f:
        corrected_data = json.load(f)

    if target_pages is None:
        target_pages = get_flagged_pages(corrected_data)

    print(f"⚠️ Found {len(target_pages)} pages requiring re-translation: {target_pages}")

    if not target_pages:
        print("🎉 No pages have untranslated Malayalam words! Checkpoint is already clean.")
        return

    # Open PDF
    doc = fitz.open(str(PDF_PATH))
    total_pages = len(doc)

    translator = get_translator("indictrans2")
    gm = GlossaryManager()

    print(f"\n🚀 Beginning reprocessing of {len(target_pages)} pages with IndicTrans2...")
    t_start = time.time()

    for idx, p_num in enumerate(target_pages, 1):
        p_str = str(p_num)
        print(f"\n[{idx}/{len(target_pages)}] Reprocessing Page {p_num}...")

        # Extract text directly from PDF page (0-indexed in PyMuPDF)
        pdf_page = doc[p_num - 1]
        raw_text = pdf_page.get_text("text")

        page_data = {
            "page_number": p_num,
            "text": raw_text,
            "page_index": p_num - 1,
        }

        t_p_start = time.time()
        res = translate_page(
            page_data=page_data,
            source_lang="mal",
            target_lang="hin",
            translator=translator,
            glossary_manager=gm,
        )
        elapsed = time.time() - t_p_start

        # Check for remaining Malayalam characters
        remaining = MALAYALAM_RE.findall(res.get("translated_text", ""))
        status_icon = "✅" if not remaining else "⚠️"
        print(f"  {status_icon} Page {p_num} completed in {elapsed:.1f}s. Remaining Malayalam tokens: {len(remaining)} {remaining[:5] if remaining else ''}")

        # Update checkpoint
        corrected_data["pages"][p_str] = {
            "page_number": p_num,
            "completed": True,
            "is_blank": not bool(raw_text.strip()),
            "elapsed_sec": round(elapsed, 2),
            "cleaned_text": res.get("cleaned_text", ""),
            "translated_text": res.get("translated_text", ""),
            "modified_words": res.get("modified_words", []),
            "char_count": res.get("char_count", 0),
            "word_count": res.get("word_count", 0),
        }

        save_atomic_json(CORRECTED_CHECKPOINT, corrected_data)
        gc.collect()

    doc.close()
    update_output_txt(CORRECTED_TXT, corrected_data["pages"], total_pages)

    total_elapsed = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"🎉 REPROCESSING COMPLETE in {total_elapsed:.1f}s!")
    print(f"💾 Updated Checkpoint: {CORRECTED_CHECKPOINT}")
    print(f"📝 Updated Text: {CORRECTED_TXT}")

    # Final verification
    remaining_flagged = get_flagged_pages(corrected_data)
    print(f"📊 Final Audit: {len(remaining_flagged)} pages with untranslated Malayalam words (down from {len(target_pages)}).")
    if remaining_flagged:
        print(f"   Pages still flagged: {remaining_flagged}")
    print("=" * 70)


if __name__ == "__main__":
    # If page numbers passed as CLI arguments, translate only those
    args = [int(a) for a in sys.argv[1:] if a.isdigit()]
    main(args if args else None)
