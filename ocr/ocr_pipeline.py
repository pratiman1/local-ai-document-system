"""
ocr/ocr_pipeline.py
-------------------
High-performance, memory-bounded document OCR pipeline.
Coordinates:
1. Smart page handling: digital text extraction vs. scanned page OCR.
2. Parallel streaming rendering with strict bounded memory.
3. Light contrast preprocessing with conditional deep cleanup.
4. Dynamic RAM-aware worker pool sizing.
5. Periodic recovery checkpointing every N pages.
6. Non-blocking QThread worker for responsive UI execution.
"""

import gc
import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Callable

from PIL import Image, ImageOps, ImageStat, ImageFilter, ImageEnhance
import pymupdf as fitz
from PySide6.QtCore import QThread, Signal

from config.settings import (
    OCR_DEFAULT_DPI,
    OCR_MIN_TEXT_CHARS,
    OCR_MAX_WORKERS,
    OCR_RECOVERY_INTERVAL,
    RECOVERY_DIR,
)
from ocr.base_engine import OCREngine
from ocr.engine_factory import get_engine
from ocr.language_mapping import map_app_lang_to_tesseract


# ==============================================================================
# 1. SMART PAGE HANDLING & PREPROCESSING
# ==============================================================================

def page_has_selectable_text(page: fitz.Page, min_chars: int = OCR_MIN_TEXT_CHARS) -> Tuple[bool, str]:
    """
    Checks if a PDF page already contains real selectable digital text.

    Returns:
        (True, text) if selectable text meets threshold, skipping OCR.
        (False, "") if page is scanned or image-only.
    """
    try:
        raw_text = page.get_text()
        stripped = raw_text.strip()
        # Count non-whitespace characters to filter out stray artifacts
        char_count = len([c for c in stripped if not c.isspace()])
        if char_count >= min_chars:
            return True, raw_text
    except Exception:
        pass
    return False, ""


def render_page_to_image(page: fitz.Page, dpi: int = OCR_DEFAULT_DPI) -> Image.Image:
    """
    Renders a single PDF page to a high-resolution PIL RGB Image at the specified DPI.
    Immediately releases the underlying PyMuPDF pixmap from memory.
    """
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    del pix
    return img


def preprocess_image(image: Image.Image) -> Image.Image:
    """
    Applies light, accuracy-preserving image preprocessing:
    1. Grayscale conversion.
    2. Histogram contrast stretching.
    3. Conditional adaptive cleanup (sharpening + contrast) ONLY for degraded/washed-out pages.
    Never downscales or compresses, preserving maximum OCR character fidelity.
    """
    # 1. Grayscale
    gray = image.convert("L")

    # 2. Light contrast enhancement (clip 1% extremes)
    enhanced = ImageOps.autocontrast(gray, cutoff=1)

    # 3. Assess quality for conditional heavier cleanup
    stat = ImageStat.Stat(enhanced)
    stddev = stat.stddev[0] if stat.stddev else 50.0
    mean_val = stat.mean[0] if stat.mean else 128.0

    # Low contrast / washed out or extreme brightness
    if stddev < 30.0 or mean_val < 45.0 or mean_val > 225.0:
        enhanced = enhanced.filter(ImageFilter.SHARPEN)
        contrast_enhancer = ImageEnhance.Contrast(enhanced)
        enhanced = contrast_enhancer.enhance(1.4)

    return enhanced


def get_optimal_worker_count(configured_max: int = OCR_MAX_WORKERS) -> int:
    """
    Dynamically sizes the parallel worker pool based on available system RAM
    and CPU cores to prevent memory pressure on 8 GB RAM machines.
    """
    base_workers = max(1, min(configured_max, (os.cpu_count() or 2) - 1))

    try:
        import psutil
        avail_gb = psutil.virtual_memory().available / (1024 ** 3)
        if avail_gb < 1.5:
            return 1
        elif avail_gb < 3.0:
            return min(2, base_workers)
    except Exception:
        pass

    return base_workers


# ==============================================================================
# 2. SINGLE PAGE PROCESSING WORKER TASK
# ==============================================================================

