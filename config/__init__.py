"""
Configuration package initialization.
"""
from .settings import APP_NAME, APP_VERSION, BASE_DIR, EXPORTS_DIR, UPLOADS_DIR
from .languages import SUPPORTED_LANGUAGES, DEFAULT_TARGET_LANGUAGE, get_language_dropdown_items

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "BASE_DIR",
    "EXPORTS_DIR",
    "UPLOADS_DIR",
    "SUPPORTED_LANGUAGES",
    "DEFAULT_TARGET_LANGUAGE",
    "get_language_dropdown_items",
]
