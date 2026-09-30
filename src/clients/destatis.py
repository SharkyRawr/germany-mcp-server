"""Destatis Client — Deutsche Statistiken via Eurostat API.

Nutzt die Eurostat JSON API fuer offizielle deutsche Statistikdaten
(Bevoelkerung, BIP, Arbeitslosigkeit, Inflation).
Eurostat bezieht die Daten direkt von Destatis — gleiche Qualitaet,
aber frei zugaenglich ohne API-Key.
"""

from datetime import date

import httpx

from src.config import settings
from src.clients.http import bounded_get


# Vordefinierte Indikatoren mit Eurostat-Dataset-IDs und Parametern
INDICATORS = {
    "bevoelkerung": {
        "dataset": "demo_pjan",
        "params": {"geo": "DE", "age": "TOTAL", "sex": "T", "unit": "NR"},
        "label": "Bevoelkerung am 1. Januar",
        "einheit": "Personen",
    },
    "bip": {
        "dataset": "nama_10_gdp",
        "params": {"geo": "DE", "na_item": "B1GQ", "unit": "CP_MEUR"},
        "label": "Bruttoinlandsprodukt (nominal)",
        "einheit": "Mio. EUR",
    },
    "bip_pro_kopf": {
        "dataset": "nama_10_pc",
        "params": {"geo": "DE", "na_item": "B1GQ", "unit": "CP_EUR_HAB"},
        "label": "BIP pro Kopf",
        "einheit": "EUR pro Einwohner",
    },
    "arbeitslosigkeit": {
        "dataset": "une_rt_a",
        "params": {"geo": "DE", "sex": "T", "age": "Y15-74", "unit": "PC_ACT"},
        "label": "Arbeitslosenquote (15-74 Jahre)",
        "einheit": "Prozent",
    },
    "inflation": {
        "dataset": "prc_hicp_aind",
        "params": {"geo": "DE", "coicop": "CP00", "unit": "RCH_A_AVG"},
        "label": "Inflationsrate (HVPI)",
        "einheit": "Prozent (Veraenderung zum Vorjahr)",
    },
    "inflation_index": {
        "dataset": "prc_hicp_aind",
        "params": {"geo": "DE", "coicop": "CP00", "unit": "INX_A_AVG"},
        "label": "Verbraucherpreisindex (HVPI, 2015=100)",
        "einheit": "Index (2015=100)",
    },
    "erwerbstaetigkeit": {
        "dataset": "lfsi_emp_a",
        "params": {"geo": "DE", "sex": "T", "age": "Y20-64", "unit": "PC_POP", "indic_em": "EMP_LFS"},
        "label": "Erwerbstaetigenquote (20-64 Jahre)",
        "einheit": "Prozent",
    },
}


class DestatisClient:
    """Async-Client fuer deutsche Statistikdaten via Eurostat.

    Kein API-Key noetig. Eurostat stellt offizielle Destatis-Daten
    als freie JSON-API bereit.
    """

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=settings.http_timeout)
        self._base = settings.eurostat_base_url

    async def get_indicator(
        self, indicator: str, year: int | None = None
    ) -> dict:
        """Einen Statistik-Indikator fuer Deutschland abrufen.

        Args:
            indicator: Indikator-Schluessel (z.B. "bevoelkerung", "bip")
            year: Optionales Jahr (z.B. 2023). Ohne = letzte 5 Jahre.
        """
        config = INDICATORS.get(indicator)
        if not config:
            return {
                "error": f"Unbekannter Indikator: {indicator}",
                "verfuegbare_indikatoren": list(INDICATORS.keys()),
            }

        params = dict(config["params"])
        params["lang"] = "de"
        params["freq"] = "A"

        if year is not None:
            if not 1900 <= year <= date.today().year:
                raise ValueError("Jahr muss zwischen 1900 und dem aktuellen Jahr liegen.")
            params["time"] = str(year)
        else:
            # Letzte 5 Jahre
            params["sinceTimePeriod"] = str(date.today().year - 4)

        url = f"{self._base}/data/{config['dataset']}"

        resp = await bounded_get(self._client, url, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Eurostat JSON-Response parsen
        values = data.get("value", {})
        # A flat time series is only unambiguous when every other dimension
        # has one member. Do not silently mix units or population categories.
        dimensions = data.get("id", [])
        sizes = data.get("size", [])
        if len(dimensions) != len(sizes) or "time" not in dimensions:
            raise ValueError("Ungültige Dimensionen in der Statistikantwort.")
        if any(size != 1 for name, size in zip(dimensions, sizes) if name != "time"):
            raise ValueError("Statistikantwort enthält mehrere Datenreihen.")

        # Index-zu-Jahr Mapping
        time_index = (
            data.get("dimension", {})
            .get("time", {})
            .get("category", {})
            .get("index", {})
        )

        # Werte den Jahren zuordnen
        if isinstance(time_index, list):
            time_index = {key: idx for idx, key in enumerate(time_index)}
        ergebnisse = {}
        for zeit_key, idx in time_index.items():
            if isinstance(values, list):
                wert = values[idx] if 0 <= idx < len(values) else None
            else:
                wert = values.get(str(idx))
            if wert is not None:
                ergebnisse[zeit_key] = wert

        return {
            "indikator": config["label"],
            "einheit": config["einheit"],
            "quelle": "Eurostat / Destatis",
            "daten": ergebnisse,
        }

    async def search_datasets(self, query: str, limit: int = 10) -> dict:
        """Eurostat-Datasets fuer Deutschland durchsuchen.

        Args:
            query: Suchbegriff (z.B. "population", "trade")
            limit: Max. Ergebnisse
        """
        # Eurostat Table of Contents als JSON
        url = f"{self._base}/dissemination/catalogue/toc"
        resp = await bounded_get(
            self._client,
            url,
            params={"q": query, "lang": "de", "limit": limit},
        )
        if resp.status_code != 200:
            # Fallback: vordefinierte Indikatoren zurueckgeben
            return {
                "hinweis": "Direkte Suche nicht verfuegbar, nutze vordefinierte Indikatoren",
                "verfuegbare_indikatoren": {
                    k: v["label"] for k, v in INDICATORS.items()
                },
            }
        return resp.json()

    async def close(self):
        """HTTP-Client schliessen."""
        await self._client.aclose()
