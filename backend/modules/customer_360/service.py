from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .repository import customer_repository


TERMS_DESCRIPTIONS: dict[str, str] = {
    "0": "C.O.D.",
    "1": "Due on the 10th",
    "2": "30/60 Net 10th",
    "3": "30/60/90 Net 10th",
    "4": "60 Net 10th",
    "6": "Tenants due 6th",
    "7": "COD Only",
    "8": "COD Cash",
    "9": "90 Net 10th",
    "11": "90/120/150 Net 10th",
    "12": "10th No Rolling",
    "13": "6 Payments",
    "15": "60/90",
    "16": "90/120",
    "17": "30/60/90/120",
    "18": "60 Days No Rolling",
    "19": "120 Net 10th",
    "20": "30 Net 10th Roll on 26th",
    "22": "12 Monthly Payments",
    "30": "Paid by Credit Card",
    "31": "Due Next Week",
    "32": "150 Days Net 10th",
    "35": "One Day Terms",
    "40": "2% 30 Net 60",
    "777": "Intercompany",
}


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _yes(value: Any) -> bool:
    return _clean_text(value).upper() in {"Y", "YES", "1", "T", "TRUE"}


def _active(delete_code: Any) -> bool:
    code = _clean_text(delete_code).upper()
    return code in {"", "A"}


def _format_phone(value: Any, extension: Any = None) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())

    if not digits or int(digits or "0") == 0:
        return ""

    digits = digits.zfill(10)[-10:]
    formatted = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    extension_text = _clean_text(extension)
    if extension_text and extension_text != "0":
        formatted += f" ext. {extension_text}"

    return formatted


