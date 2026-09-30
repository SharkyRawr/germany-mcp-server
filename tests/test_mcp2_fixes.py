"""MCP 2 transport and regressions for the API review findings."""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.clients.bundestag import BundestagClient, MissingBundestagApiKey
from src.config import settings
from src.tools import energiepreise, politik, wetter
from test_regressions import registered


class ReviewFixes(unittest.IsolatedAsyncioTestCase):
    async def test_mcp2_stdio_initializes_lists_and_calls_tools(self):
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "src.server"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={"BUNDESTAG_API_KEY": ""},
        )
        async with asyncio.timeout(20):
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual(len(tools.tools), 16)
                    for name, arguments, message in (
                        ("get_energy_prices", {"type": "gas"}, "Gaspreise"),
                        (
                            "bundestag_suche",
                            {"suchbegriff": "Klima"},
                            "BUNDESTAG_API_KEY",
                        ),
                        ("bundestag_aktivitaeten", {}, "BUNDESTAG_API_KEY"),
                    ):
                        result = await session.call_tool(name, arguments)
                        self.assertFalse(result.is_error)
                        self.assertIn(
                            message, json.loads(result.content[0].text)["error"]
                        )

    async def test_weather_warning_localized_text(self):
        tool = registered(wetter.register_wetter_tools, "wetter_warnungen")
        alerts = [
            {
                "headline_de": "Sturm",
                "description_de": "Starke Böen",
                "event_de": "BÖEN",
                "headline_en": "Storm",
                "description_en": "Gusts",
                "event_en": "GALE",
            },
            {
                "headline_de": None,
                "description_de": "",
                "event_de": None,
                "headline_en": "Storm",
                "description_en": "Gusts",
                "event_en": "GALE",
            },
        ]
        with patch.object(
            wetter._brightsky, "get_alerts", AsyncMock(return_value={"alerts": alerts})
        ):
            result = await tool()
        texts = [(w["titel"], w["beschreibung"], w["typ"]) for w in result["warnungen"]]
        self.assertEqual(
            texts, [("Sturm", "Starke Böen", "BÖEN"), ("Storm", "Gusts", "GALE")]
        )

    async def test_gas_never_fetches_an_electricity_series(self):
        tool = registered(
            energiepreise.register_energiepreise_tools, "get_energy_prices"
        )
        with patch.object(
            energiepreise._smard, "get_daily_window", AsyncMock()
        ) as fetch:
            result = await tool(" GAS ")
        fetch.assert_not_awaited()
        self.assertIn("error", result)
        self.assertNotIn("gas", result["verfuegbare_typen"])
        self.assertNotIn("aktueller_preis", result)

    async def test_bundestag_authentication_is_required_and_errors_are_safe(self):
        client = BundestagClient()
        await client.close()
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(401, text="private-upstream-detail")

        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)
        with patch.object(settings, "bundestag_api_key", " "):
            for method, args in (
                (client.search_drucksachen, ("Klima",)),
                (client.search_vorgaenge, ("Klima",)),
                (client.get_aktivitaeten, ()),
            ):
                with self.assertRaises(MissingBundestagApiKey):
                    await method(*args)
        self.assertEqual(requests, [])
        tool = registered(politik.register_politik_tools, "bundestag_aktivitaeten")
        with (
            patch.object(settings, "bundestag_api_key", "test-secret"),
            patch.object(politik, "_bundestag", client),
        ):
            result = await tool()
        self.assertEqual(requests[0].headers["Authorization"], "ApiKey test-secret")
        self.assertIn("API-Key", result["error"])
        self.assertNotIn("test-secret", str(result))
        self.assertNotIn("private-upstream-detail", str(result))


if __name__ == "__main__":
    unittest.main()
