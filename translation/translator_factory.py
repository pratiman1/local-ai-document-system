"""
translation/translator_factory.py
---------------------------------
Factory pattern for instantiating translation engines.
Enables drop-in substitution of translation engines (e.g. Argos Translate now,
AI4Bharat IndicTrans2 later) without changing document processing pipelines or UI.
"""

from typing import Dict, Type, List
from translation.base_translator import Translator
from translation.argos_translator import ArgosTranslator
from translation.indictrans2_translator import IndicTrans2Translator


_TRANSLATOR_REGISTRY: Dict[str, Type[Translator]] = {
    "argos": ArgosTranslator,
    "indictrans2": IndicTrans2Translator,
}

_ACTIVE_TRANSLATORS: Dict[str, Translator] = {}


def get_translator(name: str = "argos", force_new: bool = False) -> Translator:
    """
    Returns an instance of the requested offline translator.
    """
    key = name.lower().strip()
    if key not in _TRANSLATOR_REGISTRY:
        supported = ", ".join(_TRANSLATOR_REGISTRY.keys())
        raise ValueError(f"Unknown translation engine '{name}'. Supported: {supported}")

    if not force_new and key in _ACTIVE_TRANSLATORS:
        return _ACTIVE_TRANSLATORS[key]

    instance = _TRANSLATOR_REGISTRY[key]()
    if not force_new:
        _ACTIVE_TRANSLATORS[key] = instance

    return instance


def list_available_translators() -> List[str]:
    """Returns a list of all registered translator engine keys."""
    return list(_TRANSLATOR_REGISTRY.keys())


def register_translator(name: str, translator_cls: Type[Translator]):
    """Registers a new translation engine class (e.g. IndicTrans2)."""
    if not issubclass(translator_cls, Translator):
        raise TypeError(f"Translator class {translator_cls} must inherit from Translator")
    _TRANSLATOR_REGISTRY[name.lower().strip()] = translator_cls
