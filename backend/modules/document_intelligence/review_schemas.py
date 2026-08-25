from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_UNAVAILABLE_FIELDS = frozenset(
    {
        "vendor_number",
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "purchase_order_number",
        "terms",
        "subtotal",
        "tax",
        "freight",
        "discount",
        "total_amount",
        "currency",
    }
)

DocumentReviewStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "needs_correction",
    "needs_learning",
]


class DocumentReviewSaveRequest(BaseModel):
    expected_processing_run_id: str = Field(min_length=1, max_length=200)
    status: DocumentReviewStatus = "pending"
    reviewer: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=10000)
    corrected_fields: dict[str, Any] = Field(default_factory=dict)
    # None means an additive, legacy client omitted the property. The active
    # router preserves same-run unavailable decisions in that case; an
    # explicit empty list clears them.
    unavailable_fields: list[str] | None = Field(default=None, max_length=13)

    @field_validator("unavailable_fields")
    @classmethod
    def validate_unavailable_fields(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None
        normalized = list(dict.fromkeys(item.strip() for item in value))
        unsupported = sorted(
            item
            for item in normalized
            if item not in SUPPORTED_UNAVAILABLE_FIELDS
        )
        if unsupported:
            raise ValueError(
                "Unavailable fields must be supported AP invoice business "
                f"fields; unsupported: {', '.join(unsupported)}"
            )
        return normalized

    @model_validator(mode="after")
    def validate_review_field_dispositions(self) -> "DocumentReviewSaveRequest":
        conflicts = sorted(
            set(self.corrected_fields).intersection(
                self.unavailable_fields or []
            )
        )
        if conflicts:
            raise ValueError(
                "A review field cannot be both corrected and marked "
                f"unavailable: {', '.join(conflicts)}"
            )
        return self


class DocumentReviewModel(BaseModel):
    job_id: str
    processing_run_id: str | None = None
    status: DocumentReviewStatus
    reviewer: str
    notes: str
    corrected_fields: dict[str, Any]
    unavailable_fields: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class DocumentReviewHistoryModel(BaseModel):
    id: int
    job_id: str
    processing_run_id: str | None = None
    status: DocumentReviewStatus
    reviewer: str
    notes: str
    corrected_fields: dict[str, Any]
    unavailable_fields: list[str] = Field(default_factory=list)
    created_at: str


class DocumentReviewResponse(BaseModel):
    review: DocumentReviewModel
    history: list[DocumentReviewHistoryModel]
