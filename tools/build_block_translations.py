"""
tools/build_block_translations.py
---------------------------------
Translates each text block in uploads/Poetry_Stories_and_Poems_11p.pdf
block-by-block, preserving exact block boundaries, line counts for poem
stanzas, and isolating bylines and headings from prose.
Footers are strictly excluded from translation and left untouched.
Saves structured block-level data to exports/poetry_11p_block_checkpoint.json.
"""

import json
import time
import re
from pathlib import Path
import sys
import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from translation.translator_factory import get_translator

PDF_PATH = PROJECT_ROOT / "uploads" / "Poetry_Stories_and_Poems_11p.pdf"
OUT_CHECKPOINT = PROJECT_ROOT / "exports" / "poetry_11p_block_checkpoint.json"

DECORATIVE_TITLES_MAP = {
    "tweetspeak poetry": "ट्वीटस्पीक पोएट्री",
    "tweetspeak": "ट्वीटस्पीक",
    "poetry": "पोएट्री",
    "fell in love": "प्यार में पड़ गए",
    "she gave me": "उसने मुझे दिया",
    "fill the heart": "दिल को भरना",
    "ink & tears": "स्याही और आँसू",
    "curtain time": "पर्दा उठने का समय",
    "poems like air": "हवा जैसी कविताएँ",
    "heartbeat": "दिल की धड़कन",
    "bloom & nest": "खिलना और घोंसला",
    "poetry in bloom": "खिलती हुई कविता",
    "affiance of poetry": "कविता का नाता",
    "inviting me out": "मुझे बाहर बुलाना",
    "belonging": "अपनापन",
}

HEADING_TRANSLATIONS = {
    "poetry in bloom": "खिलती हुई कविता",
    "curtain time": "पर्दा उठने का समय",
    "affiance of poetry": "कविता का नाता",
    "ms. leah says...": "सुश्री लिआ कहती हैं...",
    "mrs. o’brien": "श्रीमती ओ'ब्रायन",
    "mrs. o'brien": "श्रीमती ओ'ब्रायन",
}

BYLINE_TRANSLATIONS = {
    "tammy cook": "टैमी कुक",
    "patty rieman": "पैटी रीमैन",
    "ms. leah": "सुश्री लिआ",
    "cheryl mann": "शेरिल मान",
    "rebecca d. martin": "रेबेका डी. मार्टिन",
    "crystal rowe": "क्रिस्टल रोवे",
    "emily dickinson": "एमिली डिकिंसन",
    "tatiana lyulkin": "तातियाना ल्युलकिन",
    "andrew guzaldo © 2019": "एंड्रयू गुज़ाल्डो © 2019",
    "alex": "एलेक्स",
    "deb y felio": "देब वाई फेलियो",
}


def split_stanza_into_n_lines(translated_text: str, target_line_count: int):
    """
    Splits translated poem stanza into target_line_count lines.
    Returns (formatted_text, had_mismatch_warning).
    """
    if target_line_count <= 1:
        return translated_text.strip(), False
        
    existing_lines = [l.strip() for l in translated_text.splitlines() if l.strip()]
    if len(existing_lines) == target_line_count:
        return "\n".join(existing_lines), False

    words = translated_text.replace("\n", " ").split()
    total_words = len(words)
    if total_words <= target_line_count:
        lines = words
        mismatch = (len(lines) != target_line_count)
        return "\n".join(lines), mismatch

    w_per_line = total_words / float(target_line_count)
    lines = []
    curr_start = 0
    for i in range(target_line_count):
        if i == target_line_count - 1:
            lines.append(" ".join(words[curr_start:]))
        else:
            curr_end = int(round((i + 1) * w_per_line))
            best_end = curr_end
            for offset in [0, 1, -1, 2, -2]:
                cand = curr_end + offset
                if curr_start < cand < total_words:
                    if words[cand - 1].endswith((",", "।", ";", ":", "-", "!", "?")):
                        best_end = cand
                        break
            lines.append(" ".join(words[curr_start:best_end]))
            curr_start = best_end

    mismatch = (len(lines) != target_line_count)
    return "\n".join(lines), mismatch


