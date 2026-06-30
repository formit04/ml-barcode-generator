import io
from pdfrw import PdfReader as PdfrwReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.code128 import Code128
from app.pdf_parser import LabelInfo, parse_summary_rows


# Barcode dimensions — sized to fit the empty space at the bottom of the
# new 10x15 label format (printed area), close to the label content so the
# operator's print scale (typically 95%) keeps it visible.
_BAR_HEIGHT = 22
_BAR_WIDTH = 0.65
_FONT_SIZE = 6
_BARCODE_BLOCK_HEIGHT = 32  # bar_height + space for the human-readable digits

# Mercado Libre's 2026 redesign extended the label content further down the
# page, which pushed the content-anchored barcode off the bottom of the
# printable area. Lift the barcode so it stays visible and scannable
# (operator request, Jun 2026): 1 cm up, then 2 mm back down per print tuning
# → net 8 mm. Other (older) formats keep ample room below their content, so the
# same lift leaves them well within the page.
_BARCODE_UP_SHIFT = 8.0 * 72.0 / 25.4  # 8 mm ≈ 22.68 pt

# White backing behind the barcode. Kept as tight as possible so it overlaps the
# recipient address (which now reaches the bottom of the label) as little as
# possible while still giving the bars a clean white field. Code128.width
# already includes the quiet zones a scanner needs, so the box width is taken
# from the barcode itself; vertically we cover the bars plus the descender of
# the human-readable digits, which sit ~4-5 pt below the barcode origin.
_BG_DIGITS_DESCENT = 5.0  # how far the human-readable digits drop below origin y
_BG_PAD = 1.0             # hairline margin around the barcode ink

# Sequential number badge (top-right of label area).
_BADGE_RADIUS = 13           # ~9 mm circle — visible at arm's length
_BADGE_MARGIN = 6            # gap from page/column edge
_BADGE_FONT_SIZE = 14

# Summary page badge — anchored to a fixed left-margin position so it never
# overlaps the "Pack ID:" / "Venta:" / hash-code text (which starts at x≈31).
_SUMMARY_BADGE_RADIUS = 11
_SUMMARY_BADGE_FONT_SIZE = 12
_SUMMARY_BADGE_CX = 16        # absolute x in the left margin
_SUMMARY_ROW_HEIGHT = 22      # approximate vertical span of one row block


def _draw_badge(c: canvas.Canvas, cx: float, cy: float, number: int,
                radius: float = _BADGE_RADIUS,
                font_size: float = _BADGE_FONT_SIZE) -> None:
    """Draw a filled black circle with a centered white digit."""
    c.setFillColorRGB(0, 0, 0)
    c.setStrokeColorRGB(0, 0, 0)
    c.circle(cx, cy, radius, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", font_size)
    text = str(number)
    text_width = c.stringWidth(text, "Helvetica-Bold", font_size)
    c.drawString(cx - text_width / 2, cy - font_size / 3, text)


def _badge_center_for_label(label: LabelInfo, page_width: float, page_height: float) -> tuple[float, float]:
    """Return (cx, cy) in reportlab coords (origin bottom-left) for the badge."""
    if label.column == "left":
        # Left half of an A4 2-col page — anchor to the column's right edge
        col_right = page_width / 2
        cx = col_right - _BADGE_RADIUS - _BADGE_MARGIN
    elif label.column == "right":
        cx = page_width - _BADGE_RADIUS - _BADGE_MARGIN
    else:
        # Full-width / single column page (A6 new format or 1-col label)
        cx = page_width - _BADGE_RADIUS - _BADGE_MARGIN
    cy = page_height - _BADGE_RADIUS - _BADGE_MARGIN
    return cx, cy


def add_barcodes_to_pdf(pdf_path: str, labels: list[LabelInfo]) -> bytes:
    """Add Code 128 barcodes, sequential number badges, and summary-page
    cross-reference badges to a Mercado Libre shipping label PDF.

    Uses pdfrw to embed each original page as a Form XObject, then draws on
    top using reportlab to keep original content intact.

    Args:
        pdf_path: Path to the original PDF.
        labels: List of LabelInfo from parse_pdf().

    Returns:
        Modified PDF as bytes.
    """
    reader = PdfrwReader(pdf_path)

    labels_by_page: dict[int, list[LabelInfo]] = {}
    for label in labels:
        labels_by_page.setdefault(label.page_number, []).append(label)

    # Build pack_id -> label_index map for summary-page numbering
    pack_id_to_index = {label.pack_id: label.label_index for label in labels}
    summary_rows = parse_summary_rows(pdf_path)
    summary_by_page: dict[int, list] = {}
    for row in summary_rows:
        idx = pack_id_to_index.get(row.pack_id)
        if idx:
            summary_by_page.setdefault(row.page_number, []).append((row, idx))

    output = io.BytesIO()

    first_mb = reader.pages[0].MediaBox
    default_w = float(first_mb[2]) - float(first_mb[0])
    default_h = float(first_mb[3]) - float(first_mb[1])

    c = canvas.Canvas(output, pagesize=(default_w, default_h))

    for page_idx, page in enumerate(reader.pages):
        mb = page.MediaBox
        pw = float(mb[2]) - float(mb[0])
        ph = float(mb[3]) - float(mb[1])
        c.setPageSize((pw, ph))

        xobj = pagexobj(page)
        rl_obj = makerl(c, xobj)
        c.saveState()
        c.doForm(rl_obj)
        c.restoreState()

        # --- Label pages: barcode + number badge ---
        for label in labels_by_page.get(page_idx, []):
            x = label.barcode_x
            # pdfplumber y (origin top) → reportlab y (origin bottom), lifted by
            # _BARCODE_UP_SHIFT to keep it on the (taller) 2026 ML label format.
            y = ph - label.barcode_y - _BARCODE_BLOCK_HEIGHT + _BARCODE_UP_SHIFT

            barcode = Code128(
                label.pack_id,
                barWidth=_BAR_WIDTH,
                barHeight=_BAR_HEIGHT,
                humanReadable=True,
                fontSize=_FONT_SIZE,
            )

            # Minimal white backing hugging the barcode footprint so it covers as
            # little of the address behind it as possible (see _BG_* notes above).
            c.setFillColorRGB(1, 1, 1)
            c.rect(
                x - _BG_PAD,
                y - _BG_DIGITS_DESCENT - _BG_PAD,
                barcode.width + 2 * _BG_PAD,
                _BAR_HEIGHT + _BG_DIGITS_DESCENT + 2 * _BG_PAD,
                fill=True,
                stroke=False,
            )

            c.setFillColorRGB(0, 0, 0)
            c.setStrokeColorRGB(0, 0, 0)
            barcode.drawOn(c, x, y)

            cx, cy = _badge_center_for_label(label, pw, ph)
            _draw_badge(c, cx, cy, label.label_index)

        # --- Summary pages: numbered badges next to each row ---
        # Anchor in the left margin (well clear of all row text) and center
        # vertically over the row block, which spans ~22pt below the Pack ID.
        for row, idx in summary_by_page.get(page_idx, []):
            cx = _SUMMARY_BADGE_CX
            cy = ph - row.y - _SUMMARY_ROW_HEIGHT / 2
            _draw_badge(c, cx, cy, idx,
                        radius=_SUMMARY_BADGE_RADIUS,
                        font_size=_SUMMARY_BADGE_FONT_SIZE)

        c.showPage()

    c.save()
    return output.getvalue()
