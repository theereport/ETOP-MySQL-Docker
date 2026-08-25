from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DifferenceType = Literal[
    "matched",
    "missing",
    "extra",
    "amount_error",
]


class ComparisonRow(BaseModel):
    transaction_id: str
    difference_type: DifferenceType
    invoice_number: str
    expected_amount: float | None = None
    actual_amount: float | None = None


class TransactionComparison(BaseModel):
    transaction_id: str
    expected_check_amount: float
    actual_check_amount: float | None = None
    expected_row_count: int
    actual_row_count: int
    matched_rows: int
    missing_rows: int
    extra_rows: int
    amount_errors: int
    balanced: bool
    accuracy: float
    differences: list[ComparisonRow]


class TrainingSessionResponse(BaseModel):
    session_id: str
    job_id: str
    dataset_type: str
    source_pdf_name: str
    ground_truth_file_name: str
    status: str
    overall_accuracy: float
    transaction_accuracy: float
    invoice_accuracy: float
    amount_accuracy: float
    expected_transactions: int
    actual_transactions: int
    matched_transactions: int
    expected_rows: int
    actual_rows: int
    matched_rows: int
    missing_rows: int
    extra_rows: int
    amount_errors: int
    created_at: str
    updated_at: str
    transactions: list[TransactionComparison] = Field(default_factory=list)


class TrainingSessionListResponse(BaseModel):
    sessions: list[TrainingSessionResponse]


class TrainingSummaryResponse(BaseModel):
    total_sessions: int
    total_documents: int
    expected_rows: int
    matched_rows: int
    missing_rows: int
    extra_rows: int
    amount_errors: int
    average_accuracy: float
    latest_session: TrainingSessionResponse | None = None
