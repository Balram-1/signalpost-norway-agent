from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class FinancialFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fiscal_year: str
    revenue_nok: Optional[int] = None
    profit_nok: Optional[int] = None
    employees: Optional[int] = None
    source_note: str
    not_found: bool

class PersonRoleFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    full_name: str
    role_title: str
    confidence_note: str
    not_found: bool

class JobPostingFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str
    location: Optional[str] = None
    published_date: str
    nav_url: str
    not_found: bool

class ActivityFact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    headline: str
    date: str
    summary: str
    not_found: bool

class ExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    org_num: str
    extracted_company_name: str
    extracted_address: Optional[str] = None
    financials: List[FinancialFact]
    people: List[PersonRoleFact]
    activity: List[ActivityFact]