def process_single_page(
    pdf_path: str,
    page_num: int,       # 1-indexed
    target_lang: str,
    dpi: int = OCR_DEFAULT_DPI,
    min_chars: int = OCR_MIN_TEXT_CHARS,
    engine: Optional[OCREngine] = None,
) -> Dict[str, Any]:
    """
    Self-contained worker function to process one PDF page.
    Opens its own read-only PyMuPDF handle, checks for digital text,
    and falls back to streaming OCR if scanned.
    """
    if engine is None:
        engine = get_engine("tesseract")

    doc = None
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num - 1]

        # 1. Check for real selectable text
        has_text, text = page_has_selectable_text(page, min_chars=min_chars)
        if has_text:
            doc.close()
            return {
                "page_number": page_num,
                "text": text,
                "source": "direct",
                "ocr_confidence": 100.0,
                "word_count": len(text.split()),
                "char_count": len(text),
                "error": None,
            }

        # 2. Scanned / image-only page requires OCR
        if not engine.is_available():
            doc.close()
            inst = engine.get_installation_instructions()
            placeholder = (
                f"[Page {page_num}: Scanned Image — OCR Engine Not Available]\n\n"
                f"{inst}"
            )
            return {
                "page_number": page_num,
                "text": placeholder,
                "source": "ocr_unavailable",
                "word_count": 0,
                "char_count": 0,
                "error": "OCR engine not available",
            }

        # 3. Render at specified DPI
        raw_img = render_page_to_image(page, dpi=dpi)
        doc.close()
        doc = None

        actual_target_lang = target_lang
        if target_lang in ("auto", "detect"):
            try:
                from translation.language_detector import detect_script_from_scanned_page, SCRIPT_TO_DEFAULT_LANG
                det_script = detect_script_from_scanned_page(raw_img)
                actual_target_lang = SCRIPT_TO_DEFAULT_LANG.get(det_script, "eng")
            except Exception:
                actual_target_lang = "eng"

        tess_lang = map_app_lang_to_tesseract(actual_target_lang)
        if not engine.is_language_installed(tess_lang):
            inst = engine.get_installation_instructions(missing_lang=tess_lang)
            placeholder = (
                f"[Page {page_num}: Scanned Image — Language Pack '{tess_lang}' Not Installed]\n\n"
                f"{inst}"
            )
            del raw_img
            return {
                "page_number": page_num,
                "text": placeholder,
                "source": "ocr_lang_missing",
                "word_count": 0,
                "char_count": 0,
                "error": f"Language pack '{tess_lang}' not installed",
            }

        prep_img = preprocess_image(raw_img)
        del raw_img

        ocr_conf = 85.0
        try:
            if hasattr(engine, "recognize_with_confidence"):
                ocr_text, ocr_conf = engine.recognize_with_confidence(prep_img, language=tess_lang)
            else:
                ocr_text = engine.recognize(prep_img, language=tess_lang)
        except Exception as ocr_err:
            ocr_text = f"[OCR Error on page {page_num}: {str(ocr_err)}]"
            ocr_conf = 0.0

        del prep_img
        gc.collect()

        return {
            "page_number": page_num,
            "text": ocr_text,
            "source": "ocr",
            "ocr_confidence": ocr_conf,
            "word_count": len(ocr_text.split()),
            "char_count": len(ocr_text),
            "error": None,
        }

    except Exception as e:
        if doc:
            try:
                doc.close()
            except Exception:
                pass
        return {
            "page_number": page_num,
            "text": f"[Error reading page {page_num}: {str(e)}]",
            "source": "error",
            "word_count": 0,
            "char_count": 0,
            "error": str(e),
        }


# ==============================================================================
# 3. RECOVERY CHECKPOINT MANAGEMENT
# ==============================================================================

def get_recovery_file_path(pdf_path: str) -> Path:
    """Returns the dedicated recovery JSON checkpoint path for a document."""
    stem = Path(pdf_path).stem
    safe_stem = "".join(c for c in stem if c.isalnum() or c in ("-", "_"))
    return RECOVERY_DIR / f".recovery_{safe_stem}.json"


def save_recovery_checkpoint(recovery_path: Path, state: Dict[str, Any]):
    """Saves partial results atomically to disk to prevent loss on crash."""
    try:
        tmp_path = recovery_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp_path.replace(recovery_path)
    except Exception:
        pass


