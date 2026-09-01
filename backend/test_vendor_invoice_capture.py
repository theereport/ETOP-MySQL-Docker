"""Focused verification for governed AP vendor-invoice capture/OCR.

The production image owns FastAPI. This focused test remains runnable in the
lightweight source-inspection environment by providing only the two FastAPI
types imported by the service when that dependency is absent.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import fitz
from sqlalchemy import create_engine


BACKEND_ROOT = Path(__file__).resolve().parent
MODULES_ROOT = BACKEND_ROOT / "modules"
DOC_ROOT = MODULES_ROOT / "document_intelligence"
AP_ROOT = MODULES_ROOT / "accounts_payable"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="etop-vendor-invoice-test-"))


def _namespace(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

_namespace("modules", MODULES_ROOT)
_namespace("modules.document_intelligence", DOC_ROOT)
_namespace("modules.accounts_payable", AP_ROOT)

try:
    import fastapi  # type: ignore[import-not-found]  # noqa: F401
except ModuleNotFoundError:
    fastapi_stub = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class UploadFile:  # pragma: no cover - typing surface only
        pass

    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.UploadFile = UploadFile
    sys.modules["fastapi"] = fastapi_stub


settings_module = types.ModuleType("modules.document_intelligence.settings")
settings_module.settings = SimpleNamespace(
    data_root=TEST_ROOT / "document-data",
    database_path=TEST_ROOT / "document-data" / "document-intelligence.db",
    upload_root=TEST_ROOT / "uploads",
    max_upload_bytes=50 * 1024 * 1024,
    max_pdf_pages=500,
    max_targeted_ocr_pages=25,
    max_ocr_render_dimension_pixels=10_000,
    max_ocr_render_pixels=20_000_000,
    ocr_page_timeout_seconds=30.0,
    ocr_total_timeout_seconds=120.0,
    processor_version="document-intelligence-processor.v3",
    module_key="document_intelligence",
    module_version="0.5.0",
)
sys.modules[settings_module.__name__] = settings_module

repository = importlib.import_module("modules.document_intelligence.repository")
review_store = importlib.import_module("modules.document_intelligence.review_store")
vendor_parser_module = importlib.import_module(
    "modules.document_intelligence.parsers.vendor_invoice"
)
vendor_extractor = importlib.import_module(
    "modules.document_intelligence.extractors.vendor_invoice"
)
ocr_engine = importlib.import_module("modules.document_intelligence.ocr_engine")
service = importlib.import_module("modules.document_intelligence.service")
review_schemas = importlib.import_module(
    "modules.document_intelligence.review_schemas"
)
document_schemas = importlib.import_module(
    "modules.document_intelligence.schemas"
)
ap_source = importlib.import_module("modules.accounts_payable.source")
ap_service_module = importlib.import_module("modules.accounts_payable.service")
data_mysql = importlib.import_module("data.mysql")


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


class VendorInvoiceParserEvidenceTests(unittest.TestCase):
    @staticmethod
    def _parse_lines(lines: list[dict], **extraction_overrides: object) -> dict:
        extraction = {
            "pages": [
                {
                    "page_number": 1,
                    "page_width": 612,
                    "lines": lines,
                }
            ],
            "full_text": "\n".join(str(line.get("text") or "") for line in lines),
            "text_source_summary": "native_pdf_text",
            "ocr_failed_pages": [],
        }
        extraction.update(extraction_overrides)
        return vendor_parser_module.VendorInvoiceParser().parse(
            {"extraction": extraction}
        )

    def test_vendor_parser_is_registered_and_ambiguity_is_preserved(self) -> None:
        registered = service.parser_registry.get("vendor_invoice")
        self.assertEqual(
            registered.parser_name,
            "deterministic_vendor_invoice_parser",
        )
        parsed = registered.parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": 1,
                            "lines": [
                                {
                                    "line_number": 1,
                                    "text": "Invoice Number: INV-1",
                                    "confidence": None,
                                    "source_method": "native_pdf_text",
                                },
                                {
                                    "line_number": 2,
                                    "text": "Invoice Number: INV-2",
                                    "confidence": None,
                                    "source_method": "native_pdf_text",
                                },
                            ],
                        }
                    ],
                    "ocr_failed_pages": [],
                }
            }
        )
        self.assertNotIn("invoice_number", parsed["fields"])
        self.assertEqual(
            len(parsed["ambiguous_fields"]["invoice_number"]),
            2,
        )
        self.assertEqual(
            parsed["field_evidence"]["invoice_number"]["validation_status"],
            "ambiguous",
        )

    def test_native_rules_do_not_invent_numeric_confidence(self) -> None:
        parsed = vendor_parser_module.VendorInvoiceParser().parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": 1,
                            "lines": [
                                {
                                    "line_number": 1,
                                    "text": "Vendor Name: Acme Supply",
                                    "bbox": [10, 10, 100, 20],
                                    "confidence": None,
                                    "source_method": "native_pdf_text",
                                },
                                {
                                    "line_number": 2,
                                    "text": "Invoice Number: INV-44",
                                    "bbox": [10, 25, 100, 35],
                                    "confidence": None,
                                    "source_method": "native_pdf_text",
                                },
                                {
                                    "line_number": 3,
                                    "text": "Amount Due: $1,250.00",
                                    "bbox": [10, 40, 100, 50],
                                    "confidence": None,
                                    "source_method": "native_pdf_text",
                                },
                            ],
                        }
                    ],
                    "ocr_average_confidence": None,
                    "ocr_failed_pages": [],
                }
            }
        )

        self.assertEqual(parsed["fields"]["invoice_number"], "INV-44")
        self.assertIsNone(
            parsed["field_evidence"]["invoice_number"]["confidence"]
        )
        self.assertIsNone(
            parsed["field_evidence"]["vendor_name"]["confidence"]
        )
        self.assertEqual(
            parsed["field_evidence"]["total_amount"]["location"],
            "page:1;bbox:10,40,100,50",
        )
        self.assertTrue(parsed["review_required"])

    def test_actual_ocr_confidence_is_retained(self) -> None:
        parsed = vendor_parser_module.VendorInvoiceParser().parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": 1,
                            "lines": [
                                {
                                    "line_number": 1,
                                    "text": "Invoice Number: OCR-9",
                                    "bbox": [3, 4, 90, 16],
                                    "confidence": 0.812345,
                                    "source_method": "local_tesseract_ocr",
                                }
                            ],
                        }
                    ],
                    "ocr_average_confidence": 0.812345,
                    "ocr_profile_version": "ocr-profile-test",
                    "ocr_failed_pages": [],
                }
            }
        )
        self.assertEqual(
            parsed["field_evidence"]["invoice_number"]["confidence"],
            0.812345,
        )
        self.assertEqual(
            parsed["field_evidence"]["ocr_confidence"]["confidence"],
            0.812345,
        )

    def test_fictional_coordinate_invoice_exercises_native_layout_pairing(self) -> None:
        pdf_path = TEST_ROOT / "fictional-coordinate-invoice.pdf"
        with fitz.open() as document:
            page = document.new_page(width=612, height=792)
            page.insert_text((40, 42), "INVOICE", fontsize=18)
            for label, value, y in (
                ("Invoice:", "FI-90017", 72),
                ("Invoice Date:", "8/9/2026", 88),
                ("Terms:", "Net 15", 104),
                ("Due Date:", "8/24/2026", 120),
            ):
                page.insert_text((420, y), label)
                page.insert_text((520, y), value)
            page.insert_text((45, 150), "Sold to")
            page.insert_text((315, 150), "Shipped to")
            page.insert_text((45, 168), "Example Buyer Manufacturing")
            page.insert_text((315, 168), "Example Receiving Warehouse")
            page.insert_text((60, 310), "Purchase Order:")
            page.insert_text((225, 328), "Service")
            page.insert_text((225, 344), "V-B01")
            page.insert_text((405, 420), "Total Price")
            page.insert_text((545, 420), "$999.99")
            page.insert_text((420, 565), "Sub Total")
            page.insert_text((550, 565), "$84.50")
            page.insert_text((420, 581), "Sales Tax")
            page.insert_text((550, 581), "$0.00")
            page.insert_text((420, 597), "Total")
            page.insert_text((550, 597), "$84.50")
            page.insert_text((420, 613), "Total Due")
            page.insert_text((550, 613), "$84.50")
            page.insert_text((45, 680), "Please Remit to:")
            page.insert_text((75, 698), "Northstar Lift Systems, Inc.")
            page.insert_text((75, 714), "PO Box 120")
            page.insert_text((420, 730), "Customer:")
            page.insert_text((510, 730), "CUST-4401")
            page.insert_text((420, 746), "Invoice:")
            page.insert_text((510, 746), "FI-90017")
            document.save(pdf_path)

        native = vendor_extractor.extract_pdf_text(pdf_path)
        extraction = vendor_extractor.extract_vendor_invoice_text(
            pdf_path,
            native_extraction=native,
        )
        parsed = vendor_parser_module.VendorInvoiceParser().parse(
            {"extraction": extraction}
        )

        self.assertEqual(extraction["extraction_version"], "vendor-invoice-extraction.v2")
        self.assertEqual(extraction["text_source_summary"], "native_pdf_text")
        self.assertEqual(extraction["native_text_pages"], [1])
        self.assertEqual(extraction["ocr_attempted_pages"], [])
        self.assertTrue(extraction["pages"][0]["lines"][0]["fragment_id"])
        self.assertEqual(extraction["pages"][0]["page_width"], 612.0)
        self.assertEqual(
            parsed["fields"],
            {
                "vendor_name": "Northstar Lift Systems, Inc.",
                "invoice_number": "FI-90017",
                "invoice_date": "8/9/2026",
                "due_date": "8/24/2026",
                "terms": "Net 15",
                "subtotal": "$84.50",
                "tax": "$0.00",
                "total_amount": "$84.50",
            },
        )
        self.assertNotIn("vendor_number", parsed["fields"])
        self.assertNotIn("purchase_order_number", parsed["fields"])
        self.assertEqual(
            parsed["field_evidence"]["purchase_order_number"]["validation_status"],
            "present_without_value",
        )
        invoice_evidence = parsed["field_evidence"]["invoice_number"]
        self.assertEqual(invoice_evidence["pairing_method"], "same_row_right")
        self.assertEqual(invoice_evidence["observation_count"], 2)
        self.assertEqual(invoice_evidence["candidate_count"], 1)
        self.assertIsNone(invoice_evidence["confidence"])
        self.assertEqual(
            [fragment["role"] for fragment in invoice_evidence["evidence_fragments"]],
            ["label", "value"],
        )
        self.assertEqual(
            parsed["field_evidence"]["vendor_name"]["pairing_method"],
            "remit_payee_block",
        )
        self.assertEqual(
            parsed["field_evidence"]["total_amount"]["observation_count"],
            2,
        )
        self.assertEqual(
            parsed["field_summary"]["quality"],
            "fields_available_requires_review",
        )
        self.assertEqual(
            parsed["key_field_readiness"]["status"],
            "key_fields_recognized",
        )

    def test_recipient_and_customer_sections_do_not_become_vendor_identity(self) -> None:
        parsed = vendor_parser_module.VendorInvoiceParser().parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": 1,
                            "page_width": 612,
                            "lines": [
                                {"text": "INVOICE", "bbox": [40, 30, 120, 50], "source_method": "native_pdf_text"},
                                {"text": "Sold to", "bbox": [40, 90, 90, 102], "source_method": "native_pdf_text"},
                                {"text": "Buyer Equipment Corporation", "bbox": [40, 108, 190, 120], "source_method": "native_pdf_text"},
                                {"text": "Shipped to", "bbox": [310, 90, 380, 102], "source_method": "native_pdf_text"},
                                {"text": "Receiving Supply Company", "bbox": [310, 108, 465, 120], "source_method": "native_pdf_text"},
                                {"text": "Customer: CUST-4401", "bbox": [420, 700, 550, 712], "source_method": "native_pdf_text"},
                            ],
                        }
                    ],
                    "full_text": "INVOICE Sold to Buyer Equipment Corporation Shipped to Receiving Supply Company Customer: CUST-4401",
                    "text_source_summary": "native_pdf_text",
                    "ocr_failed_pages": [],
                }
            }
        )
        self.assertNotIn("vendor_name", parsed["fields"])
        self.assertNotIn("vendor_number", parsed["fields"])
        self.assertNotEqual(
            parsed["field_evidence"]["vendor_name"].get("value"),
            "Shipped to",
        )

    def test_blank_purchase_order_does_not_steal_nearby_service_values(self) -> None:
        parsed = vendor_parser_module.VendorInvoiceParser().parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": 1,
                            "page_width": 612,
                            "lines": [
                                {"text": "Purchase Order:", "bbox": [40, 100, 130, 112], "source_method": "native_pdf_text"},
                                {"text": "Work Order", "bbox": [200, 100, 270, 112], "source_method": "native_pdf_text"},
                                {"text": "Service", "bbox": [200, 118, 245, 130], "source_method": "native_pdf_text"},
                                {"text": "V-B01", "bbox": [200, 136, 235, 148], "source_method": "native_pdf_text"},
                            ],
                        }
                    ],
                    "full_text": "Purchase Order Work Order Service V-B01",
                    "text_source_summary": "native_pdf_text",
                    "ocr_failed_pages": [],
                }
            }
        )
        self.assertNotIn("purchase_order_number", parsed["fields"])
        self.assertEqual(
            parsed["field_evidence"]["purchase_order_number"]["validation_status"],
            "present_without_value",
        )

    def test_generic_monetary_table_headers_never_pair_first_row_below(self) -> None:
        for field_name, label in (
            ("subtotal", "Sub Total"),
            ("tax", "Tax"),
            ("freight", "Freight"),
            ("discount", "Discount"),
            ("total_amount", "Total"),
        ):
            with self.subTest(field_name=field_name):
                parsed = self._parse_lines(
                    [
                        {
                            "text": label,
                            "bbox": [500, 200, 550, 212],
                            "source_method": "native_pdf_text",
                        },
                        {
                            "text": "$70.00",
                            "bbox": [500, 216, 550, 228],
                            "source_method": "native_pdf_text",
                        },
                    ]
                )
                self.assertNotIn(field_name, parsed["fields"])
                self.assertEqual(
                    parsed["field_evidence"][field_name]["validation_status"],
                    "present_without_value",
                )

    def test_bare_total_requires_same_value_from_strong_total_label(self) -> None:
        bare_only = self._parse_lines(
            [
                {"text": "Total", "bbox": [420, 100, 465, 112], "source_method": "native_pdf_text"},
                {"text": "$12.50", "bbox": [520, 100, 570, 112], "source_method": "native_pdf_text"},
            ]
        )
        self.assertNotIn("total_amount", bare_only["fields"])

        mismatched = self._parse_lines(
            [
                {"text": "Total", "bbox": [420, 100, 465, 112], "source_method": "native_pdf_text"},
                {"text": "$12.50", "bbox": [520, 100, 570, 112], "source_method": "native_pdf_text"},
                {"text": "Total Due", "bbox": [420, 130, 485, 142], "source_method": "native_pdf_text"},
                {"text": "$70.00", "bbox": [520, 130, 570, 142], "source_method": "native_pdf_text"},
            ]
        )
        self.assertEqual(mismatched["fields"]["total_amount"], "$70.00")
        self.assertEqual(
            mismatched["field_evidence"]["total_amount"]["observation_count"],
            1,
        )

        corroborated = self._parse_lines(
            [
                {"text": "Total", "bbox": [420, 100, 465, 112], "source_method": "native_pdf_text"},
                {"text": "$70.00", "bbox": [520, 100, 570, 112], "source_method": "native_pdf_text"},
                {"text": "Total Due", "bbox": [420, 130, 485, 142], "source_method": "native_pdf_text"},
                {"text": "$70.00", "bbox": [520, 130, 570, 142], "source_method": "native_pdf_text"},
            ]
        )
        self.assertEqual(corroborated["fields"]["total_amount"], "$70.00")
        self.assertEqual(
            corroborated["field_evidence"]["total_amount"]["observation_count"],
            2,
        )
        self.assertEqual(
            corroborated["field_evidence"]["total_amount"]["observations"][0]["selection_context"],
            "corroborated_by_strong_total_label",
        )
        self.assertNotIn(
            "selection_context",
            corroborated["field_evidence"]["total_amount"],
        )
        self.assertEqual(
            corroborated["field_evidence"]["total_amount"]["raw_label"],
            "Total Due",
        )

    def test_remittance_instructions_are_rejected_and_saint_name_is_retained(self) -> None:
        parsed = self._parse_lines(
            [
                {
                    "text": "Remit to: Attn: Cash Application",
                    "bbox": [40, 500, 225, 512],
                    "source_method": "native_pdf_text",
                },
                {
                    "text": "St. Mary's Equipment Company",
                    "bbox": [45, 520, 225, 532],
                    "source_method": "native_pdf_text",
                },
            ]
        )
        self.assertEqual(
            parsed["fields"]["vendor_name"],
            "St. Mary's Equipment Company",
        )
        self.assertEqual(
            parsed["field_evidence"]["vendor_name"]["authority"],
            "analytical_inference",
        )

    def test_remittance_requires_organization_evidence_and_preserves_conflicts(self) -> None:
        no_organization = self._parse_lines(
            [
                {"text": "Remit to:", "bbox": [40, 400, 105, 412], "source_method": "native_pdf_text"},
                {"text": "John Smith", "bbox": [45, 420, 120, 432], "source_method": "native_pdf_text"},
            ]
        )
        self.assertNotIn("vendor_name", no_organization["fields"])

        conflicting = self._parse_lines(
            [
                {"text": "Remit to:", "bbox": [40, 400, 105, 412], "source_method": "native_pdf_text"},
                {"text": "Factor Finance LLC", "bbox": [45, 420, 170, 432], "source_method": "native_pdf_text"},
                {"text": "Please Remit to:", "bbox": [40, 600, 135, 612], "source_method": "native_pdf_text"},
                {"text": "Actual Vendor Corporation", "bbox": [45, 620, 210, 632], "source_method": "native_pdf_text"},
            ]
        )
        self.assertNotIn("vendor_name", conflicting["fields"])
        evidence = conflicting["field_evidence"]["vendor_name"]
        self.assertEqual(evidence["validation_status"], "ambiguous")
        self.assertEqual(evidence["candidate_count"], 2)
        self.assertEqual(evidence["observation_count"], 2)
        self.assertEqual(len(evidence["observations"]), 2)

    def test_inline_and_coordinate_values_share_strict_validation(self) -> None:
        invalid = self._parse_lines(
            [
                {"text": "Invoice Date: Pending", "bbox": [40, 40, 180, 52], "source_method": "native_pdf_text"},
                {"text": "Due Date: 99/99/9999", "bbox": [40, 60, 180, 72], "source_method": "native_pdf_text"},
                {"text": "Subtotal: (70.00", "bbox": [40, 80, 180, 92], "source_method": "native_pdf_text"},
                {"text": "Total Due: 70.00)", "bbox": [40, 100, 180, 112], "source_method": "native_pdf_text"},
            ]
        )
        for field_name in ("invoice_date", "due_date", "subtotal", "total_amount"):
            self.assertNotIn(field_name, invalid["fields"])

        valid = self._parse_lines(
            [
                {"text": "Invoice Date: 2/29/2024", "bbox": [40, 40, 180, 52], "source_method": "native_pdf_text"},
                {"text": "Due Date: March 15, 2024", "bbox": [40, 60, 210, 72], "source_method": "native_pdf_text"},
                {"text": "Total Due: ($70.00)", "bbox": [40, 80, 180, 92], "source_method": "native_pdf_text"},
            ]
        )
        self.assertEqual(valid["fields"]["invoice_date"], "2/29/2024")
        self.assertEqual(valid["fields"]["due_date"], "March 15, 2024")
        self.assertEqual(valid["fields"]["total_amount"], "($70.00)")

    def test_malformed_extraction_shapes_degrade_without_parser_crash(self) -> None:
        malformed_documents = (
            None,
            {"extraction": {"pages": "not-a-page-list"}},
            {"extraction": {"pages": [{"page_number": "bad", "lines": None}]}},
            {"extraction": {"pages": [{"page_number": float("inf"), "lines": {}}]}},
            {"extraction": {"pages": [], "ocr_average_confidence": "bad"}},
        )
        for malformed in malformed_documents:
            with self.subTest(malformed=repr(malformed)):
                parsed = vendor_parser_module.VendorInvoiceParser().parse(malformed)
                self.assertEqual(parsed["validation"]["status"], "failed")
                self.assertTrue(parsed["review_required"])

        for malformed_confidence in ("bad", float("nan"), float("inf"), -0.1, 1.1, True):
            with self.subTest(confidence=repr(malformed_confidence)):
                parsed = vendor_parser_module.VendorInvoiceParser().parse(
                    {
                        "extraction": {
                            "pages": [],
                            "ocr_average_confidence": malformed_confidence,
                        }
                    }
                )
                self.assertNotIn("ocr_confidence", parsed["fields"])

        source_neutral = vendor_parser_module.VendorInvoiceParser().parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": "bad",
                            "lines": [
                                {
                                    "text": "unstructured OCR words",
                                    "bbox": [1, 2, 3, 4],
                                    "source_method": "local_tesseract_ocr",
                                }
                            ],
                        }
                    ],
                    "full_text": "unstructured OCR words",
                    "text_source_summary": "local_tesseract_ocr",
                    "ocr_failed_pages": [],
                }
            }
        )
        self.assertEqual(
            source_neutral["field_summary"]["quality"],
            "text_fields_unresolved",
        )

    def test_corroborating_totals_collapse_but_conflicting_totals_fail_closed(self) -> None:
        def parse(
            values: tuple[str, str],
            labels: tuple[str, str] = ("Total", "Total Due"),
        ) -> dict:
            lines = []
            for index, (label, value) in enumerate(zip(labels, values)):
                top = 100 + (index * 20)
                lines.extend(
                    [
                        {"text": label, "bbox": [400, top, 470, top + 12], "source_method": "native_pdf_text"},
                        {"text": value, "bbox": [530, top, 585, top + 12], "source_method": "native_pdf_text"},
                    ]
                )
            return vendor_parser_module.VendorInvoiceParser().parse(
                {
                    "extraction": {
                        "pages": [{"page_number": 1, "page_width": 612, "lines": lines}],
                        "full_text": "Total evidence",
                        "text_source_summary": "native_pdf_text",
                        "ocr_failed_pages": [],
                    }
                }
            )

        corroborated = parse(("$70.00", "70.000"))
        self.assertEqual(corroborated["fields"]["total_amount"], "$70.00")
        self.assertEqual(
            corroborated["field_evidence"]["total_amount"]["observation_count"],
            2,
        )
        self.assertEqual(
            corroborated["field_evidence"]["total_amount"]["candidate_count"],
            1,
        )

        conflicting = parse(
            ("$70.00", "$75.00"),
            ("Grand Total", "Total Due"),
        )
        self.assertNotIn("total_amount", conflicting["fields"])
        self.assertEqual(
            conflicting["field_evidence"]["total_amount"]["validation_status"],
            "ambiguous",
        )
        self.assertEqual(
            conflicting["field_evidence"]["total_amount"]["candidate_count"],
            2,
        )

    def test_ocr_coordinate_pair_uses_value_confidence_and_retains_fragments(self) -> None:
        parsed = vendor_parser_module.VendorInvoiceParser().parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": 1,
                            "page_width": 612,
                            "lines": [
                                {"fragment_id": "label", "text": "Invoice:", "bbox": [400, 50, 460, 62], "confidence": 0.94, "source_method": "local_tesseract_ocr"},
                                {"fragment_id": "value", "text": "OCR-901", "bbox": [500, 50, 565, 62], "confidence": 0.81, "source_method": "local_tesseract_ocr"},
                            ],
                        }
                    ],
                    "full_text": "Invoice OCR-901",
                    "text_source_summary": "local_tesseract_ocr",
                    "ocr_failed_pages": [],
                }
            }
        )
        evidence = parsed["field_evidence"]["invoice_number"]
        self.assertEqual(evidence["confidence"], 0.81)
        self.assertEqual(
            [item["confidence"] for item in evidence["evidence_fragments"]],
            [0.94, 0.81],
        )
        self.assertEqual(
            evidence["source"],
            "vendor_invoice_parser.coordinate_paired_ocr_text",
        )

    def test_malformed_bbox_falls_back_to_inline_labeled_parser(self) -> None:
        parsed = vendor_parser_module.VendorInvoiceParser().parse(
            {
                "extraction": {
                    "pages": [
                        {
                            "page_number": 1,
                            "lines": [
                                {"text": "Invoice Number: INLINE-9", "bbox": ["bad", 1, 2, 3], "confidence": None, "source_method": "native_pdf_text"},
                                {"text": "INVOICE", "bbox": [float("nan"), 1, 2, 3], "confidence": None, "source_method": "native_pdf_text"},
                            ],
                        }
                    ],
                    "full_text": "Invoice Number: INLINE-9",
                    "text_source_summary": "native_pdf_text",
                    "ocr_failed_pages": [],
                }
            }
        )
        self.assertEqual(parsed["fields"]["invoice_number"], "INLINE-9")
        self.assertEqual(
            parsed["field_evidence"]["invoice_number"]["pairing_method"],
            "inline_labeled",
        )

    def test_service_quality_message_distinguishes_native_text_from_ocr(self) -> None:
        native_extraction = {
            "text_source_summary": "native_pdf_text",
            "ocr_attempted_pages": [],
            "ocr_completed_pages": [],
            "ocr_failed_pages": [],
        }
        unresolved = service._vendor_invoice_review_message(
            {
                "field_summary": {
                    "message": "Native PDF text was extracted, but key fields need review: invoice number, invoice total."
                }
            },
            native_extraction,
        )
        self.assertIn("Native PDF text was extracted", unresolved)
        self.assertIn("key fields need review", unresolved)
        self.assertIn("OCR was not needed", unresolved)

        recognized = service._vendor_invoice_review_message(
            {
                "field_summary": {
                    "message": "Native PDF text was extracted; all three key fields were recognized. Human review remains required."
                }
            },
            native_extraction,
        )
        self.assertIn("all three key fields were recognized", recognized)
        self.assertIn("Human review remains required", recognized)

        skipped_ocr = service._vendor_invoice_review_message(
            {
                "field_summary": {
                    "message": "Native PDF text was extracted, but key fields need review."
                }
            },
            {
                "text_source_summary": "native_pdf_text",
                "ocr_attempted_pages": [],
                "ocr_completed_pages": [],
                "ocr_failed_pages": [2],
                "ocr_skipped_pages": [2],
            },
        )
        self.assertIn("failed or was skipped", skipped_ocr)
        self.assertIn("affected pages need review", skipped_ocr)
        self.assertNotIn("OCR was not needed", skipped_ocr)


class TargetedOCRTests(unittest.TestCase):
    def test_native_only_document_never_invokes_ocr(self) -> None:
        pdf_path = TEST_ROOT / "native-only.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), "Invoice Number: NATIVE-1")
            document.save(pdf_path)
        native = {
            "pages": [
                {
                    "page_number": 1,
                    "text": "Invoice Number: NATIVE-1",
                    "requires_ocr": False,
                }
            ],
            "ocr_recommended": False,
        }
        with (
            patch.object(vendor_extractor, "_ocr_lines") as ocr,
            patch.object(vendor_extractor, "tesseract_identity") as identity,
        ):
            result = vendor_extractor.extract_vendor_invoice_text(
                pdf_path,
                native_extraction=native,
            )
        ocr.assert_not_called()
        identity.assert_not_called()
        self.assertEqual(result["ocr_attempted_pages"], [])
        self.assertIsNone(result["ocr_engine"])

    def test_ocr_runs_only_for_pages_native_extraction_marks_insufficient(self) -> None:
        pdf_path = TEST_ROOT / "targeted-ocr.pdf"
        with fitz.open() as document:
            document.new_page()
            document.new_page()
            document.save(pdf_path)

        native = {
            "pages": [
                {"page_number": 1, "text": "Native invoice text", "requires_ocr": False},
                {"page_number": 2, "text": "", "requires_ocr": True},
            ],
            "ocr_recommended": True,
        }
        mocked_lines = [
            {
                "line_number": 1,
                "text": "Invoice Number: OCR-22",
                "bbox": [1, 2, 80, 12],
                "confidence": 0.91,
                "source_method": "local_tesseract_ocr",
            }
        ]
        with patch.object(
            vendor_extractor,
            "_ocr_lines",
            return_value=(mocked_lines, 0.91),
        ) as ocr:
            result = vendor_extractor.extract_vendor_invoice_text(
                pdf_path,
                native_extraction=native,
            )

        self.assertEqual(ocr.call_count, 1)
        self.assertEqual(result["ocr_attempted_pages"], [2])
        self.assertEqual(result["ocr_completed_pages"], [2])
        self.assertEqual(result["pages"][0]["text_source"], "native_pdf_text")
        self.assertEqual(result["pages"][1]["text_source"], "local_tesseract_ocr")

    def test_targeted_ocr_page_limit_is_explicit_review_evidence(self) -> None:
        pdf_path = TEST_ROOT / "bounded-ocr.pdf"
        with fitz.open() as document:
            for _ in range(3):
                document.new_page()
            document.save(pdf_path)
        native = {
            "pages": [
                {"page_number": number, "text": "", "requires_ocr": True}
                for number in (1, 2, 3)
            ],
            "ocr_recommended": True,
        }
        ocr_line = {
            "line_number": 1,
            "text": "Invoice Number: BOUNDED-1",
            "bbox": [1, 1, 100, 20],
            "confidence": 0.8,
            "source_method": "local_tesseract_ocr",
        }
        with (
            patch.object(
                vendor_extractor,
                "_ocr_lines",
                return_value=([ocr_line], 0.8),
            ) as ocr,
            patch.object(
                vendor_extractor,
                "tesseract_identity",
                return_value=("local_tesseract", "test"),
            ),
        ):
            result = vendor_extractor.extract_vendor_invoice_text(
                pdf_path,
                native_extraction=native,
                max_ocr_pages=1,
            )
        self.assertEqual(ocr.call_count, 1)
        self.assertEqual(result["ocr_attempted_pages"], [1])
        self.assertEqual(result["ocr_skipped_pages"], [2, 3])
        self.assertEqual(result["ocr_failed_pages"], [2, 3])
        self.assertEqual(result["pages"][1]["ocr_status"], "skipped_page_limit")

    def test_ocr_identity_work_cannot_overrun_document_time_limit(self) -> None:
        pdf_path = TEST_ROOT / "identity-time-limit.pdf"
        with fitz.open() as document:
            document.new_page()
            document.save(pdf_path)
        native = {
            "pages": [
                {"page_number": 1, "text": "", "requires_ocr": True},
            ],
            "ocr_recommended": True,
        }
        with (
            patch.object(
                vendor_extractor,
                "monotonic",
                side_effect=[0.0, 0.0, 2.0],
            ),
            patch.object(
                vendor_extractor,
                "tesseract_identity",
                return_value=("local_tesseract", "test"),
            ),
            patch.object(vendor_extractor, "_ocr_lines") as ocr,
        ):
            result = vendor_extractor.extract_vendor_invoice_text(
                pdf_path,
                native_extraction=native,
                ocr_total_timeout_seconds=1.0,
            )
        ocr.assert_not_called()
        self.assertEqual(result["ocr_attempted_pages"], [])
        self.assertEqual(result["ocr_skipped_pages"], [1])
        self.assertEqual(result["pages"][0]["ocr_status"], "skipped_time_limit")

    def test_oversized_ocr_raster_is_rejected_before_pixmap_allocation(self) -> None:
        page = Mock()
        page.rect = fitz.Rect(0, 0, 5_000, 5_000)
        with self.assertRaisesRegex(RuntimeError, "raster safety limit"):
            ocr_engine._image_from_page(
                page,
                clip=None,
                scale=3.0,
                max_dimension_pixels=10_000,
                max_pixels=20_000_000,
            )
        page.get_pixmap.assert_not_called()


class ProcessingRunLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        test_dir = Path(tempfile.mkdtemp(prefix="ledger-", dir=TEST_ROOT))
        repository.settings = SimpleNamespace(
            data_root=test_dir,
            upload_root=test_dir / "uploads",
        )
        self.engine = create_engine(f"sqlite:///{test_dir / 'document-intelligence.db'}")
        data_mysql._set_engine_override(self.engine)
        now = "2026-08-08T12:00:00+00:00"
        repository.create_job(
            {
                "job_id": "job-ledger",
                "original_file_name": "invoice.pdf",
                "stored_file_name": "invoice.pdf",
                "stored_path": str(test_dir / "invoice.pdf"),
                "content_type": "application/pdf",
                "file_size_bytes": 100,
                "source_sha256": "a" * 64,
                "intake_document_type": "vendor_invoice",
                "intake_source": "test",
                "document_type": "vendor_invoice",
                "confidence": 0.0,
                "status": "uploaded",
                "message": "test",
                "created_at": now,
                "updated_at": now,
            }
        )
        self.now = now

    def tearDown(self) -> None:
        data_mysql._reset_engine_override()
        self.engine.dispose()

    def _record(self, run_id: str, parsed_value: str) -> None:
        repository.record_processing_run(
            "job-ledger",
            processing_run_id=run_id,
            processor_version="processor-test",
            source_sha256="a" * 64,
            status="completed",
            classifier="test",
            classification_evidence=[],
            extraction={"full_text": parsed_value},
            parsed={"parser": "vendor", "value": parsed_value},
            message="complete",
            created_at=self.now,
            completed_at=self.now,
            make_current=True,
        )

    def test_prior_runs_remain_retrievable_when_current_advances(self) -> None:
        self._record("run-1", "first")
        self._record("run-2", "second")

        current = repository.get_result("job-ledger")
        prior = repository.get_processing_run("job-ledger", "run-1")
        runs = repository.list_processing_runs("job-ledger")
        self.assertEqual(current["processing_run_id"], "run-2")
        self.assertEqual(prior["parsed"]["value"], "first")
        self.assertEqual([run["run_number"] for run in runs], [2, 1])

        # Append-only is enforced by convention in the repository layer
        # (it never issues UPDATE/DELETE against these tables), not by a
        # DB trigger - MySQL trigger creation needs a privilege the etop
        # account doesn't have.


class ProcessingRunReviewBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        data_mysql._set_engine_override(self.engine)

    def tearDown(self) -> None:
        data_mysql._reset_engine_override()
        self.engine.dispose()

    def test_new_run_resets_current_review_and_preserves_prior_history(self) -> None:
        review_store.save_review(
            "job-review",
            processing_run_id="run-1",
            status="approved",
            reviewer="Pat Reviewer",
            notes="Reviewed run one",
            corrected_fields={"invoice_number": "CORRECTED-1"},
        )
        review_store.begin_review_for_processing_run("job-review", "run-2")
        envelope = review_store.get_review("job-review")

        self.assertEqual(envelope["review"]["processing_run_id"], "run-2")
        self.assertEqual(envelope["review"]["status"], "pending")
        self.assertEqual(envelope["review"]["corrected_fields"], {})
        approved_prior = next(
            item for item in envelope["history"] if item["status"] == "approved"
        )
        self.assertEqual(approved_prior["processing_run_id"], "run-1")
        self.assertEqual(
            approved_prior["corrected_fields"]["invoice_number"],
            "CORRECTED-1",
        )

    # test_review_and_repository_connections_close_deterministically was
    # removed: it verified that raw sqlite3.connect() calls closed their OS
    # handle deterministically (a real concern for the old one-connection-
    # per-call style). SQLAlchemy's pooled engine manages connection
    # lifecycle itself and never calls sqlite3.connect() directly in a way
    # this test's patch.object(sqlite3, "connect", ...) can observe, so the
    # premise no longer applies.

    def test_stale_review_put_is_rejected_with_conflict(self) -> None:
        with (
            patch.object(
                service,
                "get_job_result",
                return_value={"processing_run_id": "run-2"},
            ),
            patch.object(service, "save_review") as save,
        ):
            with self.assertRaises(service.HTTPException) as raised:
                service.save_current_job_review(
                    "job-review",
                    expected_processing_run_id="run-1",
                    status="approved",
                    reviewer="Pat Reviewer",
                    notes="stale",
                    corrected_fields={},
                )
        self.assertEqual(raised.exception.status_code, 409)
        save.assert_not_called()

    def test_review_request_requires_expected_processing_run_id(self) -> None:
        with self.assertRaises(Exception):
            review_schemas.DocumentReviewSaveRequest(
                status="approved",
                reviewer="Pat Reviewer",
                notes="Missing concurrency identity",
                corrected_fields={},
            )

    def test_processing_and_review_cas_share_one_serial_boundary(self) -> None:
        active = 0
        maximum_active = 0
        state_lock = threading.Lock()

        def controlled_process(job_id: str) -> dict:
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.03)
            with state_lock:
                active -= 1
            return {"job_id": job_id}

        with patch.object(service, "_process_job", side_effect=controlled_process):
            first = threading.Thread(target=service.process_job, args=("job-a",))
            second = threading.Thread(target=service.process_job, args=("job-b",))
            first.start()
            second.start()
            first.join()
            second.join()
        self.assertEqual(maximum_active, 1)

    def test_ap_projection_does_not_apply_review_from_prior_run(self) -> None:
        evidence = {
            "job": {
                "job_id": "job-review",
                "document_type": "vendor_invoice",
                "status": "completed",
                "original_file_name": "invoice.pdf",
                "content_type": "application/pdf",
                "confidence": 0.0,
                "created_at": "2026-08-08T12:00:00+00:00",
                "updated_at": "2026-08-08T12:05:00+00:00",
            },
            "result": {
                "job_id": "job-review",
                "processing_run_id": "run-2",
                "processing_run_number": 2,
                "classifier": "test",
                "classification_evidence": [],
                "extraction": {"full_text": ""},
                "parsed": {
                    "parser": "deterministic_vendor_invoice_parser",
                    "parser_version": "1.0.0",
                    "fields": {
                        "vendor_name": "Source Vendor",
                        "invoice_number": "SOURCE-2",
                        "total_amount": "25.00",
                    },
                    "review_required": True,
                },
                "created_at": "2026-08-08T12:05:00+00:00",
                "updated_at": "2026-08-08T12:05:00+00:00",
            },
            "review": {
                "review": {
                    "job_id": "job-review",
                    "processing_run_id": "run-1",
                    "status": "approved",
                    "reviewer": "Pat Reviewer",
                    "notes": "Reviewed prior run",
                    "corrected_fields": {"invoice_number": "STALE-CORRECTION"},
                    "created_at": "2026-08-08T12:01:00+00:00",
                    "updated_at": "2026-08-08T12:02:00+00:00",
                },
                "history": [],
            },
        }

        projection = ap_source.build_projections(evidence)[0]
        self.assertEqual(projection.invoice_number, "SOURCE-2")
        self.assertTrue(
            any(
                item["code"] == "document_extraction_review_pending"
                for item in projection.exceptions
            )
        )
        self.assertFalse(
            projection.source_snapshot["document_extraction_review"][
                "corrected_fields_used"
            ]
        )


class FailedReprocessRetentionTests(unittest.TestCase):
    def test_failed_reprocess_keeps_last_successful_current_result(self) -> None:
        pdf_path = TEST_ROOT / "retained-current.pdf"
        pdf_path.write_bytes(b"%PDF-test")
        source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        job = {
            "job_id": "job-retained",
            "stored_path": str(pdf_path),
            "original_file_name": "invoice.pdf",
            "source_sha256": source_hash,
            "status": "completed",
            "intake_document_type": "vendor_invoice",
        }
        fake_repository = Mock()
        fake_repository.get_result.return_value = {
            "processing_run_id": "run-success"
        }
        fake_repository.update_job.side_effect = lambda job_id, **changes: {
            **job,
            **changes,
        }

        with (
            patch.object(service, "repository", fake_repository),
            patch.object(service, "get_job", return_value=job),
            patch.object(
                service,
                "extract_pdf_text",
                side_effect=RuntimeError("transient extractor failure"),
            ),
        ):
            with self.assertRaises(service.HTTPException):
                service.process_job("job-retained")

        failed_run = fake_repository.record_processing_run.call_args.kwargs
        self.assertEqual(failed_run["status"], "failed")
        self.assertFalse(failed_run["make_current"])
        final_update = fake_repository.update_job.call_args_list[-1].kwargs
        self.assertEqual(final_update["status"], "completed")
        self.assertIn("last successful current result remains", final_update["message"])

    def test_invalid_retry_appends_failed_run_instead_of_short_circuiting(self) -> None:
        pdf_path = TEST_ROOT / "invalid-retry.pdf"
        pdf_path.write_bytes(b"%PDF-invalid")
        source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        job = {
            "job_id": "job-invalid-retry",
            "stored_path": str(pdf_path),
            "original_file_name": "invoice.pdf",
            "source_sha256": source_hash,
            "status": "failed",
            "intake_document_type": "vendor_invoice",
        }
        fake_repository = Mock()
        fake_repository.get_result.return_value = None
        fake_repository.update_job.side_effect = lambda job_id, **changes: {
            **job,
            **changes,
        }
        with (
            patch.object(service, "repository", fake_repository),
            patch.object(service, "get_job", return_value=job),
            patch.object(service, "_managed_pdf_path", return_value=pdf_path),
            patch.object(
                service,
                "_validate_preserved_pdf",
                return_value="Encrypted PDF invoices are not supported.",
            ),
        ):
            with self.assertRaises(service.HTTPException):
                service.process_job(job["job_id"])
        failed_run = fake_repository.record_processing_run.call_args.kwargs
        self.assertEqual(failed_run["status"], "failed")
        self.assertFalse(failed_run["make_current"])
        self.assertIn("Encrypted PDF", failed_run["message"])


class ProcessingSafetyBoundaryTests(unittest.TestCase):
    def test_public_job_response_does_not_disclose_stored_path(self) -> None:
        response = document_schemas.DocumentJobResponse(
            job_id="job-public",
            original_file_name="invoice.pdf",
            stored_file_name="job-public-invoice.pdf",
            stored_path="/private/workstation/uploads/job-public-invoice.pdf",
            content_type="application/pdf",
            file_size_bytes=123,
            source_sha256="a" * 64,
            intake_document_type="vendor_invoice",
            intake_source="test",
            duplicate_of_job_id=None,
            document_type="vendor_invoice",
            confidence=0.5,
            status="completed",
            message="Processed",
            created_at="2026-08-08T12:00:00+00:00",
            updated_at="2026-08-08T12:01:00+00:00",
        )
        payload = response.model_dump(mode="json")
        self.assertNotIn("stored_path", payload)
        self.assertEqual(payload["stored_file_name"], "job-public-invoice.pdf")

    def test_pdf_validation_error_does_not_reflect_local_path(self) -> None:
        private_path = Path("/private/workstation/uploads/invoice.pdf")
        with patch.object(
            service.fitz,
            "open",
            side_effect=RuntimeError(f"cannot open {private_path}"),
        ):
            error = service._validate_preserved_pdf(private_path)
        self.assertIn("RuntimeError", error)
        self.assertNotIn(str(private_path), error)

    def test_managed_path_rejects_source_outside_upload_root(self) -> None:
        managed_root = TEST_ROOT / "managed-only"
        outside = TEST_ROOT / "outside.pdf"
        outside.write_bytes(b"%PDF-outside")
        with patch.object(
            service,
            "settings",
            SimpleNamespace(upload_root=managed_root),
        ):
            with self.assertRaisesRegex(RuntimeError, "outside the managed"):
                service._managed_pdf_path({"stored_path": str(outside)})

    def test_pdf_page_limit_fails_before_page_loading(self) -> None:
        document = Mock()
        document.needs_pass = False
        document.page_count = 501
        document.__enter__ = Mock(return_value=document)
        document.__exit__ = Mock(return_value=False)
        with (
            patch.object(service.fitz, "open", return_value=document),
            patch.object(
                service,
                "settings",
                SimpleNamespace(max_pdf_pages=500),
            ),
        ):
            error = service._validate_preserved_pdf(Path("bounded.pdf"))
        self.assertIn("exceeds", error)
        document.load_page.assert_not_called()

    def test_processing_entry_points_are_serialized(self) -> None:
        active = 0
        maximum_active = 0
        state_lock = threading.Lock()

        def controlled(job_id: str) -> dict:
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02)
            with state_lock:
                active -= 1
            return {"job_id": job_id}

        with patch.object(service, "_process_job", side_effect=controlled):
            threads = [
                threading.Thread(target=service.process_job, args=(f"job-{i}",))
                for i in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(maximum_active, 1)


class VendorDatasetPaginationTests(unittest.TestCase):
    def test_vendor_jobs_are_counted_and_retrievable_across_offsets(self) -> None:
        test_dir = Path(tempfile.mkdtemp(prefix="pagination-", dir=TEST_ROOT))
        repository.settings = SimpleNamespace(
            data_root=test_dir,
            upload_root=test_dir / "uploads",
        )
        engine = create_engine(f"sqlite:///{test_dir / 'document-intelligence.db'}")
        data_mysql._set_engine_override(engine)
        self.addCleanup(data_mysql._reset_engine_override)
        self.addCleanup(engine.dispose)
        for index in range(3):
            timestamp = f"2026-08-08T12:0{index}:00+00:00"
            repository.create_job(
                {
                    "job_id": f"job-page-{index}",
                    "original_file_name": f"invoice-{index}.pdf",
                    "stored_file_name": f"invoice-{index}.pdf",
                    "stored_path": str(test_dir / f"invoice-{index}.pdf"),
                    "content_type": "application/pdf",
                    "file_size_bytes": 100,
                    "source_sha256": str(index) * 64,
                    "intake_document_type": "vendor_invoice",
                    "intake_source": "test",
                    "document_type": "vendor_invoice",
                    "confidence": 0.0,
                    "status": "uploaded",
                    "message": "test",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
        first = repository.list_jobs(
            limit=2,
            offset=0,
            document_type="vendor_invoice",
        )
        second = repository.list_jobs(
            limit=2,
            offset=2,
            document_type="vendor_invoice",
        )
        self.assertEqual(repository.count_jobs(document_type="vendor_invoice"), 3)
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 1)
        self.assertEqual(
            {job["job_id"] for job in first + second},
            {"job-page-0", "job-page-1", "job-page-2"},
        )


class ExactJobAccountsPayableSyncTests(unittest.TestCase):
    @staticmethod
    def _repository() -> Mock:
        target = Mock()
        target.sync_projections.return_value = {
            "imported": 1,
            "updated": 0,
            "unchanged": 0,
            "duplicate_candidates": 0,
            "events": 3,
        }
        target.source_statistics.return_value = {
            "count": 1,
            "ocr_count": 0,
            "structured_count": 1,
            "as_of": "2026-08-08T12:00:00+00:00",
        }
        return target

    def test_exact_job_sync_uses_only_reviewed_current_job(self) -> None:
        source = Mock()
        evidence = {
            "job": {"job_id": "job-exact"},
            "result": {"processing_run_id": "run-current"},
            "review": {
                "review": {
                    "processing_run_id": "run-current",
                    "status": "approved",
                }
            },
            "source_warning": None,
        }
        source.get_vendor_invoice_evidence.return_value = evidence
        repository_double = self._repository()
        service_under_test = ap_service_module.AccountsPayableService(
            repository=repository_double,
            source=source,
            clock=lambda: datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
            id_factory=lambda: "sync-exact",
        )
        with patch.object(
            ap_service_module,
            "build_projections",
            return_value=[Mock()],
        ) as build:
            response = service_under_test.sync_document_job("job-exact")
        source.get_vendor_invoice_evidence.assert_called_once_with("job-exact")
        source.list_vendor_invoice_evidence.assert_not_called()
        build.assert_called_once_with(evidence)
        self.assertEqual(response.eligible_job_count, 1)
        self.assertEqual(response.imported_count, 1)

    def test_exact_job_sync_rejects_prior_run_review(self) -> None:
        source = Mock()
        source.get_vendor_invoice_evidence.return_value = {
            "result": {"processing_run_id": "run-current"},
            "review": {
                "review": {
                    "processing_run_id": "run-prior",
                    "status": "approved",
                }
            },
        }
        service_under_test = ap_service_module.AccountsPayableService(
            repository=self._repository(),
            source=source,
        )
        with self.assertRaises(ap_service_module.APDocumentReviewConflict):
            service_under_test.sync_document_job("job-exact")


class UploadPreservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_vendor_intake_offloads_processing_from_async_event_loop(self) -> None:
        job = {
            "job_id": "job-threaded",
            "status": "uploaded",
        }
        result = {
            "job": {**job, "status": "completed"},
            "parsed": {"review_required": True},
        }
        with (
            patch.object(
                service,
                "create_upload_job",
                new=AsyncMock(return_value=job),
            ),
            patch.object(
                service.asyncio,
                "to_thread",
                new=AsyncMock(return_value=result),
            ) as to_thread,
        ):
            response = await service.create_vendor_invoice_intake(Mock())
        to_thread.assert_awaited_once_with(service.process_job, "job-threaded")
        self.assertEqual(response["intake_status"], "processed")

    async def test_upload_preserves_exact_pdf_bytes_and_sha256(self) -> None:
        test_dir = Path(tempfile.mkdtemp(prefix="upload-", dir=TEST_ROOT))
        test_settings = SimpleNamespace(
            data_root=test_dir / "data",
            upload_root=test_dir / "uploads",
            max_upload_bytes=50 * 1024 * 1024,
            max_pdf_pages=500,
            max_targeted_ocr_pages=25,
            max_ocr_render_dimension_pixels=10_000,
            max_ocr_render_pixels=20_000_000,
            ocr_page_timeout_seconds=30.0,
            ocr_total_timeout_seconds=120.0,
            processor_version="document-intelligence-processor.v3",
        )
        repository.settings = test_settings
        service.settings = test_settings
        engine = create_engine(f"sqlite:///{test_dir / 'data' / 'document-intelligence.db'}")
        data_mysql._set_engine_override(engine)
        self.addCleanup(data_mysql._reset_engine_override)
        self.addCleanup(engine.dispose)
        buffer = io.BytesIO()
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), "Vendor Name: Upload Test")
            document.save(buffer)
        pdf_bytes = buffer.getvalue()

        class AsyncUpload:
            filename = "invoice upload.pdf"
            content_type = "application/pdf"

            def __init__(self, content: bytes):
                self.stream = io.BytesIO(content)
                self.closed = False

            async def read(self, size: int) -> bytes:
                return self.stream.read(size)

            async def close(self) -> None:
                self.closed = True

        upload = AsyncUpload(pdf_bytes)
        job = await service.create_upload_job(
            upload,
            intake_document_type="vendor_invoice",
            intake_source="accounts_payable_vendor_invoice_capture",
        )

        preserved_path = Path(job["stored_path"])
        self.assertEqual(preserved_path.read_bytes(), pdf_bytes)
        self.assertEqual(
            job["source_sha256"],
            hashlib.sha256(pdf_bytes).hexdigest(),
        )
        self.assertEqual(job["status"], "uploaded")
        self.assertTrue(upload.closed)


if __name__ == "__main__":
    unittest.main()
