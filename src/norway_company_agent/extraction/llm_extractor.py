from typing import Optional
from .schemas import ExtractionEnvelope
from ..clients.openrouter import extract

SYSTEM_PROMPT = """You are a precise data extraction assistant. You are extracting facts about a specific Norwegian company. 
The company's official name is {brreg_navn} and its registered address is {brreg_forretningsadresse}. 
Extract facts ONLY from the content provided. 
If the content does not clearly refer to this company, set not_found: true for all fields. 
Do not infer, estimate, or hallucinate any numerical values. 
If a fiscal year for a financial figure is not explicitly stated in the content, set not_found: true for that figure and do not include it.
"""

async def extract_company_facts(
    org_num: str, 
    brreg_navn: str, 
    brreg_forretningsadresse: str, 
    normalized_content: str
) -> ExtractionEnvelope:
    
    prompt = SYSTEM_PROMPT.format(
        brreg_navn=brreg_navn, 
        brreg_forretningsadresse=brreg_forretningsadresse
    )
    
    return await extract(
        system_prompt=prompt, 
        user_content=normalized_content, 
        response_schema=ExtractionEnvelope
    )
