from typing import Any, List, Dict
import json
from ..db.dal import get_current_state

# Maps internal verification_status -> output contract availability enum
_AVAILABILITY_MAP = {
    "verified": "available",
    "ambiguous": "ambiguous",
    "fabrication_risk": "failed",
    "not_found": "not_available",
    "blocked": "blocked",
    "not_applicable": "not_applicable",
    "failed": "failed",
}

async def build_terminal_envelope(org_num: str, run_id: str, started_at: str, completed_at: str, operations: dict) -> dict:
    """
    Constructs the exact JSON structure required by OUTPUT_CONTRACT.md
    from the current_state and evidence tables.
    """
    state_rows = await get_current_state(org_num)
    
    claims = []
    evidence = []
    
    for row in state_rows:
        fact_type = row["fact_type"]
        fact_value_str = row["fact_value"]
        
        try:
            val = json.loads(fact_value_str)
        except json.JSONDecodeError:
            val = fact_value_str
            
        evidence_item = {
            "id": f"ev-{row['id']}",
            "source_url": row["source_url"],
            "source_class": row["extraction_method"],
            "retrieved_at": row["retrieved_at"],
            "content_sha256": row["content_hash"],
        }
        
        # Determine claim structure based on fact type
        if fact_type == 'job_posting':
            if isinstance(val, dict) and 'count' in val and val['count'] == 0:
                claim = {
                    "field": fact_type,
                    "value": "0",
                    "availability": "not_applicable",
                    "confidence": 1.0,
                    "evidence_ids": [evidence_item["id"]]
                }
            else:
                claim = {
                    "field": fact_type,
                    "value": val,
                    "availability": _AVAILABILITY_MAP.get(row["verification_status"], "ambiguous"),
                    "confidence": row["confidence"],
                    "evidence_ids": [evidence_item["id"]]
                }
        else:
            claim = {
                "field": fact_type,
                "value": val,
                "availability": _AVAILABILITY_MAP.get(row["verification_status"], "ambiguous"),
                "confidence": row["confidence"],
                "evidence_ids": [evidence_item["id"]]
            }
            
        claims.append(claim)
        evidence.append(evidence_item)

    terminal_status = "complete" if claims else "not_found"

    return {
        "organisation_number": org_num,
        "run": {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "terminal_status": terminal_status
        },
        "claims": claims,
        "evidence": evidence,
        "changes": [],
        "errors": [],
        "operations": operations
    }
