import logging
from dataclasses import dataclass
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)

@dataclass
class ProxyConfig:
    url: Optional[str]
    server: Optional[str]
    username: Optional[str]
    password: Optional[str]
    proxy_used: bool

class ProxyManager:
    def __init__(self):
        self.proxy_available = False
        self._proxy_url = None
        self._server = None
        self._username = None
        self._password = None
        
        api_key = settings.easyproxy_api_key
        endpoint = settings.easyproxy_endpoint
        
        if api_key and endpoint:
            # Construct the rotating residential proxy for Norway
            self._proxy_url = f"http://res-no:{api_key}@{endpoint}"
            self._server = f"http://{endpoint}"
            self._username = "res-no"
            self._password = api_key
            self.proxy_available = True
        else:
            logger.warning("EASYPROXY_API_KEY or EASYPROXY_ENDPOINT not set; all scraping will use direct connection.")
            logger.warning("proxy_used will be recorded as 0 in all evidence rows for this run.")

    def get_proxy_config(self) -> ProxyConfig:
        if self.proxy_available:
            return ProxyConfig(url=self._proxy_url, server=self._server, username=self._username, password=self._password, proxy_used=True)
        return ProxyConfig(url=None, server=None, username=None, password=None, proxy_used=False)

    def mark_proxy_failed(self):
        """Called when a proxy connection fails irrecoverably."""
        logger.warning("Proxy connection failed. Falling back to direct connection.")
        self.proxy_available = False

proxy_manager = ProxyManager()
