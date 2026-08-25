from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PageType = Literal[
    "transaction",
    "remittance",
    "invoice",
    "statement",
    "blank",
    "unknown",
]


@dataclass
class TextLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 0.0)


@dataclass
class TextBlock:
    lines: list[TextLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())

    @property
    def x0(self) -> float:
        return min((line.x0 for line in self.lines), default=0.0)

    @property
    def y0(self) -> float:
        return min((line.y0 for line in self.lines), default=0.0)

    @property
    def x1(self) -> float:
        return max((line.x1 for line in self.lines), default=0.0)

    @property
    def y1(self) -> float:
        return max((line.y1 for line in self.lines), default=0.0)


@dataclass
class CustomerIdentity:
    printed_customer_number: str = ""
    printed_customer_number_evidence: str = ""
    printed_customer_number_candidates: list[str] = field(default_factory=list)
    for_customer_number: str = ""
    for_customer_number_evidence: str = ""
    for_customer_number_candidates: list[str] = field(default_factory=list)
    customer_name: str = ""
    customer_phone: str = ""
    customer_address_line_1: str = ""
    customer_address_line_2: str = ""
    customer_city: str = ""
    customer_state: str = ""
    customer_postal_code: str = ""
    confidence: float = 0.0
    matched_block_text: str = ""
    evidence: list[str] = field(default_factory=list)

    matched_block_x0: float = 0.0
    matched_block_y0: float = 0.0
    matched_block_x1: float = 0.0
    matched_block_y1: float = 0.0

    check_region_x0: float = 0.0
    check_region_y0: float = 0.0
    check_region_x1: float = 0.0
    check_region_y1: float = 0.0

    def as_transaction_fields(self) -> dict[str, Any]:
        return {
            "printed_customer_number": self.printed_customer_number,
            "printed_customer_number_evidence": (
                self.printed_customer_number_evidence
            ),
            "printed_customer_number_candidates": list(
                self.printed_customer_number_candidates
            ),
            "for_customer_number": self.for_customer_number,
            "for_customer_number_evidence": (
                self.for_customer_number_evidence
            ),
            "for_customer_number_candidates": list(
                self.for_customer_number_candidates
            ),
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_address_line_1": self.customer_address_line_1,
            "customer_address_line_2": self.customer_address_line_2,
            "customer_city": self.customer_city,
            "customer_state": self.customer_state,
            "customer_postal_code": self.customer_postal_code,
            "customer_identity_confidence": self.confidence,
            "customer_identity_evidence": list(self.evidence),
            "customer_identity_block": {
                "x0": self.matched_block_x0,
                "y0": self.matched_block_y0,
                "x1": self.matched_block_x1,
                "y1": self.matched_block_y1,
            },
            "check_region": {
                "x0": self.check_region_x0,
                "y0": self.check_region_y0,
                "x1": self.check_region_x1,
                "y1": self.check_region_y1,
            },
        }


@dataclass
class Region:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(self.x1 - self.x0, 0.0)

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 0.0)

    def to_rect(self):
        import fitz
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)
