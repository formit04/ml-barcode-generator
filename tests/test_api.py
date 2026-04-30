import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_process_pdf_returns_json():
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    with open(pdf_path, "rb") as f:
        response = client.post(
            "/barcode/process",
            files={"file": ("test.pdf", f, "application/pdf")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["total_labels"] == 4
    assert len(data["files"]) == 1
    assert "file_id" in data["files"][0]
    assert data["files"][0]["filename"] == "test.pdf"
    assert "stats" in data


def test_process_non_pdf_rejected():
    response = client.post(
        "/barcode/process",
        files={"file": ("test.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 400


def test_process_multiple_pdfs():
    p1 = os.path.join(SAMPLES_DIR, "02 Simple example.pdf")
    p2 = os.path.join(SAMPLES_DIR, "03 example.pdf")
    with open(p1, "rb") as f1, open(p2, "rb") as f2:
        response = client.post(
            "/barcode/process",
            files=[
                ("file", ("a.pdf", f1.read(), "application/pdf")),
                ("file", ("b.pdf", f2.read(), "application/pdf")),
            ],
        )
    assert response.status_code == 200
    data = response.json()
    assert len(data["files"]) == 2
    assert data["total_labels"] == 5  # 1 + 4


def test_download_after_process():
    pdf_path = os.path.join(SAMPLES_DIR, "03 example.pdf")
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/barcode/process",
            files={"file": ("test.pdf", f, "application/pdf")},
        )
    file_id = resp.json()["files"][0]["file_id"]
    download_resp = client.get(f"/barcode/download/{file_id}")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert download_resp.content[:5] == b"%PDF-"


def test_download_invalid_id():
    response = client.get("/barcode/download/nonexistent")
    assert response.status_code == 404
