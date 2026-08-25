def select_pages_for_ocr(extraction: dict) -> list[int]:
    selected = []
    for page in extraction.get("pages", []):
        n = int(page["page_number"])
        text = " ".join((page.get("text") or "").lower().split())
        if page.get("requires_ocr") or ("supplemental images" in text) or (text.startswith("output report") and len(text) < 100):
            selected.append(n)
    return sorted(set(selected))
