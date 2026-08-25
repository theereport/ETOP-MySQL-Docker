from __future__ import annotations

import re
from collections import defaultdict

from .ocr_engine import ocr_region
from .resolution.payer_parser import (
    check_customer_account_directives,
    check_for_customer_directives,
)
from .vision_models import CustomerIdentity, TextBlock, TextLine


PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]?)?"
    r"(?:\(?\d{3}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}(?!\d)"
)
CITY_STATE_ZIP_RE = re.compile(
    r"^(?P<city>[A-Za-z .'\-]+?),?\s+"
    r"(?P<state>[A-Z]{2})\s+"
    r"(?P<zip>\d{5}(?:-\d{4})?)$",
    re.IGNORECASE,
)
STREET_RE = re.compile(
    r"^\d+\s+.+\b("
    r"street|st|road|rd|avenue|ave|boulevard|blvd|drive|dr|"
    r"lane|ln|court|ct|circle|cir|highway|hwy|route|rte|parkway|pkwy|"
    r"way|place|pl|terrace|ter"
    r")\.?$",
    re.IGNORECASE,
)
ADDRESS2_RE = re.compile(
    r"^(suite|ste|unit|building|bldg|floor|fl|department|dept|"
    r"po box|p\.o\. box)\b",
    re.IGNORECASE,
)
NAVIGATION_RE = re.compile(
    r"back\s+to\s+(the\s+)?table\s+of\s+contents",
    re.IGNORECASE,
)
MICR_RE = re.compile(r"^[^A-Za-z]*\d{6,}[^A-Za-z]*$")

HARD_REJECT_TERMS = (
    "back to table of contents",
    "table of contents",
    "transaction information",
    "transaction level details",
    "envelope and check image",
    "output report",
)
CHECK_REJECT_TERMS = (
    "pay to the order",
    "dollars",
    "memo",
    "authorized signature",
    "security features",
    "void",
)
BANK_TERMS = (
    "bank",
    "federal credit union",
    "credit union",
    "member fdic",
    "citizens",
    "chase",
    "wells fargo",
    "huntington",
    "fifth third",
    "regions",
    "pnc",
    "bmo",
)


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _hard_reject(value: str) -> bool:
    lowered = value.lower()
    return (
        NAVIGATION_RE.search(value) is not None
        or any(term in lowered for term in HARD_REJECT_TERMS)
        or MICR_RE.fullmatch(value) is not None
    )


def _looks_like_name(value: str) -> bool:
    lowered = value.lower()

    if _hard_reject(value):
        return False
    if len(value) < 3 or len(value) > 120:
        return False
    if any(term in lowered for term in CHECK_REJECT_TERMS + BANK_TERMS):
        return False
    if PHONE_RE.search(value):
        return False
    if CITY_STATE_ZIP_RE.match(value):
        return False
    if STREET_RE.match(value):
        return False
    if len(re.findall(r"[A-Za-z]", value)) < 3:
        return False

    return True


def _ocr_lines(page, region, *, psm: int = 11) -> list[TextLine]:
    data = ocr_region(
        page,
        clip=region.to_rect(),
        scale=4.0,
        psm=psm,
        include_data=True,
    )

    grouped = defaultdict(list)
    texts = data.get("text", [])

    for index, raw_text in enumerate(texts):
        text = _clean(str(raw_text))
        confidence = float(data.get("conf", ["-1"])[index] or -1)

        if not text or confidence < 20 or _hard_reject(text):
            continue

        key = (
            int(data["block_num"][index]),
            int(data["par_num"][index]),
            int(data["line_num"][index]),
        )
        grouped[key].append(
            {
                "text": text,
                "left": float(data["left"][index]),
                "top": float(data["top"][index]),
                "width": float(data["width"][index]),
                "height": float(data["height"][index]),
            }
        )

    lines = []
    scale = 4.0

    for words in grouped.values():
        words.sort(key=lambda item: item["left"])
        line_text = " ".join(item["text"] for item in words)

        if _hard_reject(line_text):
            continue

        lines.append(
            TextLine(
                text=line_text,
                x0=min(item["left"] for item in words) / scale + region.x0,
                y0=min(item["top"] for item in words) / scale + region.y0,
                x1=max(
                    item["left"] + item["width"] for item in words
                ) / scale + region.x0,
                y1=max(
                    item["top"] + item["height"] for item in words
                ) / scale + region.y0,
            )
        )

    lines.sort(key=lambda line: (line.y0, line.x0))
    return lines


def _group_lines(lines: list[TextLine]) -> list[TextBlock]:
    blocks = []

    for line in lines:
        placed = False

        for block in blocks:
            vertical_gap = line.y0 - block.y1
            horizontal_overlap = not (
                line.x1 < block.x0 - 36
                or line.x0 > block.x1 + 36
            )

            if (
                -4 <= vertical_gap <= max(line.height * 2.0, 22)
                and horizontal_overlap
            ):
                block.lines.append(line)
                placed = True
                break

        if not placed:
            blocks.append(TextBlock(lines=[line]))

    return blocks


