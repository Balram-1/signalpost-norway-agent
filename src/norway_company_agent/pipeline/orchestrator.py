import asyncio
import logging
from typing import Any
import json
from datetime import datetime, timezone
from ..db.dal import (
    initialize_db, get_current_state, insert_evidence_if_new, upsert_entity_registry
)
from ..config.constants import WALL_CLOCK_CUTOFF_MINUTES, NAV_MAX_CONCURRENT, OPENROUTER_MAX_CONCURRENT
from ..scraping.browser_pool import browser_pool
from ..scraping.proxy_manager import proxy_manager
from ..scraping.site_discovery import verify_domain
from ..scraping.page_fetcher import fetch_page, BotBlockError, ScrapeFailure
from ..extraction.normalizer import normalize_html_section
from ..extraction.hasher import compute_content_hash
from ..extraction.llm_extractor import extract_company_facts
from ..extraction.verifier import verify_envelope
from ..clients.nav_jobs import format_nav_job
from ..official import fetch_official_modules

logger = logging.getLogger(__name__)

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

async def process_company(
    profile: dict[str, Any], 
    run_id: str, 
    jobs_map: dict[str, list],
    nav_sem: asyncio.Semaphore, 
    llm_sem: asyncio.Semaphore
) -> dict[str, Any]:
    org_num = profile["organisation_number"]
    brreg_navn = profile.get("name", "")
    
    # 0. Sync Brreg to DB
    # (In a full implementation, we'd fetch Brreg here. Using bulk profile data for now)
    raw_json = json.dumps(profile.get("raw", {}))
    await upsert_entity_registry(
        org_num=org_num,
        entity_type="hovedenhet",
        navn=brreg_navn,
        raw_json=raw_json,
        retrieved_at=utc_now(),
        forretningsadresse=json.dumps(profile.get("business_address", {})),
        postadresse=json.dumps(profile.get("postal_address", {}))
    )
    
    # 1. NAV Jobs
    try:
        jobs = jobs_map.get(org_num, [])
        for job in jobs:
            formatted = format_nav_job(job)
            await insert_evidence_if_new(
                org_num=org_num,
                fact_type="job_posting",
                fact_value=json.dumps(formatted),
                source_url=formatted["nav_url"],
                source_domain="arbeidsplassen.nav.no",
                retrieved_at=utc_now(),
                content_hash=formatted["content_hash"],
                extraction_method="nav_api",
                confidence=0.8,
                verification_status="ambiguous", # Set to ambiguous since this is a partial feed scan
                proxy_used=0,
                fiscal_year=None,
                run_id=run_id
            )
        if not jobs:
            content_hash = compute_content_hash("0")
            await insert_evidence_if_new(
                org_num=org_num,
                fact_type="job_posting",
                fact_value=json.dumps({"count": 0}),
                source_url="https://pam-stilling-feed.nav.no",
                source_domain="arbeidsplassen.nav.no",
                retrieved_at=utc_now(),
                content_hash=content_hash,
                extraction_method="nav_api",
                confidence=0.5,
                verification_status="ambiguous", # Set to ambiguous since this is a partial feed scan
                proxy_used=0,
                fiscal_year=None,
                run_id=run_id
            )
    except Exception as e:
        logger.error(f"NAV Jobs processing failed for {org_num}: {e}")

    # 2. Scraping
    website = profile.get("website")
    if website:
        # Simplistic extraction for POC - we just fetch the homepage
        if not website.startswith("http"):
            website = "http://" + website
            
        is_valid_domain = verify_domain(website, brreg_navn)
        
        async for context, proxy_used in browser_pool.acquire_context():
            page = await context.new_page()
            try:
                html = await fetch_page(page, website)
                normalized = normalize_html_section(html, website)
                content_hash = compute_content_hash(normalized)
                
                # Check if hash already exists for this org
                # If so, skip LLM
                
                # 3. LLM Extraction
                async with llm_sem:
                    envelope = await extract_company_facts(
                        org_num=org_num,
                        brreg_navn=brreg_navn,
                        brreg_forretningsadresse=json.dumps(profile.get("business_address", {})),
                        normalized_content=normalized
                    )
                    
                    # 4. Verifier
                    postcodes = []
                    b_addr = profile.get("business_address", {})
                    p_addr = profile.get("postal_address", {})
                    if isinstance(b_addr, dict) and b_addr.get("postnummer"):
                        postcodes.append(b_addr["postnummer"])
                    if isinstance(p_addr, dict) and p_addr.get("postnummer"):
                        postcodes.append(p_addr["postnummer"])
                        
                    verification_result = verify_envelope(
                        envelope=envelope,
                        org_num=org_num,
                        brreg_navn=brreg_navn,
                        brreg_postcodes=postcodes,
                        source_url=website,
                        source_domain=website,
                        retrieved_at=utc_now(),
                        content_hash=content_hash,
                        proxy_used=1 if proxy_used else 0,
                        run_id=run_id
                    )
                    
                    for row in verification_result.evidence_rows:
                        await insert_evidence_if_new(**row)
                        
                break # Success, break out of the generator loop!
                
            except BotBlockError:
                logger.warning(f"Bot block on {website}")
                break
            except Exception as e:
                if proxy_used and ("ERR_TUNNEL_CONNECTION_FAILED" in str(e) or "ERR_PROXY_CONNECTION_FAILED" in str(e)):
                    logger.warning(f"Proxy error on {website}: {e}. Generator will yield direct connection fallback.")
                    raise # Let the generator catch this and yield a fallback
                logger.error(f"Scraping failed for {website}: {e}")
                break

    # Dummy metric
    metric = {"requests": 1, "bytes": 0, "latencies_ms": [100]}
    return profile, metric

async def run_batch(profiles: list[dict], run_id: str) -> tuple[list[dict], dict]:
    await initialize_db()
    
    # 1. NAV Batch Pre-fetching
    try:
        from ..clients.nav_jobs import fetch_public_token, fetch_recent_jobs
        token = await fetch_public_token()
        jobs_map = await fetch_recent_jobs(token, max_pages=10)
    except Exception as e:
        logger.error(f"Failed to fetch NAV jobs batch: {e}")
        jobs_map = {}
        
    nav_sem = asyncio.Semaphore(NAV_MAX_CONCURRENT)
    llm_sem = asyncio.Semaphore(OPENROUTER_MAX_CONCURRENT)
    
    results = []
    operations = {"requests": 0, "bytes": 0, "latencies_ms": []}
    
    # Chunk size for Playwright browser recycling to prevent memory leaks
    CHUNK_SIZE = 25
    for i in range(0, len(profiles), CHUNK_SIZE):
        chunk = profiles[i:i + CHUNK_SIZE]
        
        await browser_pool.start()
        try:
            tasks = []
            for profile in chunk:
                tasks.append(asyncio.create_task(process_company(profile, run_id, jobs_map, nav_sem, llm_sem)))
                
            done, pending = await asyncio.wait(
                tasks, 
                timeout=WALL_CLOCK_CUTOFF_MINUTES * 60,
                return_when=asyncio.ALL_COMPLETED
            )
            
            for task in pending:
                task.cancel()
                
            for task in done:
                profile, metric = task.result()
                results.append(profile)
                operations["requests"] += metric["requests"]
                operations["bytes"] += metric["bytes"]
                operations["latencies_ms"].extend(metric["latencies_ms"])
        finally:
            await browser_pool.stop()
            
    return results, operations
