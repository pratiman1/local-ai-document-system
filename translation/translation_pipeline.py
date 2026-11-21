"""
translation/translation_pipeline.py
-----------------------------------
High-performance, memory-bounded document translation pipeline.
Coordinates:
1. Sentence/paragraph chunking to keep RAM strictly low.
2. Preserves page boundaries so Translated text lines up with Original text page-by-page.
3. Same-language bypass (skips translation when source == target).
4. Non-blocking QThread worker for responsive UI execution.
5. Live ETA calculation and progress tracking ("Page 12 of 400").
6. Safe cancellation preserving completed pages and periodic recovery checkpoints.
7. Automated heuristic sanity check per page and document.
"""

import json
import re
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from PySide6.QtCore import QThread, Signal

from config.settings import (
    TRANSLATION_RECOVERY_INTERVAL,
    TRANSLATION_CHUNK_SIZE,
    RECOVERY_DIR,
)
from translation.base_translator import Translator, TranslationOutput
from translation.translator_factory import get_translator
from translation.quality_checker import evaluate_translation_sanity, TranslationSanityReport


def chunk_text(text: str, max_chunk_chars: int = TRANSLATION_CHUNK_SIZE) -> List[str]:
    """
    Splits text into cohesive chunks (paragraphs and sentences), never exceeding
    max_chunk_chars, to ensure low memory footprint on 8 GB RAM machines.
    """
    if not text or len(text) <= max_chunk_chars:
        return [text] if text else []

    paragraphs = text.split("\n\n")
    chunks = []

    for para in paragraphs:
        para_clean = para.strip()
        if not para_clean:
            continue
        if len(para_clean) <= max_chunk_chars:
            chunks.append(para_clean)
        else:
            # Split paragraph by sentence terminators (., ?, !, or Devanagari danda ।)
            sentences = re.split(r"([.?!।]\s+)", para_clean)
            current_chunk = ""
            for s in sentences:
                if len(current_chunk) + len(s) <= max_chunk_chars:
                    current_chunk += s
                else:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    current_chunk = s
            if current_chunk.strip():
                chunks.append(current_chunk.strip())

    return chunks if chunks else [text]


def translate_page(
    page_data: Dict[str, Any],
    source_lang: str,
    target_lang: str,
    translator: Translator,
) -> Dict[str, Any]:
    """
    Translates a single page's text chunk by chunk, maintaining page structure.
    """
    p_num = page_data.get("page_number", 1)
    orig_text = page_data.get("text", "")

    if not orig_text.strip():
        return {
            "page_number": p_num,
            "original_text": "",
            "translated_text": "",
            "source_language": source_lang,
            "target_language": target_lang,
            "was_pivoted": False,
            "pivot_notice": "",
            "word_count": 0,
            "char_count": 0,
            "sanity_report": evaluate_translation_sanity("", "", source_lang, target_lang),
            "skipped": False,
        }

    # Same language skip
    if source_lang.lower() == target_lang.lower():
        return {
            "page_number": p_num,
            "original_text": orig_text,
            "translated_text": orig_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "was_pivoted": False,
            "pivot_notice": f"Source and target languages are both '{source_lang}'. Translation skipped.",
            "word_count": len(orig_text.split()),
            "char_count": len(orig_text),
            "sanity_report": evaluate_translation_sanity(orig_text, orig_text, source_lang, target_lang),
            "skipped": True,
        }

    chunks = chunk_text(orig_text)
    translated_chunks = []
    was_pivoted = False
    pivot_notice = ""

    for chunk in chunks:
        out: TranslationOutput = translator.translate(chunk, source=source_lang, target=target_lang)
        translated_chunks.append(out.translated_text)
        if out.was_pivoted:
            was_pivoted = True
            pivot_notice = out.notice

    full_translated = "\n\n".join(translated_chunks)
    sanity = evaluate_translation_sanity(orig_text, full_translated, source_lang, target_lang)

    return {
        "page_number": p_num,
        "original_text": orig_text,
        "translated_text": full_translated,
        "source_language": source_lang,
        "target_language": target_lang,
        "was_pivoted": was_pivoted,
        "pivot_notice": pivot_notice,
        "word_count": len(full_translated.split()),
        "char_count": len(full_translated),
        "sanity_report": sanity,
        "skipped": False,
    }


