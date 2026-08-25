from __future__ import annotations

import csv
import io
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import fitz


DEFAULT_TESSERACT_PATH = (
    r"C:\Users\Josh.Corbit\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
)

_configured_tesseract_path: str | None = None


def _resolve_tesseract(path: str | None = None) -> str | None:
    candidates = (
        path,
        os.getenv("TESSERACT_CMD"),
        _configured_tesseract_path,
        DEFAULT_TESSERACT_PATH,
        shutil.which("tesseract"),
    )
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if candidate_path.exists() and candidate_path.is_file():
            return str(candidate_path)
    return None


def configure_tesseract(path: str | None = None) -> None:
    """Configure the existing local Tesseract runtime without requiring it.

    Document Intelligence remains importable when the optional Python wrapper
    is missing. OCR calls fail explicitly only when no local executable exists.
    """

    global _configured_tesseract_path
    _configured_tesseract_path = _resolve_tesseract(path)

    try:
        import pytesseract  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return

    if _configured_tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = _configured_tesseract_path


def tesseract_available() -> bool:
    """Report local executable availability without starting a subprocess."""

    return _resolve_tesseract() is not None


def tesseract_identity(
    *,
    timeout_seconds: float = 10.0,
) -> tuple[str | None, str | None]:
    executable = _resolve_tesseract()
    if executable is None:
        return None, None
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return "local_tesseract", None
    first_line = (completed.stdout or completed.stderr).splitlines()
    version = first_line[0].strip() if first_line else None
    return "local_tesseract", version


def _image_from_page(
    page: fitz.Page,
    *,
    clip: fitz.Rect | None,
    scale: float,
    max_dimension_pixels: int,
    max_pixels: int,
):
    from PIL import Image

    region = clip if clip is not None else page.rect
    pixel_width = max(1, math.ceil(float(region.width) * scale))
    pixel_height = max(1, math.ceil(float(region.height) * scale))
    pixel_area = pixel_width * pixel_height
    if (
        pixel_width > max_dimension_pixels
        or pixel_height > max_dimension_pixels
        or pixel_area > max_pixels
    ):
        raise RuntimeError(
            "OCR raster safety limit exceeded before page rendering: "
            f"{pixel_width}x{pixel_height} ({pixel_area} pixels); "
            f"limits are {max_dimension_pixels}px per dimension and {max_pixels} pixels."
        )
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        clip=clip,
        alpha=False,
    )
    return Image.frombytes(
        "RGB",
        [pixmap.width, pixmap.height],
        pixmap.samples,
    )


def _subprocess_ocr(
    image,
    *,
    psm: int,
    include_data: bool,
    timeout_seconds: float,
):
    executable = _resolve_tesseract()
    if executable is None:
        raise RuntimeError(
            "Local Tesseract OCR is unavailable. Configure TESSERACT_CMD or install Tesseract."
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    command = [executable, "stdin", "stdout", "--psm", str(psm)]
    if include_data:
        command.append("tsv")
    completed = subprocess.run(
        command,
        input=buffer.getvalue(),
        check=False,
        capture_output=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Local Tesseract OCR failed: {error or completed.returncode}")
    output = completed.stdout.decode("utf-8", errors="replace")
    if not include_data:
        return output

    rows = csv.DictReader(io.StringIO(output), delimiter="\t")
    columns: dict[str, list[Any]] = {
        key: []
        for key in (
            "level",
            "page_num",
            "block_num",
            "par_num",
            "line_num",
            "word_num",
            "left",
            "top",
            "width",
            "height",
            "conf",
            "text",
        )
    }
    integer_fields = set(columns) - {"conf", "text"}
    for row in rows:
        for key in columns:
            raw = row.get(key, "")
            if key in integer_fields:
                try:
                    columns[key].append(int(raw))
                except (TypeError, ValueError):
                    columns[key].append(0)
            else:
                columns[key].append(raw)
    return columns


def ocr_region(
    page: fitz.Page,
    *,
    clip: fitz.Rect | None = None,
    scale: float = 4.0,
    psm: int = 6,
    include_data: bool = False,
    timeout_seconds: float = 30.0,
    max_dimension_pixels: int = 10_000,
    max_pixels: int = 20_000_000,
):
    image = _image_from_page(
        page,
        clip=clip,
        scale=scale,
        max_dimension_pixels=max_dimension_pixels,
        max_pixels=max_pixels,
    )
    try:
        import pytesseract  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _subprocess_ocr(
            image,
            psm=psm,
            include_data=include_data,
            timeout_seconds=timeout_seconds,
        )

    configure_tesseract()
    if include_data:
        return pytesseract.image_to_data(
            image,
            config=f"--psm {psm}",
            output_type=pytesseract.Output.DICT,
            timeout=timeout_seconds,
        )
    return pytesseract.image_to_string(
        image,
        config=f"--psm {psm}",
        timeout=timeout_seconds,
    )
