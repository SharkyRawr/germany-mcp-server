"""Germany MCP Server — Deutsche Behoerden-Daten fuer AI-Agents.

Buendelt 10 kostenlose deutsche APIs:
- Autobahn (Staus, Baustellen, Sperrungen, Ladestationen)
- Wetter (DWD via Bright Sky)
- DWD-Wetterwarnungen (Sturm, Gewitter, Starkregen etc.)
- NINA Katastrophenwarnungen
- Energiemarkt (SMARD/Bundesnetzagentur)
- Energiepreise (Strompreise via SMARD)
- Bundestag (Drucksachen, Vorgaenge)
- Pollenflug (DWD)
- Statistik (Destatis via Eurostat — BIP, Bevoelkerung, Inflation)
- Bundesgesetze (gesetze-im-internet.de — 6000+ Gesetze)
"""

import os

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import PlainTextResponse

from src.tools.verkehr import register_verkehr_tools
from src.tools.wetter import register_wetter_tools
from src.tools.warnungen import register_warnungen_tools
from src.tools.dwd_warnungen import register_dwd_warnungen_tools
from src.tools.energie import register_energie_tools
from src.tools.energiepreise import register_energiepreise_tools
from src.tools.politik import register_politik_tools
from src.tools.gesundheit import register_gesundheit_tools
from src.tools.statistik import register_statistik_tools
from src.tools.recht import register_recht_tools

# MCP-Server erstellen
mcp = MCPServer(
    "Germany MCP Server",
    instructions=(
        "Gibt AI-Agents Zugriff auf deutsche Behoerden-Daten: "
        "Autobahn-Verkehr, Wetter, DWD-Wetterwarnungen, Katastrophenwarnungen, "
        "Energiemarkt, Energiepreise, Bundestag, Pollenflug, "
        "Destatis-Statistiken und Bundesgesetze."
    ),
)

# Alle Tool-Gruppen registrieren
register_verkehr_tools(mcp)
register_wetter_tools(mcp)
register_warnungen_tools(mcp)
register_dwd_warnungen_tools(mcp)
register_energie_tools(mcp)
register_energiepreise_tools(mcp)
register_politik_tools(mcp)
register_gesundheit_tools(mcp)
register_statistik_tools(mcp)
register_recht_tools(mcp)


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request):
    return PlainTextResponse("ok")


def main():
    """Server starten."""
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8000")),
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=os.getenv(
                    "MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,[::1]:*"
                ).split(","),
                allowed_origins=os.getenv(
                    "MCP_ALLOWED_ORIGINS", "http://localhost:*,http://127.0.0.1:*"
                ).split(","),
            ),
        )
    elif transport == "stdio":
        mcp.run(transport="stdio")
    else:
        raise ValueError("MCP_TRANSPORT must be stdio or streamable-http")


if __name__ == "__main__":
    main()
