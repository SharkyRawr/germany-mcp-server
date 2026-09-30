"""Energie-Tools — SMARD Energiemarktdaten (Bundesnetzagentur)."""

from mcp.server.fastmcp import FastMCP

from src.tools.errors import safe_error, safe_tool

from src.clients.smard import SmardClient, SMARD_FILTERS

_smard = SmardClient()


def register_energie_tools(mcp: FastMCP):
    """Energie-bezogene MCP-Tools registrieren."""

    @mcp.tool()
    @safe_tool
    async def strom_erzeugung() -> dict:
        """Aktuelle Stromerzeugung in Deutschland nach Energieträger.

        Zeigt die Stromerzeugung des neuesten verfügbaren Tages aus
        Wind, Solar, Kohle, Gas etc. Daten der Bundesnetzagentur (SMARD).
        """
        renewable = (
            "wind_onshore", "wind_offshore", "photovoltaik", "biomasse",
            "wasserkraft", "sonstige_erneuerbare",
        )
        conventional = (
            "braunkohle", "steinkohle", "erdgas", "kernenergie",
            "pumpspeicher", "sonstige_konventionelle",
        )
        readings = {}
        errors = {}
        for name in renewable + conventional:
            try:
                data = await _smard.get_chart_data(SMARD_FILTERS[name], resolution="day")
                readings[name] = {ts: val for ts, val in data.get("series", []) if val is not None}
            except Exception as exc:
                readings[name] = {}
                errors[name] = safe_error(exc)

        # Report the newest observed interval. Never add a stale reading from
        # another day or interpret an unavailable category as zero generation.
        timestamp = max((ts for series in readings.values() for ts in series), default=None)
        ergebnisse = {}
        for name, series in readings.items():
            value = series.get(timestamp)
            ergebnisse[name] = {"mwh": value, "timestamp": timestamp}
            if value is None:
                ergebnisse[name]["error"] = errors.get(name, "Keine Daten für diesen Zeitraum verfügbar.")

        def total(names):
            values = [ergebnisse[name]["mwh"] for name in names]
            return sum(values) if all(value is not None for value in values) else None

        erneuerbare = total(renewable)
        konventionelle = total(conventional)
        gesamt = total(renewable + conventional)
        missing = [name for name, value in ergebnisse.items() if value["mwh"] is None]
        result = {
            "timestamp": timestamp,
            "vollstaendig": not missing,
            "fehlende_traeger": missing,
            "erzeugung_nach_traeger": ergebnisse,
            "erneuerbare_mwh": erneuerbare,
            "konventionelle_mwh": konventionelle,
            "gesamt_mwh": gesamt,
            "erneuerbare_anteil_pct": round(erneuerbare / gesamt * 100, 1) if gesamt is not None and gesamt > 0 else None,
        }
        if missing:
            result["error"] = "Stromerzeugungsdaten unvollständig; Gesamtsumme und Anteil nicht verfügbar."
        return result

    @mcp.tool()
    @safe_tool
    async def stromverbrauch() -> dict:
        """Aktueller Stromverbrauch in Deutschland.

        Zeigt den Gesamtverbrauch und Trend. Daten der Bundesnetzagentur.
        """
        try:
            data = await _smard.get_chart_data(410, resolution="day")
            series = data.get("series", [])

            # Letzte Werte mit Daten
            recent = []
            for ts, val in reversed(series):
                if val is not None:
                    recent.append({"timestamp": ts, "mwh": val})
                    if len(recent) >= 7:
                        break

            recent.reverse()

            return {
                "letzte_werte": recent,
                "aktuell_mwh": recent[-1]["mwh"] if recent else None,
                "trend": _berechne_trend(recent),
            }
        except Exception as e:
            return {"error": safe_error(e)}


def _berechne_trend(werte: list[dict]) -> str:
    """Einfachen Trend aus den letzten Werten berechnen."""
    if len(werte) < 2:
        return "unbekannt"
    aktuell = werte[-1].get("mwh", 0) or 0
    vorher = werte[-2].get("mwh", 0) or 0
    if vorher == 0:
        return "unbekannt"
    diff_pct = ((aktuell - vorher) / vorher) * 100
    if diff_pct > 5:
        return f"steigend ({diff_pct:+.1f}%)"
    elif diff_pct < -5:
        return f"fallend ({diff_pct:+.1f}%)"
    return f"stabil ({diff_pct:+.1f}%)"
