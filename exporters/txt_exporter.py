"""
exporters/txt_exporter.py
-------------------------
Handles exporting extracted or translated text to plain text (.txt) files.
All exports use UTF-8 encoding to ensure full compatibility with Indian language scripts
(such as Devanagari, Tamil, Bengali, Telugu, etc.).

Never overwrites existing files without explicit permission.
"""

from pathlib import Path
from typing import Dict, Any, Union


def export_to_txt(
    text: str,
    output_path: Union[str, Path],
    overwrite: bool = True
) -> Dict[str, Any]:
    """
    Saves text to a UTF-8 encoded text file.

    Parameters:
        text (str): The document text to write.
        output_path (str | Path): Destination file path.
        overwrite (bool): Whether to allow replacing an existing file. Defaults to True.

    Returns:
        dict:
            - "success" (bool): True if write succeeded, False otherwise.
            - "file_path" (str): Absolute path to the saved file.
            - "byte_size" (int): Size of the written file.
            - "error" (str | None): Error description if write failed.
    """
    result: Dict[str, Any] = {
        "success": False,
        "file_path": str(output_path),
        "byte_size": 0,
        "error": None,
    }

    try:
        path = Path(output_path).resolve()

        # 1. Validation checks
        if not text or not text.strip():
            result["error"] = "Cannot export empty text."
            return result

        if path.exists() and not overwrite:
            result["error"] = f"File already exists and overwrite is set to False: {path.name}"
            return result

        # 2. Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # 3. Write file with explicit UTF-8 encoding for multilingual support
        # Using write_text with utf-8 ensures Indian language characters are saved accurately
        path.write_text(text, encoding="utf-8")

        result["success"] = True
        result["file_path"] = str(path)
        result["byte_size"] = path.stat().st_size
        return result

    except PermissionError:
        result["error"] = f"Permission denied when attempting to write to {output_path}."
        return result
    except Exception as e:
        result["error"] = f"Failed to export TXT file: {str(e)}"
        return result
