"""FastAPI application for FinanceNarrate AI.

Wires together the file validator, Pandas processing pipeline, and Gemini
LLM client into a set of HTTP endpoints.  State is held entirely in-process
using module-level Python dicts keyed by ``file_id``.

In-process stores:
    metrics_store: Computed MetricsResult objects keyed by file_id.
    narrative_store: Generated NarrativeResult objects keyed by file_id.
    upload_store: Uploaded file metadata (filename, path, row_count) keyed
        by file_id.
"""

import csv
import io
import uuid
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models import MetricsResult, NarrativeResult, ReportResult, UploadResponse

# ---------------------------------------------------------------------------
# 6.1 — App initialisation and CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="FinanceNarrate AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module-level in-process stores
metrics_store: dict[str, MetricsResult] = {}
narrative_store: dict[str, NarrativeResult] = {}
upload_store: dict[str, dict] = {}  # {"filename": str, "path": str, "row_count": int}

# ---------------------------------------------------------------------------
# 6.3 — File Validator helper
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {"Date", "Revenue", "Expenses", "Category"}
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def validate_file(filename: str, content: bytes) -> None:
    """Validate an uploaded file's extension and required column headers.

    Checks that the file extension is one of ``.csv``, ``.xlsx``, or
    ``.xls``, then reads the column headers from the file content and
    verifies that all four required columns (``Date``, ``Revenue``,
    ``Expenses``, ``Category``) are present.

    Args:
        filename: The original filename of the uploaded file, used to
            determine the file extension.
        content: The raw bytes of the uploaded file.

    Raises:
        HTTPException: HTTP 415 if the file extension is not supported.
        HTTPException: HTTP 422 if one or more required columns are absent,
            with a detail message listing the missing column names.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload CSV or Excel (.xlsx/.xls).",
        )

    if suffix == ".csv":
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        try:
            headers = set(next(reader))
        except StopIteration:
            headers = set()
    else:
        df = pd.read_excel(io.BytesIO(content), nrows=0)
        headers = set(df.columns.tolist())

    missing_cols = REQUIRED_COLUMNS - headers
    if missing_cols:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required columns: {sorted(missing_cols)}",
        )


# ---------------------------------------------------------------------------
# 6.2 — GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    """Liveness check endpoint.

    Returns:
        A JSON object ``{"status": "ok"}`` with HTTP 200.
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 6.6 — POST /upload
# ---------------------------------------------------------------------------

@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile) -> UploadResponse:
    """Accept a multipart file upload, validate it, and store it on disk.

    Reads the uploaded file bytes, validates the extension and required
    columns via :func:`validate_file`, generates a unique ``file_id``,
    saves the file to ``uploads/{file_id}/{filename}``, counts the data
    rows, and records the upload metadata in ``upload_store``.

    Args:
        file: The multipart file upload from the request.

    Returns:
        An :class:`UploadResponse` containing ``file_id``, ``filename``,
        ``row_count``, and ``status="uploaded"``.

    Raises:
        HTTPException: HTTP 415 for unsupported file types.
        HTTPException: HTTP 422 for missing required columns.
    """
    content = await file.read()
    validate_file(file.filename, content)

    file_id = str(uuid.uuid4())
    upload_dir = Path("uploads") / file_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    file_path.write_bytes(content)

    # Count data rows (total rows minus header)
    suffix = Path(file.filename).suffix.lower()
    if suffix == ".csv":
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        row_count = max(0, len(rows) - 1)  # subtract header
    else:
        df = pd.read_excel(io.BytesIO(content))
        row_count = len(df)

    upload_store[file_id] = {
        "filename": file.filename,
        "path": str(file_path),
        "row_count": row_count,
    }

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        row_count=row_count,
        status="uploaded",
    )


# ---------------------------------------------------------------------------
# 6.8 — POST /analyze/{file_id}
# ---------------------------------------------------------------------------

@app.post("/analyze/{file_id}", response_model=MetricsResult)
async def analyze(file_id: str) -> MetricsResult:
    """Run the Pandas processing pipeline for the given file_id.

    Looks up the uploaded file in ``upload_store``, calls
    :func:`processor.build_metrics` to compute all financial metrics, stores
    the result in ``metrics_store``, and returns it.

    Args:
        file_id: The unique identifier of the previously uploaded file.

    Returns:
        A fully populated :class:`MetricsResult` for the uploaded file.

    Raises:
        HTTPException: HTTP 404 if ``file_id`` is not found in
            ``upload_store``.
    """
    if file_id not in upload_store:
        raise HTTPException(
            status_code=404,
            detail=f"File not found for file_id: {file_id}",
        )

    from processor import build_metrics

    path = Path(upload_store[file_id]["path"])
    metrics = build_metrics(path, file_id)
    metrics_store[file_id] = metrics
    return metrics


# ---------------------------------------------------------------------------
# 6.9 — POST /generate-narrative/{file_id}
# ---------------------------------------------------------------------------

@app.post("/generate-narrative/{file_id}", response_model=NarrativeResult)
async def generate_narrative_endpoint(file_id: str) -> NarrativeResult:
    """Generate an AI narrative for the given file_id using the Gemini API.

    Looks up the computed metrics in ``metrics_store``, calls
    :func:`llm_client.generate_narrative` to produce a board-ready narrative,
    stores the result in ``narrative_store``, and returns it.

    The ``llm_client`` module is imported lazily inside this function so that
    the application can start without a valid ``GEMINI_API_KEY`` (useful for
    testing other endpoints).

    Args:
        file_id: The unique identifier of the previously analyzed file.

    Returns:
        A :class:`NarrativeResult` containing the four-section narrative.

    Raises:
        HTTPException: HTTP 400 if analysis has not been run for
            ``file_id`` (i.e. no entry in ``metrics_store``).
    """
    if file_id not in metrics_store:
        raise HTTPException(
            status_code=400,
            detail="Analysis must be run before narrative generation.",
        )

    from llm_client import generate_narrative

    metrics = metrics_store[file_id]
    narrative = generate_narrative(metrics)
    narrative_store[file_id] = narrative
    return narrative


# ---------------------------------------------------------------------------
# 6.10 — GET /report/{file_id}
# ---------------------------------------------------------------------------

@app.get("/report/{file_id}", response_model=ReportResult)
async def get_report(file_id: str) -> ReportResult:
    """Return the combined Metrics + Narrative report for the given file_id.

    Verifies that the ``file_id`` exists in ``upload_store``, then checks
    that both ``metrics_store`` and ``narrative_store`` contain entries for
    it.  Returns a :class:`ReportResult` combining both.

    Args:
        file_id: The unique identifier of the uploaded file.

    Returns:
        A :class:`ReportResult` containing both the :class:`MetricsResult`
        and the :class:`NarrativeResult` for the file.

    Raises:
        HTTPException: HTTP 404 if ``file_id`` is not found in
            ``upload_store``.
        HTTPException: HTTP 400 if either metrics or narrative are not yet
            available, with a detail message listing the missing components.
    """
    if file_id not in upload_store:
        raise HTTPException(
            status_code=404,
            detail=f"File not found for file_id: {file_id}",
        )

    missing_components = []
    if file_id not in metrics_store:
        missing_components.append("metrics")
    if file_id not in narrative_store:
        missing_components.append("narrative")

    if missing_components:
        raise HTTPException(
            status_code=400,
            detail=f"Report incomplete. Missing: {', '.join(missing_components)}",
        )

    return ReportResult(
        file_id=file_id,
        metrics=metrics_store[file_id],
        narrative=narrative_store[file_id],
    )
