from __future__ import annotations

from sqlalchemy import create_engine

from modules.credit_risk.potential_customers import (
    PotentialCustomerRepository,
    PotentialCustomerService,
    classify_km_credit_application,
    default_km_setup_values,
    parse_km_credit_application,
    validate_tmcust_readiness,
)

PAGE1 = """K&M TIRE CREDIT APPLICATION
Legal Business Name: Cheap Buffalo Towing LLC
Trade Name (DBA):
Type Of Business: C-Corp S-Corp (=) LLC Partnership Proprietorship
Shipping Address: 878 South Division Street
City: Buffalo State: NY Zip Code: 14210
Billing Address: 4394 Bailey Ave
City: Buffalo State: NY Zip Code: 14226
Business Phone: 716-2350542 Primary Language:
Cell Phone: 716-2350542 County:
Email Address: cheapbuffalotowing@gmail.com Fed Tax ID#:
Manager's Name: Vasanthan Year Started Business:
Accts. Payable Contact; Vasanthan Purchase Order Required: Yes No
Vasanthan Sitampalam, 4394 Bailey Ave Buffalo NY 14226, 02/04/1975
Reason For Claiming Exemption: for resale tires
06/16/2026
Sales tax exemption/State Sales Tax ID/Vendors Sales Tax License #: 83-3301954
Would you like to sign up for Weblink 2.0, K&M Tire’s Online Ordering System? Yes No
If yes, please supply email address: Cheapbuffalotowing@gmail.com
Would you like to sign up to receive your statements via email? Yes No
If yes, please supply email address: Cheapbuffalotowing@gmail.com
vasanthan sitampalam 06/16/2026
Salesperson Printed Name Date
"""
PAGE2 = """Trade References, Current, and Previous:
Estimated Annual Purchases From K&M Tire? (in dollars) 10000
Number of Locations? 1 Estimated Annual Purchases From K&M Tire? (in dollars) 10000
Owners, Partners, or Officers of the Corporation must sign below:
Vasanthan Sitampalam 06/16/2026
Printed Name Signature Date
The undersigned personal guarantor, recognizing that his/her individual credit history may be a necessary factor
Vasanthan Sitampalam
Printed Name Signature Witness *1 Signature
"""


def test_classifier_and_parser_extract_governed_form_fields():
    classified = classify_km_credit_application("test app #1.pdf", PAGE1 + PAGE2)
    assert classified["document_type"] == "km_credit_application"
    parsed_result = parse_km_credit_application([PAGE1, PAGE2])
    parsed = parsed_result["fields"]
    evidence = parsed_result["evidence"]
    assert parsed["legal_business_name"] == "Cheap Buffalo Towing LLC"
    assert parsed["type_of_business"] == "LLC"
    assert parsed["shipping_address"] == {"street": "878 South Division Street", "city": "Buffalo", "state": "NY", "zip": "14210"}
    assert parsed["billing_address"] == {"street": "4394 Bailey Ave", "city": "Buffalo", "state": "NY", "zip": "14226"}
    assert parsed["email_address"] == "cheapbuffalotowing@gmail.com"
    assert parsed["sales_tax_id"] == "83-3301954"
    assert parsed["sales_tax_exempt"] is True
    assert parsed["primary_language"] == ""
    assert parsed["county"] == ""
    assert parsed["federal_tax_id"] == ""
    assert parsed["year_started_business"] == ""
    assert parsed["purchase_order_required"] is None
    assert evidence["primary_language"]["status"] == "blank"
    assert evidence["county"]["status"] == "blank"
    assert evidence["federal_tax_id"]["status"] == "blank"
    assert evidence["year_started_business"]["status"] == "blank"
    assert evidence["purchase_order_required"]["status"] == "blank"
    assert evidence["sales_tax_exempt"]["status"] == "parsed"
    assert parsed["number_of_locations"] == 1
    assert parsed["estimated_annual_purchases"] == 10000.0
    assert parsed["terms_signature_present"] is True



def test_fixed_header_schema_distinguishes_blank_from_not_detected():
    parsed = parse_km_credit_application([PAGE1, PAGE2])
    required_header_keys = {
        "legal_business_name", "trade_name", "type_of_business",
        "shipping_address", "billing_address", "business_phone",
        "primary_language", "cell_phone", "county", "email_address",
        "federal_tax_id", "manager_name", "year_started_business",
        "accounts_payable_contact", "purchase_order_required",
    }
    assert required_header_keys.issubset(parsed["fields"])
    assert parsed["evidence"]["trade_name"]["status"] == "blank"

    without_county_label = PAGE1.replace(" County:", "")
    reparsed = parse_km_credit_application([without_county_label, PAGE2])
    assert "county" in reparsed["fields"]
    assert reparsed["fields"]["county"] == ""
    assert reparsed["evidence"]["county"]["status"] == "not_detected"


def test_blank_yes_no_is_never_coerced_to_no():
    page1 = PAGE1.replace("Reason For Claiming Exemption: for resale tires", "Reason For Claiming Exemption:")
    page1 = page1.replace("Sales tax exemption/State Sales Tax ID/Vendors Sales Tax License #: 83-3301954", "Sales tax exemption/State Sales Tax ID/Vendors Sales Tax License #:")
    parsed = parse_km_credit_application([page1, PAGE2])
    assert parsed["fields"]["purchase_order_required"] is None
    assert parsed["fields"]["sales_tax_exempt"] is None
    assert parsed["evidence"]["purchase_order_required"]["status"] == "blank"
    assert parsed["evidence"]["sales_tax_exempt"]["status"] == "blank"