def _parse_erp_date(value: Any) -> str | None:
    raw = _clean_text(value)

    if not raw or raw == "0" * len(raw):
        return None

    for pattern in ("%Y%m%d", "%m%d%Y"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue

    return raw


def _safe_percent(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 2)


class CustomerService:
    def search(
        self,
        *,
        search: str,
        route_code: str | None,
        store_number: int | None,
        active_only: bool,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        rows = customer_repository.search_customers(
            search=search,
            route_code=route_code,
            store_number=store_number,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )

        customers: list[dict[str, Any]] = []

        for row in rows:
            balance = _number(row.get("CUBALANCE"))
            on_order = _number(row.get("CUONORDER"))
            on_order_ar = _number(row.get("CUONORDAR"))
            credit_limit = _number(row.get("CUCRLIMIT"))

            raw_on_order = round(on_order + on_order_ar, 2)
            credit_on_order = max(raw_on_order, 0.0)
            exposure = round(balance + credit_on_order, 2)

            past_due = round(
                sum(
                    _number(row.get(field))
                    for field in (
                        "CURVCPM30",
                        "CURVCPM60",
                        "CURVCPM90",
                        "CURVCPM120",
                    )
                ),
                2,
            )

            available_credit = round(credit_limit - exposure, 2)

            amount_over_limit = round(
                max(exposure - credit_limit, 0.0),
                2,
            )

            is_over_limit = (
                exposure > credit_limit
                if credit_limit > 0
                else exposure > 0
            )

            is_past_due = past_due > 0

            customers.append(
                {
                    "customer_number": int(row["CUNUMBER"]),
                    "customer_name": _clean_text(row.get("CUNAME")),
                    "dba_name": _clean_text(row.get("CUADDRESS4")),
                    "route_code": _clean_text(row.get("CUROUTECD")),
                    "store_number": _integer(row.get("CUSTORENUM")),
                    "salesman_number": _integer(row.get("CUSALESMAN")),
                    "customer_type": _clean_text(row.get("CUTYPE")),
                    "customer_class": _clean_text(row.get("CUCLASS")),
                    "active": _active(row.get("CUDELETECD")),
                    "phone": _format_phone(row.get("CUPHONE")),
                    "email": _clean_text(row.get("CUEMAIL")),
                    "address_line_1": _clean_text(row.get("CUADDRESS1")),
                    "address_line_2": _clean_text(row.get("CUADDRESS2")),
                    # MaddenCo stores locality text in the address lines; this
                    # TMCUST layout has no standalone CUCITY column. The review
                    # workspace parses city/state/ZIP from address_line_2.
                    "city": "",
                    "state": _clean_text(row.get("CUSTATE")),
                    "zip_code": _clean_text(row.get("CUZIP")),
                    "postal_code": _clean_text(row.get("CUZIP")),
                    "credit_limit": round(credit_limit, 2),
                    "balance": round(balance, 2),
                    "on_order": raw_on_order,
                    "credit_on_order": credit_on_order,
                    "exposure": exposure,
                    "available_credit": available_credit,
                    "amount_over_limit": amount_over_limit,
                    "utilization_percent": _safe_percent(
                        exposure,
                        credit_limit,
                    ),
                    "past_due_amount": past_due,
                    "is_over_limit": is_over_limit,
                    "is_past_due": is_past_due,
                }
            )

        return {
            "customers": customers,
            "count": len(customers),
            "limit": limit,
            "offset": offset,
        }

    def summary(self, customer_number: int) -> dict[str, Any] | None:
        row = customer_repository.get_customer(customer_number)

        if row is None:
            return None

        credit_limit = _number(row.get("CUCRLIMIT"))
        balance = _number(row.get("CUBALANCE"))
        on_order = _number(row.get("CUONORDER"))
        on_order_ar = _number(row.get("CUONORDAR"))

        raw_on_order = round(on_order + on_order_ar, 2)
        credit_on_order = max(raw_on_order, 0.0)
        exposure = round(balance + credit_on_order, 2)

        aging = {
            "future": _number(row.get("CURVCPMFUT")),
            "current": _number(row.get("CURVCPMCUR")),
            "days_30": _number(row.get("CURVCPM30")),
            "days_60": _number(row.get("CURVCPM60")),
            "days_90": _number(row.get("CURVCPM90")),
            "days_120": _number(row.get("CURVCPM120")),
        }
        aging["past_due"] = round(
            aging["days_30"]
            + aging["days_60"]
            + aging["days_90"]
            + aging["days_120"],
            2,
        )
        aging["total_aging"] = round(
            sum(aging.values()),
            2,
        )

        ytd_sales = _number(row.get("CUYTDSALES"))
        day_of_year = date.today().timetuple().tm_yday
        annualized_sales = (
            round((ytd_sales / day_of_year) * 365, 2)
            if day_of_year
            else 0.0
        )
        expected_credit_line = round(
            (annualized_sales / 12 * 2) / 500
        ) * 500

        terms_code = _clean_text(row.get("CUTERMS"))

        return {
            "customer_number": int(row["CUNUMBER"]),
            "customer_name": _clean_text(row.get("CUNAME")),
            "general": {
                "dba_name": _clean_text(row.get("CUADDRESS4")),
                "address_lines": [
                    value
                    for value in (
                        _clean_text(row.get("CUADDRESS1")),
                        _clean_text(row.get("CUADDRESS2")),
                        _clean_text(row.get("CUADDRESS3")),
                    )
                    if value
                ],
                "state_code": _integer(row.get("CUSTATE")),
                "zip_code": _clean_text(row.get("CUZIP")),
                "country": _clean_text(row.get("CUCOUNTRY")),
                "phone": _format_phone(
                    row.get("CUPHONE"),
                    row.get("CUPHONEXT"),
                ),
                "fax": _clean_text(row.get("CUNUMFAX")),
                "email": _clean_text(row.get("CUEMAIL")),
                "contact": _clean_text(row.get("CUCONTACT")),
                "route_code": _clean_text(row.get("CUROUTECD")),
                "store_number": _integer(row.get("CUSTORENUM")),
                "home_site": _integer(row.get("CUSITE")),
                "salesman_number": _integer(row.get("CUSALESMAN")),
                "customer_type": _clean_text(row.get("CUTYPE")),
                "customer_class": _clean_text(row.get("CUCLASS")),
                "active": _active(row.get("CUDELETECD")),
                "delete_code": _clean_text(row.get("CUDELETECD")),
            },
            "credit": {
                "credit_limit": round(credit_limit, 2),
                "balance": round(balance, 2),
                "on_order": round(on_order, 2),
                "on_order_ar": round(on_order_ar, 2),
                "raw_on_order": raw_on_order,
                "credit_on_order": credit_on_order,
                "total_exposure": exposure,
                "available_credit": round(credit_limit - exposure, 2),
                "amount_over_limit": round(
                    max(exposure - credit_limit, 0.0),
                    2,
                ),
                "is_over_limit": (
                    exposure > credit_limit
                    if credit_limit > 0
                    else exposure > 0
                ),
                "is_past_due": aging["past_due"] > 0,
                "utilization_percent": _safe_percent(
                    exposure,
                    credit_limit,
                ),
                "high_balance": _number(row.get("CUHIGHBAL")),
                "monthly_high_balance": _number(row.get("CUMTHHIBAL")),
                "average_daily_balance": _number(row.get("CURVCBLAVG")),
                "terms_code": terms_code,
                "terms_description": TERMS_DESCRIPTIONS.get(
                    terms_code,
                    "Unknown terms code",
                ),
                "credit_grade": _clean_text(row.get("CUCRGRADE")),
                "grade_code": _clean_text(row.get("CUCRCDCOD")),
                "credit_opened_date": _parse_erp_date(
                    row.get("CUCRDATOPN")
                ),
                "credit_limit_expiration": _parse_erp_date(
                    row.get("CUDTECLEXP")
                ),
                "letter_of_credit_expiration": _parse_erp_date(
                    row.get("CUDTECREXP")
                ),
            },
            "aging": aging,
            "sales": {
                "month_to_date": _number(row.get("CUMTDSALES")),
                "year_to_date": ytd_sales,
                "last_year": _number(row.get("CULYRSALES")),
                "month_to_date_discounts": _number(
                    row.get("CUMTDDISC")
                ),
                "year_to_date_discounts": _number(
                    row.get("CUYTDDISC")
                ),
                "annualized_sales": annualized_sales,
                "expected_credit_line": expected_credit_line,
            },
            "activity": {
                "last_payment_amount": _number(
                    row.get("CULASPAYAM")
                ),
                "last_payment_date": _parse_erp_date(
                    row.get("CULASPAYDT")
                ),
                "last_activity_date": _parse_erp_date(
                    row.get("CULASTACT")
                ),
                "last_statement_date": _parse_erp_date(
                    row.get("CULASTSTMT")
                ),
                "last_sale_date": _parse_erp_date(
                    row.get("CUDTELSTSL")
                ),
                "created_date": _parse_erp_date(
                    row.get("CUDTECRT")
                ),
                "created_by": _clean_text(row.get("CUUSRCRT")),
                "changed_date": _parse_erp_date(
                    row.get("CUDTECHG")
                ),
                "changed_by": _clean_text(row.get("CUUSRCHG")),
            },
            "flags": {
                "bankruptcy": _yes(row.get("CUBNKRPYYN")),
                "past_due_flag": _yes(row.get("CUEXFLAG4")),
                "finance_charges": _yes(row.get("CUFINCHGYN")),
                "checks_accepted": _yes(row.get("CUCHKACCYN")),
                "purchase_order_required": _yes(
                    row.get("CUPOREQIRE")
                ),
                "tax_exempt_code": _clean_text(
                    row.get("CUTAXEXCD")
                ),
                "fet_exempt": _yes(row.get("CUFETEXMPT")),
                "hold_statements": _yes(row.get("CUSTMNTHLD")),
                "order_changes_blocked": _yes(
                    row.get("CUEXFLAG8")
                ),
                "backorders_allowed": _yes(
                    row.get("CUEXFLAG9")
                ),
                # CUCONTRACT ("discount structure") is a nonzero/blank
                # DECIMAL flag on TMCUST, not a Y/N column - any nonzero,
                # non-null value means this customer is on a discount
                # structure and needs review accordingly.
                "discount_customer": bool(row.get("CUCONTRACT")),
                "tax_exempt_expiration": _parse_erp_date(
                    row.get("CUDTETXEXP")
                ),
            },
        }


customer_service = CustomerService()
