"""Autobahn API Client — Staus, Baustellen, Webcams, Ladestationen."""

import httpx

from src.config import settings
from src.clients.http import bounded_get
from src.validation import road_name


class AutobahnClient:
    """Async-Client für die Autobahn App API (autobahn.de)."""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.http_timeout)
        self._base = settings.autobahn_base_url

    async def get_roads(self) -> list[str]:
        """Liste aller verfügbaren Autobahnen abrufen."""
        resp = await bounded_get(self._client, f"{self._base}")
        resp.raise_for_status()
        return resp.json().get("roads", [])

    async def get_roadworks(self, road: str) -> list[dict]:
        """Aktuelle Baustellen auf einer Autobahn."""
        resp = await bounded_get(self._client, f"{self._base}/{road_name(road)}/services/roadworks")
        resp.raise_for_status()
        return resp.json().get("roadworks", [])

    async def get_warnings(self, road: str) -> list[dict]:
        """Aktuelle Verkehrsmeldungen/Warnungen auf einer Autobahn."""
        resp = await bounded_get(self._client, f"{self._base}/{road_name(road)}/services/warning")
        resp.raise_for_status()
        return resp.json().get("warning", [])

    async def get_closures(self, road: str) -> list[dict]:
        """Aktuelle Sperrungen auf einer Autobahn."""
        resp = await bounded_get(self._client, f"{self._base}/{road_name(road)}/services/closure")
        resp.raise_for_status()
        return resp.json().get("closure", [])

    async def get_charging_stations(self, road: str) -> list[dict]:
        """Ladestationen für E-Autos entlang einer Autobahn."""
        resp = await bounded_get(
            self._client,
            f"{self._base}/{road_name(road)}/services/electric_charging_station"
        )
        resp.raise_for_status()
        return resp.json().get("electric_charging_station", [])

    async def get_webcams(self, road: str) -> list[dict]:
        """Webcams entlang einer Autobahn."""
        resp = await bounded_get(self._client, f"{self._base}/{road_name(road)}/services/webcam")
        resp.raise_for_status()
        return resp.json().get("webcam", [])

    async def close(self):
        """HTTP-Client schließen."""
        await self._client.aclose()
