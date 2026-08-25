from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ReportParameterType = Literal[
    "text",
    "number",
    "date",
    "boolean",
    "select",
]

OutputFormat = Literal[
    "csv",
    "xlsx",
    "json",
]


class ReportParameterOption(BaseModel):
    label: str
    value: str


class ReportParameter(BaseModel):
    id: str
    name: str
    label: str
    type: ReportParameterType
    required: bool = False

    defaultValue: str | None = None
    placeholder: str | None = None
    options: list[ReportParameterOption] | None = None


class ReportBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    description: str = ""

    category: str = Field(
        default="General",
        min_length=1,
        max_length=100,
    )

    sql: str = Field(
        min_length=1,
    )

    parameters: list[ReportParameter] = Field(
        default_factory=list,
    )

    database: str = Field(
        default="ERP",
        min_length=1,
        max_length=100,
    )

    outputFormat: OutputFormat = "xlsx"


class ReportCreate(ReportBase):
    id: str | None = None


class ReportUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    description: str | None = None

    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    sql: str | None = Field(
        default=None,
        min_length=1,
    )

    parameters: list[ReportParameter] | None = None

    database: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    outputFormat: OutputFormat | None = None


class ReportRecord(ReportBase):
    id: str
    createdAt: datetime
    updatedAt: datetime


class ReportListResponse(BaseModel):
    items: list[ReportRecord]
    total: int