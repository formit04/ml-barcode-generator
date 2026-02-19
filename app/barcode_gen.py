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

    img = Image.open(buffer)
    img = img.resize((width_px, height_px), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()
