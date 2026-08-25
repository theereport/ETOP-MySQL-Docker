from pathlib import Path
import fitz
from .page_selector import select_pages_for_ocr
from ..business_objects.models import OcrPageResult

class TargetedOcrService:
    def __init__(self, tesseract_path: str | None = None, dpi: int = 300):
        import pytesseract
        self.pytesseract = pytesseract
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        self.dpi = dpi

    def process(self, job_id: str, pdf_path: str, extraction: dict) -> list[OcrPageResult]:
        from PIL import Image
        pages = select_pages_for_ocr(extraction)
        out = Path("data/modules/document_intelligence/ocr")/job_id
        out.mkdir(parents=True, exist_ok=True)
        doc = fitz.open(pdf_path)
        results = []
        try:
            matrix = fitz.Matrix(self.dpi/72, self.dpi/72)
            for n in pages:
                page = doc.load_page(n-1)
                image_path = out/f"page_{n:04d}.png"
                page.get_pixmap(matrix=matrix, alpha=False).save(str(image_path))
                data = self.pytesseract.image_to_data(Image.open(image_path), output_type=self.pytesseract.Output.DICT, config="--oem 3 --psm 6")
                words, confs = [], []
                for txt, conf in zip(data.get("text",[]), data.get("conf",[])):
                    txt=(txt or "").strip()
                    try: c=float(conf)
                    except: c=-1
                    if txt: words.append(txt)
                    if c >= 0: confs.append(c)
                results.append(OcrPageResult(
                    page_number=n, text=" ".join(words),
                    confidence=round(sum(confs)/len(confs)/100,4) if confs else 0,
                    engine="tesseract", image_path=str(image_path)
                ))
        finally:
            doc.close()
        return results
