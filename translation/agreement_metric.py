"""
translation/agreement_metric.py
-------------------------------
Calculates agreement and lexical consensus between translation engines (e.g. Argos vs IndicTrans2)
for Compare Mode.

Uses a combination of word token F1 score and character n-gram overlap (chrF-style)
without requiring heavy external dependencies.

Disclosure:
"Agreement indicator, not an accuracy score; two models can agree and still be wrong."
"""

import re
from typing import Dict, Any, List, Set
from collections import Counter
from dataclasses import dataclass

AGREEMENT_NOTICE = "Agreement indicator, not an accuracy score; two models can agree and still be wrong."


@dataclass
class AgreementResult:
    """Detailed result of translation agreement between primary and secondary engines."""
    score: float             # 0.0 to 1.0
    score_percent: float     # 0.0 to 100.0%
    is_flagged: bool         # True if score < threshold
    threshold: float         # Configured threshold (e.g. 0.60)
    word_f1: float           # Token-level overlap F1
    chrf_score: float        # Character n-gram overlap
    primary_words: int
    secondary_words: int
    notice: str = AGREEMENT_NOTICE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "score_percent": round(self.score_percent, 2),
            "is_flagged": self.is_flagged,
            "threshold": self.threshold,
            "word_f1": round(self.word_f1, 4),
            "chrf_score": round(self.chrf_score, 4),
            "primary_words": self.primary_words,
            "secondary_words": self.secondary_words,
            "notice": self.notice,
        }


def _tokenize_words(text: str) -> List[str]:
    """Extracts words across Latin and Indic scripts."""
    # Split on whitespace and common punctuation, retaining Unicode letters
    tokens = re.findall(r"\w+", text.lower(), re.UNICODE)
    return tokens


def _compute_word_f1(tokens1: List[str], tokens2: List[str]) -> float:
    """Computes symmetric token multiset F1 score."""
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0

    c1 = Counter(tokens1)
    c2 = Counter(tokens2)
    intersection = sum((c1 & c2).values())
    total = len(tokens1) + len(tokens2)
    if total == 0:
        return 1.0
    return (2.0 * intersection) / total


def _extract_char_ngrams(text: str, n: int) -> Counter:
    """Extracts character n-grams ignoring extra whitespace."""
    compact = re.sub(r"\s+", " ", text.strip().lower())
    if len(compact) < n:
        return Counter([compact]) if compact else Counter()
    return Counter([compact[i:i + n] for i in range(len(compact) - n + 1)])


def _compute_chrf(text1: str, text2: str, min_n: int = 2, max_n: int = 5) -> float:
    """Computes character n-gram F-score across n=min_n..max_n."""
    t1 = text1.strip()
    t2 = text2.strip()
    if not t1 and not t2:
        return 1.0
    if not t1 or not t2:
        return 0.0

    f_scores = []
    for n in range(min_n, max_n + 1):
        ng1 = _extract_char_ngrams(t1, n)
        ng2 = _extract_char_ngrams(t2, n)
        matched = sum((ng1 & ng2).values())
        tot1 = sum(ng1.values())
        tot2 = sum(ng2.values())
        if tot1 + tot2 == 0:
            continue
        prec = matched / tot1 if tot1 > 0 else 0.0
        rec = matched / tot2 if tot2 > 0 else 0.0
        if prec + rec > 0:
            f = (2.0 * prec * rec) / (prec + rec)
        else:
            f = 0.0
        f_scores.append(f)

    if not f_scores:
        return 0.0
    return sum(f_scores) / len(f_scores)


def compute_agreement(
    primary_text: str,
    secondary_text: str,
    threshold: float = 0.60,
) -> AgreementResult:
    """
    Computes lexical agreement between primary and secondary engine outputs.

    Parameters:
        primary_text (str): Output from primary translation engine.
        secondary_text (str): Output from secondary translation engine.
        threshold (float): Agreement flag threshold (0.0 to 1.0, default 0.60).

    Returns:
        AgreementResult: Containing composite score, flags, and honest tooltip notice.
    """
    p_clean = primary_text.strip()
    s_clean = secondary_text.strip()

    if not p_clean and not s_clean:
        return AgreementResult(
            score=1.0,
            score_percent=100.0,
            is_flagged=False,
            threshold=threshold,
            word_f1=1.0,
            chrf_score=1.0,
            primary_words=0,
            secondary_words=0,
        )

    if not p_clean or not s_clean:
        return AgreementResult(
            score=0.0,
            score_percent=0.0,
            is_flagged=True,
            threshold=threshold,
            word_f1=0.0,
            chrf_score=0.0,
            primary_words=len(_tokenize_words(p_clean)),
            secondary_words=len(_tokenize_words(s_clean)),
        )

    p_tokens = _tokenize_words(p_clean)
    s_tokens = _tokenize_words(s_clean)

    word_f1 = _compute_word_f1(p_tokens, s_tokens)
    chrf_score = _compute_chrf(p_clean, s_clean)

    # 50% Word token F1 + 50% Character n-gram overlap
    composite_score = (0.5 * word_f1) + (0.5 * chrf_score)
    composite_score = max(0.0, min(1.0, composite_score))
    score_pct = composite_score * 100.0

    is_flagged = composite_score < threshold

    return AgreementResult(
        score=composite_score,
        score_percent=score_pct,
        is_flagged=is_flagged,
        threshold=threshold,
        word_f1=word_f1,
        chrf_score=chrf_score,
        primary_words=len(p_tokens),
        secondary_words=len(s_tokens),
    )
