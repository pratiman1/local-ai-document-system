"""
pdf_extractor.py
----------------
This module handles all PDF text extraction operations using PyMuPDF (fitz).
It processes documents entirely locally on your Mac without sending data anywhere.

Why keep this in a separate file?
In software development, separating the 'business logic' (extracting text)
from the 'user interface' (Streamlit) makes your code clean, modular, and easy to test.
"""

from typing import Union, Dict, Any, List
import io
import pymupdf as fitz  # Modern import for PyMuPDF (suppresses legacy fitz deprecation warning)


def extract_text_from_pdf(
    pdf_source: Union[str, bytes, io.BytesIO]
) -> Dict[str, Any]:
    """
    Extracts text and metadata from a PDF file locally.

    Parameters:
        pdf_source (str | bytes | BytesIO):
            The PDF to process. Can be:
            - A string representing the local file path.
            - Raw bytes (e.g. from Streamlit file uploader).
            - A BytesIO stream.

    Returns:
        dict: A dictionary containing:
            - "success" (bool): True if extraction succeeded, False otherwise.
            - "page_count" (int): Total number of pages.
            - "pages" (list[dict]): List with page numbers and text per page.
            - "full_text" (str): Combined text from all pages.
            - "is_empty" (bool): True if PDF has pages but contains no readable text.
            - "error" (str | None): Error description if processing failed.
    """
    # Initialize the default result structure
    result: Dict[str, Any] = {
        "success": False,
        "page_count": 0,
        "pages": [],
        "full_text": "",
        "is_empty": False,
        "error": None,
    }

    doc = None
    try:
        # 1. Open the PDF document based on the input type
        if isinstance(pdf_source, str):
            # Input is a local file path
            # Open in read-only mode so the original file is never modified or overwritten
            doc = fitz.open(pdf_source)
        elif isinstance(pdf_source, bytes):
            # Input is raw bytes (e.g., from Streamlit file upload)
            if len(pdf_source) == 0:
                result["error"] = "The uploaded file is empty (0 bytes)."
                return result
            doc = fitz.open(stream=pdf_source, filetype="pdf")
        elif isinstance(pdf_source, io.BytesIO):
            # Input is a BytesIO stream
            pdf_bytes = pdf_source.getvalue()
            if len(pdf_bytes) == 0:
                result["error"] = "The provided file stream is empty (0 bytes)."
                return result
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        else:
            result["error"] = f"Unsupported input type: {type(pdf_source).__name__}"
            return result

        # 2. Check if the PDF has any pages
        total_pages = len(doc)
        result["page_count"] = total_pages

        if total_pages == 0:
            result["error"] = "The PDF contains no pages."
            return result

        # 3. Extract text page by page
        pages_data: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []

        for page_index in range(total_pages):
            page_number = page_index + 1  # 1-indexed for human readability
            page = doc.load_page(page_index)

            # PyMuPDF extracts text directly from the digital text layer
            page_text = page.get_text("text").strip()

            pages_data.append({
                "page_number": page_number,
                "text": page_text,
                "char_count": len(page_text),
                "word_count": len(page_text.split()) if page_text else 0
            })

            if page_text:
                full_text_parts.append(f"--- Page {page_number} ---\n{page_text}")

        # Combine all extracted text with clean page separators
        result["pages"] = pages_data
        result["full_text"] = "\n\n".join(full_text_parts)

        # 4. Check if the document was empty or contains scanned images
        # If pages exist but no text was found, it's either blank or an image-only PDF
        if not result["full_text"].strip():
            result["is_empty"] = True

        result["success"] = True
        return result

    except fitz.FileDataError as e:
        # Handles corrupted or non-PDF files
        result["error"] = f"Invalid or corrupted PDF file: {str(e)}"
        return result
    except Exception as e:
        # Handles any unexpected errors
        result["error"] = f"An unexpected error occurred while reading the PDF: {str(e)}"
        return result
    finally:
        # Always close the document to free memory
        if doc is not None:
            doc.close()
