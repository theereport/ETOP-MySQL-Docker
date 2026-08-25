from fastapi import (
    APIRouter,
    HTTPException,
    Response,
    status,
)

from .schemas import (
    ReportCreate,
    ReportListResponse,
    ReportRecord,
    ReportUpdate,
)

from .service import (
    create_report,
    delete_report,
    get_report,
    list_reports,
    update_report,
)


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


@router.get(
    "",
    response_model=ReportListResponse,
)
def read_reports() -> ReportListResponse:
    reports = list_reports()

    return ReportListResponse(
        items=reports,
        total=len(reports),
    )


@router.get(
    "/{report_id}",
    response_model=ReportRecord,
)
def read_report(
    report_id: str,
) -> ReportRecord:
    report = get_report(
        report_id,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    return report


@router.post(
    "",
    response_model=ReportRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_report_endpoint(
    payload: ReportCreate,
) -> ReportRecord:
    try:
        return create_report(
            payload,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.put(
    "/{report_id}",
    response_model=ReportRecord,
)
def update_report_endpoint(
    report_id: str,
    payload: ReportUpdate,
) -> ReportRecord:
    report = update_report(
        report_id,
        payload,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    return report


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_report_endpoint(
    report_id: str,
) -> Response:
    deleted = delete_report(
        report_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )