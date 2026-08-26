from __future__ import annotations

import unittest
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if "fastapi" not in sys.modules:
    fastapi = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.prefix = kwargs.get("prefix", "")
            self.routes = []

        def _route(self, path, *args, **kwargs):
            def decorator(function):
                self.routes.append(
                    SimpleNamespace(
                        path=self.prefix + path,
                        endpoint=function,
                    )
                )
                return function

            return decorator

        get = _route
        post = _route
        put = _route

        def include_router(self, router):
            self.routes.append(SimpleNamespace(router=router))

        def openapi(self):
            paths = {}

            def collect(candidate):
                nested_router = getattr(candidate, "router", None)
                if nested_router is not None:
                    for nested in getattr(nested_router, "routes", []):
                        collect(nested)
                    return
                path = getattr(candidate, "path", "")
                if path:
                    paths.setdefault(path, {})

            for route in self.routes:
                collect(route)
            return {"paths": paths}

    fastapi.APIRouter = APIRouter
    fastapi.FastAPI = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.File = lambda default=None, *args, **kwargs: default
    fastapi.Query = lambda default=None, *args, **kwargs: default
    fastapi.UploadFile = type("UploadFile", (), {})
    sys.modules["fastapi"] = fastapi

if "fastapi.responses" not in sys.modules:
    responses = types.ModuleType("fastapi.responses")
    responses.FileResponse = SimpleNamespace
    sys.modules["fastapi.responses"] = responses

if "core.database" not in sys.modules:
    core_database = types.ModuleType("core.database")
    core_database.madden_database = SimpleNamespace()
    sys.modules["core.database"] = core_database

if "pytesseract" not in sys.modules:
    pytesseract = types.ModuleType("pytesseract")
    pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="")
    pytesseract.Output = SimpleNamespace(DICT="dict")
    pytesseract.image_to_string = lambda *args, **kwargs: ""
    pytesseract.image_to_data = lambda *args, **kwargs: {
        "text": [],
        "conf": [],
    }
    sys.modules["pytesseract"] = pytesseract

from modules.document_intelligence.pnc_lockbox_parser import (
    EXTRACTION_VERSION,
    Transaction,
    _extract_page_remittance_evidence,
    _extract_transaction_customer_identity,
    _ocr_visual_row_text,
    _transaction_from_page,
)
from modules.document_intelligence.page_classifier import classify_page
from modules.document_intelligence.pnc_lockbox_contract import (
    PNC_LOCKBOX_HEADER_RULE_VERSION,
)
from modules.document_intelligence.classifiers.rule_based import (
    classify_document,
)
from modules.document_intelligence.remittance_understanding import (
    AllocationCandidate,
    extract_km_statement_customer_directives,
    extract_remittance_evidence,
)
from modules.document_intelligence.check_understanding import (
    extract_customer_identity,
)
from modules.document_intelligence.resolution.payer_parser import (
    check_customer_account_directives,
    check_for_customer_directives,
    explicit_customer_account_directives,
)
from modules.document_intelligence.vision_models import (
    CustomerIdentity,
    Region,
    TextLine,
)


class _FakeRect:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class _FakePage:
    def __init__(
        self,
        embedded_text: str,
        *,
        image_ratio: float = 0.0,
    ) -> None:
        self._embedded_text = embedded_text
        self.rect = _FakeRect(100.0, 100.0)
        self._image_ratio = image_ratio

    def get_text(self, mode: str) -> str:
        assert mode == "text"
        return self._embedded_text

    def get_images(self, *, full: bool = False):
        return [(1,)] if full and self._image_ratio else []

    def get_image_rects(self, xref: int):
        if not self._image_ratio:
            return []
        return [_FakeRect(100.0, self._image_ratio * 100.0)]


