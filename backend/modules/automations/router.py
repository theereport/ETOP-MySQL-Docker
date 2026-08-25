from __future__ import annotations

import threading
import uuid
from datetime import datetime
from time import perf_counter

from fastapi import APIRouter, HTTPException, Query

from .repository import (
    AutomationStateConflict,
    automation_service_health,
    clear_executions,
    create_execution,
    delete_automation,
    finish_execution,
    get_automation,
    list_automations,
    list_executions,
    quarantine_automation,
    save_automation,
    update_after_run,
    validate_repository_bindings,
)
from .schemas import (
    AutomationDefinition,
    AutomationExecution,
    RunAutomationRequest,
    RunAutomationResponse,
)
from .service import (
    AutomationExecutionError,
    run_automation as execute_automation,
)
from .validation import (
    AutomationValidationError,
    health_for_automation,
    validate_for_execution,
)


router = APIRouter(
    prefix="/automations",
    tags=["Automations"],
)

_execution_lock = threading.Lock()
_running_automation_ids: set[str] = set()


def execute_and_record(
    automation: AutomationDefinition,
    triggered_by: str,
) -> RunAutomationResponse:
    validate_for_execution(automation)
    validate_repository_bindings(automation)

    with _execution_lock:
        if automation.id in _running_automation_ids:
            raise AutomationExecutionError(
                "This automation is already running."
            )

        _running_automation_ids.add(
            automation.id
        )

    execution_id = str(uuid.uuid4())
    started_at = datetime.now().astimezone()
    started = perf_counter()

    try:
        claimed = create_execution(
            AutomationExecution(
                id=execution_id,
                automationId=automation.id,
                automationName=automation.name,
                status="running",
                startedAt=started_at.isoformat(),
                completedAt=None,
                durationMs=None,
                rowCount=None,
                outputFileName="",
                outputFilePath="",
                message="Automation execution started.",
                errorDetails="",
                triggeredBy=triggered_by,
            )
        )
    except Exception:
        with _execution_lock:
            _running_automation_ids.discard(automation.id)
        raise

    if not claimed:
        with _execution_lock:
            _running_automation_ids.discard(automation.id)

        raise AutomationExecutionError(
            "This automation already has a durable running execution."
        )

    try:
        response = execute_automation(
            automation
        )

        completed_at = datetime.now().astimezone()

        finish_execution(
            execution_id,
            status=response.status,
            completed_at=completed_at.isoformat(),
            duration_ms=response.duration_ms,
            row_count=response.row_count,
            output_file_name=response.output_file_name,
            output_file_path=response.output_file_path,
            message=response.message,
            error_details="",
        )

        update_after_run(
            automation,
            status=response.status,
            completed_at=completed_at,
        )

        return response

    except Exception as exc:
        completed_at = datetime.now().astimezone()
        duration_ms = round(
            (perf_counter() - started) * 1000
        )
        message = str(exc)

        try:
            finish_execution(
                execution_id,
                status="failed",
                completed_at=completed_at.isoformat(),
                duration_ms=duration_ms,
                row_count=None,
                output_file_name="",
                output_file_path="",
                message="Automation execution failed.",
                error_details=message,
            )
        finally:
            try:
                update_after_run(
                    automation,
                    status="failed",
                    completed_at=completed_at,
                )
            except Exception:
                # A completed external script must not remain immediately due
                # merely because final schedule persistence failed.
                quarantine_automation(automation.id)

        raise

    finally:
        with _execution_lock:
            _running_automation_ids.discard(
                automation.id
            )


@router.get("")
def get_automations() -> dict:
    automations = list_automations()

    return {
        "automations": [
            automation.model_dump(
                by_alias=True
            )
            for automation in automations
        ],
        "health": [
            health_for_automation(automation)
            for automation in automations
        ],
        "count": len(automations),
    }


@router.post("")
def upsert_automation(
    automation: AutomationDefinition,
) -> dict:
    try:
        saved = save_automation(
            automation
        )
    except AutomationStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except (AutomationValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "automation": saved.model_dump(
            by_alias=True
        ),
        "message": "Automation saved.",
    }


@router.get("/executions")
def get_execution_history(
    limit: int = Query(
        default=250,
        ge=1,
        le=1000,
    ),
) -> dict:
    executions = list_executions(
        limit=limit
    )

    return {
        "executions": [
            execution.model_dump(
                by_alias=True
            )
            for execution in executions
        ],
        "count": len(executions),
    }


@router.delete("/executions")
def delete_execution_history() -> dict:
    try:
        deleted_count = clear_executions()
    except AutomationStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        "success": True,
        "deletedCount": deleted_count,
        "message": (
            "Automation execution history cleared."
        ),
    }


@router.get("/health")
def get_automation_health() -> dict:
    from .scheduler import automation_scheduler

    health = automation_service_health(
        scheduler_running=automation_scheduler.running,
    )
    diagnostics = automation_scheduler.diagnostics()
    health["scheduler"] = diagnostics

    if diagnostics["lastError"] and health["status"] == "healthy":
        health["status"] = "degraded"

    return health


@router.get("/{automation_id}")
def get_automation_by_id(
    automation_id: str,
) -> dict:
    automation = get_automation(
        automation_id
    )

    if automation is None:
        raise HTTPException(
            status_code=404,
            detail="Automation not found.",
        )

    return {
        "automation": automation.model_dump(by_alias=True),
        "health": health_for_automation(automation),
    }


@router.delete("/{automation_id}")
def remove_automation(
    automation_id: str,
) -> dict:
    try:
        deleted = delete_automation(automation_id)
    except AutomationStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Automation not found.",
        )

    return {
        "success": True,
        "message": "Automation deleted.",
    }


@router.post(
    "/run",
    response_model=RunAutomationResponse,
)
def run_automation(
    request: RunAutomationRequest,
) -> RunAutomationResponse:
    automation = request.automation

    if automation is not None:
        if request.automation_id != automation.id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "automation_id does not match "
                    "the supplied automation."
                ),
            )

        try:
            automation = save_automation(
                automation
            )
        except AutomationStateConflict as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc
        except (AutomationValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

    else:
        automation = get_automation(
            request.automation_id
        )

    if automation is None:
        raise HTTPException(
            status_code=404,
            detail="Automation not found.",
        )

    try:
        return execute_and_record(
            automation,
            request.triggered_by,
        )
    except (AutomationExecutionError, AutomationValidationError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Automation execution failed "
                f"unexpectedly: {exc}"
            ),
        ) from exc
