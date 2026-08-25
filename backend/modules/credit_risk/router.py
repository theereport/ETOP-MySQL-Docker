from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Path, Query, Response, UploadFile, status

from .schemas import (
    AssessmentCreate,
    AssessmentHistoryResponse,
    AssessmentRecord,
    CreditLineIntelligenceResponse,
    CreditLineProposalCreate,
    CreditLineProposalHistoryResponse,
    CreditLineProposalRecord,
    CustomerRiskResponse,
    OrderDecisionPreparationResponse,
    OrderRecommendationCreate,
    OrderRecommendationHistoryResponse,
    OrderRecommendationRecord,
    PortfolioMonitoringResponse,
    PortfolioReviewCreate,
    PortfolioReviewHistoryResponse,
    PortfolioReviewRecord,
    PriorityAlertsResponse,
    RiskBandSetResponse,
)
from .potential_customers import potential_customer_service
from .service import (
    CreditRiskCustomerNotFound,
    CreditRiskSourceIntegrityError,
    CreditRiskSourceUnavailable,
    credit_risk_service,
)


router = APIRouter(
    prefix="/api/v1/credit-risk",
    tags=["Credit Risk Foundation"],
)


@router.get("/potential-customers")
def get_potential_customers() -> dict:
    records = potential_customer_service.list()
    return {
        "contract_version": "credit-risk-potential-customers.v1",
        "count": len(records),
        "potential_customers": records,
    }


@router.post("/potential-customers/upload", status_code=status.HTTP_201_CREATED)
async def upload_potential_customer_application(
    file: UploadFile = File(...),
) -> dict:
    try:
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise ValueError("Credit application PDF exceeds the 25 MB R72.1 limit.")
        return potential_customer_service.ingest_pdf(file.filename or "credit-application.pdf", content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "potential_customer_application_invalid", "message": str(exc)},
        ) from exc


@router.get("/potential-customers/{potential_customer_id}/document")
def get_potential_customer_document(potential_customer_id: str) -> Response:
    try:
        file_name, content, digest = potential_customer_service.repository.get_document(potential_customer_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "potential_customer_document_not_found", "message": "Potential customer source document was not found."},
        ) from exc
    safe_name = file_name.replace('"', '')
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "ETag": digest,
        },
    )


@router.get("/potential-customers/{potential_customer_id}")
def get_potential_customer(potential_customer_id: str) -> dict:
    try:
        return potential_customer_service.get(potential_customer_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "potential_customer_not_found", "message": "Potential customer was not found."},
        ) from exc


@router.put("/potential-customers/{potential_customer_id}/review")
def update_potential_customer_review(
    potential_customer_id: str, payload: dict,
) -> dict:
    try:
        return potential_customer_service.update_review(potential_customer_id, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "potential_customer_not_found", "message": "Potential customer was not found."},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "potential_customer_review_invalid", "message": str(exc)},
        ) from exc


def _customer_number_path() -> int:
    return Path(ge=1)


def _raise_customer_error(exc: Exception) -> None:
    if isinstance(exc, CreditRiskCustomerNotFound):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "credit_risk_customer_not_found",
                "message": str(exc),
            },
        ) from exc
    if isinstance(exc, CreditRiskSourceUnavailable):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "credit_risk_source_unavailable",
                "message": str(exc),
            },
        ) from exc
    if isinstance(exc, CreditRiskSourceIntegrityError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "credit_risk_source_integrity_error",
                "message": str(exc),
            },
        ) from exc
    raise exc


@router.get(
    "/bands",
    response_model=RiskBandSetResponse,
)
def get_risk_bands() -> RiskBandSetResponse:
    return credit_risk_service.list_bands()


@router.get(
    "/priority-alerts",
    response_model=PriorityAlertsResponse,
)
def get_priority_alerts() -> PriorityAlertsResponse:
    # Each assessed customer degrades independently when live ERP evidence is
    # unavailable, so one source failure cannot erase assessment-derived work.
    return credit_risk_service.get_priority_alerts()


@router.get(
    "/portfolio-monitoring",
    response_model=PortfolioMonitoringResponse,
)
def get_portfolio_monitoring() -> PortfolioMonitoringResponse:
    return credit_risk_service.get_portfolio_monitoring()


@router.get(
    "/customers/{customer_number}",
    response_model=CustomerRiskResponse,
)
def get_customer_risk(
    customer_number: int = _customer_number_path(),
) -> CustomerRiskResponse:
    try:
        return credit_risk_service.get_customer_risk(customer_number)
    except (
        CreditRiskCustomerNotFound,
        CreditRiskSourceIntegrityError,
        CreditRiskSourceUnavailable,
    ) as exc:
        _raise_customer_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/customers/{customer_number}/assessments",
    response_model=AssessmentHistoryResponse,
)
def get_customer_assessments(
    customer_number: int = _customer_number_path(),
) -> AssessmentHistoryResponse:
    # This is intentionally local-only so historical evidence remains
    # retrievable while the ERP source is unavailable.
    return credit_risk_service.list_assessments(customer_number)


