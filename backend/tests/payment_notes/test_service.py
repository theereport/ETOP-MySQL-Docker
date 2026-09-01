import csv
import io
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from pathlib import Path

from sqlalchemy import create_engine

from modules.payment_notes.erp_repository import ExpectedPaymentResult, SignatureResult
from modules.payment_notes.matching import ExpectedPayment, SignatureEvidence
from modules.payment_notes.remote_capture import REQUIRED_HEADERS
from modules.payment_notes.repository import PaymentNotesRepository
from modules.payment_notes.schemas import ReviewRequest, ReviewResponse, RouteReferenceSummary, RunDetail
from modules.payment_notes.service import PaymentNotesPreconditionError, PaymentNotesService


class FakeERP:
    MAX_SIGNATURE_PAIRS = 250

    def get_expected_payments(self, routes, date_from, date_to):
        return ExpectedPaymentResult((ExpectedPayment(
            "pay-1", "customer-1", routes[0], "CHECK", "7", "7", Decimal("10.00"),
            raw_invoices="10000001", invoice_numbers=("10000001",),
            invoice_reference_status="provisional_8_10_digit_tokens",
        ),), True, 5000, len(routes), "2026-08-22T00:00:00+00:00")

    def get_signature_evidence(self, pairs):
        evidence = SignatureEvidence("customer-1", "10000001", "Signed", "proof.png", "", "", "1")
        return SignatureResult({("customer-1", "10000001"): (evidence,)}, True, 2000,
                               len(pairs), "2026-08-22T00:00:00+00:00")


class PartialInvoiceERP(FakeERP):
    def __init__(self):
        self.signature_calls = 0

    def get_expected_payments(self, routes, date_from, date_to):
        payment = ExpectedPayment(
            "pay-1", "customer-1", routes[0], "CHECK", "7", "7", Decimal("10.00"),
            raw_invoices="10000001 unresolved-text", invoice_numbers=("10000001",),
            invoice_reference_status="provisional_partial_8_10_digit_tokens",
        )
        return ExpectedPaymentResult((payment,), True, 5000, len(routes), "now")

    def get_signature_evidence(self, pairs):
        self.signature_calls += 1
        return super().get_signature_evidence(pairs)


class ManyAmountOnlyERP(FakeERP):
    def get_expected_payments(self, routes, date_from, date_to):
        payments = tuple(
            ExpectedPayment(
                f"amount-{index}", "customer-1", routes[0], "CHECK",
                str(1000 + index), str(1000 + index), Decimal("10.00"),
            )
            for index in range(30)
        )
        return ExpectedPaymentResult(payments, True, 5000, len(routes), "now")


def csv_bytes(deposit="D1", account_number="", routing_number=""):
    stream = io.StringIO(newline=""); writer = csv.writer(stream); writer.writerow(REQUIRED_HEADERS)
    base = ["08/20/2026 10:00:00 AM", "", "", "22 - Example", "", "Synthetic", deposit]
    writer.writerow(base + ["Business Check", "10.00", account_number, routing_number, "0007", "Warehouse"])
    writer.writerow(base + ["Virtual Credit", "10.00", "", "", "", "Warehouse"])
    return stream.getvalue().encode()