def test_tmcust_mapping_flags_length_and_governed_translation():
    checks = validate_tmcust_readiness({
        "legal_business_name": "A" * 26,
        "type_of_business": "LLC",
        "business_phone": "716-235-0542",
    })
    by_field = {item["field"]: item for item in checks}
    assert by_field["legal_business_name"]["status"] == "needs_km_value"
    assert by_field["type_of_business"]["status"] == "translation_required"
    assert by_field["business_phone"]["status"] == "ready"
    assert by_field["route_code"]["status"] == "unassigned"


def test_repository_persists_potential_customer_and_never_enables_erp_write(tmp_path, monkeypatch):
    db = tmp_path / "potential.db"
    engine = create_engine(f"sqlite:///{db}")
    try:
        repo = PotentialCustomerRepository(engine=engine)
        service = PotentialCustomerService(repo)
        monkeypatch.setattr(service, "find_existing_matches", lambda fields: [])
        record = {
            "potential_customer_id": "PCA-TEST",
            "status": "needs_review",
            "source_file_name": "application.pdf",
            "source_sha256": "a" * 64,
            "parser_name": "km-credit-application",
            "parser_version": "r72.1",
            "classifier_confidence": 1.0,
            "received_at": "2026-08-21T17:00:00+00:00",
            "updated_at": "2026-08-21T17:00:00+00:00",
            "fields": {"legal_business_name": "Test LLC"},
            "evidence": {},
        }
        saved = repo.create(record)
        enriched = service.enrich(saved)
        assert enriched["erp_write"] is False
        assert enriched["governance"]["automatic_customer_creation"] is False
        assert repo.get("PCA-TEST")["fields"]["legal_business_name"] == "Test LLC"
    finally:
        engine.dispose()

def test_new_applications_are_seeded_with_km_setup_defaults(tmp_path, monkeypatch):
    db = tmp_path / "potential-defaults.db"
    engine = create_engine(f"sqlite:///{db}")
    try:
        repo = PotentialCustomerRepository(engine=engine)
        service = PotentialCustomerService(repo)
        monkeypatch.setattr(service, "find_existing_matches", lambda fields: [])
        record = {
            "potential_customer_id": "PCA-DEFAULTS",
            "status": "needs_review",
            "source_file_name": "application.pdf",
            "source_sha256": "c" * 64,
            "parser_name": "km-credit-application",
            "parser_version": "r72.1",
            "classifier_confidence": 1.0,
            "received_at": "2026-08-21T17:00:00+00:00",
            "updated_at": "2026-08-21T17:00:00+00:00",
            "fields": {"legal_business_name": "Test LLC"},
            "evidence": {},
        }
        saved = repo.create(record)
        enriched = service.enrich(saved)
        for field, value in default_km_setup_values().items():
            assert enriched["km_setup"][field] == value
        # Fields that genuinely vary per customer are never defaulted.
        for field in ("customer_number", "route_code", "customer_type", "site", "bill_to_customer"):
            assert field not in enriched["km_setup"]
    finally:
        engine.dispose()


def test_km_setup_defaults_are_overridable_via_env(monkeypatch):
    monkeypatch.setenv("ETOP_R72_DEFAULT_CREDIT_LIMIT", "25000")
    monkeypatch.setenv("ETOP_R72_DEFAULT_STORE_NUMBER", "2")
    values = default_km_setup_values()
    assert values["credit_limit"] == "25000"
    assert values["store_number"] == "2"
    # Untouched fields still fall back to the standard defaults.
    assert values["price_code"] == "2"
    assert values["terms_code"] == "7"


def test_document_and_human_corrections_persist(tmp_path, monkeypatch):
    db = tmp_path / "potential-doc.db"
    engine = create_engine(f"sqlite:///{db}")
    try:
        repo = PotentialCustomerRepository(engine=engine)
        service = PotentialCustomerService(repo)
        monkeypatch.setattr(service, "find_existing_matches", lambda fields: [])
        record = {
            "potential_customer_id": "PCA-DOC",
            "status": "needs_review",
            "source_file_name": "application.pdf",
            "source_sha256": "b" * 64,
            "parser_name": "km-credit-application",
            "parser_version": "r72.1",
            "classifier_confidence": 1.0,
            "received_at": "2026-08-21T17:00:00+00:00",
            "updated_at": "2026-08-21T17:00:00+00:00",
            "fields": {
                "legal_business_name": "OCR Name",
                "business_phone": "",
                "shipping_address": {"street": "", "city": "", "state": "", "zip": ""},
                "billing_address": {"street": "", "city": "", "state": "", "zip": ""},
            },
            "evidence": {},
        }
        repo.create(record, b"%PDF-test")
        name, content, digest = repo.get_document("PCA-DOC")
        assert name == "application.pdf"
        assert content == b"%PDF-test"
        assert digest == "b" * 64
        updated = service.update_review("PCA-DOC", {
            "status": "application_complete",
            "field_updates": {
                "legal_business_name": "Verified Name",
                "shipping_address": {"street": "1 Main St", "city": "Delphos", "state": "OH", "zip": "45833"},
            },
            "km_setup": {"route_code": "94", "terms_code": "1"},
        })
        assert updated["fields"]["legal_business_name"] == "Verified Name"
        assert updated["evidence"]["legal_business_name"]["status"] == "human_verified"
        assert updated["fields"]["shipping_address"]["city"] == "Delphos"
        assert updated["evidence"]["shipping_address"]["status"] == "human_verified"
        assert updated["km_setup"]["route_code"] == "94"
        assert updated["status"] == "application_complete"
        assert updated["erp_write"] is False
    finally:
        engine.dispose()
