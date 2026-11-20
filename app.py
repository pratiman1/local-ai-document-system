"""
app.py
------
The main entry point for the Local AI Document System Streamlit application.
This file handles the user interface, file upload, status indicators, and downloads.

All processing occurs 100% locally on your Mac. No data ever leaves your computer.
"""

import os
from pathlib import Path
import streamlit as st
from extractors.pdf_extractor import extract_text_from_pdf

# ------------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & STYLING
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Local AI Document System",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Define project directories for reference
BASE_DIR = Path(__file__).resolve().parent
EXPORTS_DIR = BASE_DIR / "exports"
UPLOADS_DIR = BASE_DIR / "uploads"

# Ensure folders exist
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------
# 2. SIDEBAR - SYSTEM INFORMATION & GUIDE
# ------------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ System Status")

    st.success("🟢 Mode: 100% Local (Offline)")
    st.info("💻 Hardware: Apple M1 Optimized (8GB RAM friendly)")
    st.markdown("**Phase:** 1 — Local PDF Text Extraction")

    st.markdown("---")
    st.subheader("📖 How to use")
    st.markdown(
        """
        1. **Upload** any standard `.pdf` document.
        2. **Review** total pages, word count, and extracted content.
        3. **Inspect** the complete document or view page-by-page.
        4. **Download** the extracted text as a `.txt` file.
        """
    )

    st.markdown("---")
    st.subheader("🔒 Privacy Guarantee")
    st.caption(
        "Your documents are processed strictly in-memory on your local Mac. "
        "No cloud AI, no external APIs, and your original PDF is never modified."
    )


# ------------------------------------------------------------------------------
# 3. MAIN INTERFACE - HEADER
# ------------------------------------------------------------------------------
st.title("📄 Local AI Document Processing System")
st.markdown(
    "Extract clean text from PDF documents **locally and privately** on your Mac."
)
st.markdown("---")


# ------------------------------------------------------------------------------
# 4. FILE UPLOADER
# ------------------------------------------------------------------------------
uploaded_file = st.file_uploader(
    label="Select or drag and drop a PDF file to process:",
    type=["pdf"],
    help="Upload a standard PDF document. Encrypted or password-protected files must be unlocked.",
)

if uploaded_file is None:
    # Friendly placeholder when no file is uploaded yet
    st.info("👆 Please upload a PDF file using the uploader above to begin.")
else:
    # --------------------------------------------------------------------------
    # 5. LOCAL PROCESSING PIPELINE
    # --------------------------------------------------------------------------
    file_bytes = uploaded_file.getvalue()
    file_size_kb = len(file_bytes) / 1024

    with st.spinner("Extracting text locally with PyMuPDF..."):
        # We pass the raw bytes directly to our extractor module
        extraction_result = extract_text_from_pdf(file_bytes)

    # --------------------------------------------------------------------------
    # 6. RESULTS & DISPLAY
    # --------------------------------------------------------------------------
    if not extraction_result["success"]:
        # Handle invalid, corrupt, or unsupported PDF files gracefully
        st.error(f"❌ Extraction Error: {extraction_result['error']}")
        st.caption("Please check that the file is a valid, uncorrupted PDF document.")

    elif extraction_result["is_empty"]:
        # The PDF was opened successfully, but has no readable digital text layer
        st.warning("⚠️ Document opened, but no digital text could be extracted.")
        
        # Display page count metric
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Pages", extraction_result["page_count"])
        with col2:
            st.metric("File Size", f"{file_size_kb:.1f} KB")

        st.info(
            "💡 **Why did this happen?**\n\n"
            "This document is likely a **scanned image** or contains rasterized pictures of text. "
            "PyMuPDF extracts digital text layers. For scanned images, Optical Character Recognition (OCR) "
            "will be implemented in Phase 2!"
        )

    else:
        # Successful text extraction!
        total_pages = extraction_result["page_count"]
        full_text = extraction_result["full_text"]
        char_count = len(full_text)
        word_count = len(full_text.split())

        # Display Summary Metrics in clean columns
        st.subheader("📊 Document Overview")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Pages", total_pages)
        with col2:
            st.metric("Word Count", f"{word_count:,}")
        with col3:
            st.metric("Character Count", f"{char_count:,}")
        with col4:
            st.metric("File Size", f"{file_size_kb:.1f} KB")

        st.markdown("---")

        # Export & Download Section
        st.subheader("💾 Export Extracted Text")
        base_name = Path(uploaded_file.name).stem
        export_filename = f"{base_name}_extracted.txt"

        download_col, save_col = st.columns([1, 2])
        with download_col:
            st.download_button(
                label="📥 Download as TXT",
                data=full_text,
                file_name=export_filename,
                mime="text/plain",
                help="Click to download the extracted text directly to your Mac's Downloads folder.",
            )

        with save_col:
            # Optional button to also archive a copy inside the local project's exports/ directory
            if st.button("📁 Save a copy to project 'exports/' folder"):
                target_path = EXPORTS_DIR / export_filename
                target_path.write_text(full_text, encoding="utf-8")
                st.success(f"Saved locally to `{target_path}` (Original PDF remains untouched).")

        st.markdown("---")

        # Text Viewer Tabs (Combined view and Page-by-page view)
        st.subheader("📄 Extracted Content")
        tab_full, tab_pages = st.tabs(["📝 Full Text View", "📑 Page-by-Page Breakdown"])

        with tab_full:
            st.caption("Complete extracted text across all pages:")
            st.text_area(
                label="Extracted Text",
                value=full_text,
                height=450,
                label_visibility="collapsed",
            )

        with tab_pages:
            st.caption("Inspect text extracted from each individual page:")
            for page_info in extraction_result["pages"]:
                page_num = page_info["page_number"]
                p_text = page_info["text"]
                p_words = page_info["word_count"]

                with st.expander(f"Page {page_num} ({p_words} words)"):
                    if p_text:
                        st.text_area(
                            label=f"Text for Page {page_num}",
                            value=p_text,
                            height=200,
                            key=f"page_text_{page_num}",
                            label_visibility="collapsed",
                        )
                    else:
                        st.caption("*(No text on this page or contains only images)*")
