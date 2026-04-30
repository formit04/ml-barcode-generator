"""Tests for the PDF parser module.

Each test exercises one of the five sample PDFs and verifies correct label
extraction, page classification, deduplication, and barcode positioning.
"""

from pathlib import Path

import pytest

from app.pdf_parser import LabelInfo, PageType, parse_pdf

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


# ---------------------------------------------------------------------------
# 02 Simple example.pdf
# ---------------------------------------------------------------------------

class TestSimpleExample:
    """02 Simple example.pdf: 1 multi-product label + 1 summary = 1 label."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        self.result = parse_pdf(SAMPLES_DIR / "02 Simple example.pdf")

    def test_label_count(self):
        assert len(self.result) == 1

    def test_pack_id(self):
        assert self.result[0].pack_id == "2000011585730377"

    def test_page_type(self):
        assert self.result[0].page_type == PageType.STANDARD_1COL_PRODUCTS

    def test_column(self):
        assert self.result[0].column == "left"

    def test_page_number(self):
        assert self.result[0].page_number == 0

    def test_barcode_y_reasonable(self):
        """Barcode y should sit just below the column's last text line."""
        assert 560 < self.result[0].barcode_y < 720

    def test_barcode_x(self):
        assert self.result[0].barcode_x < 100  # left-side x


# ---------------------------------------------------------------------------
# 03 example.pdf
# ---------------------------------------------------------------------------

class TestStandard2Col:
    """03 example.pdf: 2 pages with 2 labels each + 1 summary = 4 labels."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        self.result = parse_pdf(SAMPLES_DIR / "03 example.pdf")

    def test_label_count(self):
        assert len(self.result) == 4

    def test_all_standard_2col(self):
        for label in self.result:
            assert label.page_type == PageType.STANDARD_2COL

    def test_pack_ids_unique(self):
        ids = [r.pack_id for r in self.result]
        assert len(set(ids)) == 4

    def test_expected_pack_ids(self):
        ids = {r.pack_id for r in self.result}
        assert "2000011633126699" in ids
        assert "2000011632217683" in ids
        assert "2000011631462469" in ids
        assert "2000011630960093" in ids

    def test_columns(self):
        """Each page should have one left and one right label."""
        page0 = [r for r in self.result if r.page_number == 0]
        assert sorted(r.column for r in page0) == ["left", "right"]
        page1 = [r for r in self.result if r.page_number == 1]
        assert sorted(r.column for r in page1) == ["left", "right"]

    def test_barcode_positions(self):
        for label in self.result:
            assert 560 < label.barcode_y < 720

    def test_summary_page_skipped(self):
        """Page 2 is the summary page and should not appear."""
        pages = {r.page_number for r in self.result}
        assert 2 not in pages


# ---------------------------------------------------------------------------
# 04 example.pdf
# ---------------------------------------------------------------------------

class TestMixedPackVenta:
    """04 example.pdf: mix of Pack ID and Venta ID."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        self.result = parse_pdf(SAMPLES_DIR / "04 example.pdf")

    def test_label_count(self):
        assert len(self.result) == 13

    def test_has_venta_ids(self):
        """Some labels should have Venta IDs (starting with 200001...)."""
        venta_ids = [r for r in self.result if r.pack_id.startswith("200001")]
        assert len(venta_ids) >= 3

    def test_has_1col_products(self):
        prods = [r for r in self.result if r.page_type == PageType.STANDARD_1COL_PRODUCTS]
        assert len(prods) == 2  # pages 0 and 7

    def test_has_1col(self):
        single = [r for r in self.result if r.page_type == PageType.STANDARD_1COL]
        assert len(single) == 1  # page 3

    def test_has_2col(self):
        two_col = [r for r in self.result if r.page_type == PageType.STANDARD_2COL]
        assert len(two_col) == 10  # pages 1,2,4,5,6 with 2 each

    def test_summary_pages_skipped(self):
        pages = {r.page_number for r in self.result}
        assert 8 not in pages
        assert 9 not in pages

    def test_barcode_y_positions(self):
        for label in self.result:
            assert 560 < label.barcode_y < 720


# ---------------------------------------------------------------------------
# 05 example with surprise.pdf
# ---------------------------------------------------------------------------

