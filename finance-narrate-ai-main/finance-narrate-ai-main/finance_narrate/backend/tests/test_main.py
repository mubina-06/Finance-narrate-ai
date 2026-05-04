"""Tests for FastAPI endpoints in main.py using Starlette TestClient."""

import io
from unittest.mock import patch

import pytest

# Patch llm_client before importing app to avoid GEMINI_API_KEY requirement
import sys
from unittest.mock import MagicMock

# Create a mock llm_client module so the import in main.py doesn't fail
mock_llm = MagicMock()
sys.modules.setdefault("llm_client", mock_llm)

from starlette.testclient import TestClient
from main import app, metrics_store, narrative_store, upload_store
from models import NarrativeResult

client = TestClient(app)

# ---------------------------------------------------------------------------
# Sample CSV content
# ---------------------------------------------------------------------------

VALID_CSV = b"""Date,Revenue,Expenses,Category
2023-01-05,120000,18000,Marketing
2023-01-15,95000,22000,Operations
2023-02-03,130000,19500,HR
"""

MISSING_COLS_CSV = b"""Date,Revenue
2023-01-05,120000
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def upload_valid_file() -> str:
    """Upload a valid CSV and return the file_id."""
    response = client.post(
        "/upload",
        files={"file": ("test.csv", io.BytesIO(VALID_CSV), "text/csv")},
    )
    assert response.status_code == 200
    return response.json()["file_id"]


def make_fake_narrative(file_id: str) -> NarrativeResult:
    return NarrativeResult(
        file_id=file_id,
        executive_summary="Summary.",
        revenue_trends=["Trend 1"],
        anomalies=["Anomaly 1"],
        recommendations=["Rec 1"],
    )


# ---------------------------------------------------------------------------
# 1. GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_status_ok(self):
        response = client.get("/health")
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. POST /upload — valid CSV
# ---------------------------------------------------------------------------

class TestUploadValid:
    def test_returns_200(self):
        response = client.post(
            "/upload",
            files={"file": ("data.csv", io.BytesIO(VALID_CSV), "text/csv")},
        )
        assert response.status_code == 200

    def test_response_has_required_fields(self):
        response = client.post(
            "/upload",
            files={"file": ("data.csv", io.BytesIO(VALID_CSV), "text/csv")},
        )
        body = response.json()
        assert "file_id" in body
        assert "filename" in body
        assert "row_count" in body
        assert "status" in body

    def test_status_is_uploaded(self):
        response = client.post(
            "/upload",
            files={"file": ("data.csv", io.BytesIO(VALID_CSV), "text/csv")},
        )
        assert response.json()["status"] == "uploaded"

    def test_row_count_correct(self):
        response = client.post(
            "/upload",
            files={"file": ("data.csv", io.BytesIO(VALID_CSV), "text/csv")},
        )
        assert response.json()["row_count"] == 3


# ---------------------------------------------------------------------------
# 3. POST /upload — missing columns → 422
# ---------------------------------------------------------------------------

class TestUploadMissingColumns:
    def test_returns_422(self):
        response = client.post(
            "/upload",
            files={"file": ("bad.csv", io.BytesIO(MISSING_COLS_CSV), "text/csv")},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# 4. POST /upload — unsupported file type → 415
# ---------------------------------------------------------------------------

class TestUploadUnsupportedType:
    def test_returns_415(self):
        response = client.post(
            "/upload",
            files={"file": ("data.txt", io.BytesIO(b"some text"), "text/plain")},
        )
        assert response.status_code == 415


# ---------------------------------------------------------------------------
# 5. POST /analyze/{file_id} — valid file_id → 200 with MetricsResult
# ---------------------------------------------------------------------------

class TestAnalyzeValid:
    def test_returns_200(self):
        file_id = upload_valid_file()
        response = client.post(f"/analyze/{file_id}")
        assert response.status_code == 200

    def test_response_has_metrics_fields(self):
        file_id = upload_valid_file()
        response = client.post(f"/analyze/{file_id}")
        body = response.json()
        assert body["file_id"] == file_id
        assert "monthly_revenue" in body
        assert "mom_growth" in body
        assert "top_categories" in body
        assert "expense_anomalies" in body
        assert "revenue_dips" in body


# ---------------------------------------------------------------------------
# 6. POST /analyze/{file_id} — invalid file_id → 404
# ---------------------------------------------------------------------------

class TestAnalyzeInvalid:
    def test_returns_404(self):
        response = client.post("/analyze/nonexistent-id")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# 7. POST /generate-narrative/{file_id} — without prior analysis → 400
# ---------------------------------------------------------------------------

class TestGenerateNarrativeNoPriorAnalysis:
    def test_returns_400_without_analysis(self):
        file_id = upload_valid_file()
        # Do NOT call /analyze first
        response = client.post(f"/generate-narrative/{file_id}")
        assert response.status_code == 400

    def test_returns_200_with_mocked_llm(self):
        file_id = upload_valid_file()
        # Run analysis first
        client.post(f"/analyze/{file_id}")
        fake_narrative = make_fake_narrative(file_id)
        with patch("llm_client.generate_narrative", return_value=fake_narrative):
            response = client.post(f"/generate-narrative/{file_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["file_id"] == file_id
        assert "executive_summary" in body


# ---------------------------------------------------------------------------
# 8. GET /report/{file_id} — without metrics/narrative → 400
# ---------------------------------------------------------------------------

class TestReportMissingComponents:
    def test_returns_400_without_metrics_and_narrative(self):
        file_id = upload_valid_file()
        response = client.get(f"/report/{file_id}")
        assert response.status_code == 400

    def test_returns_400_with_only_metrics(self):
        file_id = upload_valid_file()
        client.post(f"/analyze/{file_id}")
        # narrative not generated
        response = client.get(f"/report/{file_id}")
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# 9. GET /report/{file_id} — invalid file_id → 404
# ---------------------------------------------------------------------------

class TestReportInvalidFileId:
    def test_returns_404(self):
        response = client.get("/report/nonexistent-id")
        assert response.status_code == 404

    def test_returns_200_with_full_report(self):
        file_id = upload_valid_file()
        client.post(f"/analyze/{file_id}")
        # Manually inject narrative
        narrative_store[file_id] = make_fake_narrative(file_id)
        response = client.get(f"/report/{file_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["file_id"] == file_id
        assert "metrics" in body
        assert "narrative" in body
