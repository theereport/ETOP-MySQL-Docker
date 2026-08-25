from .base import DocumentParser
from .generic import GenericDocumentParser
from .pnc_lockbox import PNCLockboxParser
from .vendor_invoice import VendorInvoiceParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, DocumentParser] = {}
        self._fallback = GenericDocumentParser()

    def register(self, parser: DocumentParser) -> None:
        self._parsers[parser.document_type] = parser

    def get(self, document_type: str) -> DocumentParser:
        return self._parsers.get(document_type, self._fallback)

    def list_parsers(self) -> list[dict]:
        return [
            {
                "document_type": parser.document_type,
                "parser": parser.parser_name,
                "version": parser.parser_version,
            }
            for parser in self._parsers.values()
        ]


parser_registry = ParserRegistry()
parser_registry.register(PNCLockboxParser())
parser_registry.register(VendorInvoiceParser())
