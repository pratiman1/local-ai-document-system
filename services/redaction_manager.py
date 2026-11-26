"""
services/redaction_manager.py
-----------------------------
Pre-transmission redaction and post-enhancement restoration for sensitive entities:
- Names (proper names, honorific prefixes)
- Numbers (counts, IDs, monetary figures, metrics)
- E-mail addresses
- Phone numbers

Allows the user to mask sensitive personal data before any external transmission,
and restores the exact original values once the enhanced text is received.
"""

import re
from typing import Tuple, Dict, Any


def redact_sensitive_data(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Masks emails, phone numbers, numbers, and proper names with structured placeholders.
    Returns: (redacted_text, placeholder_map) where placeholder_map maps '[TAG_N]' -> original_value.
    """
    if not text:
        return "", {}

    placeholders: Dict[str, str] = {}
    redacted = text

    # 1. E-mail addresses
    email_counter = 1
    email_pat = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    for m in list(re.finditer(email_pat, redacted)):
        val = m.group(0)
        tag = f"[EMAIL_{email_counter}]"
        email_counter += 1
        placeholders[tag] = val
        redacted = redacted.replace(val, tag)

    # 2. Phone numbers (standard international and domestic patterns)
    phone_counter = 1
    phone_pat = r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,5}\)?[-.\s]?)\d{3,5}[-.\s]?\d{3,5}\b"
    for m in list(re.finditer(phone_pat, redacted)):
        val = m.group(0)
        if val not in placeholders.values():
            tag = f"[PHONE_{phone_counter}]"
            phone_counter += 1
            placeholders[tag] = val
            redacted = redacted.replace(val, tag)

    # 3. Proper Names (Honorifics / Titles followed by Capitalized Names)
    name_counter = 1
    name_pat = r"\b(?:Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Shri|Smt\.|Patient|Doctor|Client|Author)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b"
    for m in list(re.finditer(name_pat, redacted)):
        val = m.group(0)
        if val not in placeholders.values():
            tag = f"[NAME_{name_counter}]"
            name_counter += 1
            placeholders[tag] = val
            redacted = redacted.replace(val, tag)

    # 4. Numbers (isolated numbers, decimals, percentages, metric units)
    num_counter = 1
    num_pat = r"\b\d+(?:[.,]\d+)?%?\b"
    for m in list(re.finditer(num_pat, redacted)):
        val = m.group(0)
        # Avoid masking tags like [EMAIL_1]
        if val not in placeholders.values():
            tag = f"[NUM_{num_counter}]"
            num_counter += 1
            placeholders[tag] = val
            redacted = re.sub(rf"(?<![A-Za-z_])\b{re.escape(val)}\b(?![A-Za-z_])", tag, redacted)

    return redacted, placeholders


def restore_sensitive_data(text: str, placeholders: Dict[str, str]) -> str:
    """
    Restores placeholders with their original values in the enhanced text.
    Handles minor whitespace variations introduced by LLM responses (e.g. '[ NUM_1 ]').
    """
    if not text or not placeholders:
        return text or ""

    restored = text
    for tag, original_val in placeholders.items():
        # Match exact tag or tag with potential internal spaces: e.g. [NUM_1] or [ NUM_1 ]
        clean_tag = tag.strip("[]")
        tag_pat = rf"\[\s*{re.escape(clean_tag)}\s*\]"
        restored = re.sub(tag_pat, original_val, restored)

    return restored
