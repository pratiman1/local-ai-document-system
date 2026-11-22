"""
tools/translation_benchmark.py
------------------------------
Translation benchmark utility comparing Argos Translate and AI4Bharat IndicTrans2.
Evaluates:
- Execution speed (seconds per page / chunk).
- Lexical agreement (chrF score & Word F1).
- BLEU-4 score against reference human translations.

Can be run directly via CLI:
  python tools/translation_benchmark.py
"""

import sys
import time
import argparse
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from typing import List, Dict, Any, Tuple
from translation.translator_factory import get_translator
from translation.agreement_metric import compute_agreement
from tools.ocr_benchmark import calculate_smoothed_bleu


BENCHMARK_SAMPLES: List[Dict[str, Any]] = [
    {
        "id": "sample_1_en_hi",
        "source_lang": "eng",
        "target_lang": "hin",
        "source_text": (
            "The quick brown fox jumps over the lazy dog. "
            "Artificial intelligence and local machine translation ensure complete privacy and zero data leakage."
        ),
        "reference_text": (
            "तेज़ भूरी लोमड़ी आलसी कुत्ते के ऊपर से कूदती है। "
            "कृत्रिम बुद्धिमत्ता और स्थानीय मशीन अनुवाद पूर्ण गोपनीयता और शून्य डेटा रिसाव सुनिश्चित करते हैं।"
        ),
    },
    {
        "id": "sample_2_hi_ta",
        "source_lang": "hin",
        "target_lang": "tam",
        "source_text": (
            "यह दस्तावेज़ पूरी तरह से गोपनीय है। सभी पृष्ठ स्थानीय कंप्यूटर पर संसाधित होते हैं।"
        ),
        "reference_text": (
            "இந்த ஆவணம் முற்றிலும் ரகசியமானது. அனைத்து பக்கங்களும் உள்ளூர் கணினியில் செயலாக்கப்படுகின்றன."
        ),
    },
    {
        "id": "sample_3_en_mr",
        "source_lang": "eng",
        "target_lang": "mar",
        "source_text": (
            "Digital governance and multilingual accessibility empower every citizen across all states."
        ),
        "reference_text": (
            "डिजिटल शासन आणि बहुभाषिक सुलभता सर्व राज्यांमधील प्रत्येक नागरिकाला सक्षम करते."
        ),
    },
]


def run_benchmark(verbose: bool = True) -> List[Dict[str, Any]]:
    """
    Runs benchmark suite across Argos Translate and IndicTrans2.
    """
    argos = get_translator("argos")
    indic = get_translator("indictrans2")

    results = []

    if verbose:
        print("=" * 80)
        print("📊 LOCAL AI DOCUMENT SYSTEM — OFFLINE TRANSLATION BENCHMARK SUITE")
        print("=" * 80)
        print(f"Argos Translate Available:    {argos.is_available()}")
        print(f"IndicTrans2 Engine Available: {indic.is_available()}")
        print("-" * 80)

    for idx, sample in enumerate(BENCHMARK_SAMPLES, start=1):
        src = sample["source_lang"]
        tgt = sample["target_lang"]
        src_text = sample["source_text"]
        ref_text = sample["reference_text"]

        res = {
            "sample_id": sample["id"],
            "source": src,
            "target": tgt,
            "argos_supported": argos.is_pair_supported(src, tgt),
            "indic_supported": indic.is_pair_supported(src, tgt),
            "argos_time": None,
            "indic_time": None,
            "argos_bleu": None,
            "indic_bleu": None,
            "agreement": None,
        }

        # 1. Benchmark Argos
        argos_out = ""
        if res["argos_supported"] and argos.is_available():
            t0 = time.time()
            try:
                out = argos.translate(src_text, src, tgt)
                argos_out = out.translated_text
                res["argos_time"] = time.time() - t0
                res["argos_bleu"] = calculate_smoothed_bleu(argos_out, ref_text) * 100.0
            except Exception as e:
                res["argos_error"] = str(e)

        # 2. Benchmark IndicTrans2
        indic_out = ""
        if res["indic_supported"] and indic.is_available():
            t0 = time.time()
            try:
                out = indic.translate(src_text, src, tgt)
                indic_out = out.translated_text
                res["indic_time"] = time.time() - t0
                res["indic_bleu"] = calculate_smoothed_bleu(indic_out, ref_text) * 100.0
            except Exception as e:
                res["indic_error"] = str(e)

        # 3. Calculate Cross-Engine Agreement
        if argos_out and indic_out:
            agree = compute_agreement(indic_out, argos_out)
            res["agreement"] = agree.score_percent

        results.append(res)

        if verbose:
            argos_time_str = f"{res['argos_time']:.3f}s" if res['argos_time'] is not None else "N/A"
            argos_bleu_str = f"{res['argos_bleu']:.2f}%" if res['argos_bleu'] is not None else "N/A"
            indic_time_str = f"{res['indic_time']:.3f}s" if res['indic_time'] is not None else "N/A"
            indic_bleu_str = f"{res['indic_bleu']:.2f}%" if res['indic_bleu'] is not None else "N/A"

            print(f"[{idx}/{len(BENCHMARK_SAMPLES)}] {src} ➔ {tgt}:")
            print(f"  • Argos:       Installed={res['argos_supported']} | Time={argos_time_str} | BLEU={argos_bleu_str}")
            print(f"  • IndicTrans2: Installed={res['indic_supported']} | Time={indic_time_str} | BLEU={indic_bleu_str}")
            if res["agreement"] is not None:
                print(f"  • Agreement (IndicTrans2 vs Argos): {res['agreement']:.1f}%")
            print("-" * 80)

    if verbose:
        print("✅ Benchmark completed successfully.")
        print("=" * 80)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translation Benchmark Suite")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose stdout")
    args = parser.parse_args()
    run_benchmark(verbose=not args.quiet)
