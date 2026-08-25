from .base import DocumentParser


class GenericDocumentParser(DocumentParser):
    document_type = "unknown"
    parser_name = "generic_document_parser"
    parser_version = "1.0.0"

    def parse(self, document: dict) -> dict:
        return {
            "parser": self.parser_name,
            "parser_version": self.parser_version,
            "document_type": document.get("document_type", "unknown"),
            "summary": {
                "page_count": document["extraction"]["page_count"],
                "character_count": document["extraction"]["character_count"],
                "ocr_recommended": document["extraction"]["ocr_recommended"],
            },
            "records": [],
            "validation": {
                "status": "not_applicable",
                "errors": [],
                "warnings": [
                    "No specialized parser is registered for this document type."
                ],
            },
        }