def remove_recovery_checkpoint(recovery_path: Path):
    """Deletes recovery file upon successful completion."""
    try:
        if recovery_path.is_file():
            recovery_path.unlink()
    except Exception:
        pass


# ==============================================================================
# 4. SYNCHRONOUS PIPELINE RUNNER (FOR BENCHMARKS & TESTS)
# ==============================================================================

def run_ocr_pipeline_sync(
    pdf_path: str,
    target_lang: str = "eng",
    dpi: int = OCR_DEFAULT_DPI,
    max_workers: Optional[int] = None,
    engine: Optional[OCREngine] = None,
    progress_callback: Optional[Callable[[Dict[str, Any], int, int, float], None]] = None,
) -> Dict[str, Any]:
    """
    Executes the OCR pipeline synchronously.
    Used by CLI benchmark tools and automated integration test suites.
    """
    if engine is None:
        engine = get_engine("tesseract")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    if total_pages == 0:
        return {
            "success": False,
            "page_count": 0,
            "pages": [],
            "full_text": "",
            "is_empty": True,
            "direct_pages": 0,
            "ocr_pages": 0,
            "error": "Document contains 0 pages.",
        }

    workers = max_workers if max_workers is not None else get_optimal_worker_count()
    recovery_path = get_recovery_file_path(pdf_path)

    results_ordered: List[Optional[Dict[str, Any]]] = [None] * total_pages
    completed_count = 0
    direct_count = 0
    ocr_count = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                process_single_page,
                pdf_path,
                p_idx + 1,
                target_lang,
                dpi,
                OCR_MIN_TEXT_CHARS,
                engine,
            ): p_idx
            for p_idx in range(total_pages)
        }

        for future in as_completed(futures):
            p_idx = futures[future]
            page_data = future.result()
            results_ordered[p_idx] = page_data
            completed_count += 1

            if page_data.get("source") == "direct":
                direct_count += 1
            else:
                ocr_count += 1

            elapsed = time.time() - start_time
            avg_per_page = elapsed / completed_count
            eta_seconds = (total_pages - completed_count) * avg_per_page

            if progress_callback:
                progress_callback(page_data, completed_count, total_pages, eta_seconds)

            # Checkpoint every N pages
            if completed_count % OCR_RECOVERY_INTERVAL == 0:
                valid_pages = [p for p in results_ordered if p is not None]
                save_recovery_checkpoint(recovery_path, {
                    "pdf_path": pdf_path,
                    "total_pages": total_pages,
                    "completed_count": completed_count,
                    "pages": valid_pages,
                })

    # Cleanup recovery checkpoint on full success
    remove_recovery_checkpoint(recovery_path)

    valid_pages = [p for p in results_ordered if p is not None]
    full_text = "\n\n--- Page Break ---\n\n".join(p.get("text", "") for p in valid_pages)

    return {
        "success": True,
        "page_count": total_pages,
        "pages": valid_pages,
        "full_text": full_text,
        "is_empty": not bool(full_text.strip()),
        "direct_pages": direct_count,
        "ocr_pages": ocr_count,
        "elapsed_seconds": time.time() - start_time,
        "error": None,
    }


# ==============================================================================
# 5. ASYNCHRONOUS QTHREAD WORKER (FOR DESKTOP UI)
# ==============================================================================

