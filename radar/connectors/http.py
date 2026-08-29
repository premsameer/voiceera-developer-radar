import random, time
import httpx


class ResilientClient:
    def __init__(self, headers: dict | None = None):
        self.client = httpx.Client(headers=headers, timeout=20, follow_redirects=True)

    def get(self, url: str, **kwargs):
        for attempt in range(4):
            response = self.client.get(url, **kwargs)
            if response.status_code not in (429, 500, 502, 503, 504):
                response.raise_for_status(); return response
            wait = float(response.headers.get("Retry-After", 2 ** attempt)) + random.random()
            time.sleep(min(wait, 10))
        response.raise_for_status()

