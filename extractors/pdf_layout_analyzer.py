"""
extractors/pdf_layout_analyzer.py
----------------------------------
Extracts visual geometry, text blocks, bounding boxes, font attributes,
images, and vector paths from original PDF documents using PyMuPDF (fitz).

Design Principles:
1. 100% Offline execution without external dependencies.
2. Preserves precise page geometry (e.g. 513.0 x 702.0 pt B5 book format).
3. Classifies blocks semantically: headers, footers, page numbers, headings,
   callout sidebars, lists, and body paragraphs.
4. Detects columns, embedded photos/raster images, and vector line drawings.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
import re
import fitz  # PyMuPDF


@dataclass
class TextSpan:
    text: str
    font: str
    size: float
    flags: int
    color: int
    bbox: Tuple[float, float, float, float]
    is_bold: bool = False
    is_italic: bool = False


@dataclass
class TextLine:
    spans: List[TextSpan]
    bbox: Tuple[float, float, float, float]
    text: str = ""


@dataclass
class TextBlock:
    block_id: int
    bbox: Tuple[float, float, float, float]
    text: str
    lines: List[TextLine]
    avg_font_size: float
    primary_font: str
    is_bold: bool
    color: Tuple[float, float, float]
    block_type: str  # "header", "footer", "page_number", "heading", "sidebar", "bullet", "body"
    column: int  # 0 = left/single, 1 = right

    @property
    def rect(self) -> fitz.Rect:
        return fitz.Rect(self.bbox)


@dataclass
class ImageBlock:
    image_id: int
    bbox: Tuple[float, float, float, float]
    width: int
    height: int
    ext: str

    @property
    def rect(self) -> fitz.Rect:
        return fitz.Rect(self.bbox)


@dataclass
class PageLayout:
    page_number: int
    width: float
    height: float
    rect: fitz.Rect
    text_blocks: List[TextBlock] = field(default_factory=list)
    image_blocks: List[ImageBlock] = field(default_factory=list)
    drawing_count: int = 0
    column_count: int = 1
    has_images: bool = False
    has_drawings: bool = False
    header_block: Optional[TextBlock] = None
    footer_block: Optional[TextBlock] = None
    page_number_block: Optional[TextBlock] = None


class PDFLayoutAnalyzer:
    """Analyzes page geometry, text blocks, images, and graphics for PDF reconstruction."""

    def __init__(self, doc_or_path: Optional[Any] = None):
        self._doc: Optional[fitz.Document] = None
        if isinstance(doc_or_path, (str, Path)):
            self._doc = fitz.open(str(doc_or_path))
        elif isinstance(doc_or_path, fitz.Document):
            self._doc = doc_or_path

    def analyze_page(self, page: fitz.Page, page_number: int = 1) -> PageLayout:
        """Extracts complete layout metadata from a single fitz.Page."""
        p_rect = page.rect
        width = p_rect.width
        height = p_rect.height

        # 1. Extract raw dict from PyMuPDF
        raw_dict = page.get_text("dict")
        blocks_data = raw_dict.get("blocks", [])

        text_blocks: List[TextBlock] = []
        image_blocks: List[ImageBlock] = []

        block_counter = 0
        img_counter = 0

        # Collect drawing count
        drawings = page.get_drawings()
        drawing_count = len(drawings)

        # First pass: classify text blocks and image blocks
        for b in blocks_data:
            b_type = b.get("type", 0)
            bbox = tuple(b.get("bbox", (0, 0, 0, 0)))

            if b_type == 1:
                # Image block
                img_blocks_info = ImageBlock(
                    image_id=img_counter,
                    bbox=bbox,
                    width=b.get("width", 0),
                    height=b.get("height", 0),
                    ext=b.get("ext", "png"),
                )
                image_blocks.append(img_blocks_info)
                img_counter += 1
                continue

            if b_type != 0:
                continue

            # Text block processing
            lines_data = b.get("lines", [])
            lines: List[TextLine] = []
            block_spans: List[TextSpan] = []
            full_block_text_parts = []

            for l in lines_data:
                l_bbox = tuple(l.get("bbox", (0, 0, 0, 0)))
                spans_data = l.get("spans", [])
                spans: List[TextSpan] = []
                line_text_parts = []

                for s in spans_data:
                    s_text = s.get("text", "")
                    s_font = s.get("font", "Unknown")
                    s_size = float(s.get("size", 10.0))
                    s_flags = int(s.get("flags", 0))
                    s_color = int(s.get("color", 0))
                    s_bbox = tuple(s.get("bbox", (0, 0, 0, 0)))

                    is_bold = bool(s_flags & 2 or "bold" in s_font.lower())
                    is_italic = bool(s_flags & 1 or "italic" in s_font.lower())

                    span = TextSpan(
                        text=s_text,
                        font=s_font,
                        size=s_size,
                        flags=s_flags,
                        color=s_color,
                        bbox=s_bbox,
                        is_bold=is_bold,
                        is_italic=is_italic,
                    )
                    spans.append(span)
                    block_spans.append(span)
                    line_text_parts.append(s_text)

                line_full_text = "".join(line_text_parts)
                lines.append(TextLine(spans=spans, bbox=l_bbox, text=line_full_text))
                full_block_text_parts.append(line_full_text)

            block_text = "\n".join(full_block_text_parts).strip()
            if not block_text:
                continue

            # Determine average font size and primary font
            if block_spans:
                avg_size = sum(s.size * len(s.text) for s in block_spans) / max(1, sum(len(s.text) for s in block_spans))
                primary_font = max(set(s.font for s in block_spans), key=lambda f: sum(len(s.text) for s in block_spans if s.font == f))
                is_bold = any(s.is_bold for s in block_spans)
                # Decode color int to RGB float tuple
                c_int = block_spans[0].color
                r = ((c_int >> 16) & 0xFF) / 255.0
                g = ((c_int >> 8) & 0xFF) / 255.0
                b_val = (c_int & 0xFF) / 255.0
                color_rgb = (r, g, b_val)
            else:
                avg_size = 10.0
                primary_font = "Default"
                is_bold = False
                color_rgb = (0.0, 0.0, 0.0)

            # Classify semantic block type
            x0, y0, x1, y1 = bbox
            block_type = self._classify_block(
                text=block_text,
                bbox=bbox,
                avg_size=avg_size,
                is_bold=is_bold,
                page_width=width,
                page_height=height,
            )

            # Determine column (0 = left/single, 1 = right)
            column = 1 if x0 > width * 0.55 else 0

            text_blocks.append(
                TextBlock(
                    block_id=block_counter,
                    bbox=bbox,
                    text=block_text,
                    lines=lines,
                    avg_font_size=round(avg_size, 1),
                    primary_font=primary_font,
                    is_bold=is_bold,
                    color=color_rgb,
                    block_type=block_type,
                    column=column,
                )
            )
            block_counter += 1

        # Check for 2-column body text
        body_blocks = [b for b in text_blocks if b.block_type in ("body", "bullet", "heading")]
        has_left = any(b.column == 0 and b.rect.width < width * 0.55 for b in body_blocks)
        has_right = any(b.column == 1 for b in body_blocks)
        col_count = 2 if (has_left and has_right) else 1

        # Identify header, footer, page number
        hdr = next((b for b in text_blocks if b.block_type == "header"), None)
        ftr = next((b for b in text_blocks if b.block_type == "footer"), None)
        pg_num_b = next((b for b in text_blocks if b.block_type == "page_number"), None)

        return PageLayout(
            page_number=page_number,
            width=width,
            height=height,
            rect=p_rect,
            text_blocks=text_blocks,
            image_blocks=image_blocks,
            drawing_count=drawing_count,
            column_count=col_count,
            has_images=len(image_blocks) > 0,
            has_drawings=drawing_count > 0,
            header_block=hdr,
            footer_block=ftr,
            page_number_block=pg_num_b,
        )

    def _classify_block(
        self,
        text: str,
        bbox: Tuple[float, float, float, float],
        avg_size: float,
        is_bold: bool,
        page_width: float,
        page_height: float,
    ) -> str:
        """Classifies text block into semantic role."""
        s = text.strip()
        x0, y0, x1, y1 = bbox

        # Page number (top or bottom corner/center with plain digits)
        if s.isdigit() and (y0 < 65 or y1 > page_height - 65):
            return "page_number"

        # Running header (near top margin y < 70)
        if y1 < 65:
            return "header"

        # Running footer (near bottom margin y > height - 60)
        if y0 > page_height - 60:
            return "footer"

        # Sidebar / Callout box (typically on the right x0 > 340 in B5 width ~513)
        if x0 > page_width * 0.68 and (x1 - x0) < page_width * 0.32:
            return "sidebar"

        # Hierarchical Section Heading (e.g. 1.3.2 Front Office Manager)
        if re.match(r"^\d+(?:\.\d+)+\s+", s):
            return "heading"

        # Heading by typography (larger font or bold short title)
        if (avg_size >= 12.0 and is_bold) or (len(s.splitlines()) == 1 and len(s) < 60 and is_bold):
            return "heading"

        # Bullet point / list item
        if s.startswith("•") or re.match(r"^(?:[a-zA-Z0-9]+[\.\)]|\([a-zA-Z0-9]+\))\s+", s):
            return "bullet"

        return "body"

    def analyze_document(self, max_pages: Optional[int] = None) -> List[PageLayout]:
        """Analyzes all pages in the open document."""
        if not self._doc:
            raise RuntimeError("No document loaded in PDFLayoutAnalyzer.")

        layouts = []
        limit = min(len(self._doc), max_pages) if max_pages else len(self._doc)
        for i in range(limit):
            layouts.append(self.analyze_page(self._doc[i], page_number=i + 1))
        return layouts
