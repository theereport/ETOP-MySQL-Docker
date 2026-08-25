from difflib import SequenceMatcher
from ..business_objects.models import CustomerCandidate, CustomerResolutionResult
from .normalization import normalize_company_name, normalize_zip, normalize_text

class CustomerResolver:
    def __init__(self, repository): self.repository=repository

    def resolve(self, payer):
        if payer.printed_customer_number:
            row=self.repository.get_by_customer_number(payer.printed_customer_number)
            if row:
                c=CustomerCandidate(**row,score=1.0,match_reasons=["Customer number printed on document"])
                return CustomerResolutionResult(status="matched",selected_customer=c,candidates=[c],confidence=1.0)
        rows=self.repository.search_candidates(payer.payer_name,payer.postal_code,payer.state,25)
        candidates=[]
        pn,pz,ps=normalize_company_name(payer.payer_name),normalize_zip(payer.postal_code),normalize_text(payer.state)
        for r in rows:
            reasons=[]; score=0.0
            cn,cz,cs=normalize_company_name(r.get("customer_name")),normalize_zip(r.get("postal_code")),normalize_text(r.get("state"))
            if pn and cn:
                sim=SequenceMatcher(None,pn,cn).ratio(); score += sim*.70
                if sim>=.95: reasons.append("Near-exact normalized name")
                elif sim>=.80: reasons.append("Strong normalized name similarity")
            if pz and cz and pz==cz: score+=.20; reasons.append("Exact ZIP match")
            if ps and cs and ps==cs: score+=.10; reasons.append("Exact state match")
            candidates.append(CustomerCandidate(**r,score=round(min(score,1),4),match_reasons=reasons))
        candidates.sort(key=lambda x:x.score,reverse=True)
        if not candidates:
            return CustomerResolutionResult(status="not_found",warnings=["No TMCUST candidates returned."])
        top=candidates[0]; second=candidates[1] if len(candidates)>1 else None
        margin=top.score-(second.score if second else 0)
        status="matched" if top.score>=.90 and margin>=.10 else "review_required"
        return CustomerResolutionResult(status=status,selected_customer=top,candidates=candidates[:5],confidence=top.score)
