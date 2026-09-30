"""SMARD Client — Energiemarktdaten der Bundesnetzagentur."""

from bisect import bisect_right
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from src.config import settings
from src.clients.http import bounded_get

# SMARD Filter-IDs für verschiedene Datenreihen
SMARD_FILTERS = {
    # Stromerzeugung
    "biomasse": 4169,
    "wasserkraft": 4070,
    "wind_offshore": 1225,
    "wind_onshore": 4067,
    "photovoltaik": 4068,
    "sonstige_erneuerbare": 4069,
    "kernenergie": 1224,
    "braunkohle": 1223,
    "steinkohle": 4071,
    "erdgas": 4072,
    "pumpspeicher": 4073,
    "sonstige_konventionelle": 4074,
    # Stromverbrauch
    "stromverbrauch_gesamt": 410,
    # Marktpreise
    "grosshandelspreise": 4169,
    "day_ahead_preis": 4170,
}

# Auflösungen
SMARD_RESOLUTIONS = {
    "stunde": "hour",
    "viertelstunde": "quarterhour",
    "tag": "day",
    "woche": "week",
    "monat": "month",
}


class SmardClient:
    """Async-Client für SMARD Energiemarktdaten.

    Kein API-Key nötig. Daten der Bundesnetzagentur.
    """

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.http_timeout)
        self._base = settings.smard_base_url

    async def get_chart_data(
        self,
        filter_id: int,
        resolution: str = "day",
        region: str = "DE",
        timestamp: int | None = None,
    ) -> dict:
        """Zeitreihendaten für einen bestimmten Filter abrufen.

        Args:
            filter_id: SMARD Filter-ID (siehe SMARD_FILTERS)
            resolution: Zeitauflösung (hour, quarterhour, day, week, month)
            region: Ländercode (DE, AT, LU, DE-50HZ, DE-AMPRION, etc.)
            timestamp: Unix-Timestamp für den Startzeitpunkt (optional)
        """
        # Verfügbare Timestamps abrufen wenn keiner angegeben
        if timestamp is None:
            ts_resp = await bounded_get(
                self._client,
                f"{self._base}/{filter_id}/{region}/index_{resolution}.json",
            )
            ts_resp.raise_for_status()
            timestamps = ts_resp.json().get("timestamps", [])
            if not timestamps:
                return {"error": "Keine Daten verfügbar"}
            timestamp = max(timestamps)  # Neueste Daten

        resp = await bounded_get(
            self._client,
            f"{self._base}/{filter_id}/{region}/{filter_id}_{region}_{resolution}_{timestamp}.json",
        )
        resp.raise_for_status()
        return resp.json()

    async def get_available_timestamps(
        self,
        filter_id: int,
        resolution: str = "day",
        region: str = "DE",
    ) -> list[int]:
        """Verfügbare Zeitstempel für eine Datenreihe."""
        resp = await bounded_get(
            self._client, f"{self._base}/{filter_id}/{region}/index_{resolution}.json"
        )
        resp.raise_for_status()
        return resp.json().get("timestamps", [])

    async def get_daily_window(
        self,
        filter_id: int,
        days: int = 14,
        end_date: date | None = None,
    ) -> dict:
        """Read a Berlin calendar window across SMARD chunk boundaries.

        Include today by default. Gaps remain missing, and older observations
        never substitute for a missing day within the requested window.
        """
        if not 1 <= days <= 31:
            raise ValueError("days muss zwischen 1 und 31 liegen.")
        berlin = ZoneInfo("Europe/Berlin")
        end_date = end_date or datetime.now(berlin).date()
        start_date = end_date - timedelta(days=days - 1)
        start = int(datetime.combine(start_date, time.min, berlin).timestamp() * 1000)
        stop = int(
            datetime.combine(end_date + timedelta(days=1), time.min, berlin).timestamp()
            * 1000
        )
        timestamps = sorted(
            set(await self.get_available_timestamps(filter_id, resolution="day"))
        )
        first = max(0, bisect_right(timestamps, start) - 1)
        chunks = [ts for ts in timestamps[first:] if ts < stop]
        # Daily data should require at most one chunk per calendar day plus
        # its predecessor. Bound upstream work even for an unexpected index.
        if len(chunks) > days + 1:
            raise ValueError("Unerwartete Anzahl von Datenblöcken.")
        daily = {}
        for timestamp in chunks:
            data = await self.get_chart_data(
                filter_id, resolution="day", timestamp=timestamp
            )
            if "error" in data:
                raise ValueError("Zeitreihe nicht verfügbar.")
            for ts, value in sorted(data.get("series", []), key=lambda item: item[0]):
                if start <= ts < stop:
                    day = datetime.fromtimestamp(ts / 1000, berlin).date()
                    daily[day] = [ts, value]
        series = [daily[day] for day in sorted(daily) if daily[day][1] is not None]
        return {
            "series": series,
            "von": start_date.isoformat(),
            "bis": end_date.isoformat(),
            "vollstaendig": len(series) == days,
        }

    async def close(self):
        """HTTP-Client schließen."""
        await self._client.aclose()
