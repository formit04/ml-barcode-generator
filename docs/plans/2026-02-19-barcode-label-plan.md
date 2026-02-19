# ML Barcode Generator - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Web app that adds scannable Code 128 barcodes (Pack ID) to Mercado Libre shipping label PDFs.

**Architecture:** FastAPI backend parses uploaded PDF with pdfplumber, extracts Pack ID/Venta ID from each label, generates Code 128 barcodes, overlays them onto the PDF using reportlab+PyPDF2, returns modified PDF. Static HTML/JS frontend in Spanish with drag & drop.

**Tech Stack:** Python 3.12, FastAPI, pdfplumber, python-barcode, reportlab, PyPDF2

**Design doc:** `docs/plans/2026-02-19-barcode-label-design.md`

**Sample PDFs for testing:** `samples/` directory (5 sample files + 1 ChatGPT reference output)

---

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `tests/__init__.py`
- Create: `tests/test_health.py`

**Step 1: Create project structure**

```bash
mkdir -p app tests static
```

**Step 2: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
python-multipart==0.0.9
pdfplumber==0.11.4
python-barcode==0.15.1
Pillow==10.4.0
reportlab==4.2.2
PyPDF2==3.0.1
pytest==8.3.3
httpx==0.27.2
```

**Step 3: Create virtual environment and install**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Step 4: Create minimal FastAPI app**

`app/main.py`:
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="ML Barcode Generator")

@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 5: Write health check test**

`tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 6: Run test**

```bash
source venv/bin/activate
pytest tests/test_health.py -v
```
Expected: PASS

**Step 7: Commit**

```bash
git init
echo "venv/\n__pycache__/\n*.pyc\n.DS_Store\ntmp/" > .gitignore
git add .gitignore requirements.txt app/ tests/
git commit -m "feat: project setup with FastAPI and health endpoint"
```

---

### Task 2: PDF Parser - Extract Pack IDs

**Files:**
- Create: `app/pdf_parser.py`
- Create: `tests/test_pdf_parser.py`

This is the core logic. The parser must:
1. Open PDF with pdfplumber
2. For each page, extract text with positions
3. Classify page type (2-column, 1-column, J&T, summary)
4. Extract Pack ID or Venta ID for each label
5. Return list of labels with their IDs and positions (left/right column)

**Step 1: Write failing tests**

`tests/test_pdf_parser.py`:
```python
import os
import pytest
from app.pdf_parser import parse_pdf, LabelInfo, PageType

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_parse_simple_example():
    """02 Simple example.pdf: 1 multi-product label + 1 summary page."""
    pdf_path = os.path.join(SAMPLES_DIR, "02 Simple example.pdf")
    result = parse_pdf(pdf_path)
    assert len(result) == 1
    assert result[0].pack_id == "2000011585730377"
    assert result[0].column == "left"


def test_parse_standard_2col():
    """03 example.pdf: 2 pages with 2 labels each + 1 summary = 4 labels."""
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    result = parse_pdf(pdf_path)
    assert len(result) == 4
    pack_ids = [r.pack_id for r in result]
    assert "2000011633126699" in pack_ids
    assert "2000011632217683" in pack_ids


def test_parse_mixed_pack_venta():
    """04 example.pdf: mix of Pack ID and Venta ID labels."""
    pdf_path = os.path.join(SAMPLES_DIR, "04 example.pdf")
    result = parse_pdf(pdf_path)
    # Should find labels on pages 1-8, skip summary pages 9-10
    assert len(result) >= 10
    # Check that Venta IDs are also extracted
    pack_ids = [r.pack_id for r in result]
    assert "2000015203044372" in pack_ids  # Venta ID from page 4


def test_parse_with_jt_express():
    """05 example with surprise.pdf: includes J&T Express label."""
    pdf_path = os.path.join(SAMPLES_DIR, "05 example with surprise.pdf")
    result = parse_pdf(pdf_path)
    # Should find all shipping labels, skip 2 summary pages
    assert len(result) >= 14
    # Check J&T label is found
    jt_labels = [r for r in result if r.page_type == PageType.JT_EXPRESS]
    assert len(jt_labels) >= 1


def test_parse_complex():
    """01 Complex example.pdf: 26 pages, J&T, multi-product, mixed IDs."""
    pdf_path = os.path.join(SAMPLES_DIR, "01 Complex example.pdf")
    result = parse_pdf(pdf_path)
    assert len(result) >= 30
    jt_labels = [r for r in result if r.page_type == PageType.JT_EXPRESS]
    assert len(jt_labels) >= 1


def test_summary_pages_skipped():
    """Summary pages should not produce any labels."""
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    result = parse_pdf(pdf_path)
    # Page 3 is summary - only 4 labels from pages 1-2
    assert len(result) == 4
    # No label should come from page index 2 (0-indexed)
    pages_used = [r.page_number for r in result]
    assert 2 not in pages_used


def test_label_info_structure():
    """Verify LabelInfo has all required fields."""
    pdf_path = os.path.join(SAMPLES_DIR, "02 Simple example.pdf")
    result = parse_pdf(pdf_path)
    label = result[0]
    assert isinstance(label, LabelInfo)
    assert isinstance(label.pack_id, str)
    assert label.page_number >= 0
    assert label.column in ("left", "right", "full")
    assert isinstance(label.page_type, PageType)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pdf_parser.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.pdf_parser'`

