from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AutomationStatus = Literal[
    "active",
    "paused",
    "draft",
    "error",
]

AutomationFrequency = Literal[
    "manual",
    "daily",
    "weekly",
    "monthly",
    "custom",
]

ExecutionStatus = Literal[
    "running",
    "success",
    "warning",
    "failed",
    "cancelled",
]


class AutomationSchedule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    frequency: AutomationFrequency = "manual"
    time: str = "07:00"
    days_of_week: list[int] = Field(
        default_factory=lambda: [1],
        alias="daysOfWeek",
    )
    day_of_month: int | None = Field(
        default=1,
        alias="dayOfMonth",
    )
    cron_expression: str = Field(
        default="",
        alias="cronExpression",
    )
    timezone: str = "America/New_York"


class AutomationDelivery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    method: Literal["email", "folder", "none"] = "none"
    recipients: list[str] = Field(default_factory=list)
    cc_recipients: list[str] = Field(
        default_factory=list,
        alias="ccRecipients",
    )
    subject: str = ""
    message: str = ""
    output_folder: str = Field(
        default="",
        alias="outputFolder",
    )
    attach_output: bool = Field(
        default=True,
        alias="attachOutput",
    )


class AutomationDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str = ""
    category: str = "General"
    status: AutomationStatus = "draft"

    source_type: Literal[
        "report",
        "sql",
        "powershell",
        "python",
    ] = Field(alias="sourceType")

    report_id: str = Field(default="", alias="reportId")
    report_name: str = Field(default="", alias="reportName")
    sql: str = ""
    script_path: str = Field(default="", alias="scriptPath")

    output_format: Literal[
        "csv",
        "xlsx",
        "pdf",
    ] = Field(default="xlsx", alias="outputFormat")

    file_name_template: str = Field(
        default="{automation_name}_{yyyy-MM-dd}",
        alias="fileNameTemplate",
    )

    schedule: AutomationSchedule = Field(
        default_factory=AutomationSchedule,
    )
    delivery: AutomationDelivery = Field(
        default_factory=AutomationDelivery,
    )

    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    last_run_at: str | None = Field(default=None, alias="lastRunAt")
    next_run_at: str | None = Field(default=None, alias="nextRunAt")
    last_run_status: ExecutionStatus | None = Field(
        default=None,
        alias="lastRunStatus",
    )


class AutomationExecution(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    automation_id: str = Field(alias="automationId")
    automation_name: str = Field(alias="automationName")
    status: ExecutionStatus
    started_at: str = Field(alias="startedAt")
    completed_at: str | None = Field(default=None, alias="completedAt")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    row_count: int | None = Field(default=None, alias="rowCount")
    output_file_name: str = Field(default="", alias="outputFileName")
    output_file_path: str = Field(default="", alias="outputFilePath")
    message: str = ""
    error_details: str = Field(default="", alias="errorDetails")
    triggered_by: Literal[
        "schedule",
        "manual",
        "retry",
    ] = Field(alias="triggeredBy")


class RunAutomationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    automation_id: str = Field(alias="automation_id")
    automation: AutomationDefinition | None = None
    triggered_by: Literal[
        "manual",
        "retry",
        "schedule",
    ] = Field(default="manual", alias="triggered_by")


class RunAutomationResponse(BaseModel):
    status: Literal["success", "warning"]
    duration_ms: int
    row_count: int | None = None
    output_file_name: str = ""
    output_file_path: str = ""
    message: str
