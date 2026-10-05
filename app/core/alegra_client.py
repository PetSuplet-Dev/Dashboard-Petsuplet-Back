import base64
import asyncio
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings

class AlegraClient:
    def __init__(self):
        self.base_url = settings.URL_API_ALEGRA
        self.credentials = f"{settings.EMAIL_ALEGRA}:{settings.APIKEY_ALEGRA}"
        self.credentials_base64 = base64.b64encode(self.credentials.encode('utf-8')).decode('utf-8')
        self.headers = {
            'Authorization': f'Basic {self.credentials_base64}',
            'Accept': 'application/json'
        }
        self.rate_limit_retries = 5
        self.retry_delay = 2.0  # seconds
        self.initial_wait_time = 2  # seconds (kept for compatibility)

    async def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        url = f"{self.base_url}{endpoint}"
        
        response = None
        retryable_statuses = {408, 425, 429, 500, 502, 503, 504}
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(self.rate_limit_retries):
                try:
                    response = await client.get(url, headers=self.headers, params=params)
                except httpx.RequestError as exc:
                    print(f"HTTP request error for {endpoint} [{type(exc).__name__}] (attempt {attempt + 1}/{self.rate_limit_retries}): {exc}")
                    if attempt < self.rate_limit_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                    return None

                if response.status_code in retryable_statuses:
                    print(f"Transient error {response.status_code} for {endpoint}. Retrying in {self.retry_delay * (attempt + 1)}s (attempt {attempt + 1}/{self.rate_limit_retries})...")
                    if attempt < self.rate_limit_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                break

        if not response or response.status_code != 200:
            print(f"Error fetching data from Alegra API for {endpoint}: status {response.status_code if response else 'No response'}")
            return None
        
        response_data = response.json()
        
        # Alegra API can return a list directly or a dict with a 'data' key
        if isinstance(response_data, dict) and 'data' in response_data:
            return response_data.get('data', [])
        elif isinstance(response_data, list):
            return response_data
        else:
            return []

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        return await self._make_request(endpoint, params or {})

    async def get_all(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        return await self._make_request(endpoint, params or {})

    async def get_invoices_page(
        self,
        start: int = 0,
        limit: int = 30,
        order_field: str = 'id',
        order_direction: str = 'ASC',
        date: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        params = {
            'start': start,
            'limit': limit,
            'order_field': order_field,
            'order_direction': order_direction,
        }
        if metadata:
            params['metadata'] = metadata
        if date:
            params['date'] = date
        return await self._make_request("invoices", params)

    async def get_credit_notes_page(
        self,
        start: int = 0,
        limit: int = 30,
        order_field: str = 'id',
        order_direction: str = 'ASC',
        date: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        params = {
            'start': start,
            'limit': limit,
            'order_field': order_field,
            'order_direction': order_direction,
        }
        if metadata:
            params['metadata'] = metadata
        if date:
            params['date'] = date
        return await self._make_request("credit-notes", params)

def get_alegra_client() -> AlegraClient:
    return AlegraClient()
