"""Energiepreise-Tools — Deutsche Strompreise via SMARD."""

from mcp.server.mcpserver import MCPServer

from src.tools.errors import safe_error, safe_tool

from src.clients.smard import SmardClient

_smard = SmardClient()

# SMARD Filter-IDs fuer Preisdaten
PREIS_FILTER = {
    "strom": {
        "filter_id": 4170,
        "label": "Day-Ahead-Strompreis (Boerse)",
        "einheit": "EUR/MWh",
    },
    "electricity": {
        "filter_id": 4170,
        "label": "Day-Ahead-Strompreis (Boerse)",
        "einheit": "EUR/MWh",
    },
}


def register_energiepreise_tools(mcp: MCPServer):
    """Energiepreis-Tools registrieren."""

    @mcp.tool()
    @safe_tool
    async def get_energy_prices(
        type: str = "electricity",
    ) -> dict:
        """Aktuelle deutsche Strompreise abrufen.

        Zeigt Boersenpreise fuer Strom (Day-Ahead, EPEX Spot)
        aus Daten der Bundesnetzagentur (SMARD). Gaspreise sind nicht verfügbar.
        Zeitraum: heute und die 13 vorherigen Kalendertage (Europe/Berlin).
        Bei Datenlücken werden Kennzahlen nur aus verfügbaren Tagen berechnet.

        Args:
            type: Art des Energietraegers.
                - "electricity" oder "strom" — Boersenstrompreis
        """
        type_lower = type.lower().strip()
        if type_lower == "gas":
            return {
                "error": "Gaspreise sind nicht verfügbar: Es ist keine verifizierte Gaspreisquelle angebunden.",
                "verfuegbare_typen": list(PREIS_FILTER),
            }
        config = PREIS_FILTER.get(type_lower)

        if not config:
            return {
                "error": f"Unbekannter Typ: {type}",
                "verfuegbare_typen": list(PREIS_FILTER),
            }

        try:
            data = await _smard.get_daily_window(config["filter_id"], days=14)
            series = data["series"]
            werte = [{"timestamp": ts, "preis": round(val, 2)} for ts, val in series]

            # Statistik berechnen
            preise = [val for _, val in series]
            aktuell = preise[-1] if preise else None
            durchschnitt = round(sum(preise) / len(preise), 2) if preise else None
            minimum = min(preise) if preise else None
            maximum = max(preise) if preise else None

            # Trend
            trend = "unbekannt"
            if len(preise) >= 2:
                diff = preise[-1] - preise[-2]
                if diff > 1:
                    trend = f"steigend (+{diff:.1f} {config['einheit']})"
                elif diff < -1:
                    trend = f"fallend ({diff:.1f} {config['einheit']})"
                else:
                    trend = f"stabil ({diff:+.1f} {config['einheit']})"

            result = {
                "typ": config["label"],
                "einheit": config["einheit"],
                "aktueller_preis": round(aktuell, 2) if aktuell is not None else None,
                "preis_timestamp": werte[-1]["timestamp"] if werte else None,
                "zeitraum_von": data["von"],
                "zeitraum_bis": data["bis"],
                "anzahl_tage_mit_daten": len(werte),
                "vollstaendig": data["vollstaendig"],
                "durchschnitt_14_tage": durchschnitt,
                "minimum_14_tage": round(minimum, 2) if minimum is not None else None,
                "maximum_14_tage": round(maximum, 2) if maximum is not None else None,
                "trend": trend,
                "verlauf": werte,
                "quelle": "SMARD / Bundesnetzagentur",
            }
            if not data["vollstaendig"]:
                result["hinweis"] = (
                    "Daten im 14-Tage-Zeitraum unvollständig; Statistik nutzt nur verfügbare Tage."
                )
            if not werte:
                result["error"] = "Keine Preisdaten im angefragten Zeitraum verfügbar."
            return result
        except Exception as e:
            return {"error": safe_error(e)}
