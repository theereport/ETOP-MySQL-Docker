from pathlib import Path

import fitz


def extract_pdf_text(pdf_path: Path) -> dict:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages: list[dict] = []
    total_characters = 0

    with fitz.open(pdf_path) as document:
        for page_index, page in enumerate(document):
            text = page.get_text("text") or ""
            normalized = text.strip()
            total_characters += len(normalized)

            lower_text = normalized.lower()
            is_header_only = (
                len(normalized) < 120
                and "output report" in lower_text
                and "transaction information" not in lower_text
                and "transaction level details" not in lower_text
            )

            requires_ocr = (
                len(normalized) < 25
                or is_header_only
                or "supplemental images" in lower_text
            )

            pages.append(
                {
                    "page_number": page_index + 1,
                    "text": normalized,
                    "character_count": len(normalized),
                    "requires_ocr": requires_ocr,
                }
            )

    full_text = "\n\n".join(
        page["text"]
        for page in pages
        if page["text"]
    )

    return {
        "page_count": len(pages),
        "character_count": total_characters,
        "pages": pages,
        "full_text": full_text,
        "ocr_recommended": any(page["requires_ocr"] for page in pages),
    }
