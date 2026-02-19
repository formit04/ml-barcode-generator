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
    assert len(result) > os.path.getsize(pdf_path)


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
