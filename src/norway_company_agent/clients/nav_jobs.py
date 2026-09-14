import aiohttp
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import json
import logging
import hashlib
from typing import Any
from ..config import settings
from ..config.constants import NAV_TIMEOUT

logger = logging.getLogger(__name__)

class NavAPIError(Exception):
    pass

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, NavAPIError)),
    reraise=True
)
async def fetch_public_token() -> str:
    url = "https://pam-stilling-feed.nav.no/api/publicToken"
    timeout = aiohttp.ClientTimeout(total=NAV_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                raise NavAPIError(f"Failed to fetch public token, status {response.status}: {text}")
            text = await response.text()
            # Token is returned as text like "Current public token...\n<token>"
            token = text.strip().split("\n")[-1]
            return token

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, NavAPIError)),
    reraise=True
)
async def fetch_recent_jobs(token: str, max_pages: int = 10) -> dict[str, list[dict[str, Any]]]:
    """
    Fetches the recent event feed from NAV and maps active jobs to employer.orgnr.
    Since pam-stilling-feed is an event stream, this is a bounded partial search.
    """
    # For a real implementation, we would either need to sync the entire feed to a DB 
    # or query a different source. Here we just consume a budgeted window.
    # We will query the start of the feed for demonstration, as querying backwards isn't natively supported.
    url = "https://pam-stilling-feed.nav.no/api/v1/feed?size=1000"
    headers = {
        "User-Agent": "SignalpostChallengeAgent/1.0",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    timeout = aiohttp.ClientTimeout(total=NAV_TIMEOUT)
    jobs_map = {}
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        current_url = url
        for _ in range(max_pages):
            if not current_url:
                break
                
            async with session.get(current_url, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.warning(f"NAV API feed returned {response.status}: {text}")
                    break
                
                data = await response.json()
                items = data.get("items", [])
                for item in items:
                    entry = item.get("_feed_entry", {})
                    # pam-stilling-feed entry includes orgnr in the employer block if fetched via full ad,
                    # but in the feed summary we use what we have, e.g. businessName or orgnr if present.
                    # As a stub for the event feed, we check for employer or orgnr.
                    orgnr = entry.get("employer", {}).get("orgnr") or entry.get("orgnr")
                    if orgnr and entry.get("status") == "ACTIVE":
                        if orgnr not in jobs_map:
                            jobs_map[orgnr] = []
                            
                        # Lean memory indexing: store only required fields
                        lean_job = {
                            "id": entry.get("uuid", item.get("id", "")),
                            "title": entry.get("title", item.get("title", "")),
                            "date_modified": entry.get("sistEndret", item.get("date_modified", "")),
                            "municipal": entry.get("municipal")
                        }
                        jobs_map[orgnr].append(lean_job)
                
                current_url = data.get("next_url")
                if current_url and current_url.startswith("/"):
                    current_url = "https://pam-stilling-feed.nav.no" + current_url

    return jobs_map

def format_nav_job(job: dict) -> dict[str, Any]:
    """Extracts required fields and computes content_hash for idempotency."""
    title = job.get("title", "")
    published = job.get("date_modified", "")
    job_id = job.get("id", "")
    
    hash_input = f"{job_id}:{title}:{published}"
    content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    
    location = job.get("municipal")
    
    return {
        "id": job_id,
        "title": title,
        "location": location,
        "published_date": published,
        "nav_url": f"https://arbeidsplassen.nav.no/stillinger/stilling/{job_id}",
        "content_hash": content_hash
    }
