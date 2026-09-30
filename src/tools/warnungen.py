"""Warnungen-Tools — NINA Katastrophenwarnungen."""

from mcp.server.mcpserver import MCPServer

from src.tools.errors import safe_tool

from src.clients.nina import IncompleteWarningsError, NinaClient

_nina = NinaClient()


def register_warnungen_tools(mcp: MCPServer):
    """Warnungs-bezogene MCP-Tools registrieren."""

    @mcp.tool()
    @safe_tool
    async def nina_warnungen() -> dict:
        """Aktuelle Katastrophen-Warnungen in Deutschland (NINA/BBK).

        Zeigt Hochwasser, Unwetter, Stromausfälle, Brände und andere
        Gefahrenlagen. Quelle: Bundesamt für Bevölkerungsschutz.
        """
        failed_channels = []
        try:
            warnings = await _nina.get_warnings()
        except IncompleteWarningsError as exc:
            warnings = exc.warnings
            failed_channels = exc.failed_channels

        items = []
        for w in warnings[:30]:
            payload = w.get("payload") or {}
            data_list = payload.get("data", {})
            headline = ""
            area = ""

            if isinstance(data_list, dict):
                headline = data_list.get("headline", "")
                area = (data_list.get("area") or {}).get("description", "")

            items.append(
                {
                    "id": w.get("id", ""),
                    "titel": headline or (w.get("i18nTitle") or {}).get("de", ""),
                    "kanal": w.get("_channel", ""),
                    "typ": payload.get("type", ""),
                    "schweregrad": payload.get("severity", ""),
                    "gebiet": area,
                    "gesendet": payload.get("sent", ""),
                }
            )

        result = {
            "vollstaendig": not failed_channels,
            "fehlgeschlagene_kanaele": failed_channels,
            "anzahl_warnungen": len(warnings),
            "warnungen": items,
        }
        if failed_channels:
            result["error"] = (
                "Warnungsdaten unvollständig; fehlende Meldungen bedeuten keine Entwarnung."
            )
        return result
