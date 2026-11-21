"""
ocr/engine_factory.py
---------------------
Factory pattern for instantiating OCR engines.
Allows drop-in substitution of OCR engines (e.g., Tesseract now, PaddleOCR later)
without modifying any other application components.
"""

from typing import Dict, Type, List, Optional
from ocr.base_engine import OCREngine
from ocr.tesseract_engine import TesseractEngine


# Registry of known OCR engine classes
_ENGINE_REGISTRY: Dict[str, Type[OCREngine]] = {
    "tesseract": TesseractEngine,
    # Future drop-in engines can be registered here:
    # "paddleocr": PaddleOCREngine,
}

# Singleton / cached engine instances
_ACTIVE_ENGINES: Dict[str, OCREngine] = {}


def get_engine(
    name: str = "tesseract",
    oem: int = 3,
    psm: int = 3,
    custom_binary_path: Optional[str] = None,
    force_new: bool = False,
) -> OCREngine:
    """
    Retrieves or instantiates an OCR engine by identifier.

    Parameters:
        name (str): Engine name ('tesseract', etc.). Defaults to 'tesseract'.
        oem (int): OCR Engine Mode for Tesseract.
        psm (int): Page Segmentation Mode for Tesseract.
        custom_binary_path (str | None): Optional custom binary path.
        force_new (bool): If True, instantiates a fresh engine without reusing cache.

    Returns:
        OCREngine: An instantiated engine implementing the OCREngine interface.

    Raises:
        ValueError: If requested engine name is not registered.
    """
    key = name.lower().strip()
    if key not in _ENGINE_REGISTRY:
        supported = ", ".join(_ENGINE_REGISTRY.keys())
        raise ValueError(f"Unknown OCR engine '{name}'. Supported engines: {supported}")

    cache_key = f"{key}_{oem}_{psm}_{custom_binary_path}"
    if not force_new and cache_key in _ACTIVE_ENGINES:
        return _ACTIVE_ENGINES[cache_key]

    engine_cls = _ENGINE_REGISTRY[key]
    if key == "tesseract":
        instance = engine_cls(oem=oem, psm=psm, custom_binary_path=custom_binary_path)
    else:
        instance = engine_cls()

    if not force_new:
        _ACTIVE_ENGINES[cache_key] = instance

    return instance


def list_available_engines() -> List[str]:
    """
    Returns a list of all registered engine identifiers.
    """
    return list(_ENGINE_REGISTRY.keys())


def register_engine(name: str, engine_cls: Type[OCREngine]):
    """
    Registers a new OCR engine class for future extensibility (e.g., PaddleOCR).
    """
    if not issubclass(engine_cls, OCREngine):
        raise TypeError(f"Engine class {engine_cls} must inherit from OCREngine")
    _ENGINE_REGISTRY[name.lower().strip()] = engine_cls
