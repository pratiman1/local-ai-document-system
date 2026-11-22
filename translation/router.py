"""
translation/router.py
---------------------
Translation Engine Router & Arbitrator.
Coordinates between Argos Translate and AI4Bharat IndicTrans2 based on:
1. User engine preference ('automatic', 'argos_only', 'indictrans2_only').
2. Engine priority order:
   - IndicTrans2 direct (e.g. Hindi -> Tamil direct without pivot!).
   - Argos direct.
   - Argos English pivot.
   - Missing model guidance.
3. Compare Mode eligibility:
   - Evaluates whether both engines have models installed for the language pair.
   - Dispatches primary and secondary engines for sequential comparison.
"""

from typing import Dict, Any, Optional, Tuple
from translation.translator_factory import get_translator
from translation.argos_translator import get_language_display_name
from translation.indictrans2_mapping import get_model_direction, is_indic_language


def resolve_translation_route(
    source: str,
    target: str,
    engine_preference: str = "automatic",
    compare_mode: bool = False,
    argos_instance=None,
    indictrans2_instance=None,
) -> Dict[str, Any]:
    """
    Arbitrates the best translation route and engine for a source/target pair.

    Parameters:
        source (str): 3-letter app source code (e.g. 'eng', 'hin').
        target (str): 3-letter app target code (e.g. 'hin', 'tam').
        engine_preference (str): 'automatic', 'argos_only', or 'indictrans2_only'.
        compare_mode (bool): Whether the user requested Compare Mode.
        argos_instance: Optional injected ArgosTranslator instance.
        indictrans2_instance: Optional injected IndicTrans2Translator instance.

    Returns:
        Dict[str, Any]: Route resolution dictionary including primary engine,
        secondary engine (for Compare Mode), status badges, and tooltips.
    """
    src = source.lower().strip()
    tgt = target.lower().strip()
    pref = engine_preference.lower().strip() if engine_preference else "automatic"

    from_name = get_language_display_name(src)
    to_name = get_language_display_name(tgt)

    # 1. Same-language bypass check
    if src == tgt:
        return {
            "status": "same_language",
            "route_type": "same_language",
            "primary_engine": "argos",
            "secondary_engine": None,
            "can_compare": False,
            "is_ready": True,
            "can_translate": True,
            "source_code": src,
            "target_code": tgt,
            "source_name": from_name,
            "target_name": to_name,
            "status_label": "Ready (same language)",
            "status_line": f"{from_name} to {to_name} (same language)",
            "tooltip": f"Source and target languages are both '{from_name}'. Translation is bypassed.",
            "message": f"Source and target languages are both '{from_name}'. Translation skipped.",
            "notice": "",
        }

    # Instantiate translators
    argos = argos_instance or get_translator("argos")
    indic = indictrans2_instance or get_translator("indictrans2")

    # Evaluate capability of each engine
    argos_route = argos.get_route_details(src, tgt)
    indic_route = indic.get_route_details(src, tgt)

    argos_ready = argos_route.get("can_translate", False)
    indic_ready = indic_route.get("can_translate", False)

    # Check Compare Mode eligibility (both engines ready)
    both_ready = argos_ready and indic_ready
    active_compare = compare_mode and both_ready

    # 2. Forced Engine Preference: 'argos_only'
    if pref == "argos_only":
        if argos_ready:
            st = argos_route["status"]
            return {
                "status": st,
                "route_type": argos_route.get("route_type", "direct"),
                "primary_engine": "argos",
                "secondary_engine": "indictrans2" if active_compare else None,
                "can_compare": active_compare,
                "is_ready": True,
                "can_translate": True,
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": argos_route["status_label"],
                "status_line": f"{argos_route['status_line']} [Argos Only]",
                "tooltip": argos_route["tooltip"],
                "message": argos_route["message"],
                "notice": "Using Argos Translate per user preference in Settings.",
            }
        else:
            return {
                "status": argos_route["status"],
                "route_type": argos_route.get("route_type"),
                "primary_engine": "argos",
                "secondary_engine": None,
                "can_compare": False,
                "is_ready": False,
                "can_translate": False,
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": argos_route["status_label"],
                "status_line": f"{argos_route['status_line']} [Argos Only]",
                "tooltip": argos_route["tooltip"],
                "message": argos_route["message"],
                "notice": "",
            }

    # 3. Forced Engine Preference: 'indictrans2_only'
    if pref == "indictrans2_only":
        if indic_ready:
            return {
                "status": "ready_direct",
                "route_type": "direct",
                "primary_engine": "indictrans2",
                "secondary_engine": "argos" if active_compare else None,
                "can_compare": active_compare,
                "is_ready": True,
                "can_translate": True,
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": "Ready (IndicTrans2 direct)",
                "status_line": f"{indic_route['status_line']} [IndicTrans2 Only]",
                "tooltip": indic_route["tooltip"],
                "message": indic_route["message"],
                "notice": "Using IndicTrans2 per user preference in Settings.",
            }
        else:
            return {
                "status": indic_route["status"],
                "route_type": indic_route.get("route_type"),
                "primary_engine": "indictrans2",
                "secondary_engine": None,
                "can_compare": False,
                "is_ready": False,
                "can_translate": False,
                "source_code": src,
                "target_code": tgt,
                "source_name": from_name,
                "target_name": to_name,
                "status_label": indic_route["status_label"],
                "status_line": f"{indic_route['status_line']} [IndicTrans2 Only]",
                "tooltip": indic_route["tooltip"],
                "message": indic_route["message"],
                "notice": "",
            }

    # 4. 'automatic' Preference Mode (Smart Engine Choice)
    # Priority 1: IndicTrans2 direct if installed (e.g. hin -> tam direct, or eng -> indic direct)
    if indic_ready:
        sec = "argos" if (compare_mode and argos_ready) else None
        can_comp = compare_mode and argos_ready
        lbl = "Compare Mode" if can_comp else "Ready (IndicTrans2 direct)"
        line = (
            f"{from_name} to {to_name}: Compare Mode (IndicTrans2 vs Argos)"
            if can_comp
            else f"{from_name} to {to_name}: IndicTrans2 (direct)"
        )
        tip = (
            "Compare Mode enabled: Translates sequentially with IndicTrans2 and Argos to check consensus."
            if can_comp
            else indic_route["tooltip"]
        )
        return {
            "status": "ready_compare" if can_comp else "ready_indictrans2",
            "route_type": "direct",
            "primary_engine": "indictrans2",
            "secondary_engine": sec,
            "can_compare": can_comp,
            "is_ready": True,
            "can_translate": True,
            "source_code": src,
            "target_code": tgt,
            "source_name": from_name,
            "target_name": to_name,
            "status_label": lbl,
            "status_line": line,
            "tooltip": tip,
            "message": f"{from_name} to {to_name} (IndicTrans2 direct)",
            "notice": "",
        }

    # Priority 2: Argos direct if installed
    if argos_ready and argos_route.get("route_type") == "direct":
        return {
            "status": "ready_direct",
            "route_type": "direct",
            "primary_engine": "argos",
            "secondary_engine": None,
            "can_compare": False,
            "is_ready": True,
            "can_translate": True,
            "source_code": src,
            "target_code": tgt,
            "source_name": from_name,
            "target_name": to_name,
            "status_label": "Ready (Argos direct)",
            "status_line": f"{from_name} to {to_name}: Argos (direct)",
            "tooltip": argos_route["tooltip"],
            "message": argos_route["message"],
            "notice": "",
        }

    # Priority 3: Argos English pivot if installed
    if argos_ready and argos_route.get("route_type") == "pivot":
        return {
            "status": "ready_pivot",
            "route_type": "pivot",
            "primary_engine": "argos",
            "secondary_engine": None,
            "can_compare": False,
            "is_ready": True,
            "can_translate": True,
            "source_code": src,
            "target_code": tgt,
            "source_name": from_name,
            "target_name": to_name,
            "status_label": "Ready via English",
            "status_line": f"{from_name} to {to_name}: Argos (via English)",
            "tooltip": argos_route["tooltip"],
            "message": argos_route["message"],
            "notice": "Translation will pivot through English.",
        }

    # Priority 4: Both missing - provide clear, helpful guidance
    # Check if IndicTrans2 is the natural engine for this pair (e.g. Indic-to-Indic)
    indic_direction = get_model_direction(src, tgt)
    if indic_direction == "indic-indic":
        # Indic to Indic: IndicTrans2 is strongly recommended because Argos has no direct model
        msg = (
            f"{from_name} to {to_name} offline translation is best served directly by IndicTrans2. "
            f"Place 'indic-indic' model in models/indictrans2/indic-indic/ "
            f"(or download Argos pivot models into models/argos/)."
        )
        tip = f"Direct Indian language translation requires IndicTrans2 'indic-indic' model in models/indictrans2/."
    else:
        # English to Indic or vice versa
        msg = (
            f"{from_name} to {to_name} offline translation model is missing. "
            f"Place IndicTrans2 model in models/indictrans2/{indic_direction or ''}/ "
            f"or place .argosmodel in models/argos/."
        )
        tip = msg

    return {
        "status": "model_missing",
        "route_type": "model_missing",
        "primary_engine": "indictrans2" if (indic_direction == "indic-indic") else "argos",
        "secondary_engine": None,
        "can_compare": False,
        "is_ready": False,
        "can_translate": False,
        "source_code": src,
        "target_code": tgt,
        "source_name": from_name,
        "target_name": to_name,
        "status_label": "Model Missing",
        "status_line": f"{from_name} to {to_name} (models missing)",
        "tooltip": tip,
        "message": msg,
        "notice": "",
    }
