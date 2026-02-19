from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="ML Barcode Generator")

@app.get("/health")
def health():
    return {"status": "ok"}
