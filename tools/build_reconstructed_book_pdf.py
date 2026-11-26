"""
tools/build_reconstructed_book_pdf.py
-------------------------------------
Reconstructs the full 11-page English spread PDF into a professional Hindi
translated book PDF and exports high-resolution page preview images for Pages 1-8.
Generates comprehensive coverage and layout audit report.
"""

import json
import time
import shutil
from pathlib import Path
import sys
import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from exporters.pdf_reconstructor import PDFReconstructor

SOURCE_PDF = PROJECT_ROOT / "uploads" / "Poetry_Stories_and_Poems_11p.pdf"
CHECKPOINT = PROJECT_ROOT / "exports" / "poetry_11p_block_checkpoint.json"
OUTPUT_PDF = PROJECT_ROOT / "exports" / "Poetry_Stories_and_Poems_11p_hindi_translated_book.pdf"

ARTIFACT_DIR = Path("/Users/apple/.gemini/antigravity/brain/74bd16c1-dbb7-4bc7-9e6e-a2a96d646742")
PREVIEW_DIR = ARTIFACT_DIR / "preview_pages"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print(f"Loading checkpoint: {CHECKPOINT}")
    with open(CHECKPOINT, "r", encoding="utf-8") as f:
        checkpoint_data = json.load(f)

    print(f"Reconstructing {SOURCE_PDF} -> {OUTPUT_PDF}...")
    reconstructor = PDFReconstructor(str(SOURCE_PDF))

    t0 = time.time()
    res = reconstructor.reconstruct_document(
        checkpoint_data=checkpoint_data,
        output_pdf_path=str(OUTPUT_PDF),
        progress_callback=lambda c, t, eta: print(f"  Reconstructed {c}/{t} pages (ETA: {eta:.1f}s)"),
    )
    elapsed = time.time() - t0
    print(f"\nReconstruction completed in {elapsed:.1f}s:")
    print(f"  Total pages: {res.get('total_pages')}")
    print(f"  Output PDF size: {res.get('file_size_bytes'):,} bytes")
    print(f"  Total warnings: {len(res.get('warnings', []))}")
    for w in res.get("warnings", []):
        print(f"    ⚠️ {w}")

    # Open reconstructed document and render screenshots of Pages 1 through 8
    doc = fitz.open(str(OUTPUT_PDF))
    print(f"\nReconstructed PDF has {len(doc)} pages. Rendering preview images for Pages 1 to 8...")

    img_paths = []
    for p_idx in range(min(8, len(doc))):
        p = doc[p_idx]
        p_num = p_idx + 1
        # Render high-resolution pixmap (150 DPI = 2.08 scale)
        pix = p.get_pixmap(dpi=150)
        local_png = PROJECT_ROOT / "exports" / f"page_{p_num}_hindi.png"
        pix.save(str(local_png))

        artifact_png = PREVIEW_DIR / f"page_{p_num:03d}_hindi.png"
        shutil.copyfile(str(local_png), str(artifact_png))
        img_paths.append(artifact_png)
        print(f"  Page {p_num}: saved -> {artifact_png} ({pix.width}x{pix.height})")

    doc.close()

    # Save detailed audit report
    audit_summary_path = PROJECT_ROOT / "exports" / "reconstruction_audit_summary.json"
    with open(audit_summary_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"\nSaved reconstruction audit summary to: {audit_summary_path}")
    print("Done!")


if __name__ == "__main__":
    main()
