from typing import Any
from pydantic import BaseModel

class LearningExampleModel(BaseModel):
    id: int
    job_id: str
    document_type: str
    field_name: str
    original_value: Any
    corrected_value: Any
    reviewer: str
    source_status: str
    fingerprint: str
    created_at: str

class LearningExampleListResponse(BaseModel):
    examples: list[LearningExampleModel]
    total: int

class LearningSummaryModel(BaseModel):
    total_examples: int
    unique_documents: int
    unique_fields: int
    field_counts: dict[str, int]
    document_type_counts: dict[str, int]
    recent_examples: list[LearningExampleModel]

class LearningSummaryResponse(BaseModel):
    summary: LearningSummaryModel

class GenerateLearningExamplesResponse(BaseModel):
    created: int
    skipped: int
    examples: list[LearningExampleModel]
