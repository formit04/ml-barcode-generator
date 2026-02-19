import io
from PIL import Image
from app.barcode_gen import generate_barcode_image


def test_generate_barcode_returns_png():
    result = generate_barcode_image("2000011633126699")
    assert result is not None
    assert len(result) > 0
    assert result[:4] == b"\x89PNG"


def test_generate_barcode_different_ids():
    bc1 = generate_barcode_image("2000011633126699")
    bc2 = generate_barcode_image("2000011632217683")
    assert bc1 != bc2


def test_generate_barcode_dimensions():
    result = generate_barcode_image("2000011633126699")
    img = Image.open(io.BytesIO(result))
    w, h = img.size
    assert w == 300
    assert h == 40
