import unittest

from customer_match_service import (
    CustomerMatchInput,
    exact_phone_matches,
    exact_phone_postal_matches,
    normalize_invoice,
    rank_customer_matches,
)


CUSTOMERS = [
    {
        "customer_number": "220374",
        "customer_name": "Hansen Tire and Truck Repair LLC",
        "phone": "(402) 721-1188",
        "address_line_1": "1590 Morningside Road",
        "city": "Fremont",
        "state": "NE",
        "postal_code": "68025",
    },
    {
        "customer_number": "991122",
        "customer_name": "Hansen Tire LLC",
        "phone": "(402) 555-9000",
        "address_line_1": "44 Main Street",
        "city": "Fremont",
        "state": "NE",
        "postal_code": "68025",
    },
]


def test_invoice_owner_has_first_priority() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            invoice_numbers=("431051670",),
            customer_name="Hansen Tire",
        ),
        {"431051670": {"220374"}},
    )

    assert result["auto_select"] is True
    assert result["recommended_customer"]["customer_number"] == "220374"
    assert result["recommended_customer"]["match_type"] == "invoice"


def test_invoice_owner_conflict_cannot_be_broken_by_score_lead() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            invoice_numbers=(
                "431051670",
                "431051671",
                "431051672",
                "431051673",
            ),
            phone="402-721-1188",
            address_line_1="1590 Morningside Rd.",
            postal_code="68025",
        ),
        {
            "431051670": {"220374"},
            "431051671": {"220374"},
            "431051672": {"220374"},
            "431051673": {"991122"},
        },
    )

    assert result["invoice_owner_conflict"] is True
    assert result["invoice_owner_candidates"] == ["220374", "991122"]
    assert result["auto_select"] is False
    assert result["recommended_customer"] is None


def test_phone_address_and_zip_can_select_without_customer_number() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            phone="402-721-1188",
            address_line_1="1590 Morningside Rd.",
            city="Fremont",
            state="NE",
            postal_code="68025",
            customer_name="Hansen Tire and Truck Repair",
        ),
        contact_candidate_complete=True,
    )

    assert result["auto_select"] is True
    assert result["recommended_customer"]["customer_number"] == "220374"
    assert result["recommended_customer"]["confidence"] == 1.0
    assert result["selected_basis"] == "exact_phone_and_zip"


def test_phone_without_matching_zip_never_auto_selects() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            phone="4027211188",
            postal_code="99999-1234",
        ),
    )

    assert result["auto_select"] is False
    assert result["recommended_customer"] is None


def test_one_complete_exact_phone_owner_can_select_without_zip() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(phone="4027211188"),
        contact_candidate_complete=True,
    )

    assert result["exact_phone_match_count"] == 1
    assert result["auto_select"] is True
    assert result["recommended_customer"]["customer_number"] == "220374"
    assert result["recommended_customer"]["confidence"] == 0.99
    assert result["selected_basis"] == "unique_exact_phone"
    assert result["failed_selection_gates"] == []


def test_reported_unique_phone_with_contact_support_selects() -> None:
    unique_phone_customer = {
        "customer_number": "490000",
        "customer_name": "EXAMPLE VALLEY FARMS",
        "phone": "3085551504",
        "address_line_1": "204 EXAMPLE AVE",
        "city": "EXAMPLEVILLE",
        "state": "NE",
        "postal_code": "68123",
    }
    result = rank_customer_matches(
        [unique_phone_customer, *CUSTOMERS],
        CustomerMatchInput(
            phone="(308) 555-1504",
            address_line_1="204 Example Avenue",
            city="Exampleville",
            state="NE",
            postal_code="68123",
            customer_name="Example Valley Farms LLC",
        ),
        contact_candidate_complete=True,
    )

    assert result["auto_select"] is True
    assert result["recommended_customer"]["customer_number"] == "490000"
    assert result["selected_basis"] == "exact_phone_and_zip"


def test_phone_and_first_five_zip_digits_match_exactly() -> None:
    matches = exact_phone_postal_matches(
        CUSTOMERS,
        CustomerMatchInput(
            phone="(402) 721-1188",
            postal_code="68025-7711",
        ),
    )

    assert [customer["customer_number"] for customer in matches] == [
        "220374"
    ]


def test_duplicate_phone_and_zip_remains_ambiguous() -> None:
    duplicate = {
        **CUSTOMERS[0],
        "customer_number": "220375",
        "customer_name": "Hansen Tire Second Account",
    }
    result = rank_customer_matches(
        [*CUSTOMERS, duplicate],
        CustomerMatchInput(
            phone="4027211188",
            postal_code="68025",
        ),
        contact_candidate_complete=True,
    )

    assert result["auto_select"] is False
    assert result["recommended_customer"] is None


def test_duplicate_phone_without_zip_remains_ambiguous() -> None:
    duplicate = {
        **CUSTOMERS[0],
        "customer_number": "220375",
        "postal_code": "68102",
    }
    result = rank_customer_matches(
        [*CUSTOMERS, duplicate],
        CustomerMatchInput(phone="4027211188"),
        contact_candidate_complete=True,
    )

    assert result["exact_phone_match_count"] == 2
    assert result["auto_select"] is False
    assert result["recommended_customer"] is None
    assert "duplicate_exact_phone" in result["failed_selection_gates"]


