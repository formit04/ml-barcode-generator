import io
from pdfrw import PdfReader as PdfrwReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode.code128 import Code128
from app.pdf_parser import LabelInfo


def add_barcodes_to_pdf(pdf_path: str, labels: list[LabelInfo]) -> bytes:
    """Add Code 128 barcodes to a Mercado Libre shipping label PDF.

    Uses pdfrw to embed each original page as a Form XObject, then draws
    barcodes on top using reportlab. This avoids the merge_page approach
    which can make overlaid content invisible.

    Args:
        pdf_path: Path to the original PDF.
        labels: List of LabelInfo from parse_pdf().

    Returns:
        Modified PDF as bytes.
    """
    reader = PdfrwReader(pdf_path)

    # Group labels by page number
    labels_by_page: dict[int, list[LabelInfo]] = {}
    for label in labels:
        labels_by_page.setdefault(label.page_number, []).append(label)

    output = io.BytesIO()

    # Use first page dimensions as default; each page will use its own
    first_mb = reader.pages[0].MediaBox
    default_w = float(first_mb[2]) - float(first_mb[0])
    default_h = float(first_mb[3]) - float(first_mb[1])

    c = canvas.Canvas(output, pagesize=(default_w, default_h))

    for page_idx, page in enumerate(reader.pages):
        # Get this page's dimensions
        mb = page.MediaBox
        pw = float(mb[2]) - float(mb[0])
        ph = float(mb[3]) - float(mb[1])
        c.setPageSize((pw, ph))

        # Draw original page content as Form XObject
        xobj = pagexobj(page)
        rl_obj = makerl(c, xobj)
        c.saveState()
        c.doForm(rl_obj)
        c.restoreState()

        # Draw barcodes for this page
        page_labels = labels_by_page.get(page_idx, [])
        for label in page_labels:
            if label.compact:
                # Compact barcode for tight spaces (agency labels)
                bc_height = 28
                bar_width = 0.65
                bar_height = 18
                font_size = 6
                bg_width = 170
            else:
                # Standard barcode
                bc_height = 42
                bar_width = 0.8
                bar_height = 30
                font_size = 7
                bg_width = 204

            # Convert from pdfplumber coords (y=0 at top) to reportlab (y=0 at bottom)
            x = label.barcode_x
            y = ph - label.barcode_y - bc_height

            # White background behind barcode for clean scanning
            c.setFillColorRGB(1, 1, 1)
            c.rect(x - 2, y - 2, bg_width, bc_height + 4, fill=True, stroke=False)

            # Draw Code 128 barcode using reportlab's native vector renderer
            c.setFillColorRGB(0, 0, 0)
            c.setStrokeColorRGB(0, 0, 0)
            barcode = Code128(
                label.pack_id,
                barWidth=bar_width,
                barHeight=bar_height,
                humanReadable=True,
                fontSize=font_size,
            )
            barcode.drawOn(c, x, y)

        c.showPage()

    c.save()
    return output.getvalue()
