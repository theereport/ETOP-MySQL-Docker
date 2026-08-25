from abc import ABC, abstractmethod


class DocumentParser(ABC):
    document_type: str
    parser_name: str
    parser_version: str

    @abstractmethod
    def parse(self, document: dict) -> dict:
        raise NotImplementedError
