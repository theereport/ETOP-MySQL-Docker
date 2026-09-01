from dataclasses import dataclass
from pathlib import Path

from core.config import settings as platform_settings


@dataclass(frozen=True)
class DocumentIntelligenceSettings:
    module_key: str = "document_intelligence"
    module_version: str = "0.5.0"
    max_upload_bytes: int = 50 * 1024 * 1024
    # Technical safety limits, not document-validity or financial-policy rules.
    max_pdf_pages: int = 500
    max_targeted_ocr_pages: int = 25
    max_ocr_render_dimension_pixels: int = 10_000
    max_ocr_render_pixels: int = 20_000_000
    ocr_page_timeout_seconds: float = 30.0
    ocr_total_timeout_seconds: float = 120.0
    processor_version: str = "document-intelligence-processor.v3"

    @property
    def data_root(self) -> Path:
        return platform_settings.data_root / "modules" / self.module_key

    @property
    def upload_root(self) -> Path:
        return platform_settings.data_root / "uploads" / self.module_key


settings = DocumentIntelligenceSettings()