def main():
    doc = fitz.open(str(PDF_PATH))
    print(f"Loaded {len(doc)} pages from {PDF_PATH}")
    t = get_translator("indictrans2")

    footer_pat = re.compile(r"(\b\d+\s*•\s*A Little Book|A Little Book of Poetry Stories\s*&\s*Poems)", re.IGNORECASE)

    # Load existing checkpoint if any
    data = {"pages": {}}
    if OUT_CHECKPOINT.is_file():
        try:
            with open(OUT_CHECKPOINT, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"Loaded existing checkpoint with {len(data.get('pages', {}))} pages.")
        except Exception:
            data = {"pages": {}}

    for pi in range(len(doc)):
        p_num = pi + 1
        p_str = str(p_num)
        page = doc[pi]
        d = page.get_text("dict")
        text_blocks = [b for b in d["blocks"] if b.get("type") == 0]

        if p_str in data["pages"] and len(data["pages"][p_str].get("blocks", [])) == len(text_blocks):
            print(f"Page {p_num}/11 already fully translated in checkpoint, skipping.")
            continue

        print(f"\n--- Processing Page {p_num}/11 ({len(text_blocks)} blocks) ---")
        page_blocks_data = []

        for bi, b in enumerate(text_blocks):
            spans = [s for l in b["lines"] for s in l["spans"] if s["text"].strip()]
            if not spans:
                continue

            full_text = "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()
            block_lines = []
            for l in b["lines"]:
                ltxt = "".join(s["text"] for s in l["spans"]).strip()
                if ltxt:
                    block_lines.append(ltxt)

            fs = spans[0]
            fn = fs["font"]
            sz = fs["size"]
            col = fs["color"]
            r = ((col >> 16) & 255) / 255.0
            g = ((col >> 8) & 255) / 255.0
            bl = (col & 255) / 255.0
            x0, y0, x1, y1 = b["bbox"]
            side = "L" if (x0 + x1) / 2.0 < 396.0 else "R"

            is_footer = bool(footer_pat.search(full_text)) and sz <= 10.5 and y0 > 500
            is_title = "script" in fn.lower() or sz >= 35.0

            b_type = "PROSE"
            if is_footer:
                b_type = "FOOTER"
            elif is_title:
                b_type = "TITLE"
            elif "tweetspeakpoetry.com" in full_text.lower():
                b_type = "WEBSITE"
            elif full_text.lower().strip().rstrip(".").rstrip() in HEADING_TRANSLATIONS:
                b_type = "HEADING"
            elif sz <= 10.5 and (full_text.startswith("—") or full_text.startswith("–") or full_text.startswith("-") or full_text.startswith("~")):
                b_type = "BYLINE"
            elif len(block_lines) > 1 and all(len(l.split()) <= 11 for l in block_lines):
                b_type = "POEM_STANZA"

            translated_text = ""
            line_mismatch_warn = False

            if b_type == "FOOTER":
                # NEVER translate or touch footers
                translated_text = ""
            elif b_type == "WEBSITE":
                translated_text = "tweetspeakpoetry.com"
            elif b_type == "TITLE":
                # Match title
                cleaned_t = full_text.lower().strip()
                # Check for dual title in single block (e.g. Page 2, Page 3)
                if "fell in love" in cleaned_t and "she gave me" in cleaned_t:
                    translated_text = "प्यार में पड़ गए\n--- Title Split ---\nउसने मुझे दिया"
                elif "fill the heart" in cleaned_t and "ink & tears" in cleaned_t:
                    translated_text = "दिल को भरना\n--- Title Split ---\nस्याही और आँसू"
                elif "bloom & nest" in cleaned_t or ("bloom" in cleaned_t and "nest" in cleaned_t):
                    translated_text = "खिलना और घोंसला"
                elif "poems like air" in cleaned_t:
                    translated_text = "हवा जैसी कविताएँ"
                elif "heartbeat" in cleaned_t:
                    translated_text = "दिल की धड़कन"
                elif "inviting me out" in cleaned_t:
                    translated_text = "मुझे बाहर बुलाना"
                elif "belonging" in cleaned_t:
                    translated_text = "अपनापन"
                elif "tweetspeak poetry" in cleaned_t:
                    translated_text = "ट्वीटस्पीक पोएट्री"
                else:
                    for k, v in DECORATIVE_TITLES_MAP.items():
                        if k in cleaned_t:
                            translated_text = v
                            break
                    if not translated_text:
                        translated_text = t.translate(full_text, "eng", "hin").translated_text
            elif b_type == "HEADING":
                h_key = full_text.lower().strip().rstrip(".").rstrip()
                translated_text = HEADING_TRANSLATIONS.get(h_key, "")
                if not translated_text:
                    translated_text = t.translate(full_text, "eng", "hin").translated_text
            elif b_type == "BYLINE":
                prefix = ""
                raw_name = full_text
                for pfx in ["—", "–", "-", "~"]:
                    if raw_name.startswith(pfx):
                        prefix = pfx + " "
                        raw_name = raw_name[len(pfx):].strip()
                        break
                name_key = raw_name.lower().strip()
                if name_key in BYLINE_TRANSLATIONS:
                    translated_text = prefix + BYLINE_TRANSLATIONS[name_key]
                else:
                    tr = t.translate(raw_name, "eng", "hin").translated_text
                    translated_text = prefix + tr
            elif b_type == "POEM_STANZA":
                # Translate stanza as one unit, then split into target lines (Addition 2)
                stanza_unit = " ".join(block_lines)
                raw_tr = t.translate(stanza_unit, "eng", "hin").translated_text
                translated_text, line_mismatch_warn = split_stanza_into_n_lines(raw_tr, len(block_lines))
                if line_mismatch_warn:
                    print(f"  ⚠️ Warning: Page {p_num} B{bi} stanza line count expected {len(block_lines)}, got {len(translated_text.splitlines())}")
            else:
                # PROSE
                # Single paragraph translated as a unit
                translated_text = t.translate(full_text, "eng", "hin").translated_text

            page_blocks_data.append({
                "block_index": bi,
                "bbox": list(b["bbox"]),
                "side": side,
                "block_type": b_type,
                "original_text": full_text,
                "original_lines": block_lines,
                "line_count": len(block_lines),
                "font": fn,
                "size": sz,
                "color_rgb": [r, g, bl],
                "translated_text": translated_text,
                "line_mismatch_warn": line_mismatch_warn,
            })
            print(f"  ✓ B{bi:02d} [{b_type:11s}]: {repr(full_text[:30])} ➔ {repr(translated_text[:30])}")

        data["pages"][p_str] = {
            "page_number": p_num,
            "blocks": page_blocks_data,
        }

        # Periodic save
        with open(OUT_CHECKPOINT, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    doc.close()
    print(f"\nAll 11 pages translated block-by-block and saved to {OUT_CHECKPOINT}")


if __name__ == "__main__":
    main()