def get_translation_recovery_path(doc_id: str) -> Path:
    safe = "".join(c for c in doc_id if c.isalnum() or c in ("-", "_"))
    return RECOVERY_DIR / f".recovery_trans_{safe}.json"


def save_translation_recovery(recovery_path: Path, state: Dict[str, Any]):
    try:
        tmp = recovery_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp.replace(recovery_path)
    except Exception:
        pass


def remove_translation_recovery(recovery_path: Path):
    try:
        if recovery_path.is_file():
            recovery_path.unlink()
    except Exception:
        pass


def run_translation_pipeline_sync(
    pages: List[Dict[str, Any]],
    source_lang: str,
    target_lang: str,
    translator: Optional[Translator] = None,
    doc_id: str = "doc",
    progress_callback: Optional[Callable[[Dict[str, Any], int, int, float], None]] = None,
) -> Dict[str, Any]:
    """
    Runs document translation synchronously (for CLI / tests).
    """
    if translator is None:
        translator = get_translator("argos")

    total_pages = len(pages)
    if total_pages == 0:
        return {
            "success": True,
            "page_count": 0,
            "translated_pages": [],
            "full_translated_text": "",
            "was_pivoted": False,
            "skipped": False,
        }

    # Same language check across whole doc
    if source_lang.lower() == target_lang.lower():
        same_pages = [
            translate_page(p, source_lang, target_lang, translator) for p in pages
        ]
        full_text = "\n\n--- Page Break ---\n\n".join(p["translated_text"] for p in same_pages)
        return {
            "success": True,
            "page_count": total_pages,
            "translated_pages": same_pages,
            "full_translated_text": full_text,
            "was_pivoted": False,
            "skipped": True,
            "message": f"Source and target languages are both '{source_lang}'. Translation skipped.",
        }

    recovery_path = get_translation_recovery_path(doc_id)
    translated_pages = []
    any_pivoted = False
    pivot_notes = set()
    start_time = time.time()

    for idx, page in enumerate(pages):
        trans_p = translate_page(page, source_lang, target_lang, translator)
        translated_pages.append(trans_p)
        if trans_p.get("was_pivoted"):
            any_pivoted = True
            if trans_p.get("pivot_notice"):
                pivot_notes.add(trans_p.get("pivot_notice"))

        completed = idx + 1
        elapsed = time.time() - start_time
        avg_per_p = elapsed / completed
        eta_sec = (total_pages - completed) * avg_per_p

        if progress_callback:
            progress_callback(trans_p, completed, total_pages, eta_sec)

        if completed % TRANSLATION_RECOVERY_INTERVAL == 0:
            save_translation_recovery(recovery_path, {
                "doc_id": doc_id,
                "total_pages": total_pages,
                "completed": completed,
                "pages": translated_pages,
            })

    remove_translation_recovery(recovery_path)
    full_text = "\n\n--- Page Break ---\n\n".join(p["translated_text"] for p in translated_pages)

    return {
        "success": True,
        "page_count": total_pages,
        "translated_pages": translated_pages,
        "full_translated_text": full_text,
        "was_pivoted": any_pivoted,
        "pivot_notice": " ".join(pivot_notes),
        "skipped": False,
        "elapsed_seconds": time.time() - start_time,
    }