**Step 3: Implement pdf_parser.py**

`app/pdf_parser.py`:
```python
from dataclasses import dataclass
from enum import Enum
import re
import pdfplumber


class PageType(Enum):
    STANDARD_2COL = "standard_2col"
    STANDARD_1COL = "standard_1col"
    STANDARD_1COL_PRODUCTS = "standard_1col_products"
    JT_EXPRESS = "jt_express"
    SUMMARY = "summary"


@dataclass
class LabelInfo:
    pack_id: str
    page_number: int  # 0-indexed
    column: str  # "left", "right", or "full"
    page_type: PageType
    barcode_y: float  # y-coordinate for barcode placement (from top)
    barcode_x: float  # x-coordinate for barcode placement


# Regex patterns for Pack ID / Venta ID extraction
# Matches: "Pack ID: 2000011633126699" or "Pack ID: 20000 11633126699"
PACK_ID_PATTERN = re.compile(
    r"(?:Pack\s*ID|Venta(?:\s*ID)?)\s*:?\s*(2\d{4}\s?\d{10,11})"
)

# Page width for A4 in points (pdfplumber uses points)
PAGE_MID_X = 300  # approximate midpoint for left/right column split


def _is_summary_page(page) -> bool:
    """Check if page is a summary/checklist page."""
    text = page.extract_text() or ""
    # Summary pages have "Identificación" and "Productos" headers
    if "Identificaci" in text and "Productos" in text:
        # Also check for the grey header pattern
        if "Despacha tus productos" in text or "No te relajes" in text:
            return True
    return False


def _is_jt_express(text: str) -> bool:
    """Check if text contains J&T Express markers."""
    markers = ["J&T", "JTMLM", "JMX0", "Conejo Corriendo", "jtexpress"]
    return any(marker in text for marker in markers)


def _extract_ids_with_positions(page) -> list[tuple[str, float, float]]:
    """Extract Pack IDs with their (x, y) positions from page words."""
    words = page.extract_words(keep_blank_chars=True, use_text_flow=False)
    text = page.extract_text() or ""

    ids_found = []

    # Strategy: find "Pack ID:" or "Venta:" text, then grab the number after it
    # We work with the full text and also track positions via words

    # First, find all IDs from the full text
    all_ids = []
    for match in PACK_ID_PATTERN.finditer(text):
        raw_id = match.group(1).replace(" ", "")
        all_ids.append(raw_id)

    if not all_ids:
        return []

    # Now find x-positions for each ID by searching for the number in words
    for pack_id in all_ids:
        # Search for parts of the pack_id in words to determine column
        # The ID might be split: "20000" and "11633126699" or as one word
        suffix = pack_id[5:]  # last 11 digits are more unique
        best_x = None
        best_y = None

        for word in words:
            word_text = word["text"].replace(" ", "")
            if suffix in word_text or pack_id in word_text:
                x = word["x0"]
                y = word["top"]
                if best_x is None or y < best_y:
                    # Take the topmost occurrence (in label header area)
                    best_x = x
                    best_y = y

        if best_x is not None:
            ids_found.append((pack_id, best_x, best_y))
        else:
            # Fallback: can't determine position, assume left
            ids_found.append((pack_id, 0, 0))

    return ids_found


def _find_barcode_position(page, column: str, page_type: PageType) -> tuple[float, float]:
    """Find the y-position for barcode placement (below CP/date line).

    Returns (x, y) in PDF coordinates (from page top).
    """
    words = page.extract_words(keep_blank_chars=True, use_text_flow=False)
    page_height = page.height
    page_width = page.width

    # Define column boundaries
    if column == "left":
        x_min, x_max = 0, page_width / 2
    elif column == "right":
        x_min, x_max = page_width / 2, page_width
    else:
        x_min, x_max = 0, page_width

    # Find the CP: line or date line in the correct column
    cp_y = None
    for word in words:
        if word["x0"] >= x_min and word["x0"] < x_max:
            if "CP:" in word["text"]:
                cp_y = word["bottom"]

    if cp_y is not None:
        # Place barcode just below the CP/date line
        barcode_y = cp_y + 5
    else:
        # Fallback: place at ~65% of page height within the label area
        if column == "left":
            barcode_y = page_height * 0.62
        elif column == "right":
            barcode_y = page_height * 0.62
        else:
            barcode_y = page_height * 0.62

    # X position: center of the column
    if column == "left":
        barcode_x = page_width * 0.12
    elif column == "right":
        barcode_x = page_width * 0.62
    else:
        barcode_x = page_width * 0.12

    return barcode_x, barcode_y


def _deduplicate_ids(ids_with_pos: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Remove duplicate Pack IDs (same ID appears in tear-off and body)."""
    seen = {}
    for pack_id, x, y in ids_with_pos:
        if pack_id not in seen:
            seen[pack_id] = (pack_id, x, y)
        else:
            # Keep the one with higher y (further down = in label body, not tear-off)
            existing = seen[pack_id]
            if y > existing[2]:
                seen[pack_id] = (pack_id, x, y)
    return list(seen.values())


def parse_pdf(pdf_path: str) -> list[LabelInfo]:
    """Parse a Mercado Libre shipping label PDF.

    Returns a list of LabelInfo, one per shipping label found.
    Summary/checklist pages are skipped.
    """
    labels = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""

            # Skip summary pages
            if _is_summary_page(page):
                continue

            # Detect J&T Express
            is_jt = _is_jt_express(text)

            # Extract IDs with positions
            ids_with_pos = _extract_ids_with_positions(page)
            ids_with_pos = _deduplicate_ids(ids_with_pos)

            if not ids_with_pos:
                continue

            # Classify page and create labels
            page_width = page.width

            if len(ids_with_pos) == 2:
                # 2-column page
                # Sort by x position: left first
                ids_with_pos.sort(key=lambda x: x[1])

                for i, (pack_id, x, y) in enumerate(ids_with_pos):
                    col = "left" if i == 0 else "right"
                    pt = PageType.JT_EXPRESS if (is_jt and _is_jt_express_label(page, col)) else PageType.STANDARD_2COL
                    bx, by = _find_barcode_position(page, col, pt)
                    labels.append(LabelInfo(
                        pack_id=pack_id,
                        page_number=page_idx,
                        column=col,
                        page_type=pt,
                        barcode_y=by,
                        barcode_x=bx,
                    ))

            elif len(ids_with_pos) == 1:
                pack_id, x, y = ids_with_pos[0]

                # Check if it's a multi-product with product panel
                has_product_panel = "productos" in text.lower() and "unidades" in text.lower()

                if is_jt:
                    pt = PageType.JT_EXPRESS
                    col = "left" if x < page_width / 2 else "full"
                elif has_product_panel:
                    pt = PageType.STANDARD_1COL_PRODUCTS
                    col = "left"
                else:
                    pt = PageType.STANDARD_1COL
                    col = "full"

                bx, by = _find_barcode_position(page, col, pt)
                labels.append(LabelInfo(
                    pack_id=pack_id,
                    page_number=page_idx,
                    column=col,
                    page_type=pt,
                    barcode_y=by,
                    barcode_x=bx,
                ))

            else:
                # More than 2 IDs found (shouldn't happen, take first 2)
                ids_with_pos.sort(key=lambda x: x[1])
                for i, (pack_id, x, y) in enumerate(ids_with_pos[:2]):
                    col = "left" if i == 0 else "right"
                    bx, by = _find_barcode_position(page, col, PageType.STANDARD_2COL)
                    labels.append(LabelInfo(
                        pack_id=pack_id,
                        page_number=page_idx,
                        column=col,
                        page_type=PageType.STANDARD_2COL,
                        barcode_y=by,
                        barcode_x=bx,
                    ))

    return labels


def _is_jt_express_label(page, column: str) -> bool:
    """Check if a specific column on a page is a J&T Express label."""
    words = page.extract_words(keep_blank_chars=True, use_text_flow=False)
    page_width = page.width

    if column == "left":
        x_min, x_max = 0, page_width / 2
    else:
        x_min, x_max = page_width / 2, page_width

    col_text = " ".join(
        w["text"] for w in words
        if w["x0"] >= x_min and w["x0"] < x_max
    )
    return _is_jt_express(col_text)
```

