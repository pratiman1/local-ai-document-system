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
    TRANSLATION_AGREEMENT_THRESHOLD,
    RECOVERY_DIR,
)
from translation.base_translator import (
    Translator,
    TranslationOutput,
    TranslatorNotAvailableError,
    LanguagePairNotSupportedError,
)
from translation.translator_factory import get_translator
from translation.quality_checker import evaluate_translation_sanity, TranslationSanityReport
from translation.argos_translator import get_language_display_name
from translation.agreement_metric import compute_agreement, AgreementResult


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
    secondary_translator: Optional[Translator] = None,
    compare_mode: bool = False,
    agreement_threshold: float = 0.60,
) -> Dict[str, Any]:
    """
    Translates a single page's text chunk by chunk, maintaining page structure.
    If compare_mode is True and secondary_translator is provided, runs the secondary
    engine sequentially and computes lexical agreement between engines.
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
            "engine": translator.get_name(),
            "was_pivoted": False,
            "pivot_notice": "",
            "word_count": 0,
            "char_count": 0,
            "sanity_report": evaluate_translation_sanity("", "", source_lang, target_lang),
            "skipped": False,
            "comparison": None,
        }

    # Same language skip
    if source_lang.lower() == target_lang.lower():
        return {
            "page_number": p_num,
            "original_text": orig_text,
            "translated_text": orig_text,
            "source_language": source_lang,
            "target_language": target_lang,
            "engine": translator.get_name(),
            "was_pivoted": False,
            "pivot_notice": f"Source and target languages are both '{source_lang}'. Translation skipped.",
            "word_count": len(orig_text.split()),
            "char_count": len(orig_text),
            "sanity_report": evaluate_translation_sanity(orig_text, orig_text, source_lang, target_lang),
            "skipped": True,
            "comparison": None,
        }

    chunks = chunk_text(orig_text)
    translated_chunks = []
    was_pivoted = False
    pivot_notice = ""

    # Primary translation
    for chunk in chunks:
        out: TranslationOutput = translator.translate(chunk, source=source_lang, target=target_lang)
        translated_chunks.append(out.translated_text)
        if out.was_pivoted:
            was_pivoted = True
            pivot_notice = out.notice

    full_translated = "\n\n".join(translated_chunks)
    sanity = evaluate_translation_sanity(orig_text, full_translated, source_lang, target_lang)

    # Optional Sequential Compare Mode (Never run in parallel to protect 8 GB RAM)
    comparison_info = None
    if compare_mode and secondary_translator is not None:
        try:
            sec_translated_chunks = []
            for chunk in chunks:
                sec_out: TranslationOutput = secondary_translator.translate(chunk, source=source_lang, target=target_lang)
                sec_translated_chunks.append(sec_out.translated_text)
            secondary_text = "\n\n".join(sec_translated_chunks)
            agree_res = compute_agreement(full_translated, secondary_text, threshold=agreement_threshold)
            comparison_info = {
                "primary_engine": translator.get_name(),
                "secondary_engine": secondary_translator.get_name(),
                "secondary_text": secondary_text,
                "agreement_score": agree_res.score,
                "score_percent": agree_res.score_percent,
                "is_flagged": agree_res.is_flagged,
                "threshold": agree_res.threshold,
                "word_f1": agree_res.word_f1,
                "chrf_score": agree_res.chrf_score,
                "notice": agree_res.notice,
            }
        except Exception as e:
            comparison_info = {
                "primary_engine": translator.get_name(),
                "secondary_engine": secondary_translator.get_name(),
                "secondary_text": "",
                "agreement_score": 0.0,
                "score_percent": 0.0,
                "is_flagged": True,
                "threshold": agreement_threshold,
                "error": str(e),
                "notice": f"Comparison failed: {str(e)}",
            }

    return {
        "page_number": p_num,
        "original_text": orig_text,
        "translated_text": full_translated,
        "source_language": source_lang,
        "target_language": target_lang,
        "engine": translator.get_name(),
        "was_pivoted": was_pivoted,
        "pivot_notice": pivot_notice,
        "word_count": len(full_translated.split()),
        "char_count": len(full_translated),
        "sanity_report": sanity,
        "skipped": False,
        "comparison": comparison_info,
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
    secondary_translator: Optional[Translator] = None,
    compare_mode: bool = False,
    agreement_threshold: float = 0.60,
    doc_id: str = "doc",
    progress_callback: Optional[Callable[[Dict[str, Any], int, int, float], None]] = None,
) -> Dict[str, Any]:
    """
    Runs document translation synchronously (for CLI / tests).
    Supports sequential Compare Mode across two engines.
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
            "compare_mode": compare_mode,
            "flagged_count": 0,
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
            "compare_mode": False,
            "flagged_count": 0,
        }

    # Verify primary engine availability before starting
    if not translator.is_available():
        inst = translator.get_installation_instructions((source_lang, target_lang))
        raise TranslatorNotAvailableError(
            f"Translation engine '{translator.get_name()}' is not installed or available.",
            instructions=inst,
        )

    # Verify primary language pair support before starting
    if not translator.is_pair_supported(source_lang, target_lang):
        inst = translator.get_installation_instructions((source_lang, target_lang))
        from_name = get_language_display_name(source_lang)
        to_name = get_language_display_name(target_lang)
        if source_lang.lower() == "eng" and target_lang.lower() == "hin":
            err_msg = "English to Hindi offline translation model is not installed."
        else:
            err_msg = f"{from_name} to {to_name} offline translation model is not installed."
        raise LanguagePairNotSupportedError(
            source_lang, target_lang,
            message=err_msg,
            instructions=inst,
        )

    # If Compare Mode requested, verify secondary engine availability
    effective_compare_mode = False
    if compare_mode and secondary_translator is not None:
        if secondary_translator.is_available() and secondary_translator.is_pair_supported(source_lang, target_lang):
            effective_compare_mode = True

    recovery_path = get_translation_recovery_path(doc_id)
    translated_pages = []
    any_pivoted = False
    pivot_notes = set()
    start_time = time.time()

    for idx, page in enumerate(pages):
        trans_p = translate_page(
            page,
            source_lang,
            target_lang,
            translator,
            secondary_translator=secondary_translator if effective_compare_mode else None,
            compare_mode=effective_compare_mode,
            agreement_threshold=agreement_threshold,
        )
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
                "primary_engine": translator.get_name(),
                "compare_mode": effective_compare_mode,
                "pages": translated_pages,
            })

    remove_translation_recovery(recovery_path)
    full_text = "\n\n--- Page Break ---\n\n".join(p["translated_text"] for p in translated_pages)
    flagged_pages = [p for p in translated_pages if p.get("comparison") and p["comparison"].get("is_flagged")]

    return {
        "success": True,
        "page_count": total_pages,
        "translated_pages": translated_pages,
        "full_translated_text": full_text,
        "primary_engine": translator.get_name(),
        "was_pivoted": any_pivoted,
        "pivot_notice": " ".join(pivot_notes),
        "skipped": False,
        "compare_mode": effective_compare_mode,
        "flagged_count": len(flagged_pages),
        "elapsed_seconds": time.time() - start_time,
    }


