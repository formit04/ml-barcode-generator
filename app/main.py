import io
import os
import uuid
import tempfile
import zipfile
from datetime import datetime, timezone, timedelta
from typing import List
from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.responses import Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore
from app.pdf_parser import parse_pdf, PageType
from app.pdf_overlay import add_barcodes_to_pdf

app = FastAPI(title="ML Barcode Generator")

processed_files: dict[str, dict] = {}
TEMP_DIR = tempfile.mkdtemp(prefix="ml_barcode_")

_STATS_COLLECTION = "barcode_stats"
_STATS_DOC = "global"
_EVENTS_COLLECTION = "barcode_events"

# Mexico City timezone (UTC-6)
_MX_TZ = timezone(timedelta(hours=-6))


def _get_db() -> firestore.Client | None:
    try:
        return firestore.Client(project="codezuno-web", database="(default)")
    except Exception:
        return None


def _log_event(total: int, standard: int, jt_express: int, ip: str, filename: str) -> None:
    db = _get_db()
    if not db:
        return
    now = datetime.now(timezone.utc)
    db.collection(_STATS_COLLECTION).document(_STATS_DOC).set(
        {
            "total_barcodes": firestore.Increment(total),
            "total_pdfs": firestore.Increment(1),
            "standard_barcodes": firestore.Increment(standard),
            "jt_express_barcodes": firestore.Increment(jt_express),
        },
        merge=True,
    )
    db.collection(_EVENTS_COLLECTION).add({
        "timestamp": now,
        "barcodes": total,
        "standard": standard,
        "jt_express": jt_express,
        "ip": ip,
        "filename": filename,
    })


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _process_single_pdf(content: bytes, filename: str, client_ip: str) -> dict:
    """Process a single PDF and return result dict."""
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
            "original_name": filename,
            "stats": stats,
        }

        _log_event(len(labels), stats["standard"], stats["jt_express"], client_ip, filename)

        return {
            "file_id": file_id,
            "filename": filename,
            "total_labels": len(labels),
            "stats": stats,
        }
    finally:
        if os.path.exists(input_path):
            os.unlink(input_path)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/barcode")
def barcode_redirect():
    return RedirectResponse(url="/barcode/", status_code=301)


@app.post("/barcode/process")
async def process_pdf(file: List[UploadFile], request: Request):
    client_ip = _get_client_ip(request)
    results = []
    errors = []

    for f in file:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            errors.append({"filename": f.filename or "unknown", "error": "No es un PDF"})
            continue

        content = await f.read()
        if not content.startswith(b"%PDF"):
            errors.append({"filename": f.filename, "error": "PDF no válido"})
            continue

        try:
            result = _process_single_pdf(content, f.filename, client_ip)
            results.append(result)
        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})

    if not results and errors:
        raise HTTPException(status_code=400, detail=errors[0]["error"])

    total_labels = sum(r["total_labels"] for r in results)
    total_standard = sum(r["stats"]["standard"] for r in results)
    total_jt = sum(r["stats"]["jt_express"] for r in results)

    return {
        "files": results,
        "total_labels": total_labels,
        "stats": {"standard": total_standard, "jt_express": total_jt},
        "errors": errors,
    }


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


@app.post("/barcode/download-all")
async def download_all(request: Request):
    body = await request.json()
    file_ids = body.get("file_ids", [])

    if not file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fid in file_ids:
            if fid not in processed_files:
                continue
            info = processed_files[fid]
            if not os.path.exists(info["output_path"]):
                continue
            out_name = info["original_name"].replace(".pdf", "_codigos.pdf")
            with open(info["output_path"], "rb") as f:
                zf.writestr(out_name, f.read())

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="etiquetas_codigos.zip"'},
    )


@app.get("/barcode/stats")
def get_stats():
    db = _get_db()
    if not db:
        raise HTTPException(status_code=503, detail="Firestore no disponible")

    global_doc = db.collection(_STATS_COLLECTION).document(_STATS_DOC).get()
    totals = global_doc.to_dict() if global_doc.exists else {}

    now_mx = datetime.now(_MX_TZ)
    today_start = now_mx.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    week_start = (now_mx - timedelta(days=now_mx.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    month_start = now_mx.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    events_ref = db.collection(_EVENTS_COLLECTION)
    month_events = events_ref.where("timestamp", ">=", month_start).stream()

    month_barcodes = 0
    week_barcodes = 0
    today_barcodes = 0

    for doc in month_events:
        data = doc.to_dict()
        ts = data.get("timestamp")
        bc = data.get("barcodes", 0)
        if ts >= month_start:
            month_barcodes += bc
        if ts >= week_start:
            week_barcodes += bc
        if ts >= today_start:
            today_barcodes += bc

    return {
        "total_barcodes": totals.get("total_barcodes", 0),
        "month_barcodes": month_barcodes,
        "week_barcodes": week_barcodes,
        "today_barcodes": today_barcodes,
    }


app.mount("/barcode", StaticFiles(directory="static", html=True), name="static")
