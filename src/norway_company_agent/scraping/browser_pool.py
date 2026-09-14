import logging
import asyncio
from typing import AsyncGenerator
from playwright.async_api import async_playwright, Browser, BrowserContext, Error
from ..config.constants import PLAYWRIGHT_MAX_CONTEXTS
from .proxy_manager import proxy_manager

logger = logging.getLogger(__name__)

async def safe_close_context(context: BrowserContext):
    """Safely closes a Playwright context, swallowing expected teardown exceptions."""
    try:
        # Some contexts have pages we should close first if possible, though context.close() tries this.
        # But just in case, we swallow errors directly on the context.
        await context.close()
    except Error as e:
        logger.debug(f"Expected Playwright error during teardown: {e}")
    except Exception as e:
        logger.debug(f"Unexpected exception during context teardown: {e}")

class BrowserPool:
    def __init__(self):
        self._playwright = None
        self._browser: Browser = None
        self._semaphore = asyncio.Semaphore(PLAYWRIGHT_MAX_CONTEXTS)
    
    async def start(self):
        self._playwright = await async_playwright().start()
        # Launch with strict sandbox and resource limits for the hackathon runner
        args = [
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
            "--disk-cache-size=1",
            "--media-cache-size=1"
        ]
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=args
        )
        
    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def acquire_context(self) -> AsyncGenerator[tuple[BrowserContext, bool], None]:
        """
        Acquires a Playwright context for a single company scrape session, respecting the concurrency limit.
        Yields (context, proxy_used).
        """
        await self._semaphore.acquire()
        try:
            proxy_config = proxy_manager.get_proxy_config()
            proxy = None
            if proxy_config.proxy_used:
                proxy = {
                    "server": proxy_config.server,
                    "username": proxy_config.username,
                    "password": proxy_config.password
                }
            
            try:
                context = await self._browser.new_context(proxy=proxy)
                yield context, proxy_config.proxy_used
            except Exception as e:
                if proxy_config.proxy_used and ("ERR_PROXY_CONNECTION_FAILED" in str(e) or "ERR_TUNNEL_CONNECTION_FAILED" in str(e)):
                    # Fallback to direct
                    logger.warning(f"Proxy context failed: {e}. Retrying with direct connection.")
                    proxy_manager.mark_proxy_failed()
                    context = await self._browser.new_context()
                    yield context, False
                else:
                    raise
            finally:
                if 'context' in locals():
                    await safe_close_context(context)
        finally:
            self._semaphore.release()

browser_pool = BrowserPool()
