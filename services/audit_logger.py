"""
services/audit_logger.py
------------------------
Metadata-only audit logging for online AI enhancement requests.
Strict Privacy Guarantees:
- Contains ONLY: date/time (ISO 8601), provider, model, character count, and page number.
- NEVER records or logs document text, snippet contents, prompts, or API keys.
- User can view and clear the log at any time.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

AUDIT_LOG_FILE = Path(__file__).resolve().parent.parent / "exports" / "ai_request_audit.json"


def log_ai_request(
    provider: str,
    model: str,
    char_count: int,
    page_number: Union[int, str] = 1,
    is_local: bool = False,
    page_num: Optional[Union[int, str]] = None,
) -> Dict[str, Any]:
    """
    Appends a metadata-only entry to the local audit log.
    Guaranteed to contain ZERO document text and ZERO keys.
    """
    resolved_page = page_num if page_num is not None else page_number
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": str(provider),
        "model": str(model),
        "character_count": int(char_count),
        "approx_tokens": max(1, int(char_count) // 4),
        "page_number": str(resolved_page),
        "is_local": bool(is_local),
    }

    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = get_ai_audit_log()
    records.append(entry)

    try:
        with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return entry


def get_ai_audit_log() -> List[Dict[str, Any]]:
    """Retrieves all metadata-only audit entries."""
    if not AUDIT_LOG_FILE.is_file():
        return []
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def clear_ai_audit_log():
    """Clears the local audit log."""
    try:
        if AUDIT_LOG_FILE.is_file():
            with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
    except Exception:
        pass
