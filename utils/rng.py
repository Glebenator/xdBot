# utils/rng.py
import asyncio
import logging
import secrets  # Fallback for errors
from typing import List, Optional

import aiohttp

logger = logging.getLogger(__name__)

class RandomOrgRNG:
    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key
        self.base_url = "https://api.random.org/json-rpc/4/invoke"
        self.remaining_bits = None
        self._session = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _make_request(self, method: str, params: dict) -> dict:
        """Make request to Random.org API"""
        if not self.api_key:
            return None

        session = await self._get_session()

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {
                "apiKey": self.api_key,
                **params
            },
            "id": secrets.randbits(16)
        }

        try:
            async with session.post(self.base_url, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(
                        f"Random.org returned {response.status}: {body[:200]}"
                    )
                data = await response.json()
                if "error" in data:
                    raise RuntimeError(f"Random.org error: {data['error']}")
                return data["result"]
        except Exception:
            logger.warning(
                "Random.org request failed", exc_info=True,
                extra={"method": method, "params": {k: params[k] for k in params if k != 'apiKey'}}
            )
            return None

    async def _get_integers(self, n: int, min_val: int, max_val: int) -> Optional[List[int]]:
        """Get random integers from Random.org"""
        async with self._lock:  # Ensure only one request at a time
            result = await self._make_request(
                "generateIntegers",
                {
                    "n": n,
                    "min": min_val,
                    "max": max_val,
                    "replacement": True
                }
            )

            if result and "random" in result:
                self.remaining_bits = result.get("bitsLeft", 0)
                return result["random"]["data"]
            return None

    async def randint(self, min_val: int, max_val: int) -> int:
        """Get a random integer between min_val and max_val (inclusive)"""
        try:
            numbers = await self._get_integers(1, min_val, max_val)
            if numbers:
                return numbers[0]
        except Exception:
            logger.exception("Unexpected error retrieving integers from Random.org")

        # Fallback to secrets module if Random.org fails
        range_size = max_val - min_val + 1
        value = min_val + secrets.randbelow(range_size)
        logger.debug(
            "Using local randomness fallback",
            extra={"min": min_val, "max": max_val, "value": value}
        )
        return value

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_quota(self) -> Optional[int]:
        """Get remaining API quota in bits"""
        result = await self._make_request(
            "getUsage",
            {}
        )
        if result:
            return result.get("bitsLeft", 0)
        return None