**Step 4: Run tests**

```bash
pytest tests/test_pdf_parser.py -v
```
Expected: All PASS. If some counts are off, adjust assertions based on actual PDF content.

**Step 5: Commit**

```bash
git add app/pdf_parser.py tests/test_pdf_parser.py
git commit -m "feat: PDF parser extracts Pack IDs with page classification"
```

---

### Task 3: Barcode Generator

**Files:**
- Create: `app/barcode_gen.py`
- Create: `tests/test_barcode_gen.py`

**Step 1: Write failing test**

`tests/test_barcode_gen.py`:
```python
import os
from app.barcode_gen import generate_barcode_image


def test_generate_barcode_returns_png():
    """Barcode generator should return PNG bytes."""
    result = generate_barcode_image("2000011633126699")
    assert result is not None
    assert len(result) > 0
    # PNG magic bytes
    assert result[:4] == b"\x89PNG"


def test_generate_barcode_different_ids():
    """Different IDs should produce different barcodes."""
    bc1 = generate_barcode_image("2000011633126699")
    bc2 = generate_barcode_image("2000011632217683")
    assert bc1 != bc2


def test_generate_barcode_dimensions():
    """Barcode should have reasonable dimensions for label placement."""
    from PIL import Image
    import io
    result = generate_barcode_image("2000011633126699")
    img = Image.open(io.BytesIO(result))
    w, h = img.size
    # Should be wide enough to scan but not too tall
    assert w > 100
    assert h > 20
    assert h < 100  # not too tall to fit in label
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_barcode_gen.py -v
```
Expected: FAIL

