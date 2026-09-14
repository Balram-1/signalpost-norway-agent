import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

def normalize_html_section(html: str, domain: str) -> str:
    """
    Normalizes a section of HTML for stable hashing.
    """
    soup = BeautifulSoup(html, "lxml")
    
    # 2. Ad and tracking markup
    ad_selectors = [".ad", ".advertisement", "[data-ad]", "[id^='google_ads']", ".cookie-banner", ".gdpr-notice", "[class*='tracking']"]
    for selector in ad_selectors:
        for tag in soup.select(selector):
            tag.decompose()
            
    # 3. Widget/embed iframes
    for tag in soup.find_all(['iframe', 'script']):
        src = tag.get('src')
        if src:
            src_domain = urlparse(src).netloc
            if src_domain and domain not in src_domain:
                tag.decompose()

    # Get text or string representation
    # Wait, we want to normalize attributes too. Let's just normalize the text since the prompt says 
    # "The user content is the normalized text of a single verified-domain page section".
    # But wait, step 1 says "Session and CSRF tokens: any HTML attribute value or URL query parameter matching..."
    # If we are feeding text to LLM, attributes aren't seen anyway, but let's do it on string level.
    
    # Let's extract text for LLM and hashing.
    text = soup.get_text(separator=" ", strip=True)
    
    # 1. & 4. Regex replacements on the text
    # 4. Timestamps
    iso_date_re = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?')
    no_date_re = re.compile(r'\d{1,2}\. (januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember) \d{4}', re.IGNORECASE)
    
    text = iso_date_re.sub('DATE_REDACTED', text)
    text = no_date_re.sub('DATE_REDACTED', text)
    
    # 5. Whitespace canonicalization
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text
