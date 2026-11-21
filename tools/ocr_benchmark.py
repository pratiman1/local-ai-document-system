#!/usr/bin/env python3
"""
tools/ocr_benchmark.py
----------------------
CLI benchmarking tool for evaluating OCR engines, rendering DPI settings,
execution speed (throughput / time per page), and accuracy (CER & WER).

Usage:
    python tools/ocr_benchmark.py --pdf document.pdf --ground-truth truth.txt
    python tools/ocr_benchmark.py --pdf document.pdf --dpi 150,300 --ground-truth truth.txt
    python tools/ocr_benchmark.py --pdf document.pdf --engine tesseract --lang hin
"""

import argparse
import math
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymupdf as fitz
from ocr.engine_factory import get_engine, list_available_engines
from ocr.ocr_pipeline import run_ocr_pipeline_sync
from ocr.language_mapping import map_app_lang_to_tesseract
from utils.system_info import get_system_summary
from translation.translation_pipeline import run_translation_pipeline_sync
from translation.language_detector import detect_language_from_text


def compute_levenshtein_distance(seq1: List[Any], seq2: List[Any]) -> int:
    """
    Computes Levenshtein edit distance between two sequences (chars or word tokens)
    using an O(min(N, M)) memory two-row dynamic programming algorithm.
    """
    len1, len2 = len(seq1), len(seq2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1

    # Keep seq2 as the shorter sequence to minimize row memory
    if len2 > len1:
        seq1, seq2 = seq2, seq1
        len1, len2 = len2, len1

    prev_row = list(range(len2 + 1))
    curr_row = [0] * (len2 + 1)

    for i in range(len1):
        curr_row[0] = i + 1
        elem1 = seq1[i]
        for j in range(len2):
            cost = 0 if elem1 == seq2[j] else 1
            curr_row[j + 1] = min(
                curr_row[j] + 1,       # insertion
                prev_row[j + 1] + 1,   # deletion
                prev_row[j] + cost     # substitution
            )
        prev_row, curr_row = curr_row, prev_row

    return prev_row[len2]


def calculate_cer_and_wer(predicted_text: str, ground_truth_text: str) -> Dict[str, float]:
    """
    Calculates Character Error Rate (CER) and Word Error Rate (WER) against ground truth.

    Returns:
        dict: Containing 'cer', 'wer', 'char_accuracy', 'word_accuracy',
              'gt_char_count', 'pred_char_count', 'gt_word_count', 'pred_word_count'.
    """
    gt_chars = list(ground_truth_text.strip())
    pred_chars = list(predicted_text.strip())

    gt_words = ground_truth_text.strip().split()
    pred_words = predicted_text.strip().split()

    char_dist = compute_levenshtein_distance(pred_chars, gt_chars)
    word_dist = compute_levenshtein_distance(pred_words, gt_words)

    gt_char_len = max(1, len(gt_chars))
    gt_word_len = max(1, len(gt_words))

    cer = min(1.0, char_dist / gt_char_len)
    wer = min(1.0, word_dist / gt_word_len)

    return {
        "cer": cer,
        "wer": wer,
        "char_accuracy": max(0.0, 1.0 - cer),
        "word_accuracy": max(0.0, 1.0 - wer),
        "char_distance": char_dist,
        "word_distance": word_dist,
        "gt_char_count": len(gt_chars),
        "pred_char_count": len(pred_chars),
        "gt_word_count": len(gt_words),
        "pred_word_count": len(pred_words),
    }


def calculate_smoothed_bleu(hypothesis: str, reference: str, max_n: int = 4) -> float:
    """
    Computes smoothed BLEU-4 score (Brevity Penalty * geometric mean of n-gram precisions)
    using pure-Python operations without external NLP dependencies.
    Uses Chen & Cherry smoothing method 1 for zero counts.
    """
    hyp_tokens = hypothesis.strip().split()
    ref_tokens = reference.strip().split()
    c = len(hyp_tokens)
    r = len(ref_tokens)
    if c == 0 or r == 0:
        return 0.0

    # Brevity Penalty: bp = min(1.0, exp(1 - r / c))
    bp = 1.0 if c >= r else math.exp(1.0 - (r / c))

    log_prec_sum = 0.0
    weight = 1.0 / max_n

    for n in range(1, max_n + 1):
        hyp_ngrams = [tuple(hyp_tokens[i : i + n]) for i in range(len(hyp_tokens) - n + 1)]
        ref_ngrams = [tuple(ref_tokens[i : i + n]) for i in range(len(ref_tokens) - n + 1)]

        total_hyp_ngrams = len(hyp_ngrams)
        if total_hyp_ngrams == 0:
            # Short text penalty smoothing
            prec = 1.0 / (c + 1)
        else:
            hyp_counts = Counter(hyp_ngrams)
            ref_counts = Counter(ref_ngrams)
            clipped = sum(min(count, ref_counts[ng]) for ng, count in hyp_counts.items())
            if clipped == 0:
                # Smoothing method 1: epsilon smoothing
                prec = 1.0 / (2**n * total_hyp_ngrams)
            else:
                prec = clipped / total_hyp_ngrams

        log_prec_sum += weight * math.log(max(1e-9, prec))

    bleu = bp * math.exp(log_prec_sum)
    return max(0.0, min(1.0, bleu))


def run_benchmark_for_config(
    pdf_path: str,
    ground_truth_text: Optional[str],
    dpi: int,
    engine_name: str,
    lang: str,
    workers: Optional[int],
    translate_target: Optional[str] = None,
    ref_translation_text: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes a single benchmark run with specified DPI and engine configuration.
    Optionally evaluates offline translation pipeline and BLEU / CER / WER metrics.
    """
    engine = get_engine(engine_name)
    tess_lang = map_app_lang_to_tesseract(lang)

    start_time = time.perf_counter()
    result = run_ocr_pipeline_sync(
        pdf_path=pdf_path,
        target_lang=tess_lang,
        dpi=dpi,
        max_workers=workers,
        engine=engine,
    )
    elapsed = time.perf_counter() - start_time

    page_count = result.get("page_count", 0)
    avg_per_page = elapsed / max(1, page_count)
    throughput_ppm = (page_count / elapsed) * 60.0 if elapsed > 0 else 0.0

    eval_data: Dict[str, Any] = {
        "dpi": dpi,
        "engine": engine_name,
        "lang": lang,
        "page_count": page_count,
        "direct_pages": result.get("direct_pages", 0),
        "ocr_pages": result.get("ocr_pages", 0),
        "total_seconds": elapsed,
        "avg_seconds_per_page": avg_per_page,
        "throughput_ppm": throughput_ppm,
        "has_ground_truth": ground_truth_text is not None,
    }

    if ground_truth_text:
        acc_metrics = calculate_cer_and_wer(result.get("full_text", ""), ground_truth_text)
        eval_data.update(acc_metrics)

    # Optional translation evaluation
    if translate_target:
        eval_data["translate_target"] = translate_target
        pages = result.get("pages", [])
        if not pages and result.get("full_text"):
            pages = [{"page_number": 1, "text": result.get("full_text")}]

        # Detect source language if needed
        det = detect_language_from_text(result.get("full_text", ""))
        source_code = det.language_code if det.confidence >= 0.7 else lang

        trans_start = time.perf_counter()
        try:
            trans_res = run_translation_pipeline_sync(
                pages=pages,
                source_lang=source_code,
                target_lang=translate_target,
            )
            trans_elapsed = time.perf_counter() - trans_start
            full_trans_text = trans_res.get("full_translated_text", "")
            eval_data["translation_seconds"] = trans_elapsed
            eval_data["full_translated_text"] = full_trans_text
            eval_data["was_pivoted"] = trans_res.get("was_pivoted", False)
            eval_data["pivot_notice"] = trans_res.get("pivot_notice", "")

            if ref_translation_text:
                bleu = calculate_smoothed_bleu(full_trans_text, ref_translation_text)
                trans_acc = calculate_cer_and_wer(full_trans_text, ref_translation_text)
                eval_data["bleu_4"] = bleu
                eval_data["trans_cer"] = trans_acc["cer"]
                eval_data["trans_wer"] = trans_acc["wer"]
                eval_data["has_ref_translation"] = True
        except Exception as e:
            eval_data["translation_error"] = str(e)

    return eval_data


def print_benchmark_report(
    runs: List[Dict[str, Any]],
    pdf_path: str,
    ground_truth_path: Optional[str],
    ref_translation_path: Optional[str] = None,
):
    """
    Prints a clean, formatted terminal summary table of benchmark results.
    """
    sys_summary = get_system_summary()
    os_label = sys_summary.get("os_version", sys_summary.get("os_name", "Unknown OS"))
    arch_label = sys_summary.get("arch", "Unknown Arch")
    ram_label = sys_summary.get("ram", "Unknown RAM")

    print("\n" + "=" * 70)
    print("📊 LOCAL OCR PERFORMANCE & ACCURACY BENCHMARK REPORT")
    print("=" * 70)
    print(f"Host System:       {os_label} ({arch_label}) | RAM: {ram_label}")
    print(f"Document File:     {Path(pdf_path).name}")
    if ground_truth_path:
        print(f"Ground Truth File: {Path(ground_truth_path).name}")
    if ref_translation_path:
        print(f"Ref Translation:   {Path(ref_translation_path).name}")
    print("-" * 70)

    for i, run in enumerate(runs, 1):
        print(f"\nConfiguration #{i}: Engine: {run['engine']} | DPI: {run['dpi']} | Language: {run['lang']}")
        print(f"  Pages Processed: {run['page_count']} (Direct: {run['direct_pages']}, OCR: {run['ocr_pages']})")
        print(f"  Total Time:      {run['total_seconds']:.2f} s")
        print(f"  Time Per Page:   {run['avg_seconds_per_page']:.3f} s / page")
        print(f"  Throughput:      {run['throughput_ppm']:.1f} pages / minute")

        if run.get("has_ground_truth", False):
            print(f"  --- Accuracy Evaluation vs Ground Truth ---")
            print(f"  Ground Truth:    {run['gt_char_count']:,} chars | {run['gt_word_count']:,} words")
            print(f"  Extracted:       {run['pred_char_count']:,} chars | {run['pred_word_count']:,} words")
            print(f"  CER (Char Err):  {run['cer'] * 100:.2f}%  (Char Accuracy: {run['char_accuracy'] * 100:.2f}%)")
            print(f"  WER (Word Err):  {run['wer'] * 100:.2f}%  (Word Accuracy: {run['word_accuracy'] * 100:.2f}%)")

        if run.get("translate_target"):
            print(f"  --- Offline Translation Evaluation (Target: {run['translate_target']}) ---")
            if "translation_error" in run:
                print(f"  Translation Note: {run['translation_error']}")
            else:
                print(f"  Translation Time: {run.get('translation_seconds', 0.0):.2f} s")
                if run.get("was_pivoted"):
                    print(f"  Pivot Route:     Pivoted via English")
                if run.get("has_ref_translation"):
                    print(f"  Smoothed BLEU-4: {run['bleu_4'] * 100:.2f}%")
                    print(f"  Trans CER (Err): {run['trans_cer'] * 100:.2f}%")
                    print(f"  Trans WER (Err): {run['trans_wer'] * 100:.2f}%")

    # If multiple configurations were compared, print a compact comparison table
    if len(runs) > 1:
        print("\n" + "-" * 70)
        print("📈 COMPARISON SUMMARY")
        print("-" * 70)
        header = f"{'Engine':<12} {'DPI':<6} {'Total Time':<12} {'Per Page':<12} {'Throughput':<14}"
        if runs[0].get("has_ground_truth", False):
            header += f" {'CER':<10} {'WER':<10}"
        print(header)
        print("-" * len(header))

        for r in runs:
            row = f"{r['engine']:<12} {r['dpi']:<6} {r['total_seconds']:>8.2f} s   {r['avg_seconds_per_page']:>8.3f} s   {r['throughput_ppm']:>7.1f} p/min"
            if r.get("has_ground_truth", False):
                row += f"   {r['cer'] * 100:>6.2f}%    {r['wer'] * 100:>6.2f}%"
            print(row)

    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Local AI Document System - Offline OCR Performance and Accuracy Benchmark"
    )
    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Path to the PDF document to benchmark",
    )
    parser.add_argument(
        "--ground-truth",
        type=str,
        default=None,
        help="Optional path to a ground-truth plain text file for CER/WER accuracy scoring",
    )
    parser.add_argument(
        "--dpi",
        type=str,
        default="300",
        help="Rendering DPI setting or comma-separated list to compare (e.g., '150,300'). Default: 300",
    )
    parser.add_argument(
        "--engine",
        type=str,
        default="tesseract",
        help=f"OCR engine to evaluate. Available: {list_available_engines()}. Default: tesseract",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="eng",
        help="Target language code (e.g., 'eng', 'hin'). Default: eng",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel page workers (default: auto RAM/CPU bounded)",
    )
    parser.add_argument(
        "--translate-target",
        type=str,
        default=None,
        help="Optional target language code for translation evaluation (e.g., 'hin', 'tam', 'eng')",
    )
    parser.add_argument(
        "--ref-translation",
        type=str,
        default=None,
        help="Optional path to a reference translation plain text file for BLEU/CER/WER accuracy scoring",
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.is_file():
        print(f"Error: PDF file not found at: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    ground_truth_text = None
    if args.ground_truth:
        gt_path = Path(args.ground_truth).resolve()
        if not gt_path.is_file():
            print(f"Error: Ground truth file not found at: {gt_path}", file=sys.stderr)
            sys.exit(1)
        with open(gt_path, "r", encoding="utf-8") as f:
            ground_truth_text = f.read()

    ref_translation_text = None
    if args.ref_translation:
        ref_path = Path(args.ref_translation).resolve()
        if not ref_path.is_file():
            print(f"Error: Reference translation file not found at: {ref_path}", file=sys.stderr)
            sys.exit(1)
        with open(ref_path, "r", encoding="utf-8") as f:
            ref_translation_text = f.read()

    # Parse DPI list
    try:
        dpi_list = [int(d.strip()) for d in args.dpi.split(",") if d.strip()]
    except ValueError:
        print(f"Error: Invalid --dpi argument '{args.dpi}'. Must be integer(s), e.g. 150,300", file=sys.stderr)
        sys.exit(1)

    print(f"Starting benchmark for {pdf_path.name}...")
    runs = []
    for dpi in dpi_list:
        print(f"Running evaluation at {dpi} DPI with engine '{args.engine}'...")
        run_res = run_benchmark_for_config(
            pdf_path=str(pdf_path),
            ground_truth_text=ground_truth_text,
            dpi=dpi,
            engine_name=args.engine,
            lang=args.lang,
            workers=args.workers,
            translate_target=args.translate_target,
            ref_translation_text=ref_translation_text,
        )
        runs.append(run_res)

    print_benchmark_report(runs, str(pdf_path), args.ground_truth, args.ref_translation)


if __name__ == "__main__":
    main()