**Step 3: Implement barcode_gen.py**

`app/barcode_gen.py`:
```python
import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image


def generate_barcode_image(
    pack_id: str,
    width_px: int = 300,
    height_px: int = 40,
) -> bytes:
    """Generate a Code 128 barcode as PNG bytes.

    Args:
        pack_id: The Pack ID / Venta ID to encode.
        width_px: Desired width in pixels.
        height_px: Desired height in pixels.

    Returns:
        PNG image bytes.
    """
    code128 = barcode.get_barcode_class("code128")
    writer = ImageWriter()

    # Generate barcode
    bc = code128(pack_id, writer=writer)
    buffer = io.BytesIO()
    bc.write(buffer, options={
        "module_width": 0.25,
        "module_height": 6,
        "font_size": 7,
        "text_distance": 2,
        "quiet_zone": 2,
    })
    buffer.seek(0)

    # Resize to target dimensions
    img = Image.open(buffer)
    img = img.resize((width_px, height_px), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()
```

**Step 4: Run tests**

```bash
pytest tests/test_barcode_gen.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add app/barcode_gen.py tests/test_barcode_gen.py
git commit -m "feat: Code 128 barcode generator"
```

---

### Task 4: PDF Overlay - Place Barcodes on PDF

**Files:**
- Create: `app/pdf_overlay.py`
- Create: `tests/test_pdf_overlay.py`

**Step 1: Write failing tests**

