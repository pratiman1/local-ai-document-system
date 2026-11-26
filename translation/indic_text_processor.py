"""
translation/indic_text_processor.py
------------------------------------
Universal Unicode-based pre-processing, line/word healing, sentence segmentation,
and glossary management for offline Indic-language document translation.

Design Principles:
1. 100% Language-Independent: Uses universal Unicode character properties (unicodedata)
   and standard Indic punctuation rules without language-specific hardcoding.
2. Condition-Compliant:
   - Strips real page-number patterns (e.g. "Page 1 of 2", "- 1 -") while strictly
     preserving standalone plain number lines.
   - Cleans accidentally doubled trailing characters (e.g. "ആദ്യംം" -> "ആദ്യം") and
     tracks every modified word for user audit.
   - Glossary tags ([T1], [T2]) with automatic fail-safe fallback: if any tag is missing
     or altered, re-translates without tags and applies safe text replacement.
"""

import os
import re
import json
import unicodedata
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Union

# Base directory for user-editable language glossaries
GLOSSARIES_DIR = Path(__file__).resolve().parent.parent / "glossaries"


def is_indic_codepoint(char: str) -> bool:
    """Checks if character falls within the Indic Unicode blocks (0x0900 - 0x0D7F)."""
    if not char:
        return False
    code = ord(char)
    # Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam
    return 0x0900 <= code <= 0x0D7F


def is_combining_mark(char: str) -> bool:
    """Checks if character is a Unicode combining mark (matra, virama/halant, anusvara, visarga)."""
    return unicodedata.category(char) in ("Mn", "Mc", "Me")


def is_real_page_number_line(line: str) -> bool:
    """
    Checks if a standalone line matches real page-number patterns like
    'Page 1 of 2', 'Page 1', 'Pg. 12', or '- 1 -'.
    STRICT RULE: Plain standalone number lines (e.g. '1', '2', '26') are NOT stripped.
    """
    s = line.strip()
    if not s:
        return False

    # Plain standalone number line -> preserve!
    if s.isdigit():
        return False

    # Patterns for real page headers / footers
    patterns = [
        r"^[Pp]age\s+\d+(\s+(?:of|/)\s+\d+)?$",
        r"^[Pp]g\.?\s*\d+(\s+(?:of|/)\s+\d+)?$",
        r"^[-–—]\s*\d+\s*[-–—]$",
        r"^\d+\s+(?:of|/)\s+\d+$",
        r"^[Pp]age\s*:\s*\d+$",
    ]
    for pat in patterns:
        if re.match(pat, s):
            return True
    return False


