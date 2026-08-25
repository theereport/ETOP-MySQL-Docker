from .learning_schemas import GenerateLearningExamplesResponse, LearningExampleListResponse, LearningSummaryResponse
from .learning_store import create_examples, get_summary, list_examples
from .review_store import get_review

@router.get("/learning/summary", response_model=LearningSummaryResponse)
def read_learning_summary() -> LearningSummaryResponse:
    return LearningSummaryResponse(**get_summary())

@router.get("/learning/examples", response_model=LearningExampleListResponse)
def read_learning_examples(limit: int = Query(default=100, ge=1, le=500)) -> LearningExampleListResponse:
    return LearningExampleListResponse(**list_examples(limit))

@router.post("/jobs/{job_id}/learning", response_model=GenerateLearningExamplesResponse)
def create_job_learning_examples(job_id: str) -> GenerateLearningExamplesResponse:
    job = get_job(job_id)
    result = get_job_result(job_id)
    review = get_review(job_id)["review"]
    corrected_fields = review.get("corrected_fields", {})
    if not corrected_fields:
        return GenerateLearningExamplesResponse(created=0, skipped=0, examples=[])
    parsed = result.get("parsed", {})
    if not isinstance(parsed, dict):
        parsed = {}
    return GenerateLearningExamplesResponse(**create_examples(job_id=job_id, document_type=job.get("document_type", "unknown"), original_fields=parsed, corrected_fields=corrected_fields, reviewer=review.get("reviewer", ""), source_status=review.get("status", "pending")))
