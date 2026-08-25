from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .data_provider import UnconfiguredCashApplicationDataProvider
from .learning_repository import PaymentBehaviorRepository
from .models import (
    ConfirmApplicationRequest,
    LockboxRecommendationRequest,
    LockboxRecommendationResponse,
)
from .service import LockboxRecommendationService


router = APIRouter(
    prefix="/api/v1/documents/cash-application",
    tags=["Cash Application Intelligence"],
)

_behavior_repository = PaymentBehaviorRepository()
_behavior_repository.initialize()

_data_provider = UnconfiguredCashApplicationDataProvider()
_recommendation_service = LockboxRecommendationService(
    data_provider=_data_provider
)


def configure_cash_application_data_provider(provider) -> None:
    global _data_provider, _recommendation_service

    _data_provider = provider
    _recommendation_service = LockboxRecommendationService(
        data_provider=provider
    )


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "phase": 11,
        "capabilities": [
            "payment_intent_analysis",
            "invoice_candidate_filtering",
            "invoice_combination_resolution",
            "customer_payment_behavior_learning",
            "lockbox_customer_resolution_bridge",
            "existing_open_invoice_integration",
            "cash_application_recommendations",
            "confidence_scoring",
        ],
        "provider": type(_data_provider).__name__,
    }


@router.post("/confirm")
def confirm_application(
    request: ConfirmApplicationRequest,
) -> dict:
    _behavior_repository.record_observation(
        customer_number=request.customer_number,
        pattern_type=request.intent_type,
        pattern_key=request.pattern_key,
        was_successful=request.was_successful,
    )

    return {
        "status": "saved",
        "customer_number": request.customer_number,
        "pattern_type": request.intent_type,
        "pattern_key": request.pattern_key,
        "was_successful": request.was_successful,
    }


@router.post(
    "/recommend",
    response_model=LockboxRecommendationResponse,
)
def recommend_cash_application(
    request: LockboxRecommendationRequest,
) -> LockboxRecommendationResponse:
    try:
        return _recommendation_service.recommend(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cash-application recommendation failed: {exc}",
        ) from exc
