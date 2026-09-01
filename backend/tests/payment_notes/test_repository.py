import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from sqlalchemy import create_engine

from modules.payment_notes.repository import PaymentNotesIntegrityError, PaymentNotesRepository


def repo(tmp_path):
    path = tmp_path / "payment-notes.db"
    repository = PaymentNotesRepository(engine=create_engine(f"sqlite:///{path}"))
    repository.initialize()
    return repository, path


def route_payload():
    return {"source_name": "routes.csv", "source_sha256": "a" * 64, "source_size": 10,
            "parser_version": "v1", "input_row_count": 1, "blank_row_count": 0,
            "duplicate_mapping_count": 0, "raw_mappings": [],
            "mappings": [{"store": "22", "route": "AA"}], "by_store": {"22": ["AA"]},
            "conflicts": {}, "warnings": []}


class RepositoryTests(unittest.TestCase):
    def test_content_idempotency_activation_chain_and_payload_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            repository, path = repo(Path(directory))
            first = repository.create_route_reference(reference_id="r1", version_label="v1", payload=route_payload(),
                actor="u", occurred_at="2026-08-22T00:00:00+00:00", idempotency_key="route-key-1")
            replay = repository.create_route_reference(reference_id="r2", version_label="v1", payload=route_payload(),
                actor="u2", occurred_at="2026-08-22T00:01:00+00:00", idempotency_key="route-key-2")
            self.assertEqual(replay["reference_id"], first["reference_id"])
            repository.activate_route_reference(activation_id="a1", reference_id="r1", actor="u",
                occurred_at="2026-08-22T00:02:00+00:00", idempotency_key="activate-1")
            self.assertEqual(repository.get_active_route_reference()["reference_id"], "r1")
            # Append-only is enforced by convention in the repository layer
            # (it never issues UPDATE/DELETE against these tables), not by a
            # DB trigger - MySQL trigger creation needs a privilege the etop
            # account doesn't have.
            connection = sqlite3.connect(path)
            connection.execute("UPDATE pn_route_references SET payload_json = ? WHERE reference_id = 'r1'",
                               (json.dumps({"tampered": True}),))
            connection.commit(); connection.close()
            with self.assertRaises(PaymentNotesIntegrityError):
                repository.get_route_reference("r1")
            repository.engine.dispose()

    def test_two_route_activation_writers_form_one_valid_serial_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "concurrent.db"
            repository = PaymentNotesRepository(
                engine=create_engine(
                    f"sqlite:///{path}",
                    connect_args={"timeout": 10, "check_same_thread": False},
                )
            )
            repository.initialize()
            for reference_id, version in (("r1", "v1"), ("r2", "v2")):
                payload = {**route_payload(), "source_sha256": reference_id[1] * 64}
                repository.create_route_reference(
                    reference_id=reference_id, version_label=version, payload=payload,
                    actor="seed", occurred_at="2026-08-22T00:00:00+00:00",
                    idempotency_key=f"route-{reference_id}",
                )
            barrier = threading.Barrier(3)
            errors = []

            def activate(reference_id, activation_id):
                try:
                    barrier.wait()
                    repository.activate_route_reference(
                        activation_id=activation_id, reference_id=reference_id,
                        actor=activation_id, occurred_at="2026-08-22T00:01:00+00:00",
                        idempotency_key=f"activate-{activation_id}",
                    )
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            threads = [
                threading.Thread(target=activate, args=("r1", "a1")),
                threading.Thread(target=activate, args=("r2", "a2")),
            ]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            self.assertIn(repository.get_active_route_reference()["reference_id"], {"r1", "r2"})
            connection = sqlite3.connect(path)
            rows = connection.execute(
                "SELECT previous_hash, record_hash FROM pn_route_reference_activations ORDER BY rowid"
            ).fetchall()
            connection.close()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "0" * 64)
            self.assertEqual(rows[1][0], rows[0][1])
            repository.engine.dispose()
