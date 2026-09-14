import logging
import re
from typing import Dict, Any, List
from .schemas import ExtractionEnvelope
from ..scraping.site_discovery import normalize_company_name
import jellyfish

logger = logging.getLogger(__name__)

class VerificationResult:
    def __init__(self):
        self.evidence_rows: List[Dict[str, Any]] = []

def verify_envelope(
    envelope: ExtractionEnvelope, 
    org_num: str, 
    brreg_navn: str, 
    brreg_postcodes: List[str],
    source_url: str,
    source_domain: str,
    retrieved_at: str,
    content_hash: str,
    proxy_used: int,
    run_id: str
) -> VerificationResult:
    """
    Applies deterministic checks on the extracted envelope.
    Returns a list of evidence rows to be inserted.
    """
    result = VerificationResult()
    
    base_kwargs = {
        "org_num": org_num,
        "source_url": source_url,
        "source_domain": source_domain,
        "retrieved_at": retrieved_at,
        "content_hash": content_hash,
        "proxy_used": proxy_used,
        "run_id": run_id
    }
    
    # Check 1: Name similarity gate
    norm_brreg = normalize_company_name(brreg_navn)
    norm_extracted = normalize_company_name(envelope.extracted_company_name)
    name_sim = jellyfish.jaro_winkler_similarity(norm_brreg, norm_extracted)
    
    base_status = 'verified' if name_sim >= 0.80 else 'ambiguous'
    
    if name_sim < 0.80:
        logger.warning(f"[{org_num}] Name similarity {name_sim:.2f} < 0.80. Marking ambiguous.")

    # Check 2: Address plausibility gate (only if address is extracted)
    location_status = base_status
    if envelope.extracted_address:
        # Extract 4 digit postcodes from address
        extracted_postcodes = re.findall(r'\b\d{4}\b', envelope.extracted_address)
        if extracted_postcodes and not any(p in brreg_postcodes for p in extracted_postcodes):
            logger.warning(f"[{org_num}] Extracted address mismatch. Marking location/activity ambiguous.")
            location_status = 'ambiguous'
            
    # Process financials
    for fin in envelope.financials:
        if fin.not_found:
            continue
            
        status = base_status
        is_valid = 1
        # Check 3: Fiscal year presence
        if (fin.revenue_nok or fin.profit_nok or fin.employees) and not fin.fiscal_year:
            status = 'fabrication_risk'
            is_valid = 0
            logger.warning(f"[{org_num}] Financial without fiscal year. Rejecting.")
            
        if fin.revenue_nok:
            result.evidence_rows.append(_build_row('revenue', str(fin.revenue_nok), status, fin.fiscal_year, is_valid, **base_kwargs))
        if fin.profit_nok:
            result.evidence_rows.append(_build_row('profit', str(fin.profit_nok), status, fin.fiscal_year, is_valid, **base_kwargs))
        if fin.employees:
            result.evidence_rows.append(_build_row('employees_financial', str(fin.employees), status, fin.fiscal_year, is_valid, **base_kwargs))

    # Process people
    for p in envelope.people:
        if p.not_found:
            continue
        fact_val = f"{p.full_name} - {p.role_title}"
        result.evidence_rows.append(_build_row('person_role', fact_val, base_status, None, 1, **base_kwargs))

    # Process activity
    for a in envelope.activity:
        if a.not_found:
            continue
        fact_val = f"{a.date}: {a.headline} - {a.summary}"
        status = location_status if location_status == 'ambiguous' else base_status
        result.evidence_rows.append(_build_row('activity_news', fact_val, status, None, 1, **base_kwargs))

    # Check 4: not_found passthrough
    # We could insert a generic not_found if the whole thing is empty, but we can also just let it be.
    # The architecture states "If not_found = True is returned by the model for a fact category, verifier.py inserts one evidence row".
    categories = [
        ('revenue', envelope.financials),
        ('person_role', envelope.people),
        ('activity_news', envelope.activity)
    ]
    for fact_type, lst in categories:
        if all(item.not_found for item in lst) or not lst:
            # We record a not_found entry
            result.evidence_rows.append(_build_row(fact_type, '{"not_found": true}', 'verified', None, 1, **base_kwargs))

    return result

def _build_row(fact_type, fact_value, status, fiscal_year, is_valid, org_num, source_url, source_domain, retrieved_at, content_hash, proxy_used, run_id, **kwargs):
    return {
        "org_num": org_num,
        "fact_type": fact_type,
        "fact_value": fact_value,
        "source_url": source_url,
        "source_domain": source_domain,
        "retrieved_at": retrieved_at,
        "content_hash": content_hash,
        "extraction_method": "llm_scrape",
        "confidence": 1.0 if status == 'verified' else 0.5,
        "verification_status": status,
        "proxy_used": proxy_used,
        "fiscal_year": fiscal_year,
        "run_id": run_id,
        "is_valid": is_valid
    }
