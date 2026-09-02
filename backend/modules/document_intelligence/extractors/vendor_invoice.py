from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from time import monotonic
from typing import Any

import fitz

from ..ocr_engine import ocr_region, tesseract_identity
from .pdf_text import extract_pdf_text


VENDOR_INVOICE_EXTRACTION_VERSION = "vendor-invoice-extraction.v2"
VENDOR_INVOICE_OCR_PROFILE = "vendor-invoice-local-tesseract-psm6.v1"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _native_lines(page: fitz.Page) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    page_dict = page.get_text("dict")
    page_number = int(page.number) + 1
    page_width = round(float(page.rect.width), 2)
    page_height = round(float(page.rect.height), 2)
    for block_number, block in enumerate(page_dict.get("blocks", []), start=1):
        if not isinstance(block, dict):
            continue
        for block_line_number, raw_line in enumerate(
            block.get("lines", []),
            start=1,
        ):
            if not isinstance(raw_line, dict):
                continue
            text = _clean(
                "".join(
                    str(span.get("text") or "")
                    for span in raw_line.get("spans", [])
                    if isinstance(span, dict)
                )
            )
            if not text:
                continue
            bbox = raw_line.get("bbox")
            lines.append(
                {
                    "line_number": len(lines) + 1,
                    "fragment_id": (
                        f"p{page_number}-native-b{block_number}-l{block_line_number}"
                    ),
                    "block_number": block_number,
                    "block_line_number": block_line_number,
                    "text": text,
                    "bbox": (
                        [round(float(value), 2) for value in bbox]
                        if isinstance(bbox, (list, tuple)) and len(bbox) == 4
                        else None
                    ),
                    "confidence": None,
                    "source_method": "native_pdf_text",
                    "page_width": page_width,
                    "page_height": page_height,
                }
            )
    return lines


def _ocr_lines(
    page: fitz.Page,
    *,
    scale: float = 3.0,
    timeout_seconds: float = 30.0,
    max_dimension_pixels: int = 10_000,
    max_pixels: int = 20_000_000,
) -> tuple[list[dict], float | None]:
    data = ocr_region(
        page,
        scale=scale,
        psm=6,
        include_data=True,
        timeout_seconds=timeout_seconds,
        max_dimension_pixels=max_dimension_pixels,
        max_pixels=max_pixels,
    )
    if not isinstance(data, dict):
        raise RuntimeError("Local OCR did not return word-location evidence.")

    grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    texts = data.get("text", [])
    confidences: list[float] = []
    for index, raw_text in enumerate(texts):
        text = _clean(raw_text)
        try:
            confidence = float(data.get("conf", ["-1"])[index])
        except (IndexError, TypeError, ValueError):
            confidence = -1.0
        if not text or confidence < 0:
            continue
        key = (
            int(data.get("block_num", [0])[index]),
            int(data.get("par_num", [0])[index]),
            int(data.get("line_num", [0])[index]),
        )
        word = {
            "text": text,
            "left": float(data.get("left", [0])[index]) / scale,
            "top": float(data.get("top", [0])[index]) / scale,
            "width": float(data.get("width", [0])[index]) / scale,
            "height": float(data.get("height", [0])[index]) / scale,
            "confidence": confidence / 100.0,
        }
        grouped[key].append(word)
        confidences.append(word["confidence"])

    page_number = int(page.number) + 1
    page_width = round(float(page.rect.width), 2)
    page_height = round(float(page.rect.height), 2)
    raw_lines: list[dict[str, Any]] = []
    for words in grouped.values():
        words.sort(key=lambda item: item["left"])
        left = min(item["left"] for item in words)
        top = min(item["top"] for item in words)
        right = max(item["left"] + item["width"] for item in words)
        bottom = max(item["top"] + item["height"] for item in words)
        raw_lines.append(
            {
                "text": " ".join(item["text"] for item in words),
                "bbox": [
                    round(left, 2),
                    round(top, 2),
                    round(right, 2),
                    round(bottom, 2),
                ],
                "confidence": round(
                    sum(item["confidence"] for item in words) / len(words),
                    6,
                ),
                "source_method": "local_tesseract_ocr",
                "page_width": page_width,
                "page_height": page_height,
            }
        )
    raw_lines.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    lines: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_lines, start=1):
        lines.append(
            {
                **line,
                "line_number": line_number,
                "fragment_id": f"p{page_number}-ocr-l{line_number}",
            }
        )
    average = (
        round(sum(confidences) / len(confidences), 6)
        if confidences
        else None
    )
    return lines, average


