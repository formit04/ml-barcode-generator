import os
import tempfile
import pdfplumber
from app.pdf_parser import parse_pdf
from app.pdf_overlay import add_barcodes_to_pdf

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_add_barcodes_returns_pdf_bytes():
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    labels = parse_pdf(pdf_path)
    result = add_barcodes_to_pdf(pdf_path, labels)
    assert result[:5] == b"%PDF-"
    assert len(result) > 0


def test_add_barcodes_preserves_page_count():
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    labels = parse_pdf(pdf_path)
    result_bytes = add_barcodes_to_pdf(pdf_path, labels)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(result_bytes)
        tmp_path = f.name
    with pdfplumber.open(tmp_path) as pdf:
        assert len(pdf.pages) == 3
    os.unlink(tmp_path)


def test_all_samples_process_without_error():
    for filename in os.listdir(SAMPLES_DIR):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(SAMPLES_DIR, filename)
            labels = parse_pdf(pdf_path)
            result = add_barcodes_to_pdf(pdf_path, labels)
            assert result[:5] == b"%PDF-", f"Failed for {filename}"


def test_barcodes_add_text_to_output():
    """Verify barcode Pack IDs appear as text in the output PDF."""
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    labels = parse_pdf(pdf_path)
    result_bytes = add_barcodes_to_pdf(pdf_path, labels)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(result_bytes)
        tmp_path = f.name
    with pdfplumber.open(tmp_path) as pdf:
        all_text = ""
        for page in pdf.pages:
            all_text += page.extract_text() or ""
    os.unlink(tmp_path)
    # The barcode humanReadable text should appear in the output
    for label in labels:
        assert label.pack_id in all_text, f"Pack ID {label.pack_id} not found in output"
