"""Bundestag DIP Client — Parlamentarische Daten (Drucksachen, Vorgänge, Plenarprotokolle)."""

import httpx

from src.config import settings
from src.clients.http import bounded_get


class BundestagClient:
    """Async-Client für die Bundestag DIP API.

    Braucht optional einen API-Key (kostenlos registrierbar).
    Ohne Key: eingeschränktes Rate-Limit.
    """

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.http_timeout)
        self._base = settings.bundestag_base_url

    def _headers(self) -> dict:
        """Request-Headers mit optionalem API-Key."""
        headers = {"Accept": "application/json"}
        key = settings.bundestag_api_key
        if key:
            headers["Authorization"] = f"ApiKey {key}"
        return headers

    async def search_drucksachen(
        self, query: str, wahlperiode: int = 21, limit: int = 10
    ) -> dict:
        """Bundestagsdrucksachen durchsuchen.

        Args:
            query: Suchbegriff
            wahlperiode: Wahlperiode (21 = aktuell)
            limit: Max. Ergebnisse
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit muss zwischen 1 und 100 liegen.")
        resp = await bounded_get(
            self._client,
            f"{self._base}/drucksache",
            params={
                "f.zuordnung": "BT",
                "f.wahlperiode": wahlperiode,
                "f.drucksachetyp": "Gesetzentwurf",
                "f.titel": query,
                "format": "json",
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return {**data, "documents": data.get("documents", [])[:limit]}

    async def search_vorgaenge(
        self, query: str, wahlperiode: int = 21, limit: int = 10
    ) -> dict:
        """Parlamentarische Vorgänge durchsuchen."""
        params = {
            "f.wahlperiode": wahlperiode,
            "format": "json",
        }
        if query:
            params["f.titel"] = query
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit muss zwischen 1 und 100 liegen.")
        resp = await bounded_get(
            self._client,
            f"{self._base}/vorgang",
            params=params,
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return {**data, "documents": data.get("documents", [])[:limit]}

    async def get_aktivitaeten(self, limit: int = 10) -> dict:
        """Letzte parlamentarische Aktivitäten."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit muss zwischen 1 und 100 liegen.")
        resp = await bounded_get(
            self._client,
            f"{self._base}/aktivitaet",
            params={"format": "json"},
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return {**data, "documents": data.get("documents", [])[:limit]}

    async def close(self):
        """HTTP-Client schließen."""
        await self._client.aclose()
