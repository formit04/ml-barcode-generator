import io
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
from app.barcode_gen import generate_barcode_image
from app.pdf_parser import LabelInfo


def add_barcodes_to_pdf(pdf_path: str, labels: list[LabelInfo]) -> bytes:
    """Add Code 128 barcodes to a Mercado Libre shipping label PDF.

    Args:
        pdf_path: Path to the original PDF.
        labels: List of LabelInfo from parse_pdf().

    Returns:
        Modified PDF as bytes.
    """
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Group labels by page number
    labels_by_page: dict[int, list[LabelInfo]] = {}
    for label in labels:
        labels_by_page.setdefault(label.page_number, []).append(label)

    for page_idx, page in enumerate(reader.pages):
        page_labels = labels_by_page.get(page_idx, [])

        if not page_labels:
            writer.add_page(page)
            continue

        media_box = page.mediabox
        page_width = float(media_box.width)
        page_height = float(media_box.height)

        # Create overlay with barcodes
        overlay_buffer = io.BytesIO()
        c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))

        for label in page_labels:
            barcode_png = generate_barcode_image(label.pack_id)
            barcode_img = ImageReader(io.BytesIO(barcode_png))

            bc_width = 170
            bc_height = 28

            # Convert from pdfplumber coords (y=0 at top) to reportlab (y=0 at bottom)
            x = label.barcode_x
            y = page_height - label.barcode_y - bc_height

            c.drawImage(barcode_img, x, y, width=bc_width, height=bc_height)

        c.save()
        overlay_buffer.seek(0)

        overlay_reader = PdfReader(overlay_buffer)
        overlay_page = overlay_reader.pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
