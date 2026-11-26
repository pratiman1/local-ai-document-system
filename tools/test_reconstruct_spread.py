import fitz
import re
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from exporters.pdf_reconstructor import resolve_devanagari_font, resolve_devanagari_title_font, DECORATIVE_TITLES_MAP

PDF_PATH = PROJECT_ROOT / "uploads" / "Poetry_Stories_and_Poems_11p.pdf"
OUT_PDF = PROJECT_ROOT / "exports" / "test_spread_preview.pdf"

font_path = resolve_devanagari_font()
title_font_path = resolve_devanagari_title_font()
print(f"Body font: {font_path}")
print(f"Title font: {title_font_path}")

doc = fitz.open(str(PDF_PATH))
page = doc[1] # Page 2

# Inspect blocks
d = page.get_text("dict")
print("Blocks on Page 2:")
for bi, b in enumerate(d["blocks"]):
    if b.get("type") == 0:
        txt = "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()
        fs = b["lines"][0]["spans"][0]
        print(f"  B{bi}: bbox={b['bbox']} font={fs['font']} sz={fs['size']} txt={repr(txt[:40])}")

doc.close()
