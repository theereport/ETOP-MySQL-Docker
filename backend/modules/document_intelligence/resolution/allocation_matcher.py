from decimal import Decimal
from itertools import combinations
from ..business_objects.models import AllocationProposal, AllocationResolutionResult

class AllocationMatcher:
    def __init__(self,tolerance=Decimal("0.01"),max_combination_size=8,max_candidate_invoices=30):
        self.tolerance=tolerance; self.max_combination_size=max_combination_size; self.max_candidate_invoices=max_candidate_invoices

    def match(self,check_amount,invoices):
        active=[i for i in invoices if i.open_amount>0][:self.max_candidate_invoices]
        active.sort(key=lambda i:(i.invoice_date or i.due_date,i.invoice_number))
        singles=[i for i in active if abs(i.open_amount-check_amount)<=self.tolerance]
        if len(singles)==1: return self._result(check_amount,singles,"single_invoice_exact",1.0)
        buckets={}
        for i in active: buckets.setdefault(i.aging_bucket or "UNASSIGNED",[]).append(i)
        bm=[(b,v) for b,v in buckets.items() if abs(sum((x.open_amount for x in v),Decimal("0"))-check_amount)<=self.tolerance]
        if len(bm)==1: return self._result(check_amount,bm[0][1],f"whole_bucket:{bm[0][0]}",.96)
        running=[]; total=Decimal("0")
        for i in active:
            running.append(i); total+=i.open_amount
            if abs(total-check_amount)<=self.tolerance: return self._result(check_amount,running,"oldest_first_exact",.93)
            if total>check_amount+self.tolerance: break
        matches=[]
        for size in range(2,min(self.max_combination_size,len(active))+1):
            for combo in combinations(active,size):
                if abs(sum((x.open_amount for x in combo),Decimal("0"))-check_amount)<=self.tolerance:
                    matches.append(list(combo))
                    if len(matches)>=5: break
            if len(matches)>=5: break
        if len(matches)==1: return self._result(check_amount,matches[0],"subset_sum_exact",.88)
        if len(matches)>1:
            r=self._result(check_amount,matches[0],"ambiguous_exact_match",.70)
            r.status="review_required"; r.alternate_matches=len(matches); r.warnings=["Multiple invoice combinations match."]
            return r
        return AllocationResolutionResult(status="not_found",method="none",check_amount=check_amount,difference=check_amount,warnings=["No exact match found."])

    def _result(self,amount,invoices,method,confidence):
        total=sum((i.open_amount for i in invoices),Decimal("0"))
        return AllocationResolutionResult(status="exact",method=method,check_amount=amount,matched_total=total,difference=amount-total,confidence=confidence,
            proposals=[AllocationProposal(invoice_number=i.invoice_number,proposed_amount=i.open_amount,open_amount=i.open_amount,aging_bucket=i.aging_bucket) for i in invoices])
