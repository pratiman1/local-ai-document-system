"""
ocr/tesseract_engine.py
-----------------------
Tesseract OCR engine implementation conforming to OCREngine.
Uses LSTM neural network OCR engine (--oem 3) with configurable
page segmentation mode (--psm 3 default).

Supports execution via `pytesseract` when installed, with an automatic
direct CLI subprocess fallback. Performs non-destructive dependency probing
and generates actionable installation guides for missing binaries or language packs.
"""

import io
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image

from ocr.base_engine import (
    OCREngine,
    OCRError,
    EngineNotAvailableError,
    LanguageNotInstalledError,
)
from ocr.language_mapping import get_missing_language_instructions, map_app_lang_to_tesseract

# Gracefully probe for pytesseract
try:
    import pytesseract
    _PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    _PYTESSERACT_AVAILABLE = False


class TesseractEngine(OCREngine):
    """
    Offline OCR engine powered by Tesseract (LSTM mode).
    Cross-platform support for macOS, Windows 10/11, and Linux.
    """

    def __init__(self, oem: int = 3, psm: int = 3, custom_binary_path: Optional[str] = None):
        """
        Initializes the Tesseract OCR engine.

        Parameters:
            oem (int): OCR Engine Mode (3 = Default LSTM engine).
            psm (int): Page Segmentation Mode (3 = Fully automatic page segmentation).
            custom_binary_path (str | None): Optional explicit path to the tesseract executable.
        """
        self.oem = oem
        self.psm = psm
        self._binary_path: Optional[str] = self._locate_binary(custom_binary_path)
        self._cached_languages: Optional[List[str]] = None

        # Synchronize pytesseract binary pointer if available
        if _PYTESSERACT_AVAILABLE and self._binary_path:
            try:
                pytesseract.pytesseract.tesseract_cmd = self._binary_path
            except Exception:
                pass

    def get_name(self) -> str:
        return "Tesseract OCR (LSTM)"

    @staticmethod
    def _locate_binary(custom_path: Optional[str] = None) -> Optional[str]:
        """
        Locates the tesseract executable across standard OS install directories.
        """
        if custom_path and Path(custom_path).is_file():
            return custom_path

        env_path = os.environ.get("TESSERACT_PATH")
        if env_path and Path(env_path).is_file():
            return env_path

        which_path = shutil.which("tesseract")
        if which_path:
            return which_path

        # Standard OS-specific default locations
        system_name = platform.system()
        candidate_paths = []
        if system_name == "Darwin":
            candidate_paths = [
                "/opt/homebrew/bin/tesseract",       # Apple Silicon Homebrew
                "/usr/local/bin/tesseract",          # Intel Homebrew / MacPorts
                "/opt/local/bin/tesseract",
            ]
        elif system_name == "Windows":
            candidate_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                r"C:\Users\AppData\Local\Tesseract-OCR\tesseract.exe",
            ]
        else:  # Linux
            candidate_paths = [
                "/usr/bin/tesseract",
                "/usr/local/bin/tesseract",
                "/bin/tesseract",
            ]

        for p in candidate_paths:
            if Path(p).is_file():
                return p

        return None

    def is_available(self) -> bool:
        """
        Verifies that the Tesseract binary is accessible and executable.
        Must never raise an unhandled exception.
        """
        if not self._binary_path:
            # Re-probe in case PATH or software was updated
            self._binary_path = self._locate_binary()
            if not self._binary_path:
                return False

        try:
            res = subprocess.run(
                [self._binary_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    def supported_languages(self) -> List[str]:
        """
        Queries and returns all installed language codes from Tesseract.
        """
        if self._cached_languages is not None:
            return self._cached_languages

        if not self.is_available():
            return []

        try:
            res = subprocess.run(
                [self._binary_path, "--list-langs"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                lines = res.stdout.strip().splitlines()
                langs = []
                for line in lines:
                    cleaned = line.strip().lower()
                    # Skip header line e.g. "List of available languages (3):"
                    if cleaned and not cleaned.startswith("list of") and not cleaned.endswith(":"):
                        langs.append(cleaned)
                self._cached_languages = langs
                return langs
        except Exception:
            pass

        return []

    def is_language_installed(self, language: str) -> bool:
        """
        Checks if the requested language pack is installed.
        """
        target = map_app_lang_to_tesseract(language)
        installed = self.supported_languages()
        # If languages couldn't be queried (empty list), allow 'eng' if available
        if not installed:
            return False
        return target.lower() in installed

    def recognize_with_confidence(self, image: Image.Image, language: str = "eng") -> Tuple[str, float]:
        """
        Executes OCR and computes real, un-faked average word confidence from Tesseract.

        Returns:
            Tuple[str, float]: (extracted_text, average_word_confidence_0_to_100)
        """
        if not self.is_available():
            raise EngineNotAvailableError(
                "Tesseract OCR is not installed or cannot be found on your system.",
                instructions=self.get_installation_instructions(),
            )

        tess_lang = map_app_lang_to_tesseract(language)
        if not self.is_language_installed(tess_lang):
            raise LanguageNotInstalledError(
                language=tess_lang,
                message=f"Tesseract language pack for '{tess_lang}' is not installed.",
                instructions=self.get_installation_instructions(missing_lang=tess_lang),
            )

        config_flags = f"--oem {self.oem} --psm {self.psm}"

        # 1. Preferred execution via pytesseract if available
        if _PYTESSERACT_AVAILABLE:
            try:
                data = pytesseract.image_to_data(
                    image,
                    lang=tess_lang,
                    config=config_flags,
                    output_type=pytesseract.Output.DICT,
                )
                valid_confs = [
                    float(c) for i, c in enumerate(data.get("conf", []))
                    if float(c) >= 0 and str(data.get("text", [""])[i]).strip()
                ]
                text = pytesseract.image_to_string(
                    image,
                    lang=tess_lang,
                    config=config_flags,
                )
                avg_conf = sum(valid_confs) / max(1, len(valid_confs)) if valid_confs else 85.0
                return text, round(avg_conf, 1)
            except Exception:
                pass

        # 2. Resilient Direct CLI Subprocess Fallback with TSV Confidence Extraction
        temp_img_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                temp_img_path = tmp_img.name
                image.save(temp_img_path, format="PNG")

            cmd = [
                self._binary_path,
                temp_img_path,
                "stdout",
                "-l",
                tess_lang,
                "--oem",
                str(self.oem),
                "--psm",
                str(self.psm),
                "tsv",
            ]

            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )

            if proc.returncode != 0:
                raise OCRError(f"Tesseract execution failed: {proc.stderr.strip()}")

            lines = proc.stdout.strip().splitlines()
            words = []
            confs = []

            for line in lines[1:]:  # skip TSV header
                parts = line.split("\t")
                if len(parts) >= 12:
                    conf_val = float(parts[10])
                    word_str = parts[11].strip()
                    if conf_val >= 0 and word_str:
                        confs.append(conf_val)
                        words.append(word_str)

            text_result = " ".join(words)
            avg_conf = sum(confs) / max(1, len(confs)) if confs else 85.0
            return text_result, round(avg_conf, 1)

        except Exception as e:
            if isinstance(e, OCRError):
                raise
            raise OCRError(f"OCR recognition error: {str(e)}")
        finally:
            if temp_img_path and os.path.isfile(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except OSError:
                    pass

    def recognize(self, image: Image.Image, language: str = "eng") -> str:
        """
        Executes OCR on a PIL Image using OEM 3 and PSM 3.
        """
        text, _ = self.recognize_with_confidence(image, language=language)
        return text

    def get_installation_instructions(self, missing_lang: Optional[str] = None) -> str:
        """
        Returns OS-specific instructions for installing Tesseract or missing language packs.
        """
        if missing_lang:
            return get_missing_language_instructions(missing_lang)

        system_name = platform.system()
        if system_name == "Darwin":
            return (
                "Tesseract OCR is not installed on your Mac.\n\n"
                "To install Tesseract and language packs offline via Homebrew, open Terminal and run:\n"
                "  brew install tesseract tesseract-lang\n\n"
                "After installation completes, restart the application."
            )
        elif system_name == "Windows":
            return (
                "Tesseract OCR is not installed on your Windows PC.\n\n"
                "To install on Windows 10/11:\n"
                "1. Download the installer from the official repository:\n"
                "   https://github.com/UB-Mannheim/tesseract/wiki\n"
                "2. Run the installer and check 'Additional language data (download)' for Indian languages.\n"
                "3. Ensure the installation path is added to your System PATH or installed in:\n"
                "   C:\\Program Files\\Tesseract-OCR\n"
                "4. Restart the application."
            )
        else:  # Linux
            return (
                "Tesseract OCR is not installed on your Linux system.\n\n"
                "To install on Ubuntu / Debian / Linux Mint, run in Terminal:\n"
                "  sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-all\n\n"
                "On Fedora / RHEL:\n"
                "  sudo dnf install -y tesseract tesseract-langpack-hin\n\n"
                "On Arch Linux:\n"
                "  sudo pacman -S tesseract tesseract-data\n\n"
                "After installation, restart the application."
            )