def extract_vendor_invoice_text(
    pdf_path: Path,
    native_extraction: dict[str, Any] | None = None,
    *,
    max_ocr_pages: int = 25,
    ocr_page_timeout_seconds: float = 30.0,
    ocr_total_timeout_seconds: float = 120.0,
    max_ocr_render_dimension_pixels: int = 10_000,
    max_ocr_render_pixels: int = 20_000_000,
) -> dict[str, Any]:
    """Extract vendor-invoice text with bounded, local OCR fallback.

    Native PDF text remains first priority. Tesseract is invoked only on pages
    the existing extraction contract marked as requiring OCR. Page text,
    method, confidence, and bounding boxes are preserved for field evidence.
    """

    base = native_extraction or extract_pdf_text(pdf_path)
    native_pages = {
        int(page["page_number"]): page
        for page in base.get("pages", [])
        if isinstance(page, dict) and page.get("page_number") is not None
    }
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    attempted_pages: list[int] = []
    completed_pages: list[int] = []
    failed_pages: list[int] = []
    skipped_pages: list[int] = []
    ocr_confidences: list[float] = []
    engine_name: str | None = None
    engine_version: str | None = None
    engine_identity_checked = False
    ocr_started_at = monotonic()

    with fitz.open(pdf_path) as document:
        if document.needs_pass:
            raise ValueError("Encrypted PDF invoices are not supported by this intake.")
        if document.page_count < 1:
            raise ValueError("The PDF invoice contains no pages.")
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            native = native_pages.get(page_number, {})
            native_text = str(native.get("text") or "").strip()
            requires_ocr = bool(native.get("requires_ocr"))
            lines = _native_lines(page)
            text = native_text
            method = "native_pdf_text"
            page_ocr_confidence: float | None = None
            ocr_status = "not_required"
            ocr_error: str | None = None

            if requires_ocr:
                elapsed = monotonic() - ocr_started_at
                remaining_total = ocr_total_timeout_seconds - elapsed
                if len(attempted_pages) >= max_ocr_pages:
                    skipped_pages.append(page_number)
                    ocr_status = "skipped_page_limit"
                    ocr_error = (
                        "Targeted OCR was not attempted because the governed "
                        f"technical limit is {max_ocr_pages} pages per document."
                    )
                    warnings.append(
                        f"Page {page_number} requires OCR but was not attempted: {ocr_error}"
                    )
                elif remaining_total <= 0:
                    skipped_pages.append(page_number)
                    ocr_status = "skipped_time_limit"
                    ocr_error = (
                        "Targeted OCR was not attempted because the governed "
                        f"{ocr_total_timeout_seconds:g}-second document work limit was reached."
                    )
                    warnings.append(
                        f"Page {page_number} requires OCR but was not attempted: {ocr_error}"
                    )
                else:
                    if not engine_identity_checked:
                        engine_name, engine_version = tesseract_identity(
                            timeout_seconds=min(10.0, remaining_total)
                        )
                        engine_identity_checked = True
                    remaining_total = (
                        ocr_total_timeout_seconds
                        - (monotonic() - ocr_started_at)
                    )
                    if remaining_total <= 0:
                        skipped_pages.append(page_number)
                        ocr_status = "skipped_time_limit"
                        ocr_error = (
                            "Targeted OCR was not attempted because the governed "
                            f"{ocr_total_timeout_seconds:g}-second document work limit "
                            "was reached while identifying the local OCR engine."
                        )
                        warnings.append(
                            f"Page {page_number} requires OCR but was not attempted: {ocr_error}"
                        )
                    else:
                        page_timeout = min(
                            ocr_page_timeout_seconds,
                            remaining_total,
                        )
                        attempted_pages.append(page_number)
                        ocr_status = "attempted"
                        try:
                            ocr_lines, page_ocr_confidence = _ocr_lines(
                                page,
                                timeout_seconds=page_timeout,
                                max_dimension_pixels=max_ocr_render_dimension_pixels,
                                max_pixels=max_ocr_render_pixels,
                            )
                            ocr_text = "\n".join(
                                item["text"] for item in ocr_lines
                            ).strip()
                            if not ocr_text:
                                raise RuntimeError("Local OCR returned no readable text.")
                            lines = ocr_lines
                            text = ocr_text
                            method = "local_tesseract_ocr"
                            ocr_status = "completed"
                            completed_pages.append(page_number)
                            if page_ocr_confidence is not None:
                                ocr_confidences.append(page_ocr_confidence)
                        except Exception as exc:  # page-local degradation is reviewable
                            failed_pages.append(page_number)
                            ocr_status = "failed"
                            ocr_error = f"{type(exc).__name__}: {exc}"
                            warnings.append(
                                f"Page {page_number} OCR failed and requires human review: {ocr_error}"
                            )

            pages.append(
                {
                    "page_number": page_number,
                    "page_width": round(float(page.rect.width), 2),
                    "page_height": round(float(page.rect.height), 2),
                    "text": text,
                    "character_count": len(text),
                    "requires_ocr": requires_ocr,
                    "text_source": method,
                    "ocr_status": ocr_status,
                    "ocr_confidence": page_ocr_confidence,
                    "ocr_error": ocr_error,
                    "lines": lines,
                }
            )

    full_text = "\n\n".join(page["text"] for page in pages if page["text"])
    native_text_pages = [
        int(page["page_number"])
        for page in pages
        if page["text_source"] == "native_pdf_text" and page["text"]
    ]
    ocr_text_pages = [
        int(page["page_number"])
        for page in pages
        if page["text_source"] == "local_tesseract_ocr" and page["text"]
    ]
    if native_text_pages and ocr_text_pages:
        text_source_summary = "mixed_native_and_ocr"
    elif native_text_pages:
        text_source_summary = "native_pdf_text"
    elif ocr_text_pages:
        text_source_summary = "local_tesseract_ocr"
    else:
        text_source_summary = "unavailable"
    average_ocr_confidence = (
        round(sum(ocr_confidences) / len(ocr_confidences), 6)
        if ocr_confidences
        else None
    )
    return {
        "extraction_version": VENDOR_INVOICE_EXTRACTION_VERSION,
        "ocr_profile_version": VENDOR_INVOICE_OCR_PROFILE,
        "page_count": len(pages),
        "character_count": len(full_text),
        "pages": pages,
        "full_text": full_text,
        "native_text_pages": native_text_pages,
        "ocr_text_pages": ocr_text_pages,
        "text_source_summary": text_source_summary,
        "native_ocr_recommended": bool(base.get("ocr_recommended")),
        "ocr_recommended": bool(failed_pages),
        "ocr_attempted_pages": attempted_pages,
        "ocr_completed_pages": completed_pages,
        "ocr_failed_pages": failed_pages,
        "ocr_skipped_pages": skipped_pages,
        "ocr_page_limit": max_ocr_pages,
        "ocr_page_timeout_seconds": ocr_page_timeout_seconds,
        "ocr_total_timeout_seconds": ocr_total_timeout_seconds,
        "ocr_render_dimension_limit_pixels": max_ocr_render_dimension_pixels,
        "ocr_render_area_limit_pixels": max_ocr_render_pixels,
        "ocr_engine": engine_name if attempted_pages else None,
        "ocr_engine_version": engine_version if attempted_pages else None,
        "ocr_average_confidence": average_ocr_confidence,
        "warnings": warnings,
    }