def _parse_block(block: TextBlock) -> CustomerIdentity:
    lines = [
        _clean(line.text)
        for line in block.lines
        if line.text.strip() and not _hard_reject(line.text)
    ]

    identity = CustomerIdentity(
        matched_block_text="\n".join(lines),
        matched_block_x0=block.x0,
        matched_block_y0=block.y0,
        matched_block_x1=block.x1,
        matched_block_y1=block.y1,
    )

    if not lines:
        return identity

    for line in lines:
        match = PHONE_RE.search(line)
        if match:
            identity.customer_phone = match.group(0).strip()
            break

    address_index = None
    city_index = None

    for index, line in enumerate(lines):
        if STREET_RE.match(line):
            identity.customer_address_line_1 = line
            address_index = index

            if index + 1 < len(lines) and ADDRESS2_RE.match(lines[index + 1]):
                identity.customer_address_line_2 = lines[index + 1]

            break

    for index, line in enumerate(lines):
        match = CITY_STATE_ZIP_RE.match(line)

        if match:
            identity.customer_city = match.group("city").strip(" ,")
            identity.customer_state = match.group("state").upper()
            identity.customer_postal_code = match.group("zip")
            city_index = index
            break

    anchor = address_index if address_index is not None else city_index

    if anchor is not None:
        for index in range(anchor - 1, -1, -1):
            if _looks_like_name(lines[index]):
                identity.customer_name = lines[index]
                break

    if not identity.customer_name:
        for line in lines:
            if _looks_like_name(line):
                identity.customer_name = line
                break

    score = 0.0
    evidence = []

    if identity.customer_name:
        score += 0.30
        evidence.append("business or payer name")

    if identity.customer_address_line_1:
        score += 0.25
        evidence.append("street address")

    if (
        identity.customer_city
        and identity.customer_state
        and identity.customer_postal_code
    ):
        score += 0.30
        evidence.append("city/state/ZIP")

    if identity.customer_phone:
        score += 0.25
        evidence.append("phone number")

    if 2 <= len(lines) <= 8:
        score += 0.05
        evidence.append("compact identity block")

    lowered = block.text.lower()

    if any(term in lowered for term in BANK_TERMS):
        score -= 0.40

    if any(term in lowered for term in CHECK_REJECT_TERMS):
        score -= 0.25

    if any(term in lowered for term in HARD_REJECT_TERMS):
        score = 0.0

    identity.confidence = max(0.0, min(round(score, 4), 0.99))
    identity.evidence = evidence
    return identity


def _in_payee_band(identity: CustomerIdentity, lines: list[TextLine]) -> bool:
    """Reject a name printed as the check payee, not the payer identity."""

    for line in lines:
        lowered = line.text.lower()
        if "pay to" not in lowered or "order" not in lowered:
            continue
        same_band = not (
            identity.matched_block_y1 < line.y0 - max(line.height, 8)
            or identity.matched_block_y0 > line.y1 + max(line.height * 2, 16)
        )
        to_the_right = identity.matched_block_x1 >= line.x0
        if same_band and to_the_right:
            return True
    return False


def extract_customer_identity(page, region) -> CustomerIdentity:
    line_groups = [
        _ocr_lines(page, region, psm=psm)
        for psm in (11, 6)
    ]
    candidates: list[CustomerIdentity] = []
    directive_evidence: list[dict[str, str]] = []
    for_directive_evidence: list[dict[str, str]] = []
    seen: set[tuple[str, int, int]] = set()
    for lines in line_groups:
        directive_evidence.extend(
            check_customer_account_directives(
                "\n".join(line.text for line in lines)
            )
        )
        for_directive_evidence.extend(
            check_for_customer_directives(
                "\n".join(line.text for line in lines)
            )
        )
        for block in _group_lines(lines):
            candidate = _parse_block(block)
            if _in_payee_band(candidate, lines):
                continue
            key = (
                candidate.matched_block_text.upper(),
                round(candidate.matched_block_x0),
                round(candidate.matched_block_y0),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    candidates = [
        candidate
        for candidate in candidates
        if candidate.customer_name
        or candidate.customer_address_line_1
        or candidate.customer_postal_code
    ]

    directive_by_number: dict[str, str] = {}
    for directive in directive_evidence:
        number = str(directive.get("customer_number") or "").strip()
        evidence_text = str(directive.get("evidence_text") or "").strip()
        if number and number not in directive_by_number:
            directive_by_number[number] = evidence_text

    for_directive_by_number: dict[str, str] = {}
    for directive in for_directive_evidence:
        number = str(directive.get("customer_number") or "").strip()
        evidence_text = str(directive.get("evidence_text") or "").strip()
        if number and number not in for_directive_by_number:
            for_directive_by_number[number] = evidence_text

    if (
        not candidates
        and not directive_by_number
        and not for_directive_by_number
    ):
        empty = CustomerIdentity()
        empty.check_region_x0 = region.x0
        empty.check_region_y0 = region.y0
        empty.check_region_x1 = region.x1
        empty.check_region_y1 = region.y1
        return empty

    if candidates:
        candidates.sort(
            key=lambda item: (
                item.confidence,
                bool(item.customer_postal_code),
                bool(item.customer_address_line_1),
                bool(item.customer_name),
            ),
            reverse=True,
        )
        winner = candidates[0]
    else:
        winner = CustomerIdentity()

    winner.printed_customer_number_candidates = sorted(directive_by_number)
    if len(directive_by_number) == 1:
        number, evidence_text = next(iter(directive_by_number.items()))
        winner.printed_customer_number = number
        winner.printed_customer_number_evidence = evidence_text
        winner.confidence = max(winner.confidence, 0.95)
        winner.evidence = list(
            dict.fromkeys(
                (*winner.evidence, "explicit payer customer-account directive")
            )
        )
    winner.for_customer_number_candidates = sorted(for_directive_by_number)
    if len(for_directive_by_number) == 1:
        number, evidence_text = next(iter(for_directive_by_number.items()))
        winner.for_customer_number = number
        winner.for_customer_number_evidence = evidence_text
        winner.evidence = list(
            dict.fromkeys(
                (*winner.evidence, "check FOR-line customer-number candidate")
            )
        )
    winner.check_region_x0 = region.x0
    winner.check_region_y0 = region.y0
    winner.check_region_x1 = region.x1
    winner.check_region_y1 = region.y1
    return winner