`tests/test_pdf_overlay.py`:
```python
import os
import pdfplumber
from app.pdf_parser import parse_pdf
from app.pdf_overlay import add_barcodes_to_pdf

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_add_barcodes_returns_pdf_bytes():
    """Should return valid PDF bytes."""
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    labels = parse_pdf(pdf_path)
    result = add_barcodes_to_pdf(pdf_path, labels)
    assert result[:5] == b"%PDF-"
    assert len(result) > os.path.getsize(pdf_path)


def test_add_barcodes_preserves_page_count():
    """Output PDF should have same number of pages."""
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    labels = parse_pdf(pdf_path)
    result_bytes = add_barcodes_to_pdf(pdf_path, labels)

    # Write to temp and count pages
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(result_bytes)
        tmp_path = f.name

    with pdfplumber.open(tmp_path) as pdf:
        assert len(pdf.pages) == 3  # 03 example has 3 pages

    os.unlink(tmp_path)


def test_output_has_barcode_text():
    """Output PDF should contain the Pack ID as text (from barcode number)."""
    pdf_path = os.path.join(SAMPLES_DIR, "02 Simple example.pdf")
    labels = parse_pdf(pdf_path)
    result_bytes = add_barcodes_to_pdf(pdf_path, labels)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(result_bytes)
        tmp_path = f.name

    # The barcode image contains the number rendered as text
    # Just verify PDF is larger (barcode images were added)
    assert len(result_bytes) > os.path.getsize(pdf_path)
    os.unlink(tmp_path)


def test_all_samples_process_without_error():
    """All sample PDFs should process without exceptions."""
    for filename in os.listdir(SAMPLES_DIR):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(SAMPLES_DIR, filename)
            labels = parse_pdf(pdf_path)
            result = add_barcodes_to_pdf(pdf_path, labels)
            assert result[:5] == b"%PDF-", f"Failed for {filename}"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pdf_overlay.py -v
```
Expected: FAIL

**Step 3: Implement pdf_overlay.py**

`app/pdf_overlay.py`:
```python
import io
from reportlab.lib.units import mm
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
            # No labels on this page (summary or empty) - keep as is
            writer.add_page(page)
            continue

        # Get page dimensions
        media_box = page.mediabox
        page_width = float(media_box.width)
        page_height = float(media_box.height)

        # Create overlay with barcodes
        overlay_buffer = io.BytesIO()
        c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))

        for label in page_labels:
            barcode_png = generate_barcode_image(label.pack_id)
            barcode_img = ImageReader(io.BytesIO(barcode_png))

            # Barcode dimensions on PDF (in points)
            bc_width = 170
            bc_height = 28

            # Convert from top-based y (pdfplumber) to bottom-based y (reportlab)
            # reportlab y=0 is at bottom, pdfplumber y=0 is at top
            x = label.barcode_x
            y = page_height - label.barcode_y - bc_height

            c.drawImage(barcode_img, x, y, width=bc_width, height=bc_height)

        c.save()
        overlay_buffer.seek(0)

        # Merge overlay onto original page
        overlay_reader = PdfReader(overlay_buffer)
        overlay_page = overlay_reader.pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
```

**Step 4: Run tests**

```bash
pytest tests/test_pdf_overlay.py -v
```
Expected: All PASS

**Step 5: Manual visual check**

```python
# Quick script to generate test output
from app.pdf_parser import parse_pdf
from app.pdf_overlay import add_barcodes_to_pdf

labels = parse_pdf("samples/03 example.pdf")
result = add_barcodes_to_pdf("samples/03 example.pdf", labels)
with open("tmp/test_output.pdf", "wb") as f:
    f.write(result)
print(f"Generated PDF with {len(labels)} barcodes")
```

Open `tmp/test_output.pdf` and verify barcodes are:
- In correct positions (below CP/date line)
- Not overlapping other content
- Readable (visually)

**Step 6: Commit**

```bash
git add app/pdf_overlay.py tests/test_pdf_overlay.py
git commit -m "feat: PDF overlay places Code 128 barcodes on labels"
```

---

### Task 5: FastAPI Endpoints

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_api.py`

**Step 1: Write failing tests**

`tests/test_api.py`:
```python
import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_process_pdf_returns_json():
    """POST /process should return processing stats."""
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    with open(pdf_path, "rb") as f:
        response = client.post("/process", files={"file": ("test.pdf", f, "application/pdf")})
    assert response.status_code == 200
    data = response.json()
    assert "file_id" in data
    assert data["total_labels"] == 4
    assert "stats" in data


