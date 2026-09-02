from __future__ import annotations

import hashlib
import importlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import fitz
from fastapi import HTTPException
from sqlalchemy import create_engine

data_mysql = importlib.import_module("data.mysql")
service = importlib.import_module("modules.document_intelligence.service")
repository = importlib.import_module("modules.document_intelligence.repository")

TEST_ROOT = Path(tempfile.mkdtemp(prefix="etop-lockbox-route-guard-test-"))


class AsyncUpload:
    content_type = "application/pdf"

    def __init__(self, content: bytes, filename: str) -> None:
        self.filename = filename
        self.stream = io.BytesIO(content)
        self.closed = False

    async def read(self, size: int) -> bytes:
        return self.stream.read(size)

    async def close(self) -> None:
        self.closed = True


class GenericRouteRejectsLockboxDocumentsTests(unittest.IsolatedAsyncioTestCase):
    """A lockbox check remittance PDF processed through the generic
    /jobs/{job_id}/process route must not silently run through
    PNCLockboxParser - that parser does no customer/ERP matching and its
    result never feeds the governed lockbox_preparation reconciliation
    pipeline, so it would produce a materially different, weaker "current
    result" than the dedicated /jobs/{job_id}/lockbox/process route for the
    exact same document."""

    async def asyncSetUp(self) -> None:
        test_dir = Path(tempfile.mkdtemp(prefix="upload-", dir=TEST_ROOT))
        self.test_settings = SimpleNamespace(
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
        repository.settings = self.test_settings
        service.settings = self.test_settings
        engine = create_engine(
            f"sqlite:///{test_dir / 'data' / 'document-intelligence.db'}"
        )
        data_mysql._set_engine_override(engine)
        self.addCleanup(data_mysql._reset_engine_override)
        self.addCleanup(engine.dispose)

    async def test_lockbox_classified_upload_is_rejected_by_generic_process(
        self,
    ) -> None:
        buffer = io.BytesIO()
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text(
                (72, 72),
                "PNC Lockbox Transactions for Output "
                "Transaction Level Details",
            )
            document.save(buffer)
        pdf_bytes = buffer.getvalue()

        upload = AsyncUpload(pdf_bytes, "remittance.pdf")
        job = await service.create_upload_job(upload)

        with self.assertRaises(HTTPException) as raised:
            service.process_job(job["job_id"])
        self.assertEqual(raised.exception.status_code, 500)
        self.assertIn("lockbox", str(raised.exception.detail).lower())
        self.assertIn(
            "lockbox/process",
            str(raised.exception.detail),
        )

        failed_job = repository.get_job(job["job_id"])
        self.assertEqual(failed_job["status"], "failed")


if __name__ == "__main__":
    unittest.main()
