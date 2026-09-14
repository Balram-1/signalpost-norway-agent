import asyncio
import logging
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from ..config.constants import PAGE_GOTO_TIMEOUT, PAGE_NAV_TIMEOUT

logger = logging.getLogger(__name__)

class BotBlockError(Exception):
    pass

class ScrapeFailure(Exception):
    def __init__(self, message: str, error_type: str, status: int = None):
        super().__init__(message)
        self.error_type = error_type
        self.status = status

async def fetch_page(page: Page, url: str) -> str:
    """
    Fetches a URL, checks for bot blocks, and returns the raw HTML body.
    Raises ScrapeFailure or BotBlockError on failure.
    """
    try:
        response = await page.goto(url, timeout=PAGE_GOTO_TIMEOUT * 1000, wait_until="domcontentloaded")
    except PlaywrightTimeoutError:
        raise ScrapeFailure(f"Timeout loading {url}", "timeout")
    except Exception as e:
        raise ScrapeFailure(f"Error loading {url}: {e}", "navigation_error")

    if not response:
        raise ScrapeFailure(f"No response from {url}", "no_response")

    status = response.status
    if status in (403, 429):
        # Could be bot block, raise immediately
        raise BotBlockError(f"HTTP {status}")
    if status >= 400:
        raise ScrapeFailure(f"HTTP {status}", "http_error", status=status)

    html = await page.content()
    
    # Bot detection
    lower_html = html.lower()
    if any(marker in lower_html for marker in ("cf-mitigated", "cf_chl_opt", "jschl_vc", "g-recaptcha", "hcaptcha", "data-sitekey")):
        raise BotBlockError("Bot protection detected in HTML")

    return html
