"""
translation/argos_translator.py
-------------------------------
Argos Translate offline translation engine implementation conforming to Translator.
Features:
1. Lightweight, 100% offline neural machine translation.
2. Direct language pair translation when direct models are installed.
3. Automatic pivot translation through English when no direct pair exists
   (e.g., Hindi -> English -> Tamil), notifying the user regarding potential quality loss.
4. Non-crashing dependency probing and clear instructions for downloading offline .argosmodel files.
5. User-controlled local model package validation and import (.argosmodel).
6. Zero network activity guarantee.
"""

import os
import json
import zipfile
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union

from translation.base_translator import (
    Translator,
    TranslationError,
    TranslatorNotAvailableError,
    LanguagePairNotSupportedError,
    TranslationOutput,
)

# Configure environment variables prior to importing argostranslate
# to ensure data, cache, and packages stay within the application workspace
# and never cause permissions errors or conflict with system-level paths.
from config.settings import ARGOS_MODELS_DIR, ARGOS_PACKAGES_DIR

# Probing for argostranslate
try:
    import argostranslate.package
    import argostranslate.translate
    import argostranslate.settings
    _ARGOS_AVAILABLE = True

    # Also register user standard packages directory if present on host
    try:
        user_packages = Path.home() / ".local" / "share" / "argos-translate" / "packages"
        if user_packages.is_dir() and user_packages not in argostranslate.settings.package_dirs:
            argostranslate.settings.package_dirs.append(user_packages)
    except Exception:
        pass
except (ImportError, OSError, Exception):
    argostranslate = None
    _ARGOS_AVAILABLE = False


# Map 3-letter app codes to Argos 2-letter ISO 639-1 codes
APP_TO_ARGOS_LANG: Dict[str, str] = {
    "eng": "en",
    "hin": "hi",
    "tam": "ta",
    "tel": "te",
    "mar": "mr",
    "ben": "bn",
    "guj": "gu",
    "pan": "pa",
    "kan": "kn",
    "mal": "ml",
    "ori": "or",
    "asm": "as",
    "urd": "ur",
}

ARGOS_TO_APP_LANG: Dict[str, str] = {
    v: k for k, v in APP_TO_ARGOS_LANG.items()
}

# Direct pairs available in the official Argos Translate model index
# (Used to verify if a direct or pivot model theoretically exists in ArgosPM)
ARGOS_INDEX_DIRECT_PAIRS = {
    # English to / from Indian Languages
    ("en", "hi"), ("hi", "en"),
    ("en", "ta"),
    ("en", "te"),
    ("en", "bn"),
    ("en", "mr"),
    ("en", "gu"),
    ("en", "pa"),
    ("en", "kn"),
    ("en", "ml"),
    ("en", "ur"), ("ur", "en"),
    # Common global pairs
    ("en", "es"), ("es", "en"),
    ("en", "fr"), ("fr", "en"),
    ("en", "de"), ("de", "en"),
    ("en", "it"), ("it", "en"),
    ("en", "pt"), ("pt", "en"),
    ("en", "ru"), ("ru", "en"),
    ("en", "zh"), ("zh", "en"),
    ("en", "ja"), ("ja", "en"),
    ("en", "ar"), ("ar", "en"),
}


def get_language_display_name(code: str) -> str:
    """Returns human-friendly English display name for a 3-letter language code."""
    from config.languages import SUPPORTED_LANGUAGES
    info = SUPPORTED_LANGUAGES.get(code.lower())
    if info:
        return info.name
    return code.upper()


