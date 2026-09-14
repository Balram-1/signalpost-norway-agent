import jellyfish
import urllib.parse
from tldextract import extract

def normalize_domain(url: str) -> str:
    if not url:
        return ""
    if not url.startswith("http"):
        url = "http://" + url
    ext = extract(url)
    return f"{ext.domain}.{ext.suffix}".lower()

def normalize_company_name(name: str) -> str:
    name = name.lower()
    for suffix in [" asa", " as", " sa", " enk", " nuf"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()

def verify_domain(url: str, brreg_name: str, brreg_kommune: str = None) -> bool:
    """
    Verifies if a domain likely belongs to the company.
    Requires Jaro-Winkler >= 0.82 between domain and name.
    """
    domain = normalize_domain(url)
    if not domain:
        return False
    
    # Just the domain part without suffix for similarity
    domain_core = domain.split(".")[0].replace("-", " ")
    norm_name = normalize_company_name(brreg_name)
    
    similarity = jellyfish.jaro_winkler_similarity(domain_core, norm_name)
    if similarity >= 0.82:
        return True
    
    return False
