from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from ..lockbox_service import get_lockbox_result
from ..service import get_job
from .comparison_engine import compare_lockbox
from .database import GROUND_TRUTH_ROOT, get_session, list_sessions, save_session
from .workbook_reader import read_pnc_ground_truth


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name.strip()) or "ground_truth.xlsx"


async def create_lockbox_training_session(job_id: str, file: UploadFile) -> dict:
    job = get_job(job_id)
    original_name = file.filename or "ground_truth.xlsx"
    safe_name = _safe_name(original_name)
    if Path(safe_name).suffix.lower() not in {".xlsx", ".xlsm"}:
        raise HTTPException(status_code=415, detail="Ground truth must be an Excel .xlsx or .xlsm workbook.")

    try:
        actual = get_lockbox_result(job_id)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=409,
            detail="Process the selected PDF through PNC Lockbox Automation before uploading ground truth.",
        ) from error

    session_id = str(uuid4())
    session_dir = GROUND_TRUTH_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    target = session_dir / safe_name
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    try:
        expected = read_pnc_ground_truth(target)
        comparison = compare_lockbox(actual, expected)
    except Exception as error:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Unable to read or compare the ground-truth workbook: {error}") from error

    now = _now()
    metrics = {key: value for key, value in comparison.items() if key != "transactions"}
    return save_session(
        {
            "session_id": session_id,
            "job_id": job_id,
            "dataset_type": "pnc_lockbox",
            "source_pdf_name": job["original_file_name"],
            "ground_truth_file_name": original_name,
            "ground_truth_path": str(target),
            "status": "compared",
            "metrics": metrics,
            "transactions": comparison["transactions"],
            "created_at": now,
            "updated_at": now,
        }
    )


def get_training_sessions(limit: int = 100) -> list[dict]:
    return list_sessions(limit)


def get_training_summary() -> dict:
    sessions = list_sessions(10000)
    if not sessions:
        return {
            "total_sessions": 0,
            "total_documents": 0,
            "expected_rows": 0,
            "matched_rows": 0,
            "missing_rows": 0,
            "extra_rows": 0,
            "amount_errors": 0,
            "average_accuracy": 0.0,
            "latest_session": None,
        }
    return {
        "total_sessions": len(sessions),
        "total_documents": len({item["job_id"] for item in sessions}),
        "expected_rows": sum(item["expected_rows"] for item in sessions),
        "matched_rows": sum(item["matched_rows"] for item in sessions),
        "missing_rows": sum(item["missing_rows"] for item in sessions),
        "extra_rows": sum(item["extra_rows"] for item in sessions),
        "amount_errors": sum(item["amount_errors"] for item in sessions),
        "average_accuracy": round(sum(item["overall_accuracy"] for item in sessions) / len(sessions), 2),
        "latest_session": sessions[0],
    }


def get_training_session(session_id: str) -> dict:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Training session was not found.")
    return session