def test_duplicate_phone_zip_cannot_be_broken_by_address_or_name() -> None:
    duplicate = {
        **CUSTOMERS[0],
        "customer_number": "220375",
        "customer_name": "Different Weak Name",
        "address_line_1": "900 Different Road",
    }
    result = rank_customer_matches(
        [*CUSTOMERS, duplicate],
        CustomerMatchInput(
            phone="4027211188",
            postal_code="68025",
            address_line_1="1590 Morningside Road",
            customer_name="Hansen Tire and Truck Repair LLC",
        ),
        contact_candidate_complete=True,
    )

    assert result["exact_phone_postal_match_count"] == 2
    assert result["auto_select"] is False
    assert result["recommended_customer"] is None


def test_incomplete_phone_zip_candidate_universe_never_selects() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            phone="4027211188",
            postal_code="68025",
        ),
        contact_candidate_complete=False,
    )

    assert result["exact_phone_postal_match_count"] == 1
    assert result["auto_select"] is False
    assert result["recommended_customer"] is None


def test_incomplete_unique_phone_candidate_universe_never_selects() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(phone="4027211188"),
        contact_candidate_complete=False,
    )

    assert result["exact_phone_match_count"] == 1
    assert result["auto_select"] is False
    assert result["recommended_customer"] is None
    assert "phone_candidate_set_incomplete" in result["failed_selection_gates"]


def test_partial_invoice_owner_evidence_never_selects_known_owner() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            invoice_numbers=("431051670", "431051671"),
        ),
        {
            "431051670": {"220374"},
            "431051671": set(),
        },
    )

    assert result["partial_invoice_owner_evidence"] is True
    assert result["unresolved_invoice_owner_count"] == 1
    assert result["auto_select"] is False
    assert result["recommended_customer"] is None


def test_address_and_zip_without_phone_is_supporting_only() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            address_line_1="1590 Morningside Road",
            postal_code="68025",
            customer_name="Hansen Tire and Truck Repair LLC",
        ),
        contact_candidate_complete=True,
    )

    assert result["candidates"][0]["match_type"] == "address_and_zip"
    assert result["auto_select"] is False
    assert result["recommended_customer"] is None


def test_complete_unique_exact_address_and_zip_can_select() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            address_line_1="1590 Morningside Rd.",
            postal_code="68025-7711",
            customer_name="Weak OCR Name",
        ),
        address_candidate_complete=True,
    )

    assert result["exact_address_postal_match_count"] == 1
    assert result["auto_select"] is True
    assert result["recommended_customer"]["customer_number"] == "220374"
    assert result["selected_basis"] == "exact_address_and_zip"
    assert result["recommended_customer"]["confidence"] == 1.0


def test_incomplete_address_candidate_universe_never_selects() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            address_line_1="1590 Morningside Road",
            postal_code="68025",
        ),
        address_candidate_complete=False,
    )

    assert result["auto_select"] is False
    assert "address_candidate_set_incomplete" in result[
        "failed_selection_gates"
    ]


def test_exact_address_and_zip_cannot_override_phone_conflict() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            phone="4025559000",
            address_line_1="1590 Morningside Road",
            postal_code="68025",
        ),
        contact_candidate_complete=True,
        address_candidate_complete=True,
    )

    # The supplied phone belongs to the other ERP customer, so street/ZIP
    # cannot silently select 220374.
    assert result["recommended_customer"]["customer_number"] == "991122"
    assert result["selected_basis"] == "exact_phone_and_zip"
    assert "address_phone_conflict" in result["failed_selection_gates"]


def test_seven_digit_phone_and_zip_is_not_exact_contact_evidence() -> None:
    matches = exact_phone_postal_matches(
        CUSTOMERS,
        CustomerMatchInput(phone="7211188", postal_code="68025"),
    )

    assert matches == []


def test_leading_country_code_is_normalized_for_exact_contact() -> None:
    matches = exact_phone_postal_matches(
        CUSTOMERS,
        CustomerMatchInput(phone="1-402-721-1188", postal_code="68025"),
    )

    assert [customer["customer_number"] for customer in matches] == [
        "220374"
    ]


def test_leading_country_code_is_normalized_for_exact_phone() -> None:
    matches = exact_phone_matches(
        CUSTOMERS,
        CustomerMatchInput(phone="1-402-721-1188"),
    )

    assert [customer["customer_number"] for customer in matches] == [
        "220374"
    ]


def test_unique_phone_never_overrides_complete_invoice_owner() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(
            invoice_numbers=("431051670",),
            phone="4025559000",
        ),
        {"431051670": {"220374"}},
        contact_candidate_complete=True,
    )

    assert result["auto_select"] is True
    assert result["recommended_customer"]["customer_number"] == "220374"
    assert result["selected_basis"] == "invoice"


def test_phone_extension_is_not_exact_contact_evidence() -> None:
    matches = exact_phone_postal_matches(
        CUSTOMERS,
        CustomerMatchInput(
            phone="402-721-1188 ext 42",
            postal_code="68025",
        ),
    )

    assert matches == []