@router.post(
    "/customers/{customer_number}/assessments",
    response_model=AssessmentRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_assessment(
    payload: AssessmentCreate,
    customer_number: int = _customer_number_path(),
) -> AssessmentRecord:
    try:
        return credit_risk_service.create_assessment(
            customer_number,
            payload,
        )
    except (
        CreditRiskCustomerNotFound,
        CreditRiskSourceIntegrityError,
        CreditRiskSourceUnavailable,
    ) as exc:
        _raise_customer_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/customers/{customer_number}/credit-line-intelligence",
    response_model=CreditLineIntelligenceResponse,
)
def get_customer_credit_line_intelligence(
    customer_number: int = _customer_number_path(),
) -> CreditLineIntelligenceResponse:
    try:
        return credit_risk_service.get_credit_line_intelligence(
            customer_number
        )
    except (
        CreditRiskCustomerNotFound,
        CreditRiskSourceIntegrityError,
        CreditRiskSourceUnavailable,
    ) as exc:
        _raise_customer_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/customers/{customer_number}/credit-line-proposals",
    response_model=CreditLineProposalHistoryResponse,
)
def get_customer_credit_line_proposals(
    customer_number: int = _customer_number_path(),
) -> CreditLineProposalHistoryResponse:
    return credit_risk_service.list_credit_line_proposals(customer_number)


@router.post(
    "/customers/{customer_number}/credit-line-proposals",
    response_model=CreditLineProposalRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_credit_line_proposal(
    payload: CreditLineProposalCreate,
    customer_number: int = _customer_number_path(),
) -> CreditLineProposalRecord:
    try:
        return credit_risk_service.create_credit_line_proposal(
            customer_number,
            payload,
        )
    except (
        CreditRiskCustomerNotFound,
        CreditRiskSourceIntegrityError,
        CreditRiskSourceUnavailable,
    ) as exc:
        _raise_customer_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/customers/{customer_number}/portfolio-reviews",
    response_model=PortfolioReviewHistoryResponse,
)
def get_customer_portfolio_reviews(
    customer_number: int = _customer_number_path(),
) -> PortfolioReviewHistoryResponse:
    return credit_risk_service.list_portfolio_reviews(customer_number)


@router.post(
    "/customers/{customer_number}/portfolio-reviews",
    response_model=PortfolioReviewRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_portfolio_review(
    payload: PortfolioReviewCreate,
    customer_number: int = _customer_number_path(),
) -> PortfolioReviewRecord:
    try:
        return credit_risk_service.create_portfolio_review(
            customer_number,
            payload,
        )
    except (
        CreditRiskCustomerNotFound,
        CreditRiskSourceIntegrityError,
        CreditRiskSourceUnavailable,
    ) as exc:
        _raise_customer_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/customers/{customer_number}/order-decision-preparation",
    response_model=OrderDecisionPreparationResponse,
)
def get_customer_order_decision_preparation(
    customer_number: int = _customer_number_path(),
    contemplated_order_amount: float = Query(gt=0, le=1_000_000_000),
    order_reference: str | None = Query(default=None, max_length=100),
) -> OrderDecisionPreparationResponse:
    try:
        return credit_risk_service.get_order_decision_preparation(
            customer_number,
            contemplated_order_amount,
            order_reference,
        )
    except (
        CreditRiskCustomerNotFound,
        CreditRiskSourceIntegrityError,
        CreditRiskSourceUnavailable,
    ) as exc:
        _raise_customer_error(exc)
        raise AssertionError("unreachable")


@router.get(
    "/customers/{customer_number}/order-recommendations",
    response_model=OrderRecommendationHistoryResponse,
)
def get_customer_order_recommendations(
    customer_number: int = _customer_number_path(),
) -> OrderRecommendationHistoryResponse:
    return credit_risk_service.list_order_recommendations(customer_number)


@router.post(
    "/customers/{customer_number}/order-recommendations",
    response_model=OrderRecommendationRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_order_recommendation(
    payload: OrderRecommendationCreate,
    customer_number: int = _customer_number_path(),
) -> OrderRecommendationRecord:
    try:
        return credit_risk_service.create_order_recommendation(
            customer_number,
            payload,
        )
    except (
        CreditRiskCustomerNotFound,
        CreditRiskSourceIntegrityError,
        CreditRiskSourceUnavailable,
    ) as exc:
        _raise_customer_error(exc)
        raise AssertionError("unreachable")