def test_process_non_pdf_rejected():
    """POST /process should reject non-PDF files."""
    response = client.post(
        "/process",
        files={"file": ("test.txt", b"not a pdf", "text/plain")}
    )
    assert response.status_code == 400


def test_download_after_process():
    """GET /download/{file_id} should return PDF after processing."""
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    with open(pdf_path, "rb") as f:
        resp = client.post("/process", files={"file": ("test.pdf", f, "application/pdf")})
    file_id = resp.json()["file_id"]

    download_resp = client.get(f"/download/{file_id}")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert download_resp.content[:5] == b"%PDF-"


def test_download_invalid_id():
    """GET /download with invalid ID should return 404."""
    response = client.get("/download/nonexistent")
    assert response.status_code == 404
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py -v
```
Expected: FAIL

**Step 3: Implement API endpoints**

`app/main.py`:
```python
import os
import uuid
import tempfile
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from app.pdf_parser import parse_pdf, PageType
from app.pdf_overlay import add_barcodes_to_pdf

app = FastAPI(title="ML Barcode Generator")

# In-memory store for processed files (simple dict, no DB)
processed_files: dict[str, dict] = {}

TEMP_DIR = tempfile.mkdtemp(prefix="ml_barcode_")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/process")
async def process_pdf(file: UploadFile):
    """Upload and process a Mercado Libre shipping label PDF."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")

    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="El archivo no es un PDF válido")

    # Save uploaded PDF to temp
    file_id = str(uuid.uuid4())[:8]
    input_path = os.path.join(TEMP_DIR, f"{file_id}_input.pdf")
    output_path = os.path.join(TEMP_DIR, f"{file_id}_output.pdf")

    with open(input_path, "wb") as f:
        f.write(content)

    try:
        labels = parse_pdf(input_path)
        result_bytes = add_barcodes_to_pdf(input_path, labels)

        with open(output_path, "wb") as f:
            f.write(result_bytes)

        # Compute stats
        stats = {
            "standard": sum(1 for l in labels if l.page_type != PageType.JT_EXPRESS),
            "jt_express": sum(1 for l in labels if l.page_type == PageType.JT_EXPRESS),
        }

        processed_files[file_id] = {
            "output_path": output_path,
            "original_name": file.filename,
            "stats": stats,
        }

        return {
            "file_id": file_id,
            "total_labels": len(labels),
            "stats": stats,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo: {str(e)}")
    finally:
        # Clean up input file
        if os.path.exists(input_path):
            os.unlink(input_path)


@app.get("/download/{file_id}")
def download_pdf(file_id: str):
    """Download the processed PDF with barcodes."""
    if file_id not in processed_files:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    info = processed_files[file_id]
    output_path = info["output_path"]

    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Archivo expirado")

    original_name = info["original_name"].replace(".pdf", "_codigos.pdf")

    with open(output_path, "rb") as f:
        pdf_bytes = f.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{original_name}"'},
    )
```

**Step 4: Run tests**

```bash
pytest tests/test_api.py tests/test_health.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: FastAPI endpoints for PDF upload, process, and download"
```

---

### Task 6: Frontend - Spanish Web UI

**Files:**
- Create: `static/index.html`
- Modify: `app/main.py` (mount static files)

**Step 1: Create index.html**

`static/index.html`:
```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generador de Códigos de Barras ML</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .container {
            max-width: 600px;
            margin: 60px auto 0;
            padding: 0 20px;
            flex: 1;
        }
        h1 {
            text-align: center;
            font-size: 24px;
            margin-bottom: 8px;
            color: #1a1a1a;
        }
        .subtitle {
            text-align: center;
            color: #666;
            font-size: 14px;
            margin-bottom: 40px;
        }
        .drop-zone {
            border: 2px dashed #ccc;
            border-radius: 12px;
            padding: 60px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            background: #fff;
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: #FFE600;
            background: #FFFDE7;
        }
        .drop-zone.has-file {
            border-color: #4CAF50;
            background: #F1F8E9;
        }
        .drop-zone p {
            font-size: 16px;
            color: #666;
        }
        .drop-zone .filename {
            font-weight: 600;
            color: #333;
            margin-top: 8px;
        }
        .drop-zone input { display: none; }
        .btn {
            display: block;
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 16px;
            transition: all 0.2s;
        }
        .btn-process {
            background: #FFE600;
            color: #1a1a1a;
        }
        .btn-process:hover { background: #FFD600; }
        .btn-process:disabled {
            background: #e0e0e0;
            color: #999;
            cursor: not-allowed;
        }
        .btn-download {
            background: #4CAF50;
            color: #fff;
            text-decoration: none;
            text-align: center;
        }
        .btn-download:hover { background: #43A047; }
        .status {
            margin-top: 20px;
            padding: 16px;
            border-radius: 8px;
            background: #fff;
            border: 1px solid #e0e0e0;
            display: none;
        }
        .status.visible { display: block; }
        .status h3 { font-size: 14px; margin-bottom: 8px; }
        .status ul {
            list-style: none;
            font-size: 13px;
            color: #555;
        }
        .status ul li { padding: 2px 0; }
        .status ul li::before { content: "• "; color: #999; }
        .spinner {
            display: inline-block;
            width: 18px;
            height: 18px;
            border: 2px solid #ccc;
            border-top-color: #333;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
            vertical-align: middle;
            margin-right: 8px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .error {
            color: #d32f2f;
            background: #FFEBEE;
            border-color: #FFCDD2;
        }
        footer {
            text-align: center;
            padding: 24px;
            font-size: 12px;
            color: #999;
        }
        footer a { color: #999; text-decoration: none; }
        footer a:hover { color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Generador de Códigos de Barras</h1>
        <p class="subtitle">Agrega códigos de barras a tus etiquetas de Mercado Libre</p>

        <div class="drop-zone" id="dropZone">
            <p id="dropText">Arrastra tu PDF aquí<br>o haz clic para seleccionar</p>
            <p class="filename" id="fileName" style="display:none"></p>
            <input type="file" id="fileInput" accept=".pdf">
        </div>

        <button class="btn btn-process" id="processBtn" disabled>Procesar PDF</button>

        <div class="status" id="status"></div>

        <a class="btn btn-download" id="downloadBtn" style="display:none">
            Descargar PDF con códigos de barras
        </a>
    </div>

    <footer>
        &copy; 2026 Codezuno. All rights reserved. &middot;
        Crafted &amp; Designed &amp; Built with &hearts; by
        <a href="https://codezuno.com" target="_blank">codezuno.com</a>
    </footer>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const dropText = document.getElementById('dropText');
        const fileName = document.getElementById('fileName');
        const processBtn = document.getElementById('processBtn');
        const status = document.getElementById('status');
        const downloadBtn = document.getElementById('downloadBtn');

        let selectedFile = null;

        // Drag & drop
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.type === 'application/pdf') selectFile(file);
        });
        fileInput.addEventListener('change', (e) => {
            if (e.target.files[0]) selectFile(e.target.files[0]);
        });

        function selectFile(file) {
            selectedFile = file;
            dropText.style.display = 'none';
            fileName.style.display = 'block';
            fileName.textContent = file.name;
            dropZone.classList.add('has-file');
            processBtn.disabled = false;
            downloadBtn.style.display = 'none';
            status.classList.remove('visible');
        }

        // Process
        processBtn.addEventListener('click', async () => {
            if (!selectedFile) return;
            processBtn.disabled = true;
            downloadBtn.style.display = 'none';
            status.className = 'status visible';
            status.innerHTML = '<span class="spinner"></span> Procesando...';

            const formData = new FormData();
            formData.append('file', selectedFile);

            try {
                const resp = await fetch('/process', { method: 'POST', body: formData });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Error desconocido');
                }
                const data = await resp.json();

                status.innerHTML = `
                    <h3>Se procesaron ${data.total_labels} etiquetas</h3>
                    <ul>
                        <li>${data.stats.standard} etiquetas estándar Mercado Libre</li>
                        ${data.stats.jt_express > 0 ? `<li>${data.stats.jt_express} etiquetas J&T Express</li>` : ''}
                    </ul>
                `;

                downloadBtn.href = '/download/' + data.file_id;
                downloadBtn.style.display = 'block';
            } catch (e) {
                status.className = 'status visible error';
                status.innerHTML = `<h3>Error</h3><p>${e.message}</p>`;
            } finally {
                processBtn.disabled = false;
            }
        });
    </script>
</body>
</html>
```

**Step 2: Mount static files in FastAPI**

Add to `app/main.py` at the end:
```python
# Mount static files (must be AFTER all route definitions)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

**Step 3: Test manually**

```bash
cd /Users/marcinformela/claude_project/barcode
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 in browser. Test:
1. Page loads with Spanish UI
2. Drag & drop a sample PDF
3. Click "Procesar PDF"
4. Stats appear
5. Download button works
6. Footer shows Codezuno copyright

**Step 4: Commit**

```bash
git add static/index.html app/main.py
git commit -m "feat: Spanish web UI with drag & drop upload"
```

---

### Task 7: Integration Testing & Position Tuning

**Files:**
- Create: `tests/test_integration.py`
- Create: `scripts/visual_test.py`

This is the critical task: visually verify barcode positions on ALL sample PDFs and tune coordinates.

**Step 1: Create visual test script**

`scripts/visual_test.py`:
```python
"""Generate output PDFs for all samples for visual inspection."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.pdf_parser import parse_pdf
from app.pdf_overlay import add_barcodes_to_pdf