class OCRWorkerThread(QThread):
    """
    Background worker thread running OCR across multi-page documents (up to 400 pages)
    without freezing the PySide6 UI.
    """

    page_completed = Signal(dict, int, int, float)  # (page_dict, completed_count, total_pages, eta_sec)
    pipeline_finished = Signal(dict)                # full_result
    pipeline_cancelled = Signal(dict)               # partial_result
    pipeline_error = Signal(str, str)               # (error_message, instructions)

    def __init__(
        self,
        pdf_path: str,
        target_lang: str = "eng",
        dpi: int = OCR_DEFAULT_DPI,
        max_workers: Optional[int] = None,
        engine: Optional[OCREngine] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.target_lang = target_lang
        self.dpi = dpi
        self.max_workers = max_workers or get_optimal_worker_count()
        self.engine = engine or get_engine("tesseract")
        self._is_cancelled = threading.Event()

    def cancel(self):
        """Signals the worker to cancel processing and finalize partial results."""
        self._is_cancelled.set()

    def is_cancelled(self) -> bool:
        return self._is_cancelled.is_set()

    def run(self):
        """Thread entry point."""
        try:
            doc = fitz.open(self.pdf_path)
            total_pages = len(doc)
            doc.close()
        except Exception as e:
            self.pipeline_error.emit(f"Failed to open PDF document:\n{str(e)}", "")
            return

        if total_pages == 0:
            self.pipeline_finished.emit({
                "success": False,
                "page_count": 0,
                "pages": [],
                "full_text": "",
                "is_empty": True,
                "direct_pages": 0,
                "ocr_pages": 0,
                "error": "The document contains 0 pages.",
            })
            return

        recovery_path = get_recovery_file_path(self.pdf_path)
        results_ordered: List[Optional[Dict[str, Any]]] = [None] * total_pages
        completed_count = 0
        direct_count = 0
        ocr_count = 0
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks in a streaming window to keep memory strictly bounded
            # Max tasks in flight = max_workers * 2
            future_to_page: Dict[Any, int] = {}
            page_cursor = 0
            window_size = self.max_workers * 2

            # Seed the window
            while page_cursor < total_pages and len(future_to_page) < window_size:
                fut = executor.submit(
                    process_single_page,
                    self.pdf_path,
                    page_cursor + 1,
                    self.target_lang,
                    self.dpi,
                    OCR_MIN_TEXT_CHARS,
                    self.engine,
                )
                future_to_page[fut] = page_cursor
                page_cursor += 1

            while future_to_page:
                if self._is_cancelled.is_set():
                    # User clicked Cancel: drain current tasks and stop submitting new ones
                    for fut in list(future_to_page.keys()):
                        if fut.done():
                            p_idx = future_to_page.pop(fut)
                            try:
                                res = fut.result()
                                results_ordered[p_idx] = res
                            except Exception:
                                pass
                        else:
                            fut.cancel()
                    break

                # Wait for the next completed future
                for fut in as_completed(list(future_to_page.keys())):
                    p_idx = future_to_page.pop(fut)
                    page_data = fut.result()
                    results_ordered[p_idx] = page_data
                    completed_count += 1

                    if page_data.get("source") == "direct":
                        direct_count += 1
                    else:
                        ocr_count += 1

                    elapsed = time.time() - start_time
                    avg_per_page = elapsed / completed_count
                    eta_seconds = (total_pages - completed_count) * avg_per_page

                    # Emit incremental page completion signal
                    self.page_completed.emit(page_data, completed_count, total_pages, eta_seconds)

                    # Periodic recovery checkpoint
                    if completed_count % OCR_RECOVERY_INTERVAL == 0:
                        valid_pages = [p for p in results_ordered if p is not None]
                        save_recovery_checkpoint(recovery_path, {
                            "pdf_path": self.pdf_path,
                            "total_pages": total_pages,
                            "completed_count": completed_count,
                            "pages": valid_pages,
                        })

                    # Refill the sliding window if not cancelled
                    if not self._is_cancelled.is_set() and page_cursor < total_pages:
                        new_fut = executor.submit(
                            process_single_page,
                            self.pdf_path,
                            page_cursor + 1,
                            self.target_lang,
                            self.dpi,
                            OCR_MIN_TEXT_CHARS,
                            self.engine,
                        )
                        future_to_page[new_fut] = page_cursor
                        page_cursor += 1

                    # Break inner loop to re-evaluate cancellation and active tasks
                    break

        valid_pages = [p for p in results_ordered if p is not None]
        full_text = "\n\n--- Page Break ---\n\n".join(p.get("text", "") for p in valid_pages)

        result_payload = {
            "success": True,
            "page_count": total_pages,
            "completed_count": len(valid_pages),
            "pages": valid_pages,
            "full_text": full_text,
            "is_empty": not bool(full_text.strip()),
            "direct_pages": direct_count,
            "ocr_pages": ocr_count,
            "elapsed_seconds": time.time() - start_time,
            "was_cancelled": self._is_cancelled.is_set(),
            "error": None,
        }

        # Always clean up active document's recovery checkpoint on finish or cancellation
        remove_recovery_checkpoint(recovery_path)

        if self._is_cancelled.is_set():
            self.pipeline_cancelled.emit(result_payload)
        else:
            self.pipeline_finished.emit(result_payload)