class ArgosTranslator(Translator):
    """
    Offline neural translation powered by Argos Translate.
    Supports local .argosmodel weights with automatic English pivoting.
    """

    def __init__(self):
        self._cached_installed_langs = None

    def get_name(self) -> str:
        return "Argos Translate (Offline Open-Source Engine)"

    def is_available(self) -> bool:
        """Checks if argostranslate is importable and available in environment."""
        return _ARGOS_AVAILABLE

    def _get_argos_languages(self):
        if not self.is_available():
            return []
        try:
            return argostranslate.translate.get_installed_languages()
        except Exception:
            return []

    @classmethod
    def refresh_installed_languages(cls, instance: Optional["ArgosTranslator"] = None):
        """Clears language caches and re-evaluates all packages from disk."""
        if not _ARGOS_AVAILABLE:
            return
        if instance is not None and hasattr(instance, "_cached_installed_langs"):
            instance._cached_installed_langs = None
        try:
            argostranslate.translate.get_installed_languages.cache_clear()
        except Exception:
            pass

    def get_installed_pairs_info(self) -> List[Dict[str, Any]]:
        """
        Returns structured details of installed direct language pairs for UI display.
        """
        if not self.is_available():
            return []

        try:
            packages = argostranslate.package.get_installed_packages()
        except Exception:
            packages = []

        pairs_info = []
        for pkg in packages:
            src_app = ARGOS_TO_APP_LANG.get(pkg.from_code, pkg.from_code)
            tgt_app = ARGOS_TO_APP_LANG.get(pkg.to_code, pkg.to_code)
            pairs_info.append({
                "source_code": src_app,
                "source_name": get_language_display_name(src_app),
                "target_code": tgt_app,
                "target_name": get_language_display_name(tgt_app),
                "from_argos": pkg.from_code,
                "to_argos": pkg.to_code,
                "is_direct": True,
            })
        return pairs_info

    def scan_and_install_models_folder(self, folder_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        Scans models/argos/ folder for .argosmodel files.
        Validates each model file using validate_model_file.
        Installs new valid models into the local Argos package store automatically.
        Skips already installed packages.
        Never deletes or modifies the user's files.

        Returns:
            Dict[str, Any]: Summary dictionary with 'scanned', 'installed', 'skipped', 'errors', 'installed_pairs'.
        """
        target_dir = Path(folder_path or ARGOS_MODELS_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        packages_dir = Path(ARGOS_PACKAGES_DIR)
        packages_dir.mkdir(parents=True, exist_ok=True)

        scanned_count = 0
        installed_count = 0
        skipped_count = 0
        errors = []

        if not self.is_available():
            return {
                "scanned": 0,
                "installed": 0,
                "skipped": 0,
                "errors": ["Argos Translate is not available in the current environment."],
                "installed_pairs": [],
            }

        # Find all .argosmodel files directly in target_dir
        model_files = [
            f for f in target_dir.iterdir()
            if f.is_file() and f.suffix.lower() == ".argosmodel"
        ]
        model_files.sort(key=lambda x: x.name.lower())

        for file_path in model_files:
            scanned_count += 1
            is_valid, val_msg, meta = self.validate_model_file(file_path)
            if not is_valid:
                errors.append(f"Skipped invalid file '{file_path.name}': {val_msg}")
                continue

            from_code = meta["from_code"]
            to_code = meta["to_code"]
            pkg_folder_name = f"translate-{from_code}_{to_code}"
            installed_pkg_path = packages_dir / pkg_folder_name

            # Check if package is already installed
            already_installed = False
            if installed_pkg_path.is_dir() and (installed_pkg_path / "metadata.json").is_file():
                already_installed = True
            elif hasattr(argostranslate, "package"):
                try:
                    pkgs = argostranslate.package.get_installed_packages()
                    already_installed = any(p.from_code == from_code and p.to_code == to_code for p in pkgs)
                except Exception:
                    pass

            if already_installed:
                skipped_count += 1
                continue

            # Install new package
            success, inst_msg = self.install_model_from_file(file_path)
            if success:
                installed_count += 1
            else:
                errors.append(f"Failed to install '{file_path.name}': {inst_msg}")

        if installed_count > 0:
            self.refresh_installed_languages()

        return {
            "scanned": scanned_count,
            "installed": installed_count,
            "skipped": skipped_count,
            "errors": errors,
            "installed_pairs": self.get_installed_pairs_info(),
        }

    def get_route_details(self, source: str, target: str) -> Dict[str, Any]:
        """
        Works out the required translation route and checks availability:
        1. Same language check (bypassed)
        2. Direct model check
        3. Pivot through English check (if both halves are installed)
        4. Theoretical Argos catalog check (if model does not exist in Argos index at all)
        5. Missing model guidance specifying exact pair and models/argos/ folder.
        """
        src_app = source.lower().strip()
        tgt_app = target.lower().strip()
        from_name = get_language_display_name(src_app)
        to_name = get_language_display_name(tgt_app)
        src_argos = APP_TO_ARGOS_LANG.get(src_app, src_app)
        tgt_argos = APP_TO_ARGOS_LANG.get(tgt_app, tgt_app)

        # 1. Same Language Bypass
        if src_app == tgt_app:
            return {
                "status": "same_language",
                "route_type": "same_language",
                "is_ready": True,
                "can_translate": True,
                "source_code": src_app,
                "target_code": tgt_app,
                "source_name": from_name,
                "target_name": to_name,
                "pivot_language": None,
                "status_label": "Ready (same language)",
                "status_line": f"{from_name} to {to_name} (same language)",
                "tooltip": f"Source and target languages are both '{from_name}'. Translation is bypassed.",
                "message": f"Source and target languages are both '{from_name}'. Translation skipped.",
                "missing_models": [],
            }

        if not self.is_available():
            inst = self.get_installation_instructions((src_app, tgt_app))
            return {
                "status": "engine_missing",
                "route_type": None,
                "is_ready": False,
                "can_translate": False,
                "source_code": src_app,
                "target_code": tgt_app,
                "source_name": from_name,
                "target_name": to_name,
                "pivot_language": None,
                "status_label": "Engine Missing",
                "status_line": f"{from_name} to {to_name} (engine missing)",
                "tooltip": "Argos Translate engine is not installed in your Python environment.",
                "message": "Argos Translate engine is not installed in your Python environment.",
                "missing_models": [],
                "instructions": inst,
            }

        installed = self._get_argos_languages()
        lang_dict = {lang.code: lang for lang in installed}
        src_obj = lang_dict.get(src_argos)
        tgt_obj = lang_dict.get(tgt_argos)

        # Check installed packages directly
        installed_packages = []
        if hasattr(argostranslate, "package"):
            try:
                installed_packages = argostranslate.package.get_installed_packages()
            except Exception:
                installed_packages = []

        installed_pkg_pairs = {(p.from_code, p.to_code) for p in installed_packages}

        # 2. Direct model check: a direct package is installed for this pair
        has_direct = (src_argos, tgt_argos) in installed_pkg_pairs

        if has_direct:
            return {
                "status": "ready_direct",
                "route_type": "direct",
                "is_ready": True,
                "can_translate": True,
                "source_code": src_app,
                "target_code": tgt_app,
                "source_name": from_name,
                "target_name": to_name,
                "pivot_language": None,
                "status_label": "Ready (direct)",
                "status_line": f"{from_name} to {to_name} (direct)",
                "tooltip": f"Direct offline translation model installed and ready for {from_name} to {to_name}.",
                "message": f"{from_name} to {to_name} (direct)",
                "missing_models": [],
            }

        # 3. Pivot through English ('en') check
        # A pivot route requires installed packages for (src_argos, "en") AND ("en", tgt_argos)
        has_to_en = (src_argos, "en") in installed_pkg_pairs
        has_from_en = ("en", tgt_argos) in installed_pkg_pairs

        if src_argos != "en" and tgt_argos != "en" and has_to_en and has_from_en:
            return {
                "status": "ready_pivot",
                "route_type": "pivot",
                "is_ready": True,
                "can_translate": True,
                "source_code": src_app,
                "target_code": tgt_app,
                "source_name": from_name,
                "target_name": to_name,
                "pivot_language": "eng",
                "status_label": "Ready via English",
                "status_line": f"{from_name} to {to_name} (via English)",
                "tooltip": f"Translation will pivot through English ({from_name} ➔ English ➔ {to_name}). Translation quality may be lower.",
                "message": f"{from_name} to {to_name} (via English)",
                "missing_models": [],
            }

        # 4. Check if the pair exists in the Argos index at all
        direct_in_catalog = (src_argos, tgt_argos) in ARGOS_INDEX_DIRECT_PAIRS
        pivot_in_catalog = (
            src_argos != "en" and tgt_argos != "en"
            and (src_argos, "en") in ARGOS_INDEX_DIRECT_PAIRS
            and ("en", tgt_argos) in ARGOS_INDEX_DIRECT_PAIRS
        )

        if not direct_in_catalog and not pivot_in_catalog:
            # Model does not exist in Argos index at all
            msg = (
                f"{from_name} to {to_name} offline translation model is not available "
                f"in the Argos Translate library (even via English pivot). "
                f"Please use the online AI Enhance option for this language pair."
            )
            return {
                "status": "unavailable_in_argos",
                "route_type": None,
                "is_ready": False,
                "can_translate": False,
                "source_code": src_app,
                "target_code": tgt_app,
                "source_name": from_name,
                "target_name": to_name,
                "pivot_language": None,
                "status_label": "Model Missing",
                "status_line": f"{from_name} to {to_name} (unavailable in Argos)",
                "tooltip": f"{from_name} to {to_name} is not available in Argos Translate. Please use the online AI Enhance option.",
                "message": msg,
                "missing_models": [],
            }

        # 5. Model exists in Argos catalog, but is not installed yet
        missing_models = []
        if src_argos == "en":
            missing_models.append(f"English to {to_name} (translate-en_{tgt_argos}.argosmodel)")
            if src_app == "eng" and tgt_app == "hin":
                msg = "English to Hindi offline translation model is not installed. Place translate-en_hi.argosmodel in models/argos/ folder."
            else:
                msg = f"{from_name} to {to_name} offline translation model is missing. Place translate-en_{tgt_argos}.argosmodel in models/argos/ folder."
        elif tgt_argos == "en":
            missing_models.append(f"{from_name} to English (translate-{src_argos}_en.argosmodel)")
            msg = f"{from_name} to English offline translation model is missing. Place translate-{src_argos}_en.argosmodel in models/argos/ folder."
        else:
            # Requires pivot via English (e.g. Hindi to Tamil)
            missing_parts = []
            if not has_to_en:
                missing_parts.append(f"{from_name} to English (translate-{src_argos}_en.argosmodel)")
                missing_models.append(f"{from_name} to English")
            if not has_from_en:
                missing_parts.append(f"English to {to_name} (translate-en_{tgt_argos}.argosmodel)")
                missing_models.append(f"English to {to_name}")
            parts_str = " and ".join(missing_parts)
            msg = (
                f"{from_name} to {to_name} offline translation requires English pivot "
                f"({from_name} ➔ English ➔ {to_name}). Missing model(s): {parts_str}. "
                f"Place .argosmodel file(s) in models/argos/ folder."
            )

        return {
            "status": "model_missing",
            "route_type": "pivot" if (src_argos != "en" and tgt_argos != "en") else "direct",
            "is_ready": False,
            "can_translate": False,
            "source_code": src_app,
            "target_code": tgt_app,
            "source_name": from_name,
            "target_name": to_name,
            "pivot_language": "eng" if (src_argos != "en" and tgt_argos != "en") else None,
            "status_label": "Model Missing",
            "status_line": f"{from_name} to {to_name} (model missing)",
            "tooltip": f"{msg}",
            "message": msg,
            "missing_models": missing_models,
        }

    def get_target_languages_availability(self, source: str = "eng") -> List[Dict[str, Any]]:
        """
        Returns availability info for all supported languages in the target dropdown
        when translating from the specified source language.
        """
        from config.languages import SUPPORTED_LANGUAGES
        results = []
        for code, lang in SUPPORTED_LANGUAGES.items():
            if code.lower() == source.lower():
                continue
            route = self.get_route_details(source, code)
            results.append({
                "code": code,
                "name": lang.name,
                "status": route["status"],
                "status_label": route["status_label"],
                "status_line": route["status_line"],
                "can_translate": route["can_translate"],
                "message": route["message"],
                "route_type": route["route_type"],
            })
        return results

    def supported_pairs(self) -> List[Tuple[str, str]]:
        """
        Returns all supported (source_app_code, target_app_code) pairs,
        including direct packages and pivoted combinations through English.
        """
        if not self.is_available():
            return []

        installed = self._get_argos_languages()
        if not installed:
            return []

        direct_pairs: List[Tuple[str, str]] = []
        lang_dict = {lang.code: lang for lang in installed}

        for src_lang in installed:
            src_app = ARGOS_TO_APP_LANG.get(src_lang.code, src_lang.code)
            for tgt_lang in installed:
                if src_lang == tgt_lang:
                    continue
                try:
                    trans = src_lang.get_translation(tgt_lang)
                    if trans is not None:
                        tgt_app = ARGOS_TO_APP_LANG.get(tgt_lang.code, tgt_lang.code)
                        direct_pairs.append((src_app, tgt_app))
                except Exception:
                    pass

        # Add pivoted pairs through 'en'
        all_pairs = list(direct_pairs)
        if "en" in lang_dict:
            sources_to_en = [src for src, tgt in direct_pairs if tgt == "eng"]
            targets_from_en = [tgt for src, tgt in direct_pairs if src == "eng"]

            for src in sources_to_en:
                for tgt in targets_from_en:
                    if src != tgt and (src, tgt) not in all_pairs:
                        all_pairs.append((src, tgt))

        return all_pairs

    def is_pair_supported(self, source: str, target: str) -> bool:
        """Checks if a direct or pivoted translation route exists between source and target."""
        if source.lower() == target.lower():
            return True
        route = self.get_route_details(source, target)
        return route.get("can_translate", False)

    @staticmethod
    def validate_model_file(model_path: Union[str, Path]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Strictly validates an .argosmodel file before installation.
        Checks:
        1. File existence and non-zero size.
        2. Valid zip archive format.
        3. Security: No path traversal (Zip Slip vulnerability).
        4. Presence and validity of metadata.json.
        5. Valid from_code and to_code language identifiers.
        6. Presence of model weights or tokenizers.

        Returns:
            Tuple[bool, str, Optional[Dict[str, Any]]]: (is_valid, message, metadata)
        """
        p = Path(model_path)
        if not p.is_file():
            return False, f"File does not exist: {model_path}", None

        if p.stat().st_size == 0:
            return False, "Selected model file is 0 bytes (empty).", None

        if not zipfile.is_zipfile(p):
            return False, "Not a valid Argos model file (must be a valid zip archive).", None

        try:
            with zipfile.ZipFile(p, "r") as zf:
                # Security Check: Prevent Zip Slip (path traversal)
                for member in zf.infolist():
                    name = member.filename
                    if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
                        return False, "Security violation: Archive contains path traversal components.", None

                # Find metadata.json
                meta_names = [n for n in zf.namelist() if n == "metadata.json" or n.endswith("/metadata.json")]
                if not meta_names:
                    return False, "Model archive is missing required 'metadata.json'.", None

                # Read and parse metadata.json
                meta_content = zf.read(meta_names[0]).decode("utf-8")
                try:
                    metadata = json.loads(meta_content)
                except json.JSONDecodeError as err:
                    return False, f"Corrupted 'metadata.json' in model: {str(err)}", None

                if not isinstance(metadata, dict):
                    return False, "'metadata.json' must contain a valid JSON object.", None

                # Extract from_code and to_code
                from_code = metadata.get("from_code") or (metadata.get("from_codes") and metadata["from_codes"][0])
                to_code = metadata.get("to_code") or (metadata.get("to_codes") and metadata["to_codes"][0])

                if not from_code or not to_code:
                    return False, "Model metadata is missing 'from_code' or 'to_code'.", None

                # Check for model weights or tokenizer
                has_weights = any(
                    "sentencepiece" in n or "bpe" in n or "model" in n or n.endswith(".bin") or n.endswith(".txt")
                    for n in zf.namelist()
                )
                if not has_weights:
                    return False, "Model archive does not contain translation weights or tokenizer.", None

                from_name = metadata.get("from_name", from_code)
                to_name = metadata.get("to_name", to_code)
                version = metadata.get("package_version", "1.0")

                info_dict = {
                    "from_code": from_code,
                    "to_code": to_code,
                    "from_name": from_name,
                    "to_name": to_name,
                    "package_version": version,
                    "raw_metadata": metadata,
                }
                return True, f"Valid model package: {from_name} to {to_name} (v{version})", info_dict

        except Exception as e:
            return False, f"Error validating model file: {str(e)}", None

    def install_model_from_file(self, model_path: Union[str, Path]) -> Tuple[bool, str]:
        """
        Validates and installs an offline .argosmodel package into the local packages directory.
        Refreshes language caches immediately upon successful installation.

        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self.is_available():
            return False, "Argos Translate is not available in the current environment."

        is_valid, val_msg, meta = self.validate_model_file(model_path)
        if not is_valid:
            return False, val_msg

        try:
            p = Path(model_path)
            target_packages_dir = Path(argostranslate.settings.package_data_dir)
            target_packages_dir.mkdir(parents=True, exist_ok=True)

            with argostranslate.package.package_lock:
                with zipfile.ZipFile(p, "r") as zf:
                    # Check if metadata.json is at root or inside a folder
                    has_root_meta = "metadata.json" in zf.namelist()
                    if has_root_meta:
                        # Extract into a dedicated subfolder so Package(dir) recognizes it
                        pkg_folder_name = f"translate-{meta['from_code']}_{meta['to_code']}"
                        extract_dir = target_packages_dir / pkg_folder_name
                        extract_dir.mkdir(parents=True, exist_ok=True)
                        zf.extractall(path=extract_dir)
                    else:
                        zf.extractall(path=target_packages_dir)

            self.refresh_installed_languages()
            from_name = meta.get("from_name", meta["from_code"])
            to_name = meta.get("to_name", meta["to_code"])
            return True, f"Successfully installed offline translation model: {from_name} to {to_name}."

        except Exception as e:
            return False, f"Failed to install model package: {str(e)}"

    def translate(self, text: str, source: str, target: str) -> TranslationOutput:
        """
        Translates text from source to target language code.
        Automatically applies pivoting through English when no direct pair exists.
        """
        if not text or not text.strip():
            return TranslationOutput(
                translated_text="",
                source_language=source,
                target_language=target,
            )

        if source.lower() == target.lower():
            return TranslationOutput(
                translated_text=text,
                source_language=source,
                target_language=target,
                was_pivoted=False,
                notice=f"Source and target languages are both '{source}'. Translation skipped.",
            )

        if not self.is_available():
            raise TranslatorNotAvailableError(
                "Argos Translate engine is not installed in your Python environment.",
                instructions=self.get_installation_instructions((source, target)),
            )

        src_argos = APP_TO_ARGOS_LANG.get(source.lower(), source.lower())
        tgt_argos = APP_TO_ARGOS_LANG.get(target.lower(), target.lower())

        installed = self._get_argos_languages()
        lang_dict = {lang.code: lang for lang in installed}

        src_obj = lang_dict.get(src_argos)
        tgt_obj = lang_dict.get(tgt_argos)

        # Pre-flight route and availability check
        route = self.get_route_details(source, target)
        if not route.get("can_translate", False):
            raise LanguagePairNotSupportedError(
                source, target,
                message=route["message"],
                instructions=self.get_installation_instructions((source, target)),
            )

        # 1. Attempt Direct Translation
        if route.get("route_type") == "direct" and src_obj and tgt_obj:
            try:
                direct_trans = src_obj.get_translation(tgt_obj)
                if direct_trans is not None:
                    translated_str = direct_trans.translate(text)
                    return TranslationOutput(
                        translated_text=translated_str,
                        source_language=source,
                        target_language=target,
                        was_pivoted=False,
                    )
            except Exception:
                pass

        # 2. Attempt Pivot Translation through English ('en')
        en_obj = lang_dict.get("en")
        if en_obj and src_obj and tgt_obj and src_obj != en_obj and tgt_obj != en_obj:
            try:
                to_en = src_obj.get_translation(en_obj)
                from_en = en_obj.get_translation(tgt_obj)

                if to_en is not None and from_en is not None:
                    intermediate_en = to_en.translate(text)
                    final_translated = from_en.translate(intermediate_en)
                    from_name = get_language_display_name(source)
                    to_name = get_language_display_name(target)
                    notice_msg = f"Pivoted through English ({from_name} ➔ English ➔ {to_name}). Translation quality may be lower."
                    return TranslationOutput(
                        translated_text=final_translated,
                        source_language=source,
                        target_language=target,
                        was_pivoted=True,
                        pivot_language="eng",
                        notice=notice_msg,
                    )
            except Exception as e:
                raise TranslationError(f"Pivot translation failed: {str(e)}")

        raise LanguagePairNotSupportedError(
            source, target,
            message=route["message"],
            instructions=self.get_installation_instructions((source, target)),
        )

    def get_installation_instructions(self, missing_pair: Optional[Tuple[str, str]] = None) -> str:
        """
        Returns copy-pasteable instructions for downloading offline .argosmodel packages.
        """
        if missing_pair:
            src, tgt = missing_pair
            from_name = get_language_display_name(src)
            to_name = get_language_display_name(tgt)
            if src.lower() == "eng" and tgt.lower() == "hin":
                header = "English to Hindi offline translation model is not installed."
            else:
                header = f"{from_name} to {to_name} offline translation model is not installed."
            pair_hint = f" for '{src}' to '{tgt}'"
        else:
            header = "Offline translation model is not installed."
            pair_hint = ""

        return (
            f"{header}\n\n"
            "To install Argos Translate in your local virtual environment, run:\n"
            "  pip install argostranslate\n\n"
            f"To enable offline translation{pair_hint}:\n"
            "1. Download the offline '.argosmodel' package file from:\n"
            "   https://www.argosopentech.com/argospm/index/\n"
            "2. Place the '.argosmodel' file directly into the 'models/argos/' folder.\n"
            "   (Or open Settings ⚙️ and click 'Import Offline Model' to copy it automatically).\n"
            "3. The application will automatically detect and install it on startup or Refresh.\n\n"
            "All models run 100% offline with zero cloud API dependency."
        )
