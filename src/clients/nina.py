"""NINA Client — Warnungen des BBK (Bundesamt für Bevölkerungsschutz)."""

import re

import httpx

from src.config import settings
from src.clients.http import bounded_get


class IncompleteWarningsError(RuntimeError):
    """Some warning feeds could not be read; retain the available warnings."""

    def __init__(self, warnings: list[dict], failed_channels: list[str]):
        super().__init__("NINA-Warnungen konnten nicht vollständig abgerufen werden.")
        self.warnings = warnings
        self.failed_channels = failed_channels


class NinaClient:
    """Async-Client für die NINA Warn-API.

    Liefert Katastrophen-Warnungen, Hochwasser, Unwetter etc.
    Kein API-Key nötig.
    """

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.http_timeout)
        self._base = settings.nina_base_url

    async def get_warnings(self) -> list[dict]:
        """Alle aktuellen Warnungen (bundesweit, Mowas + Katwarn + DWD + Hochwasser)."""
        all_warnings = []
        failed_channels = []
        # Verschiedene Warn-Kanäle abfragen
        for channel in ("mowas", "katwarn", "biwapp", "dwd", "lhp"):
            try:
                resp = await bounded_get(
                    self._client, f"{self._base}/{channel}/mapData.json"
                )
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list) or not all(
                    isinstance(w, dict) for w in data
                ):
                    raise ValueError("Ungültiges Warnungsformat")
                all_warnings.extend({**w, "_channel": channel} for w in data)
            except (httpx.HTTPError, ValueError, TimeoutError):
                failed_channels.append(channel)
        if failed_channels:
            raise IncompleteWarningsError(all_warnings, failed_channels)
        return all_warnings

    async def get_warning_details(self, warning_id: str) -> dict:
        """Details zu einer bestimmten Warnung abrufen."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", warning_id):
            raise ValueError("Ungültige Warnungs-ID.")
        resp = await bounded_get(
            self._client, f"{self._base}/warnings/{warning_id}.json"
        )
        resp.raise_for_status()
        return resp.json()

    async def get_ags_warnings(self, ags: str) -> list[dict]:
        """Warnungen für einen bestimmten Ort via AGS-Code.

        AGS = Amtlicher Gemeindeschlüssel (z.B. '091620000000' für München).
        Die ersten 5 Stellen reichen oft (Kreis-Ebene).
        """
        if not re.fullmatch(r"[0-9]{5}(?:[0-9]{7})?", ags):
            raise ValueError(
                "Kreisschlüssel muss aus 5 oder Regionalschlüssel aus 12 Ziffern bestehen."
            )
        ags = ags.ljust(12, "0")
        resp = await bounded_get(self._client, f"{self._base}/dashboard/{ags}.json")
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        """HTTP-Client schließen."""
        await self._client.aclose()
