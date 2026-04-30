"""PDF parser for Mercado Libre shipping labels.

Extracts Pack IDs, Venta IDs, page types, and barcode placement positions
from multi-format shipping label PDFs.

Barcode is positioned just below the column's last text line so it adapts
automatically to label height (with or without product header / encabezado).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

import pdfplumber


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class PageType(Enum):
    STANDARD_2COL = "standard_2col"
    STANDARD_1COL = "standard_1col"
    STANDARD_1COL_PRODUCTS = "standard_1col_products"
    JT_EXPRESS = "jt_express"
    SUMMARY = "summary"


@dataclass
class LabelInfo:
    pack_id: str          # Full ID like "2000011633126699"
    page_number: int      # 0-indexed
    column: str           # "left", "right", or "full"
    page_type: PageType
    barcode_y: float      # y-coordinate for barcode (from page top, pdfplumber coords)
    barcode_x: float      # x-coordinate for barcode start
    label_index: int = 0  # sequential 1..N within a single PDF (assigned at end of parse_pdf)


@dataclass
class SummaryRow:
    pack_id: str
    page_number: int
    y: float              # vertical position of the row (pdfplumber coords)
    x_left: float         # left-most x of the row's content (for badge placement)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pattern to normalise IDs (remove internal spaces)
_SPACE_STRIP = re.compile(r'\s+')

# Gap between last text line and our barcode
_BARCODE_Y_GAP = 6.0

# Default barcode x margins
_BARCODE_X_LEFT = 42.0
_BARCODE_X_RIGHT = 304.0
_BARCODE_X_FULL = 42.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_id(raw: str) -> str:
    """Remove spaces from an extracted ID string."""
    return _SPACE_STRIP.sub('', raw).strip()


def _is_summary_page(words: list[dict]) -> bool:
    """Detect summary / checklist pages.

    Summary pages contain "Identif(i)icaci(o|ó)n" and "Productos" in a
    header row near the top of the page.
    """
    has_ident = False
    has_productos = False
    for w in words:
        top = float(w['top'])
        text = w['text']
        if top < 120:
            if 'Identif' in text or 'dentif' in text:
                has_ident = True
            if text == 'Productos' and top > 60:
                has_productos = True
    return has_ident and has_productos


def _has_jt_markers(words: list[dict], x_min: float | None = None, x_max: float | None = None) -> bool:
    """Return True if the page (or column region) has J&T Express markers."""
    for w in words:
        text = w['text']
        x0 = float(w['x0'])
        if x_min is not None and x0 < x_min:
            continue
        if x_max is not None and x0 > x_max:
            continue
        if text in ('JTMLM', 'JMX') or text.startswith('JMX0'):
            return True
        if 'jtexpress' in text.lower():
            return True
    return False


def _extract_ids_with_positions(words: list[dict]) -> list[tuple[str, float, float]]:
    """Extract (normalised_id, x0, top) tuples from words.

    We look for consecutive words forming patterns like:
      "Pack" "ID:" "2000011633126699"    (tear-off header, no space in number)
      "Pack" "ID:2000011633126699"       (body, merged)
      "Venta" "ID:" "2000..." or "Venta:" "2000..."
      "Venta:2000..."                    (body, merged)

    For the tear-off header "Pack ID: 2000 11633126699" the number may be
    split across 2 words.
    """
    results: list[tuple[str, float, float]] = []
    n = len(words)

    # Sort words by (top, x0) for sequential scanning
    sorted_words = sorted(words, key=lambda w: (float(w['top']), float(w['x0'])))

    i = 0
    while i < n:
        w = sorted_words[i]
        text = w['text']
        x0 = float(w['x0'])
        top = float(w['top'])

        # --- Pattern 1: merged body form "ID:2000..." or "Venta:2000..." or "Pack ID:2000..." ---
        m = re.search(r'(?:ID|Venta)\s*:\s*(2000[\d ]{12,16})', text)
        if m:
            nid = _normalise_id(m.group(1))
            if len(nid) >= 16:
                results.append((nid, x0, top))
                i += 1
                continue

        # --- Pattern 2: "Pack" or "Venta" followed by "ID:" then number ---
        if text in ('Pack', 'Venta'):
            # Look ahead for "ID:" and then the number
            j = i + 1
            # Skip to the ID: part
            if j < n:
                next_text = sorted_words[j]['text']
                next_top = float(sorted_words[j]['top'])

                # Must be on similar line (within 5 pts)
                if abs(next_top - top) < 5:
                    # "ID:" followed by number in next word(s)
                    if next_text == 'ID:':
                        # Number should be in subsequent word(s)
                        k = j + 1
                        if k < n and abs(float(sorted_words[k]['top']) - top) < 5:
                            num_text = sorted_words[k]['text']
                            # Check if number starts with 2000
                            if num_text.startswith('2000'):
                                # May need to combine with next word if split
                                full_num = num_text
                                while len(_normalise_id(full_num)) < 16 and k + 1 < n:
                                    k += 1
                                    if abs(float(sorted_words[k]['top']) - top) < 5:
                                        candidate = sorted_words[k]['text']
                                        if candidate.isdigit():
                                            full_num += candidate
                                        else:
                                            break
                                    else:
                                        break
                                nid = _normalise_id(full_num)
                                if len(nid) >= 16:
                                    results.append((nid, x0, top))
                                    i = k + 1
                                    continue

                    # "ID:" merged with number: "ID:2000..."
                    id_match = re.match(r'ID:\s*(2000[\d ]{12,16})', next_text)
                    if id_match:
                        nid = _normalise_id(id_match.group(1))
                        if len(nid) >= 16:
                            results.append((nid, x0, top))
                            i = j + 1
                            continue

        i += 1

    return results


def _max_content_bottom(words: list[dict], x_min: float, x_max: float) -> float | None:
    """Return the maximum 'bottom' y-coordinate of any text within the given
    x-range, or None if no words fall in the range.

    Used to position the barcode just below the last line of label content,
    independent of whether the label has an encabezado (product header) or
    not, and independent of label format (10x15 vs 10x20).
    """
    bottoms = [
        float(w['bottom'])
        for w in words
        if x_min <= float(w['x0']) <= x_max
    ]
    return max(bottoms) if bottoms else None


def _has_product_panel(words: list[dict]) -> bool:
    """Detect if the page has a product panel on the right side.

    1-column + products pages have "productos" or "unidades" text
    on the right side (x > page_width/2), typically near the top.
    They also have a "Productos" header on the right.
    """
    for w in words:
        text = w['text']
        x0 = float(w['x0'])
        top = float(w['top'])
        if x0 > 280 and top < 100:
            if text == 'Productos':
                return True
    return False


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_pdf(pdf_path: str | Path) -> List[LabelInfo]:
    """Parse a Mercado Libre shipping label PDF and extract label information.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of LabelInfo dataclasses, one per shipping label found.
    """
    pdf_path = Path(pdf_path)
    labels: list[LabelInfo] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_width = float(page.width)
            midpoint = page_width / 2
            words = page.extract_words()

            # --- Skip summary pages ---
            if _is_summary_page(words):
                continue

            # --- Extract IDs with positions ---
            raw_ids = _extract_ids_with_positions(words)
            if not raw_ids:
                continue

            # --- Deduplicate: keep unique IDs per column side ---
            # Group by (id, side)
            seen_left: set[str] = set()
            seen_right: set[str] = set()

            left_ids: list[tuple[str, float, float]] = []
            right_ids: list[tuple[str, float, float]] = []

            for nid, x0, top in raw_ids:
                if x0 < midpoint:
                    if nid not in seen_left:
                        seen_left.add(nid)
                        left_ids.append((nid, x0, top))
                else:
                    if nid not in seen_right:
                        seen_right.add(nid)
                        right_ids.append((nid, x0, top))

            # --- Classify page type ---
            has_left = len(left_ids) > 0
            has_right = len(right_ids) > 0
            has_products = _has_product_panel(words)
            has_jt_any = _has_jt_markers(words)

            # Determine if truly 2-column or 1-col+products.
            # On 1-col+products pages the right side repeats the SAME ID
            # from the left (product tear-off strip header). True 2-col
            # pages have DIFFERENT IDs on left and right.
            right_only_ids = seen_right - seen_left
            is_two_col = has_left and has_right and len(right_only_ids) > 0

            # Check J&T per column
            has_jt_left = _has_jt_markers(words, x_min=0, x_max=midpoint)
            has_jt_right = _has_jt_markers(words, x_min=midpoint, x_max=page_width)

            if is_two_col:
                # Two-column page - one label per side
                for nid, _x0, _top in left_ids:
                    ptype = PageType.JT_EXPRESS if has_jt_left else PageType.STANDARD_2COL
                    content_bottom = _max_content_bottom(words, 0, midpoint)
                    barcode_y = (content_bottom + _BARCODE_Y_GAP) if content_bottom else 530.0
                    labels.append(LabelInfo(
                        pack_id=nid,
                        page_number=page_idx,
                        column="left",
                        page_type=ptype,
                        barcode_y=barcode_y,
                        barcode_x=_BARCODE_X_LEFT,
                    ))

                for nid, _x0, _top in right_ids:
                    if nid in seen_left:
                        # Right-side ID that's actually a product strip echo, skip
                        continue
                    ptype = PageType.JT_EXPRESS if has_jt_right else PageType.STANDARD_2COL
                    content_bottom = _max_content_bottom(words, midpoint, page_width)
                    barcode_y = (content_bottom + _BARCODE_Y_GAP) if content_bottom else 530.0
                    labels.append(LabelInfo(
                        pack_id=nid,
                        page_number=page_idx,
                        column="right",
                        page_type=ptype,
                        barcode_y=barcode_y,
                        barcode_x=_BARCODE_X_RIGHT,
                    ))

            elif has_left:
                # Single column: 1-col, 1-col+products, J&T, or new 10x15 format
                nid = left_ids[0][0]
                if has_jt_any:
                    ptype = PageType.JT_EXPRESS
                elif has_products:
                    ptype = PageType.STANDARD_1COL_PRODUCTS
                else:
                    ptype = PageType.STANDARD_1COL

                # Restrict content scan to the label's column when products are
                # in the right half — otherwise the long product list pushes
                # the barcode way below the label area.
                if has_products:
                    content_bottom = _max_content_bottom(words, 0, midpoint)
                else:
                    content_bottom = _max_content_bottom(words, 0, page_width)

                barcode_y = (content_bottom + _BARCODE_Y_GAP) if content_bottom else 530.0
                labels.append(LabelInfo(
                    pack_id=nid,
                    page_number=page_idx,
                    column="full" if not has_products else "left",
                    page_type=ptype,
                    barcode_y=barcode_y,
                    barcode_x=_BARCODE_X_FULL,
                ))

            elif has_right:
                # Unusual: only right column has ID
                nid = right_ids[0][0]
                ptype = PageType.JT_EXPRESS if has_jt_any else PageType.STANDARD_1COL
                content_bottom = _max_content_bottom(words, midpoint, page_width)
                barcode_y = (content_bottom + _BARCODE_Y_GAP) if content_bottom else 530.0
                labels.append(LabelInfo(
                    pack_id=nid,
                    page_number=page_idx,
                    column="full",
                    page_type=ptype,
                    barcode_y=barcode_y,
                    barcode_x=_BARCODE_X_RIGHT,
                ))

    # Assign sequential per-PDF index (1..N)
    for i, label in enumerate(labels, start=1):
        label.label_index = i

    return labels


# ---------------------------------------------------------------------------
# Summary page parsing — for matching label numbers to summary rows
# ---------------------------------------------------------------------------

def parse_summary_rows(pdf_path: str | Path) -> List[SummaryRow]:
    """Locate Pack/Venta IDs on summary pages and return their row positions.

    Used to draw operator-friendly numeric badges next to each row on the
    summary so the printed label number matches the surtido checklist.
    """
    pdf_path = Path(pdf_path)
    rows: list[SummaryRow] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            words = page.extract_words()
            if not _is_summary_page(words):
                continue

            # On summary pages, Pack IDs appear as 16-digit numbers prefixed
            # by "Pack ID:" (or merged "ID:200001..."). The row's leftmost
            # text is typically the "Identificación" hash code at x≈30-60.
            for w in words:
                text = w['text']
                x0 = float(w['x0'])
                top = float(w['top'])

                m = re.match(r'(?:Pack\s*ID:|Venta:|ID:)?\s*(2000\d{12,16})$', text)
                if not m:
                    continue
                nid = _normalise_id(m.group(1))
                if len(nid) < 16:
                    continue
                # Skip IDs that don't start with 2000 (already enforced by regex)
                rows.append(SummaryRow(
                    pack_id=nid,
                    page_number=page_idx,
                    y=top,
                    x_left=x0,
                ))

    return rows
