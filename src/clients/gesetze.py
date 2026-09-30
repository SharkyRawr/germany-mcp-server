"""Gesetze Client — Deutsche Bundesgesetze via gesetze-im-internet.de.

Laedt den XML-Gesamtindex aller Bundesgesetze und ermoeglicht
eine Volltextsuche ueber Titel. Kein API-Key noetig.
"""

import asyncio
from time import monotonic

from defusedxml import ElementTree as ET

import httpx

from src.config import settings
from src.clients.http import bounded_get


class GesetzeClient:
    """Async-Client fuer deutsche Bundesgesetze.

    Nutzt den oeffentlichen XML-Index von gesetze-im-internet.de
    (BMJ — Bundesministerium der Justiz).
    """

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.http_timeout)
        self._base = settings.gesetze_base_url
        self._cache: list[dict] | None = None
        self._cache_expires = 0.0
        self._cache_lock = asyncio.Lock()

    async def _load_index(self) -> list[dict]:
        """Gesetzes-Index laden und cachen (ca. 6000+ Eintraege)."""
        async with self._cache_lock:
            if self._cache is not None and monotonic() < self._cache_expires:
                return self._cache
            # Failed refreshes raise; an expired index is never presented as fresh.
            index = await self._fetch_index()
            self._cache = index
            self._cache_expires = monotonic() + settings.law_index_cache_ttl
            return index

    async def _fetch_index(self) -> list[dict]:
        resp = await bounded_get(
            self._client,
            f"{self._base}/gii-toc.xml",
            follow_redirects=True,
        )
        resp.raise_for_status()

        # XML parsen
        root = ET.fromstring(resp.content, forbid_dtd=True)
        gesetze = []
        for item in root.findall("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is not None and title_el.text:
                # Abkuerzung aus dem Link extrahieren
                link = link_el.text if link_el is not None and link_el.text else ""
                abkuerzung = ""
                if link:
                    # z.B. http://www.gesetze-im-internet.de/gg/xml.zip -> gg
                    parts = link.rstrip("/").split("/")
                    if len(parts) >= 2:
                        abkuerzung = parts[-2]

                gesetze.append(
                    {
                        "titel": title_el.text.strip(),
                        "abkuerzung": abkuerzung,
                        "link": link,
                        "url": (
                            f"https://www.gesetze-im-internet.de/{abkuerzung}/"
                            if abkuerzung
                            else ""
                        ),
                    }
                )

        return gesetze

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Gesetze nach Titel durchsuchen.

        Args:
            query: Suchbegriff (z.B. "Grundgesetz", "Strafgesetzbuch", "Mietrecht")
            limit: Max. Ergebnisse (Standard: 10)
        """
        if not 1 <= limit <= 50:
            raise ValueError("limit muss zwischen 1 und 50 liegen.")
        query_lower = query.strip().lower()
        if not query_lower:
            raise ValueError("Suchbegriff darf nicht leer sein.")
        gesetze = await self._load_index()
        query_parts = query_lower.split()

        treffer = []
        for g in gesetze:
            titel_lower = g["titel"].lower()
            abk_lower = g["abkuerzung"].lower()

            # Exakter Abkuerzungs-Treffer (z.B. "gg", "stgb", "bgb")
            if query_lower == abk_lower:
                treffer.insert(0, {**g, "_score": 100})
                continue

            # Alle Suchbegriffe muessen im Titel vorkommen
            if all(part in titel_lower for part in query_parts):
                # Besserer Score fuer kuerzere Titel (spezifischer)
                score = 50 - min(len(g["titel"]), 50)
                treffer.append({**g, "_score": score})

        # Nach Score sortieren, beste zuerst
        treffer.sort(key=lambda x: x.get("_score", 0), reverse=True)

        # Score-Feld entfernen
        ergebnis = []
        for t in treffer[:limit]:
            t.pop("_score", None)
            ergebnis.append(t)

        return ergebnis

    async def get_law_count(self) -> int:
        """Anzahl aller verfuegbaren Bundesgesetze zurueckgeben."""
        gesetze = await self._load_index()
        return len(gesetze)

    async def close(self):
        """HTTP-Client schliessen."""
        await self._client.aclose()
