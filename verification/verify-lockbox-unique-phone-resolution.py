"""Deterministic Increment 3K unique-phone contract verification.

Uses only synthetic values. It performs no network, database, document,
review, approval, export, posting, or ERP operation.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from customer_match_service import CustomerMatchInput, rank_customer_matches


PRIMARY = {
    "customer_number": "490000",
    "customer_name": "EXAMPLE VALLEY FARMS",
    "phone": "3085551504",
    "address_line_1": "204 EXAMPLE AVE",
    "city": "EXAMPLEVILLE",
    "state": "NE",
    "postal_code": "68123",
}
OTHER = {
    "customer_number": "490001",
    "customer_name": "OTHER EXAMPLE CUSTOMER",
    "phone": "3085559999",
    "address_line_1": "1 OTHER ROAD",
    "city": "EXAMPLEVILLE",
    "state": "NE",
    "postal_code": "68123",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    resolved = rank_customer_matches(
        [PRIMARY, OTHER],
        CustomerMatchInput(
            phone="(308) 555-1504",
            customer_name="Example Valley Farms",
        ),
        contact_candidate_complete=True,
    )
    require(resolved["auto_select"], "Unique exact phone did not select.")
    require(
        resolved["recommended_customer"]["customer_number"] == "490000",
        "Unique exact phone selected the wrong synthetic customer.",
    )
    require(
        resolved["selected_basis"] == "unique_exact_phone",
        "Unique exact phone did not retain its governed basis.",
    )

    zip_conflict = rank_customer_matches(
        [PRIMARY, OTHER],
        CustomerMatchInput(phone="3085551504", postal_code="99999"),
        contact_candidate_complete=True,
    )
    require(
        not zip_conflict["auto_select"],
        "A conflicting supplied ZIP did not block phone selection.",
    )

    duplicate_phone = {**PRIMARY, "customer_number": "490002"}
    duplicated = rank_customer_matches(
        [PRIMARY, duplicate_phone, OTHER],
        CustomerMatchInput(phone="3085551504"),
        contact_candidate_complete=True,
    )
    require(
        not duplicated["auto_select"],
        "A duplicate exact phone did not remain ambiguous.",
    )

    incomplete = rank_customer_matches(
        [PRIMARY, OTHER],
        CustomerMatchInput(phone="3085551504"),
        contact_candidate_complete=False,
    )
    require(
        not incomplete["auto_select"],
        "An incomplete phone-candidate universe selected a customer.",
    )

    invoice_first = rank_customer_matches(
        [PRIMARY, OTHER],
        CustomerMatchInput(
            invoice_numbers=("431051670",),
            phone="3085559999",
        ),
        {"431051670": {"490000"}},
        contact_candidate_complete=True,
    )
    require(
        invoice_first["recommended_customer"]["customer_number"]
        == "490000",
        "Unique phone overrode complete invoice ownership.",
    )
    require(
        invoice_first["selected_basis"] == "invoice",
        "Invoice ownership did not remain first priority.",
    )

    print("Increment 3K unique-phone contract passed.")
    print("Synthetic unique phone resolved one customer.")
    print("ZIP conflict, duplicate phone, and incomplete reads failed closed.")
    print("Complete invoice ownership remained first priority.")
    print("No operational data or ERP write path was used.")


if __name__ == "__main__":
    main()