class TranslationWorkerThread(QThread):
    """
    Background worker thread translating documents page-by-page
    without freezing the UI. Supports sequential Compare Mode.
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
        secondary_translator: Optional[Translator] = None,
        compare_mode: bool = False,
        agreement_threshold: float = 0.60,
        doc_id: str = "doc",
        parent=None,
    ):
        super().__init__(parent)
        self.pages = pages
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.translator = translator or get_translator("argos")
        self.secondary_translator = secondary_translator
        self.compare_mode = compare_mode
        self.agreement_threshold = agreement_threshold
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
                "compare_mode": self.compare_mode,
                "flagged_count": 0,
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
                "compare_mode": False,
                "flagged_count": 0,
            })
            return

        # Verify primary engine availability before starting
        if not self.translator.is_available():
            inst = self.translator.get_installation_instructions((self.source_lang, self.target_lang))
            self.translation_error.emit(
                f"Translation engine '{self.translator.get_name()}' is not installed or available.",
                inst,
            )
            return

        # Verify primary language pair support before starting page processing
        if not self.translator.is_pair_supported(self.source_lang, self.target_lang):
            inst = self.translator.get_installation_instructions((self.source_lang, self.target_lang))
            from_name = get_language_display_name(self.source_lang)
            to_name = get_language_display_name(self.target_lang)
            if self.source_lang.lower() == "eng" and self.target_lang.lower() == "hin":
                err_msg = "English to Hindi offline translation model is not installed."
            else:
                err_msg = f"{from_name} to {to_name} offline translation model is not installed."
            self.translation_error.emit(err_msg, inst)
            return

        # Evaluate effective compare mode
        effective_compare = False
        if self.compare_mode and self.secondary_translator is not None:
            if self.secondary_translator.is_available() and self.secondary_translator.is_pair_supported(self.source_lang, self.target_lang):
                effective_compare = True

        recovery_path = get_translation_recovery_path(self.doc_id)
        translated_pages = []
        any_pivoted = False
        pivot_notes = set()
        start_time = time.time()

        for idx, page in enumerate(self.pages):
            if self._is_cancelled.is_set():
                break

            try:
                trans_p = translate_page(
                    page,
                    self.source_lang,
                    self.target_lang,
                    self.translator,
                    secondary_translator=self.secondary_translator if effective_compare else None,
                    compare_mode=effective_compare,
                    agreement_threshold=self.agreement_threshold,
                )
            except Exception as e:
                trans_p = {
                    "page_number": page.get("page_number", idx + 1),
                    "original_text": page.get("text", ""),
                    "translated_text": f"[Translation error on page {idx+1}: {str(e)}]",
                    "source_language": self.source_lang,
                    "target_language": self.target_lang,
                    "engine": self.translator.get_name(),
                    "was_pivoted": False,
                    "pivot_notice": "",
                    "word_count": 0,
                    "char_count": 0,
                    "sanity_report": evaluate_translation_sanity("", "", self.source_lang, self.target_lang),
                    "comparison": None,
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
                    "primary_engine": self.translator.get_name(),
                    "compare_mode": effective_compare,
                    "pages": translated_pages,
                })

        full_text = "\n\n--- Page Break ---\n\n".join(p["translated_text"] for p in translated_pages)
        flagged_pages = [p for p in translated_pages if p.get("comparison") and p["comparison"].get("is_flagged")]

        result_payload = {
            "success": True,
            "page_count": total_pages,
            "completed_count": len(translated_pages),
            "translated_pages": translated_pages,
            "full_translated_text": full_text,
            "primary_engine": self.translator.get_name(),
            "was_pivoted": any_pivoted,
            "pivot_notice": " ".join(pivot_notes),
            "compare_mode": effective_compare,
            "flagged_count": len(flagged_pages),
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