def test_partial_zip_is_not_exact_contact_evidence() -> None:
    matches = exact_phone_postal_matches(
        CUSTOMERS,
        CustomerMatchInput(phone="402-721-1188", postal_code="6802"),
    )

    assert matches == []


def test_name_alone_never_auto_selects() -> None:
    result = rank_customer_matches(
        CUSTOMERS,
        CustomerMatchInput(customer_name="Hansen Tire"),
    )

    assert result["auto_select"] is False
    assert result["recommended_customer"] is None
    assert len(result["candidates"]) >= 1


def test_invoice_numbers_must_be_eight_or_nine_digits() -> None:
    assert normalize_invoice("43051670") == "43051670"
    assert normalize_invoice("43-051-670") == "43051670"
    assert normalize_invoice("431051670") == "431051670"
    assert normalize_invoice("55-048-5932") == "550485932"
    assert normalize_invoice("1234567") == ""
    assert normalize_invoice("1234567890") == ""
    assert normalize_invoice("12345678901") == ""
    assert normalize_invoice("9999999999") == ""


class CustomerMatchServiceUnittest(unittest.TestCase):
    """Expose the existing assertions to the release's unittest gate."""

    def test_invoice_owner_has_first_priority(self) -> None:
        test_invoice_owner_has_first_priority()

    def test_invoice_owner_conflict_cannot_be_broken_by_score_lead(
        self,
    ) -> None:
        test_invoice_owner_conflict_cannot_be_broken_by_score_lead()

    def test_phone_address_and_zip_can_select_without_customer_number(
        self,
    ) -> None:
        test_phone_address_and_zip_can_select_without_customer_number()

    def test_name_alone_never_auto_selects(self) -> None:
        test_name_alone_never_auto_selects()

    def test_phone_without_matching_zip_never_auto_selects(self) -> None:
        test_phone_without_matching_zip_never_auto_selects()

    def test_one_complete_exact_phone_owner_can_select_without_zip(
        self,
    ) -> None:
        test_one_complete_exact_phone_owner_can_select_without_zip()

    def test_reported_unique_phone_with_contact_support_selects(
        self,
    ) -> None:
        test_reported_unique_phone_with_contact_support_selects()

    def test_phone_and_first_five_zip_digits_match_exactly(self) -> None:
        test_phone_and_first_five_zip_digits_match_exactly()

    def test_duplicate_phone_and_zip_remains_ambiguous(self) -> None:
        test_duplicate_phone_and_zip_remains_ambiguous()

    def test_duplicate_phone_without_zip_remains_ambiguous(self) -> None:
        test_duplicate_phone_without_zip_remains_ambiguous()

    def test_duplicate_phone_zip_cannot_be_broken_by_address_or_name(
        self,
    ) -> None:
        test_duplicate_phone_zip_cannot_be_broken_by_address_or_name()

    def test_incomplete_phone_zip_candidate_universe_never_selects(
        self,
    ) -> None:
        test_incomplete_phone_zip_candidate_universe_never_selects()

    def test_incomplete_unique_phone_candidate_universe_never_selects(
        self,
    ) -> None:
        test_incomplete_unique_phone_candidate_universe_never_selects()

    def test_partial_invoice_owner_evidence_never_selects_known_owner(
        self,
    ) -> None:
        test_partial_invoice_owner_evidence_never_selects_known_owner()

    def test_address_and_zip_without_phone_is_supporting_only(self) -> None:
        test_address_and_zip_without_phone_is_supporting_only()

    def test_complete_unique_exact_address_and_zip_can_select(self) -> None:
        test_complete_unique_exact_address_and_zip_can_select()

    def test_incomplete_address_candidate_universe_never_selects(self) -> None:
        test_incomplete_address_candidate_universe_never_selects()

    def test_exact_address_and_zip_cannot_override_phone_conflict(self) -> None:
        test_exact_address_and_zip_cannot_override_phone_conflict()

    def test_seven_digit_phone_and_zip_is_not_exact_contact_evidence(
        self,
    ) -> None:
        test_seven_digit_phone_and_zip_is_not_exact_contact_evidence()

    def test_leading_country_code_is_normalized_for_exact_contact(
        self,
    ) -> None:
        test_leading_country_code_is_normalized_for_exact_contact()

    def test_leading_country_code_is_normalized_for_exact_phone(
        self,
    ) -> None:
        test_leading_country_code_is_normalized_for_exact_phone()

    def test_unique_phone_never_overrides_complete_invoice_owner(
        self,
    ) -> None:
        test_unique_phone_never_overrides_complete_invoice_owner()

    def test_phone_extension_is_not_exact_contact_evidence(self) -> None:
        test_phone_extension_is_not_exact_contact_evidence()

    def test_partial_zip_is_not_exact_contact_evidence(self) -> None:
        test_partial_zip_is_not_exact_contact_evidence()

    def test_invoice_numbers_must_be_eight_or_nine_digits(self) -> None:
        test_invoice_numbers_must_be_eight_or_nine_digits()
