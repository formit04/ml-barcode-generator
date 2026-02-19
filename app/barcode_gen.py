import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image


def generate_barcode_image(pack_id: str) -> bytes:
    """Generate a Code 128 barcode as high-resolution PNG bytes.

    The barcode is generated at high DPI with thick bars for clear
    scanning when printed on shipping labels.

    Args:
        pack_id: The Pack ID / Venta ID to encode.

    Returns:
        PNG image bytes.
    """
    code128 = barcode.get_barcode_class("code128")
    writer = ImageWriter()

    bc = code128(pack_id, writer=writer)
    buffer = io.BytesIO()
    bc.write(buffer, options={
        "module_width": 0.4,
        "module_height": 12,
        "font_size": 10,
        "text_distance": 3,
        "quiet_zone": 3,
        "dpi": 300,
    })
    buffer.seek(0)

    output = io.BytesIO()
    img = Image.open(buffer)
    img.save(output, format="PNG")
    return output.getvalue()