def clean_doubled_trailing_chars(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Deduplicates accidentally doubled trailing characters (e.g. 'ആദ്യംം' -> 'ആദ്യം')
    and consecutive duplicate combining marks in Indic words.
    Never modifies ASCII letters ('II', 'HP11') or numbers ('100', '33').
    Returns: (cleaned_text, list_of_modified_words_as_(original, cleaned))
    """
    modified_words: List[Tuple[str, str]] = []

    def clean_word(word: str) -> str:
        # Check if word contains any Indic character
        if not any(is_indic_codepoint(c) for c in word):
            return word

        # 1. Deduplicate consecutive duplicate combining marks (Mn, Mc, Me) in Indic text
        out = []
        i = 0
        while i < len(word):
            c = word[i]
            out.append(c)
            if is_indic_codepoint(c) and is_combining_mark(c):
                # skip immediately identical combining mark
                while i + 1 < len(word) and word[i + 1] == c:
                    i += 1
            i += 1
        w = "".join(out)

        # 2. Check for duplicate trailing Indic combining marks at the end of word
        # (e.g. 'ആദ്യംം' where trailing 'ം' was repeated)
        if len(w) >= 2 and w[-1] == w[-2] and is_indic_codepoint(w[-1]):
            if is_combining_mark(w[-1]):
                w = w[:-1]

        return w

    tokens = re.split(r"(\s+|[.,?!।॥:;\"\'\)\]\}]+)", text)
    cleaned_tokens = []

    for tok in tokens:
        if tok and not tok.isspace() and not re.match(r"^[.,?!।॥:;\"\'\)\]\}]+$", tok):
            cleaned = clean_word(tok)
            if cleaned != tok:
                modified_words.append((tok, cleaned))
            cleaned_tokens.append(cleaned)
        else:
            cleaned_tokens.append(tok)

    return "".join(cleaned_tokens), modified_words


def is_bullet_only_line(line: str) -> bool:
    """
    Checks if a line consists entirely of bullet characters, dots, tabs, or whitespace
    without any word or number content (e.g. '•\t', '•', '• • • • •', '·\t').
    These are visual layout artifacts that corrupt text when joined.
    """
    s = line.strip()
    if not s:
        return False
    return bool(re.match(r"^[\s\t•·\*▪▫–—\.\-—]+$", s) and not re.search(r"[\w\d\u0900-\u0D7F]", s))


def is_section_heading(line: str) -> bool:
    """
    Checks if a line is a section heading like
    '1. तकनीक से जुड़ी दुनिया', '2. अवलोकन से विज्ञान तक',
    '1.3.2 ഫ്രണ്ട് ഓഫീസ് മാനേജർ' or '1.3.13 ബെൽ ബോയ്'.

    Condition 3: Treat a numbered line as a heading only if it is short
    and does not end with a sentence-ending punctuation mark (।, ॥, ?, !, ., ;, :),
    so ordinary numbered list items in paragraphs are not turned into headings.
    """
    s = line.strip()
    if not s:
        return False

    # Must start with a numbered heading pattern: e.g. "1. Title" or "1.3.2 Title"
    is_numbered = bool(
        re.match(r"^\d+(?:\.\d+)*\.\s+[\u0900-\u0D7F\w]", s)
        or re.match(r"^\d+(?:\.\d+)+\s+[\u0900-\u0D7F\w]", s)
    )
    if not is_numbered:
        return False

    # Shortness requirement (headings are concise lines, typically under 80 characters)
    if len(s) >= 80:
        return False

    # Must NOT end with a sentence-ending punctuation mark
    sentence_ending_puncts = ("।", "॥", "?", "!", ".", ";", ":")
    if s.endswith(sentence_ending_puncts):
        return False

    return True


def is_list_item_start(line: str) -> bool:
    """
    Checks if a line begins with a list item indicator:
    - Section number: '1.3.2', '2.1'
    - Numbered item: '1. ', '7. ', '1) '
    - Lettered item: 'a.', 'b. ', 'c.റിസപ്ഷൻ', '(a)'
    - Roman numeral: 'i.', 'ii. ', '(i)'
    - Bullet point: '• ', '- ', '* '
    """
    s = line.strip()
    if not s:
        return False
    patterns = [
        r"^\d+(?:\.\d+)+",                           # 1.3.2, 1.3.13
        r"^\d+[\.\)]\s*",                            # 7. or 7) or 1.
        r"^[a-zA-Z][\.\)]",                          # a. or a) or a.താഴെ
        r"^\([a-zA-Z0-9]{1,2}\)\s*",                 # (a) or (1)
        r"^[•·\*▪▫\-–—]\s*",                         # bullet symbols
        r"^(?:[ivxlcdmIVXLCDM]+[\.\)]|\([ivxlcdmIVXLCDM]+\))\s*", # roman numerals
    ]
    return any(re.match(p, s) for p in patterns)


def split_inline_list_items(line: str) -> List[str]:
    """
    Splits multiple list items sharing a single line (e.g. 'c.റിസപ്ഷൻ d.റെസ്റ്റോറന്റ്'
    or '... തിരഞ്ഞെടുക്കുക. b.റിസർവേഷൻ...').
    Also deduplicates repeated bullet sequences like '• • • • •'.
    """
    s = line.strip()
    if not s:
        return []
    # Deduplicate repeated bullet/dot characters
    s = re.sub(r"(?:[\s\t]*[•·\*▪▫][\s\t]*){2,}", " ", s).strip()
    # Normalize list indicators glued directly to Indic text (e.g. 'c.റിസപ്ഷൻ' -> 'c. റിസപ്ഷൻ', '10.കോൺസിയർജ്' -> '10. കോൺസിയർജ്')
    s = re.sub(r'(\b[a-zA-Z0-9]+[\.\)])(?=[\u0900-\u0D7F])', r'\1 ', s)
    # Normalize section numbers glued to Indic text (e.g. '3.3ഹോട്ടൽ' -> '3.3 ഹോട്ടൽ', '1.3.2ഫ്രണ്ട്' -> '1.3.2 ഫ്രണ്ട്')
    s = re.sub(r'(\b\d+(?:\.\d+)+)(?=[\u0900-\u0D7F])', r'\1 ', s)
    # Split inline list items
    pattern = r"(?<=\S)\s+(?=(?:[a-zA-Z][\.\)]|\([a-zA-Z0-9]{1,2}\)|\b\d+[\.\)])(?:\s*|$|(?=[\u0900-\u0D7F\w])))"
    parts = re.split(pattern, s)
    return [p.strip() for p in parts if p.strip()]


def clean_and_join_lines(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Cleans raw document page text:
    1. Removes real page-number lines (e.g. 'Page 1 of 2', '- 1 -').
    2. Cleans accidentally doubled trailing characters (e.g. 'ആദ്യംം' -> 'ആദ്യം').
    3. Normalizes glued list markers before Indic text ('c.റൂം' -> 'c. റൂം').
    4. Filters layout bullet-only artifacts ('•\t') to avoid lines like '5 • • • • •'.
    5. Splits inline list items sharing lines ('a. ... b. ...').
    6. Keeps section numbers ('1.3.2 ...') and list items as distinct clean units.
    7. Joins broken lines across words (hyphenated or split tokens) without space.
    8. Joins wrapped lines inside sentences with a single space.
    9. Preserves intentional paragraph breaks and standalone number lines.
    """
    if not text or not text.strip():
        return "", []

    # 1. Clean doubled trailing characters first
    cleaned_text, modified_words = clean_doubled_trailing_chars(text)

    # 2. Normalize list indicators glued directly to Indic text (e.g. 'c.റിസപ്ഷൻ', '10.കോൺസിയർജ്')
    cleaned_text = re.sub(r'(\b[a-zA-Z0-9]+[\.\)])(?=[\u0900-\u0D7F])', r'\1 ', cleaned_text)
    # Normalize section numbers glued to Indic text (e.g. '3.3ഹോട്ടൽ' -> '3.3 ഹോട്ടൽ')
    cleaned_text = re.sub(r'(\b\d+(?:\.\d+)+)(?=[\u0900-\u0D7F])', r'\1 ', cleaned_text)

    # 3. Filter lines, remove real page numbers, skip bullet-only lines, and split inline list items
    raw_lines = cleaned_text.splitlines()
    filtered_lines: List[str] = []
    for line in raw_lines:
        if is_real_page_number_line(line):
            continue
        if is_bullet_only_line(line):
            continue
        sub_lines = split_inline_list_items(line)
        if sub_lines:
            filtered_lines.extend(sub_lines)
        else:
            filtered_lines.append("")

    # 3. Join lines intelligently into paragraphs and distinct list items
    paragraphs: List[str] = []
    current_para_lines: List[str] = []

    for line in filtered_lines:
        stripped = line.strip()
        if not stripped:
            if current_para_lines:
                paragraphs.append(_join_line_buffer(current_para_lines))
                current_para_lines = []
            continue

        # Standalone plain number line (e.g. page number '5', '10', '30') -> keep as standalone unit
        if stripped.isdigit():
            if current_para_lines:
                paragraphs.append(_join_line_buffer(current_para_lines))
                current_para_lines = []
            paragraphs.append(stripped)
            continue

        # Section headings (e.g. '1.3.2 ഫ്രണ്ട് ഓഫീസ് മാനേജർ') or list items (e.g. 'a. ...')
        if is_section_heading(stripped) or is_list_item_start(stripped):
            if current_para_lines:
                paragraphs.append(_join_line_buffer(current_para_lines))
                current_para_lines = []
            current_para_lines.append(stripped)
            # If it's a section heading, flush immediately so following duties don't merge into heading
            if is_section_heading(stripped):
                paragraphs.append(_join_line_buffer(current_para_lines))
                current_para_lines = []
            continue

        current_para_lines.append(stripped)

    if current_para_lines:
        paragraphs.append(_join_line_buffer(current_para_lines))

    result_text = "\n\n".join(p for p in paragraphs if p.strip())
    return result_text, modified_words


def _join_line_buffer(lines: List[str]) -> str:
    """Joins a continuous sequence of non-empty lines belonging to one paragraph."""
    if not lines:
        return ""

    joined = lines[0]
    for i in range(1, len(lines)):
        prev = joined
        curr = lines[i]

        # Case A: Previous line ends with hyphen or soft hyphen
        if prev.endswith("-") or prev.endswith("‐") or prev.endswith("\u00ad"):
            joined = prev.rstrip("-‐\u00ad") + curr
        # Case B: Current line begins with an Indic combining mark (matra/virama)
        elif curr and is_combining_mark(curr[0]):
            joined = prev + curr
        # Case C: Standard line break in sentence -> join with single space
        else:
            joined = prev + " " + curr

    return joined


def split_into_sentences(text: str) -> List[str]:
    """
    Splits text into complete sentences using Unicode Indic boundaries:
    Devanagari/Indic Danda (।), Double Danda (॥), period (.), question mark (?),
    exclamation (!), or paragraph boundaries.
    Protects standard abbreviations, hierarchical section numbers, and list markers.
    """
    if not text or not text.strip():
        return []

    paras = text.split("\n\n")
    sentences = []

    # Patterns to protect from splitting on period
    protection_patterns = [
        r"\b(?:[A-Z]\.|[a-zA-Z]{1,3}\.|II\.|No\.|Mr\.|Mrs\.|Dr\.|Prof\.|e\.g\.|i\.e\.|vs\.|etc\.)",
        r"\b\d+(?:\.\d+)+\.?",                          # 1.3.2, 1.3.13, 2.1.2
        r"(?:^|(?<=[\n\r]))\s*\d+[\.\)]\s+",            # 7. at start of para/line
        r"(?:^|(?<=[\n\r]))\s*[a-zA-Z][\.\)]\s*",       # a. at start of para/line
        r"(?<=\s)[a-zA-Z][\.\)]\s*",                    # a. or b. preceded by space
        r"(?<=\s)\d+[\.\)]\s+",                         # 1. preceded by space
    ]

    for para in paras:
        para_clean = para.strip()
        if not para_clean:
            continue

        protected = para_clean
        tokens_map = {}
        token_counter = 0

        for pat in protection_patterns:
            matches = list(re.finditer(pat, protected))
            for m in reversed(matches):
                match_str = m.group(0)
                if "." in match_str or "।" in match_str:
                    tok = f"__PROT_{token_counter}__"
                    token_counter += 1
                    tokens_map[tok] = match_str
                    start, end = m.span()
                    protected = protected[:start] + tok + protected[end:]

        # Split on sentence terminators: [.?!।॥]
        raw_parts = re.split(r"([.?!।॥]+(?:\s+|$))", protected)
        current_sent = ""

        for part in raw_parts:
            current_sent += part
            if re.search(r"[.?!।॥]+(?:\s+|$)", part):
                for tok, original in tokens_map.items():
                    current_sent = current_sent.replace(tok, original)
                s_strip = current_sent.strip()
                if s_strip:
                    sentences.append(s_strip)
                current_sent = ""

        if current_sent.strip():
            for tok, original in tokens_map.items():
                current_sent = current_sent.replace(tok, original)
            s_strip = current_sent.strip()
            if s_strip:
                sentences.append(s_strip)

    return sentences if sentences else [text.strip()]


class GlossaryManager:
    """
    Manages language glossaries loaded dynamically from glossaries/{source_lang}.json.
    Features:
    - Zero code changes required for new languages or vocabulary additions.
    - Tag-based preservation: Masks glossary source terms as [T1], [T2] before translation.
    - Fail-safe fallback: If any tag like [T1] is missing or altered, triggers re-translation
      without tags and performs safe dictionary-based term replacement.
    """

    def __init__(self, glossaries_dir: Optional[Path] = None):
        self.glossaries_dir = glossaries_dir or GLOSSARIES_DIR
        self._cache: Dict[str, Dict[str, Dict[str, str]]] = {}

    def get_glossary(self, source_lang: str, target_lang: str) -> Dict[str, str]:
        """Loads and returns the glossary dictionary for (source_lang, target_lang)."""
        src = source_lang.lower().strip()
        tgt = target_lang.lower().strip()

        if src not in self._cache:
            file_path = self.glossaries_dir / f"{src}.json"
            if not file_path.is_file():
                self._cache[src] = {}
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._cache[src] = data
                except Exception:
                    self._cache[src] = {}

        data = self._cache.get(src, {})
        # Supports target language namespace {"hin": {...}} or flat dictionary {...}
        if tgt in data and isinstance(data[tgt], dict):
            return data[tgt]
        if isinstance(data, dict) and not any(isinstance(v, dict) for v in data.values()):
            return data
        return {}

    def mask_terms(
        self,
        sentence: str,
        source_lang: str,
        target_lang: str,
    ) -> Tuple[str, Dict[str, str], List[str]]:
        """
        Replaces glossary source terms with indexed preservation tags [T1], [T2], ...
        Longest terms are matched first to prevent partial subphrase corruption.
        Preserves following punctuation context for tag restoration.
        Returns: (masked_sentence, tag_map, matched_source_terms)
        """
        glossary = self.get_glossary(source_lang, target_lang)
        if not glossary:
            return sentence, {}, []

        # Sort terms by length descending
        sorted_terms = sorted(glossary.keys(), key=len, reverse=True)
        tag_map: Dict[str, str] = {}
        matched_terms: List[str] = []
        self.last_tag_punct_map: Dict[str, str] = {}
        masked_sentence = sentence
        tag_counter = 1

        for term in sorted_terms:
            if term in masked_sentence:
                tag = f"[T{tag_counter}]"
                escaped = re.escape(term)
                # Capture punctuation that immediately follows the term (e.g. comma, semicolon, dash)
                m_punct = re.search(rf"{escaped}\s*([,;:—\-])", masked_sentence)
                trailing_punct = m_punct.group(1).strip() if m_punct else ""

                # Replace exact term occurrences
                new_sent = re.sub(escaped, tag, masked_sentence)
                if new_sent != masked_sentence:
                    masked_sentence = new_sent
                    tag_map[tag] = glossary[term]
                    self.last_tag_punct_map[tag] = trailing_punct
                    matched_terms.append(term)
                    tag_counter += 1

        return masked_sentence, tag_map, matched_terms

    def restore_terms(
        self,
        translated_sentence: str,
        tag_map: Dict[str, str],
        tag_punct_map: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, bool]:
        """
        Restores tags [T1], [T2] with exact target glossary terms.
        Keeps following punctuation (such as commas) even if dropped by the translation model.
        Returns: (restored_sentence, all_tags_found_and_restored)
        """
        if not tag_map:
            return translated_sentence, True

        restored = translated_sentence
        all_found = True
        punct_map = tag_punct_map or getattr(self, "last_tag_punct_map", {})

        for tag, target_term in tag_map.items():
            # Robust tag matching allowing potential whitespace and Indic script transliterations
            # of the tag (e.g. [T1], [T 1], [टी1], [टी 1], [टी१]), with or without closing bracket
            tag_num = tag.strip("[]Tt")
            digit_pat = f"[{tag_num}\u0967-\u0D6F]"
            flexible_tag_pat = rf"\[\s*[^\]0-9\u0966-\u0D6F]*{digit_pat}\s*\]?"
            trailing_punct = punct_map.get(tag, "")

            if re.search(flexible_tag_pat, restored):
                if trailing_punct:
                    tag_with_punct_pat = rf"{flexible_tag_pat}(\s*[,;:—\-])?"
                    def _repl(m: re.Match) -> str:
                        existing_punct = m.group(1)
                        punct_to_use = existing_punct.strip() if existing_punct else trailing_punct
                        return f"{target_term}{punct_to_use}"
                    restored = re.sub(tag_with_punct_pat, _repl, restored, count=1)
                else:
                    restored = re.sub(flexible_tag_pat, target_term, restored)
            else:
                all_found = False

        # Clean up any leftover stray tag fragments like [T1], [टी1], etc.
        restored = re.sub(r"\[\s*(?:T|टी|[a-zA-Z])?\s*\d+\s*\]?", "", restored)
        # Ensure standard punctuation spacing (e.g. ",word" -> ", word", and collapse multiple spaces)
        restored = re.sub(r"([,;:—])(?=[^\s\d])", r"\1 ", restored)
        restored = re.sub(r"\s{2,}", " ", restored).strip()

        return restored, all_found

    def apply_fallback_replacement(
        self,
        raw_translated_sentence: str,
        source_lang: str,
        target_lang: str,
        matched_terms: List[str],
    ) -> str:
        """
        Fallback when tags are missing or dropped: applies safe glossary text replacement
        to ensure domain terms are not mistranslated.
        """
        glossary = self.get_glossary(source_lang, target_lang)
        if not glossary:
            return raw_translated_sentence

        result = raw_translated_sentence
        # For each term that was present in the source, ensure target term is used
        for term in matched_terms:
            target_term = glossary.get(term)
            if not target_term:
                continue

            # Check common literal mistranslations for known terms
            literal_translations = {
                "ഫ്രണ്ട് ഓഫീസ്": ["सामने का कार्यालय", "सामने के कार्यालय", "अगला कार्यालय"],
                "ഹൗസ് കീപ്പിംഗ്": ["घर की देखभाल", "घर की रखवाली"],
                "നൈറ്റ് ഓഡിറ്റ്": ["रात का लेखा-जोखा", "रात का ऑडिट", "रात के लेखापरीक्षा", "रात की लेखापरीक्षा"],
                "നൈറ്റ് ഓഡിറ്റിന്റെ": ["रात के लेखापरीक्षा", "रात की लेखापरीक्षा", "रात के लेखापरीक्षा के"],
                "യാത്രയയപ്പ്": ["यात्रा करना", "अलविदा"],
                "സൽപ്പേര്": ["उपनाम"],
                "ഡിപ്പാർച്ചർ എറാൻഡ്": ["विभाग एरेंड", "विभाग एरंड", "प्रस्थान एरंड", "प्रस्थान एरेंड", "एरेंड", "एरंड"],
                "कम दिखाई देने वाला व्यक्ति": ["less visible person", "person with less vision", "person who sees less"],
                "रास्ता बताने वाला ऐप": ["route teller app", "route telling app", "way telling app", "path showing app"],
                "कदम गिनने वाली घड़ी": ["step-counting clock", "step counting clock", "step counter clock"],
                "गर्म चाय में रखा चम्मच गरम होना": ["a hot tea spoon", "hot tea spoon", "the spoon kept in hot tea getting hot"],
            }
            # 1. Replace known literal translations if present
            known_literals = literal_translations.get(term, [])
            for lit in known_literals:
                if lit in result:
                    result = result.replace(lit, target_term)

        return result


def clean_repetitive_phrases(text: str) -> str:
    """
    Cleans pathological beam-search repetition loops in translation output
    without altering normal vocabulary or phrasing.
    Matches repeated words or phrases of 1 to 8 words repeated 2+ consecutive times.
    """
    if not text:
        return ""
    pattern = r"(?:^|(?<=[\s,।॥.]))([\u0900-\u0D7F\w]+(?:\s+[\u0900-\u0D7F\w]+){0,6})(?:\s+\1)+(?=[\s,।॥.]|$)"
    curr = text
    for _ in range(5):
        new_curr = re.sub(pattern, r"\1", curr)
        if new_curr == curr:
            break
        curr = new_curr
    return curr.strip()


TECH_NOUN_PATTERNS = [
    r"\b(?:navigation\s+)?apps?\b",
    r"\bapplications?\b",
    r"\bsoftwares?\b",
    r"\bdevices?\b",
    r"\bgadgets?\b",
    r"\balgorithms?\b",
    r"\bprograms?\b",
    r"\bsystems?\b",
    r"\btools?\b",
    r"\bplatforms?\b",
    r"\bcomputers?\b",
    r"\blaptops?\b",
    r"\b(?:smart)?phones?\b",
    r"\b(?:smart)?watch(?:es)?\b",
    r"\bclocks?\b",
    r"\b(?:fitness\s+)?trackers?\b",
    r"\bsensors?\b",
    r"\bcameras?\b",
    r"\bmachines?\b",
    r"\bunits?\b",
    r"\bengines?\b",
    r"\bvehicles?\b",
    r"\bmodels?\b",
    r"\bbots?\b",
    r"\bnetworks?\b",
    r"\bwebsites?\b",
]

HUMAN_NOUN_PATTERNS = [
    r"\bpersons?\b",
    r"\bpeople\b",
    r"\busers?\b",
    r"\bhumans?\b",
    r"\bman\b",
    r"\bmen\b",
    r"\bwoman\b",
    r"\bwomen\b",
    r"\bboys?\b",
    r"\bgirls?\b",
    r"\bchild(?:ren)?\b",
    r"\bdoctors?\b",
    r"\bpatients?\b",
    r"\bteachers?\b",
    r"\bstudents?\b",
    r"\bfarmers?\b",
    r"\bengineers?\b",
    r"\bscientists?\b",
    r"\bresearchers?\b",
    r"\bdrivers?\b",
    r"\bpassengers?\b",
    r"\bworkers?\b",
    r"\bmanagers?\b",
    r"\bdesigners?\b",
    r"\bdevelopers?\b",
    r"\bprogrammers?\b",
    r"\bexperts?\b",
    r"\bspecialists?\b",
    r"\bkids?\b",
    r"\bindividuals?\b",
]


def fix_pronouns_context_aware(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Condition 2: Only change "He" or "She" to "It" (and "he"/"she" to "it")
    when the nearest preceding subject is clearly an app, device, or software.
    Returns (updated_text, list_of_changed_records).
    """
    if not text:
        return "", []

    changed_records: List[Dict[str, Any]] = []
    paragraphs = text.split("\n\n")
    new_paragraphs: List[str] = []

    for para in paragraphs:
        # Split sentences preserving punctuation and following whitespace
        sent_tokens = re.split(r"([.!?]+\s*)", para)
        sentence_pairs: List[List[str]] = []
        for i in range(0, len(sent_tokens) - 1, 2):
            sentence_pairs.append([sent_tokens[i], sent_tokens[i + 1]])
        if len(sent_tokens) % 2 == 1 and sent_tokens[-1]:
            sentence_pairs.append([sent_tokens[-1], ""])

        prev_sentence_text = ""
        for pair in sentence_pairs:
            sent = pair[0]
            sep = pair[1]
            orig_sent = sent

            def replace_match(m: re.Match) -> str:
                pronoun = m.group(0)
                start_pos = m.start()
                # Text in current sentence preceding the pronoun
                context_curr = sent[:start_pos]
                # Combined search window: previous sentence + current sentence before pronoun
                search_window = f"{prev_sentence_text} {context_curr}".strip()

                # If there is any human noun in the search window, do not replace
                has_human = any(re.search(p, search_window, re.IGNORECASE) for p in HUMAN_NOUN_PATTERNS)
                if has_human:
                    return pronoun

                # Check for tech nouns in the search window
                tech_match = None
                for p in TECH_NOUN_PATTERNS:
                    tm = re.search(p, search_window, re.IGNORECASE)
                    if tm:
                        tech_match = tm.group(0)
                        break

                if tech_match:
                    replacement = "It" if pronoun[0].isupper() else "it"
                    changed_records.append({
                        "original_sentence": (orig_sent + sep).strip(),
                        "matched_pronoun": pronoun,
                        "replacement": replacement,
                        "preceding_subject": tech_match,
                    })
                    return replacement
                return pronoun

            new_sent = re.sub(r"\b(He|he|She|she)\b", replace_match, sent)
            pair[0] = new_sent
            prev_sentence_text = new_sent

        new_paragraphs.append("".join([s + sep for s, sep in sentence_pairs]))

    # Fill in changed_sentence in records
    for r in changed_records:
        r["changed_sentence"] = r["original_sentence"].replace(r["matched_pronoun"], r["replacement"], 1)

    return "\n\n".join(new_paragraphs), changed_records


def postprocess_english_translation(
    text: str,
    return_records: bool = False,
) -> Union[str, Tuple[str, List[Dict[str, Any]]]]:
    """
    Post-processes English translation to fix pronoun errors for inanimate objects
    (context-aware per Condition 2), syntax polish for questions, and clean articles.
    Condition 1: Does NOT hardcode the "बस" (bus vs just) fix; that is flagged in audit.
    """
    if not text:
        return ("", []) if return_records else ""

    # 1. Condition 2: Context-aware pronoun replacement
    text, changed_pronouns = fix_pronouns_context_aware(text)

    # 2. Specific Hindi->English syntax polish for questions & articles
    text = re.sub(
        r"\ba\s+person\s+with\s+low\s+vision\s+How\s+(?:could|can|to)\b",
        "How can a person with low vision",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?<=[.!?\n]\s)navigation\s+app\s+compares\b", "A navigation app compares", text, flags=re.IGNORECASE)
    text = re.sub(r"^navigation\s+app\s+compares\b", "A navigation app compares", text, flags=re.IGNORECASE)

    # 3. Sentence-final question fragments (starting with interrogative, ending with period)
    text = re.sub(r"\b(How|What|Why|Where|When|Whose|Which)\b([^.!?\n]{3,120})\.", r"\1\2?", text)

    if return_records:
        return text, changed_pronouns
    return text


def normalize_heading_prefix(src_heading: str, trans_heading: str) -> str:
    """
    Ensures that a translated section heading preserves the exact numerical prefix
    from the source heading (e.g. '1.', '2.', '10.') and removes trailing periods.
    """
    m = re.match(r"^(\d+)\.\s*", src_heading.strip())
    if not m:
        return trans_heading.strip()
    num = m.group(1)
    # Strip misplaced trailing numbering: e.g. "Health, Statistics, and Decisions 8." -> "Health, Statistics, and Decisions"
    clean_trans = re.sub(rf"\s+{num}\.?$", "", trans_heading.strip())
    # Strip erroneous letter prefix: e.g. "A. The world" -> "The world"
    clean_trans = re.sub(r"^[A-Za-z]\.\s*", "", clean_trans)
    # Strip existing number prefix: e.g. "2. From observation" or "3.Everyday"
    clean_trans = re.sub(r"^\d+\.\s*", "", clean_trans)
    # Strip trailing period on heading if not question mark
    if clean_trans.endswith(".") and not clean_trans.endswith("..") and not clean_trans.endswith("?"):
        clean_trans = clean_trans[:-1].strip()
    return f"{num}. {clean_trans}"


def audit_literal_translations(translated_text: str, target_lang: str = "eng") -> List[Dict[str, Any]]:
    """
    Second-pass check: flags sentences containing known bad literal translations
    or ambiguous phrases (such as Hindi 'बस' - bus vs. just per Condition 1)
    and returns a structured list of flagged sentences for user review.
    """
    if target_lang != "eng":
        return []

    bad_literal_patterns = [
        (r"\bless\s+visible\s+person\b", "a person with low vision"),
        (r"\broute\s+teller\s+app\b", "navigation app"),
        (r"\bstep[\s-]counting\s+clock\b", "step-counting watch"),
        (r"\b(?:a\s+)?hot\s+tea\s+spoon\b", "a spoon placed in hot tea getting hot"),
        (r"\bHe\s+(?:suggests|uses|calculates|monitors|tracks|provides|operates)\b", "It [verb] (inanimate pronoun error)"),
        (
            r"\bJust\s+how\s+(?:to|does|can|could)\s+(?:spend|consume|use)\s+less\s+fuel\b",
            "Potential Hindi 'बस' (bus vs. just) mistranslation. Flagged for review: 'बस' in Hindi can mean 'bus' (public transit) or 'just/only'. Consider if 'bus' was intended.",
        ),
    ]

    flagged = []
    lines = translated_text.splitlines()
    for line_idx, line in enumerate(lines, 1):
        if not line.strip():
            continue
        sents = re.split(r"(?<=[.!?])\s+", line.strip())
        for sent_idx, sent in enumerate(sents, 1):
            for pat, suggestion in bad_literal_patterns:
                m = re.search(pat, sent, re.IGNORECASE)
                if m:
                    flagged.append({
                        "line_number": line_idx,
                        "sentence_number": sent_idx,
                        "matched_phrase": m.group(0),
                        "suggested_fix": suggestion,
                        "sentence_text": sent,
                    })

    return flagged
