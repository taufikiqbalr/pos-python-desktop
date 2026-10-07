from __future__ import annotations

import json
from urllib import error, parse, request

from app.config import BUSINESS_API_TIMEOUT_SECONDS, BUSINESS_API_TOKEN


class IntegrationError(RuntimeError):
    pass


class JsonApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str = BUSINESS_API_TOKEN,
        timeout: float = BUSINESS_API_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None):
        if not self.base_url:
            raise IntegrationError("Base URL integration belum dikonfigurasi")

        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:
            raise IntegrationError(f"API HTTP {exc.code}: {path}") from exc
        except error.URLError as exc:
            raise IntegrationError(f"API tidak dapat diakses: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise IntegrationError("Respons API bukan JSON yang valid") from exc

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str, payload: dict):
        return self._request("POST", path, payload)


class InventoryApiClient(JsonApiClient):
    def lookup_product(self, code: str) -> dict | None:
        query = parse.urlencode({"code": code})
        data = self.get(f"/api/v1/products/lookup?{query}")
        if not data:
            return None
        return data.get("data", data)

    def search_products(self, term: str, limit: int = 100) -> list[dict]:
        query = parse.urlencode({"q": term, "limit": limit})
        data = self.get(f"/api/v1/products/search?{query}")
        if not data:
            return []
        result = data.get("data", data)
        return result if isinstance(result, list) else result.get("items", [])


class MembershipApiClient(JsonApiClient):
    def search_members(self, term: str, limit: int = 100) -> list[dict]:
        query = parse.urlencode({"q": term, "limit": limit})
        data = self.get(f"/api/v1/members/search?{query}")
        if not data:
            return []
        result = data.get("data", data)
        return result if isinstance(result, list) else result.get("items", [])


class PricingApiClient(JsonApiClient):
    def quote(
        self,
        *,
        member_no: str | None,
        items: list[dict],
        store_id: str,
    ) -> dict:
        data = self.post(
            "/api/v1/pricing/quote",
            {
                "member_no": member_no,
                "store_id": store_id,
                "items": items,
            },
        )
        return data.get("data", data) if data else {}
