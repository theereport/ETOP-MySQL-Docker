import re, unicodedata
SUFFIXES={"LLC","INC","INCORPORATED","CORP","CORPORATION","CO","COMPANY","LTD","LIMITED","LP","LLP"}
def normalize_text(v):
    if not v: return ""
    v=unicodedata.normalize("NFKD",v).encode("ascii","ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9 ]+"," ",v).split())
def normalize_company_name(v):
    return " ".join(x for x in normalize_text(v).split() if x not in SUFFIXES)
def normalize_zip(v):
    return re.sub(r"\D","",v or "")[:5]
def last4(v):
    d=re.sub(r"\D","",v or "")
    return d[-4:] if d else ""