class TestWithJTExpress:
    """05 example with surprise.pdf: includes J&T Express."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        self.result = parse_pdf(SAMPLES_DIR / "05 example with surprise.pdf")

    def test_label_count(self):
        assert len(self.result) == 14

    def test_jt_express_detected(self):
        jt = [r for r in self.result if r.page_type == PageType.JT_EXPRESS]
        assert len(jt) >= 1

    def test_jt_express_on_page_7(self):
        jt = [r for r in self.result if r.page_type == PageType.JT_EXPRESS]
        assert any(r.page_number == 7 for r in jt)

    def test_jt_express_venta_id(self):
        jt = [r for r in self.result if r.page_type == PageType.JT_EXPRESS]
        jt_ids = {r.pack_id for r in jt}
        assert "2000014854906006" in jt_ids

    def test_has_1col_products(self):
        prods = [r for r in self.result if r.page_type == PageType.STANDARD_1COL_PRODUCTS]
        assert len(prods) == 2  # pages 1 and 2

    def test_summary_pages_skipped(self):
        pages = {r.page_number for r in self.result}
        assert 8 not in pages
        assert 9 not in pages

    def test_barcode_y_for_jt(self):
        jt = [r for r in self.result if r.page_type == PageType.JT_EXPRESS]
        for label in jt:
            assert 540 < label.barcode_y < 720


# ---------------------------------------------------------------------------
# 01 Complex example.pdf
# ---------------------------------------------------------------------------

class TestComplexExample:
    """01 Complex example.pdf: 26 pages, J&T, mixed."""

    @pytest.fixture(autouse=True)
    def _parse(self):
        self.result = parse_pdf(SAMPLES_DIR / "01 Complex example.pdf")

    def test_label_count(self):
        assert len(self.result) == 41

    def test_has_jt_express(self):
        jt = [r for r in self.result if r.page_type == PageType.JT_EXPRESS]
        assert len(jt) >= 1

    def test_jt_on_page_21(self):
        jt = [r for r in self.result if r.page_type == PageType.JT_EXPRESS]
        assert any(r.page_number == 21 for r in jt)

    def test_summary_pages_skipped(self):
        pages = {r.page_number for r in self.result}
        for pg in [22, 23, 24, 25]:
            assert pg not in pages

    def test_has_2col(self):
        two_col = [r for r in self.result if r.page_type == PageType.STANDARD_2COL]
        assert len(two_col) >= 30

    def test_has_1col_products(self):
        prods = [r for r in self.result if r.page_type == PageType.STANDARD_1COL_PRODUCTS]
        assert len(prods) >= 1

    def test_has_1col(self):
        single = [r for r in self.result if r.page_type == PageType.STANDARD_1COL]
        assert len(single) >= 1

    def test_all_ids_valid_format(self):
        for label in self.result:
            assert label.pack_id.startswith("2000")
            assert len(label.pack_id) >= 16
            assert label.pack_id.isdigit()

    def test_barcode_positions_reasonable(self):
        for label in self.result:
            assert 540 < label.barcode_y < 720
            assert 30 < label.barcode_x < 350

    def test_no_duplicate_labels_per_page_column(self):
        """Each (page_number, column) pair should appear at most once."""
        seen = set()
        for label in self.result:
            key = (label.page_number, label.column)
            assert key not in seen, f"Duplicate label at page {label.page_number}, column {label.column}"
            seen.add(key)


# ---------------------------------------------------------------------------
# Cross-cutting tests
# ---------------------------------------------------------------------------

class TestSummaryPagesSkipped:
    """Summary pages produce no labels in any sample."""

    def test_02_simple_no_summary_labels(self):
        result = parse_pdf(SAMPLES_DIR / "02 Simple example.pdf")
        assert all(r.page_number != 1 for r in result)

    def test_03_example_no_summary_labels(self):
        result = parse_pdf(SAMPLES_DIR / "03 example.pdf")
        assert all(r.page_number != 2 for r in result)

    def test_04_example_no_summary_labels(self):
        result = parse_pdf(SAMPLES_DIR / "04 example.pdf")
        assert all(r.page_number not in (8, 9) for r in result)

    def test_05_example_no_summary_labels(self):
        result = parse_pdf(SAMPLES_DIR / "05 example with surprise.pdf")
        assert all(r.page_number not in (8, 9) for r in result)

    def test_01_complex_no_summary_labels(self):
        result = parse_pdf(SAMPLES_DIR / "01 Complex example.pdf")
        assert all(r.page_number not in (22, 23, 24, 25) for r in result)


class TestDeduplication:
    """Same ID in tear-off header + body should be counted only once per column."""

    def test_02_simple_no_duplicates(self):
        result = parse_pdf(SAMPLES_DIR / "02 Simple example.pdf")
        # Only 1 label even though Pack ID appears 3 times
        assert len(result) == 1

    def test_03_example_no_duplicates(self):
        result = parse_pdf(SAMPLES_DIR / "03 example.pdf")
        ids = [r.pack_id for r in result]
        assert len(ids) == len(set(ids))  # all unique


class TestLabelInfoFields:
    """Verify all fields of LabelInfo are populated correctly."""

    def test_label_info_fields(self):
        result = parse_pdf(SAMPLES_DIR / "02 Simple example.pdf")
        label = result[0]
        assert isinstance(label.pack_id, str)
        assert isinstance(label.page_number, int)
        assert isinstance(label.column, str)
        assert isinstance(label.page_type, PageType)
        assert isinstance(label.barcode_y, float)
        assert isinstance(label.barcode_x, float)

    def test_column_values(self):
        """Columns should only be 'left', 'right', or 'full'."""
        for sample in SAMPLES_DIR.glob("*.pdf"):
            if sample.name.startswith(("01", "02", "03", "04", "05")):
                result = parse_pdf(sample)
                for label in result:
                    assert label.column in ("left", "right", "full")