class ServiceTests(unittest.TestCase):
    def build_service(self, path, ids):
        repository = PaymentNotesRepository(engine=create_engine(f"sqlite:///{path}"))
        return PaymentNotesService(repository, FakeERP(),
            clock=lambda: datetime(2026, 8, 22, tzinfo=timezone.utc), id_factory=lambda: next(ids))

    def activate(self, service):
        route = service.import_route_reference(b"STORE,ROUTE\n22,AA\n", "routes.csv", "v1", "route-key", "actor")
        RouteReferenceSummary.model_validate(route)
        service.activate_route_reference(route["reference_id"], "activate-key", "actor")

    def test_service_construction_is_lazy_and_does_not_open_repository(self):
        engine = create_engine("sqlite://")
        calls = []
        original_connect = engine.connect

        def tracking_connect(*args, **kwargs):
            calls.append(True)
            return original_connect(*args, **kwargs)

        engine.connect = tracking_connect

        PaymentNotesService(PaymentNotesRepository(engine=engine), FakeERP())
        self.assertEqual(calls, [])

    def test_run_creation_signature_enrichment_and_review_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_service(Path(directory) / "service.db", iter(["r", "a", "run", "review"]))
            self.activate(service)
            run = service.create_run(csv_bytes(), "synthetic.csv", "2026-08-19", "2026-08-21", "run-key-1", "actor")
            RunDetail.model_validate(run)
            self.assertEqual(run["status"], "completed")
            item = run["items"][0]
            self.assertEqual(item["match"]["selected_payment_id"], "pay-1")
            self.assertEqual(item["match"]["candidates"][0]["signatures"][0]["filename"], "proof.png")
            review = service.review_item(run["run_id"], item["item_id"], ReviewRequest(
                decision="accept_candidate", selected_payment_id="pay-1", reason="Verified evidence",
                idempotency_key="review-key-1"), "actor")
            ReviewResponse.model_validate(review)
            self.assertEqual(review["current_review"]["selected_payment_id"], "pay-1")
            self.assertEqual(service.get_run(run["run_id"])["items"][0]["current_review"]["decision"], "accept_candidate")
            provenance = run["erp_provenance"]
            self.assertEqual(provenance["snapshot_mode"], "independent_bounded_read_only_queries")
            self.assertEqual(provenance["expected_payment_queries"][0]["source_object"], "KMTDTA.WHSIGPAY")
            self.assertEqual(provenance["signature_queries"][0]["source_object"], "KMTDTA.WHSIGIMG")
            stored = service.repository.get_run(run["run_id"])["payload"]
            private = stored["_private_evidence"]
            self.assertEqual(
                PaymentNotesRepository.sha256(private["erp_expected_payment_snapshots"][0]),
                provenance["expected_payment_queries"][0]["canonical_evidence_sha256"],
            )
            self.assertEqual(
                PaymentNotesRepository.sha256(private["erp_signature_snapshots"][0]),
                provenance["signature_queries"][0]["canonical_evidence_sha256"],
            )
            service.repository.engine.dispose()

    def test_persisted_bank_evidence_redacts_account_and_routing_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "redacted.db"
            service = self.build_service(path, iter(["r", "a", "run"]))
            self.activate(service)
            run = service.create_run(
                csv_bytes(account_number="SECRET-ACCOUNT", routing_number="SECRET-ROUTING"),
                "synthetic.csv", "2026-08-19", "2026-08-21", "run-key-1", "actor",
            )
            stored = service.repository.get_run(run["run_id"])["payload"]
            serialized = PaymentNotesRepository.canonical_json(stored["_private_evidence"])
            self.assertNotIn("SECRET-ACCOUNT", serialized)
            self.assertNotIn("SECRET-ROUTING", serialized)
            self.assertIn("[REDACTED]", serialized)
            service.repository.engine.dispose()

    def test_run_creation_fails_closed_without_active_route_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_service(Path(directory) / "no-route.db", iter(["run"]))
            with self.assertRaises(PaymentNotesPreconditionError):
                service.create_run(csv_bytes(), "synthetic.csv", "2026-08-19", "2026-08-21",
                                   "run-key-1", "actor")
            service.repository.engine.dispose()

    def test_route_conflict_marks_store_population_incomplete_and_blocks_auto_match(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_service(Path(directory) / "conflict.db", iter(["r", "a", "run"]))
            route = service.import_route_reference(
                b"STORE,ROUTE\n22,AA\n22,ZZ\n23,ZZ\n", "routes.csv", "conflicted-v1",
                "route-key", "actor")
            service.activate_route_reference(route["reference_id"], "activate-key", "actor")
            run = service.create_run(csv_bytes(), "synthetic.csv", "2026-08-19", "2026-08-21",
                                     "run-key-1", "actor")
            self.assertEqual(run["status"], "source_incomplete")
            self.assertEqual(run["items"][0]["match"]["disposition"], "SOURCE_INCOMPLETE")
            self.assertIsNone(run["items"][0]["match"]["selected_payment_id"])
            service.repository.engine.dispose()

    def test_partial_invoice_reference_does_not_query_or_assert_signature_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            erp = PartialInvoiceERP()
            repository = PaymentNotesRepository(
                engine=create_engine(f"sqlite:///{Path(directory) / 'partial.db'}")
            )
            ids = iter(["r", "a", "run"])
            service = PaymentNotesService(repository, erp,
                clock=lambda: datetime(2026, 8, 22, tzinfo=timezone.utc), id_factory=lambda: next(ids))
            self.activate(service)
            run = service.create_run(csv_bytes(), "synthetic.csv", "2026-08-19", "2026-08-21",
                                     "run-key-1", "actor")
            candidate = run["items"][0]["match"]["candidates"][0]
            self.assertEqual(erp.signature_calls, 0)
            self.assertEqual(candidate["signature_lookup_status"], "SIGNATURE_UNDETERMINED")
            self.assertEqual(candidate["signatures"], [])
            repository.engine.dispose()

    def test_manual_review_cannot_reuse_an_effectively_assigned_payment(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_service(Path(directory) / "manual.db", iter(["r", "a", "run", "review"]))
            self.activate(service)
            content = csv_bytes().decode().splitlines(); content.insert(2, content[1])
            run = service.create_run(("\n".join(content) + "\n").encode(), "synthetic.csv",
                                     "2026-08-19", "2026-08-21", "run-key-1", "actor")
            first, second = run["items"]
            service.review_item(run["run_id"], first["item_id"], ReviewRequest(
                decision="accept_candidate", selected_payment_id="pay-1", reason="First assignment",
                idempotency_key="review-key-1"), "actor")
            with self.assertRaises(PaymentNotesPreconditionError):
                service.review_item(run["run_id"], second["item_id"], ReviewRequest(
                    decision="accept_candidate", selected_payment_id="pay-1", reason="Duplicate assignment",
                    idempotency_key="review-key-2"), "actor")
            service.repository.engine.dispose()

    def test_truncated_amount_only_candidates_cannot_be_manually_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = PaymentNotesRepository(
                engine=create_engine(f"sqlite:///{Path(directory) / 'amount.db'}")
            )
            service = PaymentNotesService(repository, ManyAmountOnlyERP(),
                clock=lambda: datetime(2026, 8, 22, tzinfo=timezone.utc),
                id_factory=lambda: next(iter_ids))
            iter_ids = iter(["r", "a", "run"])
            self.activate(service)
            run = service.create_run(csv_bytes(), "synthetic.csv", "2026-08-19", "2026-08-21",
                                     "run-key-1", "actor")
            item = run["items"][0]
            self.assertFalse(item["match"]["candidate_population_complete"])
            with self.assertRaises(PaymentNotesPreconditionError):
                service.review_item(run["run_id"], item["item_id"], ReviewRequest(
                    decision="accept_candidate", selected_payment_id="amount-0",
                    reason="Attempt incomplete population", idempotency_key="review-key-1"), "actor")
            repository.engine.dispose()

    def test_prior_run_payment_use_blocks_new_selection_and_manual_accept(self):
        with tempfile.TemporaryDirectory() as directory:
            ids = iter(["r", "a", "run1", "run2"])
            service = self.build_service(Path(directory) / "reuse.db", ids)
            self.activate(service)
            service.create_run(csv_bytes("D1"), "first.csv", "2026-08-19", "2026-08-21",
                               "run-key-1", "actor")
            second = service.create_run(csv_bytes("D2"), "second.csv", "2026-08-19", "2026-08-21",
                                        "run-key-2", "actor")
            item = second["items"][0]
            self.assertEqual(item["match"]["disposition"], "CROSS_RUN_REUSE_POLICY_UNRESOLVED")
            self.assertTrue(item["match"]["cross_run_reuse_evidence"])
            with self.assertRaises(PaymentNotesPreconditionError):
                service.review_item(second["run_id"], item["item_id"], ReviewRequest(
                    decision="accept_candidate", selected_payment_id="pay-1",
                    reason="Attempt prior use", idempotency_key="review-key-1"), "actor")
            service.repository.engine.dispose()
