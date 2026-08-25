import re
from ..business_objects.models import PayerIdentity, OcrPageResult
from .normalization import last4


_EXPLICIT_CUSTOMER_ACCOUNT_PATTERNS = (
    re.compile(
        r"\b(?:apply|angly|post)(?:\s*(?:this|the))?"
        r"(?:\s*(?:payment|check))?\s*to\s*"
        r"(?:(?:k\s*&?\s*m)\s+)?(?:customer\s+)?"
        r"(?:account|acct)(?:\s*(?:no|number))?\s*[:#-]?\s*"
        r"(?P<number>\d{4,12})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:k\s*&?\s*m)\s+(?:customer\s+)?"
        r"(?:account|acct)(?:\s*(?:no|number))?\s*[:#-]?\s*"
        r"(?P<number>\d{4,12})\b",
        re.IGNORECASE,
    ),
)

_CHECK_ACCOUNT_PATTERN = re.compile(
    r"\b(?:account|acct)\s*[:#-]?\s*(?P<number>\d{6,7})\b",
    re.IGNORECASE,
)
_BANK_ACCOUNT_CONTEXT = re.compile(
    r"\b(?:bank|routing|transit|aba|micr|checking|savings|account\s+number)\b",
    re.IGNORECASE,
)
_CHECK_FOR_LABEL = re.compile(
    r"\b(?:for|f0r|ror)\b(?P<body>[^\n]*)",
    re.IGNORECASE,
)
_CHECK_FOR_ACCOUNT = re.compile(
    r"\b(?:account|acct)(?:\s*(?:no|number))?\s*[:#-]?\s*"
    r"(?P<number>\d(?:[\s._-]*\d){5,6})(?!\d)",
    re.IGNORECASE,
)
_CHECK_FOR_NUMBER = re.compile(
    r"(?<!\d)(?P<number>\d(?:[\s._-]*\d){5,6})(?!\d)",
    re.IGNORECASE,
)
_CHECK_FOR_NONCUSTOMER_CONTEXT = re.compile(
    r"\b(?:invoice|inv|purchase\s+order|p\.?\s*o\.?|routing|transit|"
    r"aba|micr|checking|savings|bank)\b",
    re.IGNORECASE,
)


def _ocr_line_windows(text: str) -> list[str]:
    """Return OCR lines plus adjacent-line joins in preserved order."""

    lines = [" ".join(line.split()).strip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    windows = list(lines)
    windows.extend(
        f"{left} {right}"
        for left, right in zip(lines, lines[1:])
    )
    return windows


def explicit_customer_account_directives(text: str) -> list[dict[str, str]]:
    """Return unique payer-authored customer-account directives.

    Generic ``Account`` labels are deliberately excluded because a check also
    contains a bank-account number. Only an explicit apply/post instruction or
    a K&M-labelled customer account may enter this evidence set.
    """

    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in _ocr_line_windows(text):
        for pattern in _EXPLICIT_CUSTOMER_ACCOUNT_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            number = match.group("number")
            key = (number, line.casefold())
            if key not in seen:
                seen.add(key)
                matches.append(
                    {
                        "customer_number": number,
                        "evidence_text": line,
                    }
                )
            break
    return matches


def check_customer_account_directives(text: str) -> list[dict[str, str]]:
    """Return explicit customer-account evidence from a bounded check image.

    The existing apply/post and K&M-labelled rules remain authoritative.  A
    bare ``Account:`` or ``Memo: Acct #`` label is admitted only in this
    check-image-specific fallback, only for a six- or seven-digit K&M
    customer number (MaddenCo TMCUST.CUNUMBER is decimal(7,0)), and never
    when the OCR line identifies a bank, routing, MICR, checking, or
    savings account.  The separator is optional because check-image OCR often
    drops a colon or number sign even when it is plainly visible in the image.
    """

    matches = explicit_customer_account_directives(text)
    seen_numbers = {item["customer_number"] for item in matches}
    for line in _ocr_line_windows(text):
        if _BANK_ACCOUNT_CONTEXT.search(line):
            continue
        match = _CHECK_ACCOUNT_PATTERN.search(line)
        if not match:
            continue
        number = match.group("number")
        if number in seen_numbers:
            continue
        seen_numbers.add(number)
        matches.append(
            {
                "customer_number": number,
                "evidence_text": line,
            }
        )
    return matches


def check_for_customer_directives(text: str) -> list[dict[str, str]]:
    """Return six- or seven-digit customer-number evidence from a check
    ``FOR`` line.

    MaddenCo customer numbers (TMCUST.CUNUMBER) are decimal(7,0) — a real
    customer number can be six or seven digits. This evidence is
    intentionally separate from the stronger apply/account directives. It
    is consumed only as the final account-number fallback after invoice
    ownership, explicit check account instructions, and governed K&M
    statement evidence. Generic six- or seven-digit values outside a
    check-bounded ``FOR`` line are never admitted. A line explicitly
    labelled as an invoice, purchase order, bank, routing, or MICR
    reference is also rejected unless it contains an explicit
    ``Account``/``Acct`` label. The trailing digit-boundary check in this
    regex family rejects any longer run (e.g. a bank routing/MICR number),
    so widening to seven digits does not admit eight-or-more-digit values.
    """

    matches: list[dict[str, str]] = []
    seen_numbers: set[str] = set()
    for line in _ocr_line_windows(text):
        label = _CHECK_FOR_LABEL.search(line)
        if not label:
            continue
        body = label.group("body")
        explicit_account = _CHECK_FOR_ACCOUNT.search(body)
        if explicit_account:
            number_match = explicit_account
        elif _CHECK_FOR_NONCUSTOMER_CONTEXT.search(body):
            continue
        else:
            number_match = _CHECK_FOR_NUMBER.search(body)
        if not number_match:
            continue
        number = re.sub(r"\D", "", number_match.group("number"))
        if len(number) not in (6, 7) or number in seen_numbers:
            continue
        seen_numbers.add(number)
        matches.append(
            {
                "customer_number": number,
                "evidence_text": line,
            }
        )
    return matches

def parse_payer_identity(pages: list[OcrPageResult], routing_number=None, bank_account=None, check_number=None):
    text="\n".join(p.text for p in pages if p.text)
    directives = explicit_customer_account_directives(text)
    directive_numbers = {
        item["customer_number"] for item in directives
    }
    cust = next(iter(directive_numbers)) if len(directive_numbers) == 1 else None
    state=zip_code=None
    m=re.search(r"\b([A-Z]{2})\s+(\d{5})(?:-\d{4})?\b", text.upper())
    if m: state,zip_code=m.groups()
    payer=None
    for line in [x.strip() for x in text.splitlines() if x.strip()]:
        u=line.upper()
        if any(t in u for t in ("PAY TO","DOLLARS","AUTHORIZED","BANK","CHECK NO")): continue
        if 3 <= len(line) <= 80 and re.search("[A-Za-z]", line):
            payer=line; break
    return PayerIdentity(
        payer_name=payer, state=state, postal_code=zip_code,
        printed_customer_number=cust, routing_number=routing_number,
        bank_account_last4=last4(bank_account), check_number=check_number,
        memo_text=text[:1000] or None, source_pages=[p.page_number for p in pages]
    )
