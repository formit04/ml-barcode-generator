import os
import uuid
import tempfile
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.pdf_parser import parse_pdf, PageType
from app.pdf_overlay import add_barcodes_to_pdf

app = FastAPI(title="ML Barcode Generator")

processed_files: dict[str, dict] = {}
TEMP_DIR = tempfile.mkdtemp(prefix="ml_barcode_")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/barcode")
def barcode_redirect():
    return RedirectResponse(url="/barcode/", status_code=301)


@app.post("/barcode/process")
async def process_pdf(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un PDF")

    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="El archivo no es un PDF válido")

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
        if os.path.exists(input_path):
            os.unlink(input_path)


@app.get("/barcode/download/{file_id}")
def download_pdf(file_id: str):
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


app.mount("/barcode", StaticFiles(directory="static", html=True), name="static")
