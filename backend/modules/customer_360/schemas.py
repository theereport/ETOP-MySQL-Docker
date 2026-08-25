from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CustomerSearchResult(BaseModel):
    customer_number: int
    customer_name: str
    dba_name: str
    route_code: str
    store_number: int | None
    salesman_number: int | None
    customer_type: str
    customer_class: str
    active: bool
    phone: str
    email: str
    address_line_1: str = ""
    address_line_2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    postal_code: str = ""
    credit_limit: float
    balance: float
    on_order: float
    credit_on_order: float
    exposure: float
    available_credit: float
    amount_over_limit: float
    utilization_percent: float | None
    past_due_amount: float
    is_over_limit: bool
    is_past_due: bool


class CustomerSearchResponse(BaseModel):
    customers: list[CustomerSearchResult]
    count: int
    limit: int
    offset: int


class CustomerSummaryResponse(BaseModel):
    customer_number: int
    customer_name: str
    general: dict[str, Any]
    credit: dict[str, Any]
    aging: dict[str, Any]
    sales: dict[str, Any]
    activity: dict[str, Any]
    flags: dict[str, Any]