class TranslationWorkerThread(QThread):
    """
    Background worker thread translating documents page-by-page
    without freezing the UI.
    """
    page_translated = Signal(dict, int, int, float)   # (page_dict, completed, total, eta_sec)
    translation_finished = Signal(dict)              # full_result
    translation_cancelled = Signal(dict)             # partial_result
    translation_error = Signal(str, str)             # (message, instructions)

    def __init__(
        self,
        pages: List[Dict[str, Any]],
        source_lang: str,
        target_lang: str,
        translator: Optional[Translator] = None,
        doc_id: str = "doc",
        parent=None,
    ):
        super().__init__(parent)
        self.pages = pages
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.translator = translator or get_translator("argos")
        self.doc_id = doc_id
        self._is_cancelled = threading.Event()

    def cancel(self):
        """Cancels translation while preserving completed pages."""
        self._is_cancelled.set()

    def is_cancelled(self) -> bool:
        return self._is_cancelled.is_set()

    def run(self):
        total_pages = len(self.pages)
        if total_pages == 0:
            self.translation_finished.emit({
                "success": True,
                "page_count": 0,
                "translated_pages": [],
                "full_translated_text": "",
                "was_pivoted": False,
                "skipped": False,
            })
            return

        # Skip if source == target
        if self.source_lang.lower() == self.target_lang.lower():
            same_pages = [
                translate_page(p, self.source_lang, self.target_lang, self.translator)
                for p in self.pages
            ]
            full_text = "\n\n--- Page Break ---\n\n".join(p["translated_text"] for p in same_pages)
            self.translation_finished.emit({
                "success": True,
                "page_count": total_pages,
                "translated_pages": same_pages,
                "full_translated_text": full_text,
                "was_pivoted": False,
                "skipped": True,
                "message": f"Source and target languages are both '{self.source_lang}'. Translation skipped.",
            })
            return

        # Verify engine availability before starting
        if not self.translator.is_available():
            inst = self.translator.get_installation_instructions((self.source_lang, self.target_lang))
            self.translation_error.emit(
                f"Translation engine '{self.translator.get_name()}' is not installed or available.",
                inst,
            )
            return

        recovery_path = get_translation_recovery_path(self.doc_id)
        translated_pages = []
        any_pivoted = False
        pivot_notes = set()
        start_time = time.time()

        for idx, page in enumerate(self.pages):
            if self._is_cancelled.is_set():
                break

            try:
                trans_p = translate_page(page, self.source_lang, self.target_lang, self.translator)
            except Exception as e:
                trans_p = {
                    "page_number": page.get("page_number", idx + 1),
                    "original_text": page.get("text", ""),
                    "translated_text": f"[Translation error on page {idx+1}: {str(e)}]",
                    "source_language": self.source_lang,
                    "target_language": self.target_lang,
                    "was_pivoted": False,
                    "pivot_notice": "",
                    "word_count": 0,
                    "char_count": 0,
                    "sanity_report": evaluate_translation_sanity("", "", self.source_lang, self.target_lang),
                    "error": str(e),
                }

            translated_pages.append(trans_p)
            if trans_p.get("was_pivoted"):
                any_pivoted = True
                if trans_p.get("pivot_notice"):
                    pivot_notes.add(trans_p.get("pivot_notice"))

            completed = idx + 1
            elapsed = time.time() - start_time
            avg_per_p = elapsed / completed
            eta_sec = (total_pages - completed) * avg_per_p

            self.page_translated.emit(trans_p, completed, total_pages, eta_sec)

            if completed % TRANSLATION_RECOVERY_INTERVAL == 0:
                save_translation_recovery(recovery_path, {
                    "doc_id": self.doc_id,
                    "total_pages": total_pages,
                    "completed": completed,
                    "pages": translated_pages,
                })

        full_text = "\n\n--- Page Break ---\n\n".join(p["translated_text"] for p in translated_pages)
        result_payload = {
            "success": True,
            "page_count": total_pages,
            "completed_count": len(translated_pages),
            "translated_pages": translated_pages,
            "full_translated_text": full_text,
            "was_pivoted": any_pivoted,
            "pivot_notice": " ".join(pivot_notes),
            "was_cancelled": self._is_cancelled.is_set(),
            "elapsed_seconds": time.time() - start_time,
            "skipped": False,
        }

        # Always clean up active document's recovery checkpoint on finish or cancellation
        remove_translation_recovery(recovery_path)

        if self._is_cancelled.is_set():
            self.translation_cancelled.emit(result_payload)
        else:
            self.translation_finished.emit(result_payload)
