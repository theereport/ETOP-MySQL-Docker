import os
from fastapi import APIRouter
from pydantic import BaseModel
from ..resolution.payer_mapping_repository import PayerCustomerMappingRepository

router=APIRouter(prefix="/api/v1/documents",tags=["Document Intelligence Phase 3"])
repo=PayerCustomerMappingRepository(); repo.initialize()

class ConfirmMapping(BaseModel):
    routing_number: str|None=None
    bank_account_last4: str|None=None
    normalized_payer_name: str|None=None
    customer_number: str
    confidence: float=1.0

@router.get("/phase3/health")
def health():
    return {"status":"ok","phase":3,"capabilities":["targeted_ocr","payer_identity","customer_resolution","invoice_combination_matching","payer_customer_memory"],"tesseract_configured":bool(os.getenv("TESSERACT_CMD"))}

@router.post("/phase3/payer-mappings/confirm")
def confirm_mapping(r:ConfirmMapping):
    repo.upsert(r.routing_number,r.bank_account_last4,r.normalized_payer_name,r.customer_number,r.confidence,True)
    return {"status":"saved","customer_number":r.customer_number}
