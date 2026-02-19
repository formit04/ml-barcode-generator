import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_process_pdf_returns_json():
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    with open(pdf_path, "rb") as f:
        response = client.post("/process", files={"file": ("test.pdf", f, "application/pdf")})
    assert response.status_code == 200
    data = response.json()
    assert "file_id" in data
    assert data["total_labels"] == 4
    assert "stats" in data


def test_process_non_pdf_rejected():
    response = client.post(
        "/process",
        files={"file": ("test.txt", b"not a pdf", "text/plain")}
    )
    assert response.status_code == 400


def test_download_after_process():
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    with open(pdf_path, "rb") as f:
        resp = client.post("/process", files={"file": ("test.pdf", f, "application/pdf")})
    file_id = resp.json()["file_id"]
    download_resp = client.get(f"/download/{file_id}")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert download_resp.content[:5] == b"%PDF-"


def test_download_invalid_id():
    response = client.get("/download/nonexistent")
    assert response.status_code == 404