class PncLockboxParserTest(unittest.TestCase):
    def test_extraction_version_is_explicit(self) -> None:
        self.assertEqual(
            EXTRACTION_VERSION,
            "pnc-lockbox-parser@0.7.0-r75.1",
        )

    def test_pnc_site_header_rule_version_is_explicit(self) -> None:
        self.assertEqual(
            PNC_LOCKBOX_HEADER_RULE_VERSION,
            "pnc-lockbox-site-header@0.7.0-wave2-increment3y",
        )

    def test_dallas_transaction_header_is_planned_for_processing(self) -> None:
        header = "\n".join(
            (
                "Transaction Information G-9000001 DAL-640045 2026/08/04",
                "Reported Amount $ 1,234.56",
                "Check Number 012345",
            )
        )

        transaction = _transaction_from_page(header, 7)

        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.transaction_id, "G-9000001")
        self.assertEqual(transaction.lockbox, "DAL-640045")
        self.assertEqual(transaction.date, "2026/08/04")
        self.assertEqual(transaction.check_amount, 1234.56)
        self.assertEqual(classify_page(header), "transaction")

    def test_dallas_site_code_supports_document_classification(self) -> None:
        classification = classify_document(
            "sample-dallas-lockbox.pdf",
            "\n".join(
                (
                    "PNC",
                    "Transaction Information G-9000001 DAL-640045 2026/08/04",
                )
            ),
        )

        self.assertEqual(classification["document_type"], "pnc_lockbox")
        self.assertIn(
            "Found PNC lockbox identifier (AAA-######)",
            classification["evidence"],
        )

    def test_explicit_apply_to_customer_account_is_preserved(self) -> None:
        matches = explicit_customer_account_directives(
            "Apply this payment to customer account: 700001"
        )

        self.assertEqual(
            matches,
            [{
                "customer_number": "700001",
                "evidence_text": (
                    "Apply this payment to customer account: 700001"
                ),
            }],
        )

    def test_generic_bank_account_label_is_not_customer_evidence(self) -> None:
        matches = explicit_customer_account_directives(
            "Account Number: 123456789\nRouting Number: 021000021"
        )

        self.assertEqual(matches, [])

    def test_check_fallback_accepts_bare_six_digit_account_label(self) -> None:
        matches = check_customer_account_directives(
            "Account: 650426\nRedco Tire Inc."
        )

        self.assertEqual(
            [item["customer_number"] for item in matches],
            ["650426"],
        )

    def test_check_fallback_accepts_bare_seven_digit_account_label(
        self,
    ) -> None:
        # MaddenCo customer numbers (TMCUST.CUNUMBER) are decimal(7,0) — a
        # real customer number can be seven digits, not only six.
        matches = check_customer_account_directives(
            "Account: 1000045\nRedco Tire Inc."
        )

        self.assertEqual(
            [item["customer_number"] for item in matches],
            ["1000045"],
        )

    def test_check_fallback_rejects_out_of_range_bare_account_digit_counts(
        self,
    ) -> None:
        self.assertEqual(
            check_customer_account_directives("Account: 65042"),  # 5 digits
            [],
        )
        self.assertEqual(
            check_customer_account_directives(
                "Account: 123456789"  # 9 digits, e.g. a routing number
            ),
            [],
        )

    def test_check_fallback_tolerates_dropped_separator_and_memo_acct(
        self,
    ) -> None:
        matches = check_customer_account_directives(
            "\n".join(
                (
                    "Account 770939",
                    "EFFINGHAM TIRE AND AUTO CENTER",
                    "MEMO: Acct # 770939",
                )
            )
        )

        self.assertEqual(
            [item["customer_number"] for item in matches],
            ["770939"],
        )

    def test_check_fallback_rejects_bank_account_context(self) -> None:
        matches = check_customer_account_directives(
            "Bank Account: 650426\nRouting Number: 021000021"
        )

        self.assertEqual(matches, [])

        memo_matches = check_customer_account_directives(
            "Checking Acct # 770939\nRouting Number: 009457753"
        )

        self.assertEqual(memo_matches, [])

    def test_check_for_line_accepts_supplied_customer_number_layouts(
        self,
    ) -> None:
        examples = {
            "For 331002": "331002",
            "FOR Tire Sales Acct# 726882": "726882",
            "FOR 180645": "180645",
            "For 370036": "370036",
            "F0R 3 3 1 0 0 2": "331002",
            "ROR 370036": "370036",
            # MaddenCo customer numbers (TMCUST.CUNUMBER) are decimal(7,0) —
            # a real customer number can be seven digits, not only six.
            "For 1000045": "1000045",
            "FOR Tire Sales Acct# 9876543": "9876543",
        }

        for text, expected in examples.items():
            with self.subTest(text=text):
                matches = check_for_customer_directives(text)
                self.assertEqual(
                    [item["customer_number"] for item in matches],
                    [expected],
                )

    def test_check_for_line_accepts_memo_label(self) -> None:
        examples = {
            "Memo 331002": "331002",
            "MEMO Tire Sales Acct# 726882": "726882",
            "Memo: 180645": "180645",
        }

        for text, expected in examples.items():
            with self.subTest(text=text):
                matches = check_for_customer_directives(text)
                self.assertEqual(
                    [item["customer_number"] for item in matches],
                    [expected],
                )

    def test_check_for_line_rejects_out_of_range_digit_counts(self) -> None:
        for text in (
            "For 33100",  # five digits
            "FOR Acct# 33100",  # five digits, explicit account label
            "For 123456789",  # nine digits (e.g. a routing number)
            "FOR Acct# 123456789",
        ):
            with self.subTest(text=text):
                self.assertEqual(check_for_customer_directives(text), [])

    def test_check_for_line_rejects_noncustomer_reference_context(self) -> None:
        for text in (
            "FOR Invoice 331002",
            "FOR INV 331002",
            "FOR PO 370036",
            "FOR Purchase Order 370036",
            "FOR Routing 180645",
            "FOR Bank 726882",
        ):
            with self.subTest(text=text):
                self.assertEqual(check_for_customer_directives(text), [])

    def test_check_for_line_explicit_account_survives_other_words(self) -> None:
        matches = check_for_customer_directives(
            "FOR Invoice Payment Acct# 726882"
        )

        self.assertEqual(
            [item["customer_number"] for item in matches],
            ["726882"],
        )

    def test_collapsed_or_wrapped_apply_to_acct_ocr_is_preserved(self) -> None:
        for text in (
            "ApplytoAcct 867946",
            "AnglytoAcct 867946",
            "Apply to Acct:\n867946",
        ):
            with self.subTest(text=text):
                matches = explicit_customer_account_directives(text)
                self.assertIn(
                    "867946",
                    {item["customer_number"] for item in matches},
                )

    def test_km_statement_parenthesized_customer_number_is_preserved(
        self,
    ) -> None:
        matches = extract_km_statement_customer_directives(
            "\n".join(
                (
                    "Remit Payment To:",
                    "K&M Tire Inc",
                    "PO Box 640045",
                    "Pittsburgh, PA 15264",
                    "KUNES NISSAN OF DAVENPORT (350063)",
                )
            )
        )

        self.assertEqual(
            [item["customer_number"] for item in matches],
            ["350063"],
        )

    def test_km_statement_split_dash_customer_number_is_preserved(self) -> None:
        matches = extract_km_statement_customer_directives(
            "\n".join(
                (
                    "Remit Payment To:",
                    "K6M Tire Inc",
                    "PO Box 673535",
                    "Dallas, TX 75267",
                    "(419) 695-1061",
                    "JV AUTO TECH",
                    "- 640516",
                )
            )
        )

        self.assertEqual(
            [item["customer_number"] for item in matches],
            ["640516"],
        )

    def test_km_statement_seven_digit_customer_number_is_preserved(
        self,
    ) -> None:
        # MaddenCo customer numbers (TMCUST.CUNUMBER) are decimal(7,0) — a
        # real customer number can be seven digits, not only six.
        paren_matches = extract_km_statement_customer_directives(
            "\n".join(
                (
                    "Remit Payment To:",
                    "K&M Tire Inc",
                    "PO Box 640045",
                    "Pittsburgh, PA 15264",
                    "KUNES NISSAN OF DAVENPORT (1000045)",
                )
            )
        )
        self.assertEqual(
            [item["customer_number"] for item in paren_matches],
            ["1000045"],
        )

        dash_matches = extract_km_statement_customer_directives(
            "\n".join(
                (
                    "Remit Payment To:",
                    "K6M Tire Inc",
                    "PO Box 673535",
                    "Dallas, TX 75267",
                    "JV AUTO TECH",
                    "- 1000045",
                )
            )
        )
        self.assertEqual(
            [item["customer_number"] for item in dash_matches],
            ["1000045"],
        )

    def test_km_statement_rejects_out_of_range_digit_counts(self) -> None:
        header = (
            "Remit Payment To:",
            "K&M Tire Inc",
            "PO Box 640045",
            "Pittsburgh, PA 15264",
        )
        five_digit = extract_km_statement_customer_directives(
            "\n".join((*header, "KUNES NISSAN OF DAVENPORT (35006)"))
        )
        self.assertEqual(five_digit, [])

        nine_digit = extract_km_statement_customer_directives(
            "\n".join((*header, "KUNES NISSAN OF DAVENPORT (350063123)"))
        )
        self.assertEqual(nine_digit, [])

    def test_customer_syntax_without_km_remit_block_is_not_statement_evidence(
        self,
    ) -> None:
        matches = extract_km_statement_customer_directives(
            "OTHER COMPANY\nCUSTOMER NAME (350063)"
        )

        self.assertEqual(matches, [])

    def test_conflicting_statement_customer_numbers_remain_unselected(
        self,
    ) -> None:
        transaction = Transaction(transaction_id="G-STATEMENT-CONFLICT")
        transaction.merge_statement_customer_directives(
            [
                {
                    "customer_number": "350063",
                    "evidence_text": "CUSTOMER ONE (350063)",
                },
                {
                    "customer_number": "640516",
                    "evidence_text": "CUSTOMER TWO - 640516",
                },
            ]
        )

        self.assertEqual(transaction.statement_customer_number, "")
        self.assertEqual(
            transaction.statement_customer_number_candidates,
            ["350063", "640516"],
        )

    def test_conflicting_explicit_accounts_are_not_collapsed(self) -> None:
        matches = explicit_customer_account_directives(
            "Apply check to acct 700001\nPost payment to acct 700002"
        )

        self.assertEqual(
            {item["customer_number"] for item in matches},
            {"700001", "700002"},
        )

    def test_incomplete_primary_crop_uses_complete_bounded_payer_fallback(
        self,
    ) -> None:
        primary = CustomerIdentity(
            customer_name="PAYEE COMPANY",
            confidence=0.55,
            evidence=["business or payer name"],
        )
        fallback = CustomerIdentity(
            customer_name="EXAMPLE AUTOMOTIVE, INC.",
            customer_phone="(312) 555-0184",
            customer_address_line_1="1200 EXAMPLE ROAD",
            customer_city="EXAMPLE CITY",
            customer_state="IL",
            customer_postal_code="60601",
            confidence=0.99,
            evidence=[
                "business or payer name",
                "street address",
                "city/state/ZIP",
                "phone number",
            ],
        )
        regions = [
            ("detected_check_image", Region(0, 50, 100, 100)),
            ("below_label_full_width", Region(0, 20, 100, 100)),
        ]
        with (
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "find_check_regions",
                return_value=regions,
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "extract_customer_identity",
                side_effect=(primary, fallback),
            ),
        ):
            identity, strategy, attempts = (
                _extract_transaction_customer_identity(
                    SimpleNamespace(),
                    "transaction page",
                )
            )

        self.assertEqual(identity.customer_name, "EXAMPLE AUTOMOTIVE, INC.")
        self.assertEqual(strategy, "below_label_full_width")
        self.assertEqual(len(attempts), 2)
        self.assertTrue(attempts[1]["exact_phone_present"])
        self.assertTrue(attempts[1]["five_digit_zip_present"])
        self.assertIn("bounded check-region fallback", identity.evidence)

    def test_payee_name_phone_and_zip_without_street_keeps_payer_search_open(
        self,
    ) -> None:
        primary = CustomerIdentity(
            customer_name="PAYEE COMPANY",
            customer_phone="(312) 555-0184",
            customer_postal_code="60601",
            confidence=0.96,
            evidence=[
                "business or payer name",
                "city/state/ZIP",
                "phone number",
            ],
        )
        fallback = CustomerIdentity(
            customer_name="EXAMPLE AUTOMOTIVE, INC.",
            customer_phone="(312) 555-0184",
            customer_address_line_1="1200 EXAMPLE ROAD",
            customer_city="EXAMPLE CITY",
            customer_state="IL",
            customer_postal_code="60601",
            confidence=0.99,
            evidence=[
                "business or payer name",
                "street address",
                "city/state/ZIP",
                "phone number",
            ],
        )
        regions = [
            ("detected_check_image", Region(0, 50, 100, 100)),
            ("below_label_full_width", Region(0, 20, 100, 100)),
        ]
        with (
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "find_check_regions",
                return_value=regions,
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "extract_customer_identity",
                side_effect=(primary, fallback),
            ) as extractor,
        ):
            identity, strategy, attempts = (
                _extract_transaction_customer_identity(
                    SimpleNamespace(),
                    "transaction page",
                )
            )

        self.assertEqual(extractor.call_count, 2)
        self.assertEqual(strategy, "below_label_full_width")
        self.assertEqual(identity.customer_name, "EXAMPLE AUTOMOTIVE, INC.")
        self.assertEqual(identity.customer_address_line_1, "1200 EXAMPLE ROAD")
        self.assertEqual(len(attempts), 2)
        self.assertFalse(attempts[0]["street_present"])
        self.assertTrue(attempts[1]["street_present"])

    def test_complete_primary_contact_does_not_run_fallback_ocr(self) -> None:
        primary = CustomerIdentity(
            customer_name="EXAMPLE CUSTOMER",
            customer_phone="3125550184",
            customer_address_line_1="1200 EXAMPLE ROAD",
            customer_postal_code="60601",
            confidence=0.99,
        )
        regions = [
            ("detected_check_image", Region(0, 20, 100, 100)),
            ("below_label_full_width", Region(0, 10, 100, 100)),
        ]
        with (
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "find_check_regions",
                return_value=regions,
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "extract_customer_identity",
                return_value=primary,
            ) as extractor,
        ):
            _, strategy, attempts = _extract_transaction_customer_identity(
                SimpleNamespace(),
                "transaction page",
            )

        self.assertEqual(strategy, "detected_check_image")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(extractor.call_count, 1)

    def test_conflicting_accounts_across_bounded_regions_remain_unselected(
        self,
    ) -> None:
        primary = CustomerIdentity(
            printed_customer_number="700001",
            printed_customer_number_evidence=(
                "Apply payment to customer account 700001"
            ),
            printed_customer_number_candidates=["700001"],
            confidence=0.95,
        )
        fallback = CustomerIdentity(
            printed_customer_number="700002",
            printed_customer_number_evidence=(
                "Post payment to customer account 700002"
            ),
            printed_customer_number_candidates=["700002"],
            confidence=0.95,
        )
        regions = [
            ("detected_check_image", Region(0, 20, 100, 100)),
            ("below_label_full_width", Region(0, 10, 100, 100)),
        ]
        with (
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "find_check_regions",
                return_value=regions,
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "extract_customer_identity",
                side_effect=(primary, fallback),
            ) as extractor,
        ):
            identity, _, attempts = _extract_transaction_customer_identity(
                SimpleNamespace(),
                "transaction page",
            )

        self.assertEqual(extractor.call_count, 2)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(identity.printed_customer_number, "")
        self.assertEqual(
            identity.printed_customer_number_candidates,
            ["700001", "700002"],
        )

    def test_raw_bounded_check_fallback_recovers_real_account_and_memo(
        self,
    ) -> None:
        incomplete = CustomerIdentity(
            customer_name="Chicago, i 0675-4618",
            customer_phone="877-246-7923",
            confidence=0.55,
            evidence=["business or payer name", "phone number"],
        )
        regions = [
            ("detected_check_image", Region(0, 50, 100, 100)),
            ("below_label_full_width", Region(0, 20, 100, 100)),
        ]
        with (
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "find_check_regions",
                return_value=regions,
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "extract_customer_identity",
                side_effect=(incomplete, incomplete),
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "ocr_region",
                return_value="\n".join(
                    (
                        "Account: 770939",
                        "EFFINGHAM TIRE AND AUTO CENTER",
                        "MEMO: Acct # 770939",
                    )
                ),
            ) as raw_ocr,
        ):
            identity, _, attempts = _extract_transaction_customer_identity(
                SimpleNamespace(),
                "transaction page",
            )

        self.assertEqual(raw_ocr.call_count, 1)
        self.assertEqual(identity.printed_customer_number, "770939")
        self.assertEqual(
            identity.printed_customer_number_candidates,
            ["770939"],
        )
        self.assertEqual(
            identity.printed_customer_number_evidence,
            "Account: 770939",
        )
        self.assertEqual(
            attempts[-1]["strategy"],
            "bounded_raw_account_fallback",
        )
        self.assertEqual(
            attempts[-1]["printed_customer_number_candidate_count"],
            1,
        )

    def test_bounded_for_line_fallback_recovers_customer_number(self) -> None:
        incomplete = CustomerIdentity(
            customer_name="PAYEE COMPANY",
            confidence=0.30,
            evidence=["business or payer name"],
        )
        regions = [
            ("detected_check_image", Region(0, 50, 100, 100)),
            ("below_label_full_width", Region(0, 20, 100, 100)),
        ]
        with (
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "find_check_regions",
                return_value=regions,
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "extract_customer_identity",
                side_effect=(incomplete, incomplete),
            ),
            patch(
                "modules.document_intelligence.pnc_lockbox_parser."
                "ocr_region",
                side_effect=("", "", "FOR Tire Sales Acct# 726882"),
            ) as raw_ocr,
        ):
            identity, _, attempts = _extract_transaction_customer_identity(
                SimpleNamespace(),
                "transaction page",
            )

        self.assertEqual(raw_ocr.call_count, 3)
        self.assertEqual(identity.printed_customer_number, "")
        self.assertEqual(identity.for_customer_number, "726882")
        self.assertEqual(
            identity.for_customer_number_candidates,
            ["726882"],
        )
        self.assertEqual(
            attempts[-1]["strategy"],
            "bounded_for_line_fallback",
        )
        self.assertEqual(
            attempts[-1]["for_customer_number_candidate_count"],
            1,
        )

    def test_sparse_ocr_columns_reconstruct_only_shared_visual_rows(self) -> None:
        data = {
            "text": [
                "430000101",
                "06/06/26",
                "723.00",
                "430000202",
                "06/20/26",
                "330.00",
            ],
            "left": [10, 140, 280, 10, 140, 280],
            "top": [100, 101, 100, 130, 131, 130],
            "width": [80, 70, 60, 80, 70, 60],
            "height": [12, 11, 12, 12, 11, 12],
        }

        reconstructed = _ocr_visual_row_text(data)

        self.assertEqual(
            reconstructed.splitlines(),
            [
                "430000101 06/06/26 723.00",
                "430000202 06/20/26 330.00",
            ],
        )
        evidence = extract_remittance_evidence(
            reconstructed,
            12,
            extraction_source="ocr_visual_row",
            ocr_psm=11,
        )
        self.assertEqual(
            [item.invoice_number for item in evidence.allocations],
            ["430000101", "430000202"],
        )
        self.assertEqual(
            [item.net_invoice_amount for item in evidence.allocations],
            [723.00, 330.00],
        )

    def test_ten_digit_values_remain_rejected_source_evidence(self) -> None:
        evidence = extract_remittance_evidence(
            "9999000001 3000.00\n9999999999 100.00",
            12,
            extraction_source="embedded_text",
        )

        self.assertEqual(evidence.allocations, [])
        self.assertEqual(len(evidence.rejected_candidates), 2)
        self.assertTrue(
            all(
                item.reason == "no_governed_invoice_candidate"
                for item in evidence.rejected_candidates
            )
        )

    def test_sparse_ocr_visual_rows_join_split_table_columns_in_page_flow(self) -> None:
        page = _FakePage("Supplemental Images", image_ratio=0.50)
        sparse_data = {
            "text": [
                "430000101",
                "06/06/26",
                "723.00",
                "430000202",
                "06/20/26",
                "330.00",
            ],
            "left": [10, 140, 280, 10, 140, 280],
            "top": [100, 100, 101, 130, 130, 131],
            "width": [80, 70, 60, 80, 70, 60],
            "height": [12, 12, 11, 12, 12, 11],
        }
        with patch(
            "modules.document_intelligence.pnc_lockbox_parser.ocr_region",
            side_effect=("", sparse_data),
        ) as ocr:
            evidence = _extract_page_remittance_evidence(page, 12)

        self.assertEqual(evidence.ocr_attempts, [6, 11])
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(
            [item.invoice_number for item in evidence.allocations],
            ["430000101", "430000202"],
        )
        self.assertEqual(
            [item.net_invoice_amount for item in evidence.allocations],
            [723.00, 330.00],
        )
        self.assertTrue(
            all(
                item.extraction_source == "ocr_visual_row"
                for item in evidence.allocations
            )
        )
        self.assertTrue(evidence.extraction_complete)

    def test_sparse_ocr_never_joins_tokens_from_adjacent_visual_rows(self) -> None:
        data = {
            "text": ["430000101", "412.34"],
            "left": [10, 280],
            "top": [100, 116],
            "width": [80, 60],
            "height": [10, 10],
        }

        reconstructed = _ocr_visual_row_text(data)
        evidence = extract_remittance_evidence(
            reconstructed,
            12,
            extraction_source="ocr_visual_row",
            ocr_psm=11,
        )

        self.assertEqual(
            reconstructed.splitlines(),
            ["430000101", "412.34"],
        )
        self.assertEqual(evidence.allocations, [])
        self.assertEqual(evidence.rejected_candidates, [])

    def test_displayed_page_count_is_not_a_transaction_boundary(self) -> None:
        transaction = _transaction_from_page(
            "\n".join(
                (
                    "Transaction Information G-8572002 PGH-640045 2026/07/31",
                    "Reported Amount $ 29,263.23",
                    "Check Number 018081",
                    "Num Pages 2",
                )
            ),
            47,
        )

        self.assertIsNotNone(transaction)
        self.assertFalse(hasattr(transaction, "declared_page_count"))
        self.assertEqual(
            transaction.transaction_boundary_rule,
            "next_transaction_information",
        )
        self.assertFalse(transaction.transaction_boundary_closed)

    def test_transaction_wide_duplicate_and_conflict_are_governed(self) -> None:
        transaction = Transaction(
            transaction_id="G-1",
            check_page=10,
            check_amount=100.00,
            remittance_pages_examined=[11, 12],
            transaction_boundary_closed=True,
        )
        transaction.merge_allocations(
            [
                AllocationCandidate(
                    invoice_number="100000001",
                    net_invoice_amount=100.00,
                    invoice_page="11;1",
                ),
                AllocationCandidate(
                    invoice_number="100000001",
                    net_invoice_amount=100.00,
                    invoice_page="12;1",
                ),
            ]
        )
        self.assertEqual(len(transaction.allocations), 1)
        self.assertEqual(transaction.allocations[0].invoice_page, "11;1,12;1")
        self.assertTrue(transaction.serialize()["remittance_evidence_complete"])

        transaction.merge_allocations(
            [
                AllocationCandidate(
                    invoice_number="100000001",
                    net_invoice_amount=99.00,
                    invoice_page="12;1",
                )
            ]
        )
        serialized = transaction.serialize()
        self.assertEqual(serialized["allocations"], [])
        self.assertFalse(serialized["remittance_evidence_complete"])
        self.assertEqual(
            {
                item["reason"]
                for item in serialized["rejected_remittance_candidates"]
            },
            {"conflicting_cross_page_amount"},
        )

    def test_substantial_image_bypasses_embedded_length_shortcut(self) -> None:
        page = _FakePage("Header " * 30, image_ratio=0.50)
        with patch(
            "modules.document_intelligence.pnc_lockbox_parser.ocr_region",
            return_value="431063896 125.00",
        ) as ocr:
            evidence = _extract_page_remittance_evidence(page, 2)

        self.assertEqual(evidence.ocr_attempts, [6, 11])
        self.assertEqual(evidence.allocations[0].invoice_number, "431063896")
        self.assertEqual(ocr.call_count, 2)

    def test_governed_embedded_row_avoids_unnecessary_ocr(self) -> None:
        page = _FakePage("431063896 125.00")
        with patch(
            "modules.document_intelligence.pnc_lockbox_parser.ocr_region",
        ) as ocr:
            evidence = _extract_page_remittance_evidence(page, 2)

        self.assertEqual(evidence.ocr_attempts, [])
        self.assertEqual(evidence.allocations[0].invoice_number, "431063896")
        ocr.assert_not_called()

    def test_invalid_embedded_row_uses_psm6_then_psm11(self) -> None:
        page = _FakePage("Invoice 123456 125.00", image_ratio=0.50)
        with patch(
            "modules.document_intelligence.pnc_lockbox_parser.ocr_region",
            side_effect=("Invoice 123456 125.00", "431063896 125.00"),
        ) as ocr:
            evidence = _extract_page_remittance_evidence(page, 2)

        self.assertEqual(evidence.ocr_attempts, [6, 11])
        self.assertEqual(
            [item.invoice_number for item in evidence.allocations],
            ["431063896"],
        )
        self.assertEqual(ocr.call_count, 2)

    def test_partial_embedded_and_both_ocr_modes_merge_all_five_rows(self) -> None:
        page = _FakePage("550489157 240.00", image_ratio=0.50)
        complete_ocr = "\n".join(
            (
                "431067399 1121.76 431067401 1240.20 "
                "550488667 841.32 550488669 3100.50",
                "550489157 240.00",
            )
        )
        with patch(
            "modules.document_intelligence.pnc_lockbox_parser.ocr_region",
            side_effect=(complete_ocr, complete_ocr),
        ) as ocr:
            evidence = _extract_page_remittance_evidence(page, 44)

        self.assertEqual(evidence.ocr_attempts, [6, 11])
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(
            [item.invoice_number for item in evidence.allocations],
            [
                "550489157",
                "431067399",
                "431067401",
                "550488667",
                "550488669",
            ],
        )
        self.assertAlmostEqual(
            sum(item.net_invoice_amount for item in evidence.allocations),
            6543.78,
            places=2,
        )
        self.assertTrue(evidence.extraction_complete)
        self.assertEqual(evidence.rejected_candidates, [])

    def test_cross_source_amount_conflict_is_withheld(self) -> None:
        page = _FakePage("431063896 125.00", image_ratio=0.50)
        with patch(
            "modules.document_intelligence.pnc_lockbox_parser.ocr_region",
            side_effect=("431063896 130.00", "431063896 130.00"),
        ):
            evidence = _extract_page_remittance_evidence(page, 2)

        self.assertEqual(evidence.allocations, [])
        self.assertFalse(evidence.extraction_complete)
        self.assertEqual(
            {item.reason for item in evidence.rejected_candidates},
            {"conflicting_cross_source_amount"},
        )

    def test_examined_page_without_row_retains_rejection_evidence(self) -> None:
        page = _FakePage("Invoice 123456 125.00")
        with patch(
            "modules.document_intelligence.pnc_lockbox_parser.ocr_region",
            return_value="",
        ):
            evidence = _extract_page_remittance_evidence(page, 2)

        self.assertEqual(evidence.allocations, [])
        self.assertTrue(evidence.rejected_candidates)

    def test_payer_identity_wins_over_payee_name_across_ocr_modes(self) -> None:
        payee_lines = [
            TextLine("PAY TO THE ORDER OF", 10, 100, 130, 110),
            TextLine("PAYEE DISTRIBUTION", 140, 100, 240, 110),
        ]
        payer_lines = [
            TextLine("EXAMPLE AUTOMOTIVE, INC.", 10, 10, 190, 20),
            TextLine("1200 EXAMPLE ROAD", 10, 22, 160, 32),
            TextLine("SAMPLEVILLE, IL 60601", 10, 34, 180, 44),
            TextLine("PHONE: (312) 555-0184", 10, 46, 190, 56),
        ]
        region = SimpleNamespace(
            x0=0.0,
            y0=0.0,
            x1=300.0,
            y1=200.0,
        )
        with patch(
            "modules.document_intelligence.check_understanding._ocr_lines",
            side_effect=(payee_lines, payer_lines),
        ):
            identity = extract_customer_identity(SimpleNamespace(), region)

        self.assertEqual(identity.customer_name, "EXAMPLE AUTOMOTIVE, INC.")
        self.assertEqual(identity.customer_phone, "(312) 555-0184")
        self.assertEqual(identity.customer_address_line_1, "1200 EXAMPLE ROAD")
        self.assertEqual(identity.customer_city, "SAMPLEVILLE")
        self.assertEqual(identity.customer_state, "IL")
        self.assertEqual(identity.customer_postal_code, "60601")
        self.assertGreaterEqual(identity.confidence, 0.95)

    def test_split_payee_label_cannot_replace_complete_payer_block(self) -> None:
        realistic_lines = [
            TextLine("EXAMPLE AUTOMOTIVE, INC.", 10, 10, 190, 20),
            TextLine("1200 EXAMPLE ROAD", 10, 22, 160, 32),
            TextLine("SAMPLEVILLE, IL 60601", 10, 34, 180, 44),
            TextLine("PHONE: (312) 555-0184", 10, 46, 190, 56),
            TextLine("FIRST NATIONAL BANK OF ILLINOIS", 220, 10, 390, 20),
            TextLine("PAY TO THE", 10, 100, 90, 110),
            TextLine("ORDER OF", 10, 112, 90, 122),
            TextLine("PAYEE DISTRIBUTION", 140, 112, 240, 122),
            TextLine("PO BOX 1000", 140, 124, 240, 134),
            TextLine("EXAMPLE CITY, PA 19001", 140, 136, 300, 146),
        ]
        region = SimpleNamespace(
            x0=0.0,
            y0=0.0,
            x1=420.0,
            y1=200.0,
        )
        with patch(
            "modules.document_intelligence.check_understanding._ocr_lines",
            side_effect=(realistic_lines, realistic_lines),
        ):
            identity = extract_customer_identity(SimpleNamespace(), region)

        self.assertEqual(identity.customer_name, "EXAMPLE AUTOMOTIVE, INC.")
        self.assertEqual(identity.customer_phone, "(312) 555-0184")
        self.assertEqual(identity.customer_postal_code, "60601")


if __name__ == "__main__":
    unittest.main()
