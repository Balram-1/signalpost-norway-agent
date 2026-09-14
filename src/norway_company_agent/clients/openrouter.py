import aiohttp
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, retry_if_result
from pydantic import BaseModel
import json
import logging
from typing import TypeVar, Type
from ..config import settings
from ..config.constants import OPENROUTER_TIMEOUT

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class OpenRouterError(Exception):
    pass
class OpenRouterRateLimitError(OpenRouterError):
    pass

def _is_rate_limit(exception: BaseException) -> bool:
    return isinstance(exception, OpenRouterRateLimitError)

def _force_required(schema: dict) -> dict:
    if "$defs" in schema:
        for v in schema["$defs"].values():
            _force_required(v)
            
    if "type" in schema and schema["type"] == "object":
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
            schema["additionalProperties"] = False
            for v in schema["properties"].values():
                _force_required(v)
    elif "type" in schema and schema["type"] == "array":
        if "items" in schema:
            _force_required(schema["items"])
            
    return schema

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=2, min=5, max=15),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, OpenRouterRateLimitError)),
    reraise=True
)
async def extract(system_prompt: str, user_content: str, response_schema: Type[T]) -> T:
    """
    Calls OpenRouter with structured output via json_schema.
    Retries once on 429.
    """
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "HTTP-Referer": "https://builderr.ai",
        "X-Title": "Signalpost Company Agent",
        "Content-Type": "application/json"
    }
    
    schema_dict = response_schema.model_json_schema()
    _force_required(schema_dict)
    
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": response_schema.__name__,
                "strict": True,
                "schema": schema_dict
            }
        },
        "temperature": 0.0
    }
    
    timeout = aiohttp.ClientTimeout(total=OPENROUTER_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status == 429:
                # Use Retry-After if provided, else rely on tenacity wait
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    await asyncio.sleep(int(retry_after))
                raise OpenRouterRateLimitError("Rate limited by OpenRouter")
            if response.status != 200:
                text = await response.text()
                raise OpenRouterError(f"OpenRouter returned {response.status}: {text}")
            
            data = await response.json()
            message = data["choices"][0]["message"]["content"]
            
            # Pydantic validates the JSON payload automatically
            try:
                parsed_json = json.loads(message)
                return response_schema.model_validate(parsed_json)
            except Exception as e:
                raise OpenRouterError(f"Failed to parse or validate LLM output: {e}")