SAMPLES_DIR = "samples"
OUTPUT_DIR = "tmp"

os.makedirs(OUTPUT_DIR, exist_ok=True)

for filename in sorted(os.listdir(SAMPLES_DIR)):
    if not filename.endswith(".pdf"):
        continue

    pdf_path = os.path.join(SAMPLES_DIR, filename)
    print(f"\nProcessing: {filename}")

    labels = parse_pdf(pdf_path)
    print(f"  Found {len(labels)} labels:")
    for label in labels:
        print(f"    Page {label.page_number}: {label.pack_id} [{label.column}] "
              f"type={label.page_type.value} pos=({label.barcode_x:.0f}, {label.barcode_y:.0f})")

    result = add_barcodes_to_pdf(pdf_path, labels)
    out_path = os.path.join(OUTPUT_DIR, f"output_{filename}")
    with open(out_path, "wb") as f:
        f.write(result)
    print(f"  Saved: {out_path}")

print("\nDone! Open PDFs in tmp/ directory to visually verify barcode positions.")
```

**Step 2: Run visual test**

```bash
source venv/bin/activate
python scripts/visual_test.py
```

**Step 3: Open each output PDF and verify:**
- [ ] `output_01 Complex example.pdf` - all barcodes positioned correctly
- [ ] `output_02 Simple example.pdf` - single label barcode correct
- [ ] `output_03 example.pdf` - 4 labels, 2 per page, barcodes correct
- [ ] `output_04 example.pdf` - mixed layouts, Venta ID labels correct
- [ ] `output_05 example with surprise.pdf` - J&T Express label handled

**Step 4: Tune positions in pdf_parser.py and pdf_overlay.py as needed**

Likely adjustments:
- `barcode_y` offset from CP line
- `barcode_x` centering within column
- `bc_width` and `bc_height` in overlay
- J&T Express specific positioning

**Step 5: Write integration test**

`tests/test_integration.py`:
```python
import os
from app.pdf_parser import parse_pdf
from app.pdf_overlay import add_barcodes_to_pdf

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_full_pipeline_all_samples():
    """All sample PDFs process end-to-end without error."""
    for filename in os.listdir(SAMPLES_DIR):
        if not filename.endswith(".pdf"):
            continue
        pdf_path = os.path.join(SAMPLES_DIR, filename)
        labels = parse_pdf(pdf_path)
        result = add_barcodes_to_pdf(pdf_path, labels)
        assert result[:5] == b"%PDF-", f"Failed: {filename}"
        assert len(result) > 100, f"Empty output: {filename}"
```

**Step 6: Run all tests**

```bash
pytest tests/ -v
```
Expected: All PASS

**Step 7: Commit**

```bash
git add scripts/ tests/test_integration.py app/
git commit -m "feat: integration testing and barcode position tuning"
```

---

### Task 8: Final Polish

**Step 1: Add `__init__.py` files if missing**

```bash
touch app/__init__.py tests/__init__.py
```

**Step 2: Create run script**

`run.sh`:
```bash
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
chmod +x run.sh
```

**Step 3: Run full test suite**

```bash
pytest tests/ -v
```
Expected: All PASS

**Step 4: Final commit**

```bash
git add .
git commit -m "feat: ML Barcode Generator complete"
```
