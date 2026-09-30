"""Offline tests for aligned energy data and bounded upstream access."""

import asyncio
import unittest
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx

from src.clients.bundestag import BundestagClient
from src.clients.gesetze import GesetzeClient
from src.clients.nina import NinaClient, IncompleteWarningsError
from src.clients.http import ResponseTooLarge, bounded_get
from src.clients.smard import SmardClient, SMARD_FILTERS
from src.config import settings
from src.tools import energie, energiepreise, gesundheit, recht
from src.tools.errors import safe_error, safe_tool
from test_regressions import registered


def timestamp(day):
    return int(
        datetime.combine(day, time.min, ZoneInfo("Europe/Berlin")).timestamp() * 1000
    )


class Chunks(httpx.AsyncByteStream):
    def __init__(self, *chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class RemainingFixes(unittest.IsolatedAsyncioTestCase):
    async def client(self, cls, handler):
        client = cls()
        await client.close()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)
        return client

    async def test_energy_includes_all_categories_and_real_zeros(self):
        tool = registered(energie.register_energie_tools, "strom_erzeugung")
        get = AsyncMock(return_value={"series": [[1000, 0], [2000, 10]]})
        with patch.object(energie._smard, "get_chart_data", get):
            result = await tool()
        self.assertEqual(get.await_count, 12)
        self.assertEqual(result["gesamt_mwh"], 120)
        self.assertEqual(result["erneuerbare_mwh"], 60)
        self.assertEqual(result["erneuerbare_anteil_pct"], 50)
        self.assertTrue(result["vollstaendig"])
        for name in ("sonstige_erneuerbare", "pumpspeicher", "sonstige_konventionelle"):
            self.assertIn(name, result["erzeugung_nach_traeger"])
        with patch.object(
            energie._smard,
            "get_chart_data",
            AsyncMock(return_value={"series": [[2000, 0]]}),
        ):
            result = await tool()
        self.assertEqual(result["gesamt_mwh"], 0)
        self.assertTrue(result["vollstaendig"])
        self.assertIsNone(result["erneuerbare_anteil_pct"])

    async def test_energy_never_adds_stale_or_missing_values(self):
        async def get(filter_id, **kwargs):
            if filter_id == SMARD_FILTERS["erdgas"]:
                return {"series": [[1000, 999], [2000, None]]}
            return {"series": [[2000, 10]]}

        tool = registered(energie.register_energie_tools, "strom_erzeugung")
        with patch.object(energie._smard, "get_chart_data", get):
            result = await tool()
        self.assertEqual(result["timestamp"], 2000)
        self.assertEqual(result["erneuerbare_mwh"], 60)
        self.assertIsNone(result["konventionelle_mwh"])
        self.assertIsNone(result["gesamt_mwh"])
        self.assertIsNone(result["erneuerbare_anteil_pct"])
        self.assertEqual(result["fehlende_traeger"], ["erdgas"])
        self.assertIsNone(result["erzeugung_nach_traeger"]["erdgas"]["mwh"])
        with patch.object(
            energie._smard,
            "get_chart_data",
            AsyncMock(side_effect=httpx.ConnectError("private-detail")),
        ):
            result = await tool()
        self.assertIsNone(result["gesamt_mwh"])
        self.assertFalse(result["vollstaendig"])
        self.assertNotIn("private-detail", str(result))

    async def test_price_window_fetches_previous_chunk_across_dst(self):
        # This 14-calendar-day interval includes the 23-hour DST transition.
        start, end = date(2026, 3, 24), date(2026, 4, 6)
        days = [start + timedelta(days=i) for i in range(14)]
        march, april = timestamp(date(2026, 3, 1)), timestamp(date(2026, 4, 1))
        requests = []

        def handler(request):
            requests.append(request.url.path)
            if "/index_day.json" in request.url.path:
                return httpx.Response(200, json={"timestamps": [april, march]})
            month = 3 if str(march) in request.url.path else 4
            data = [[timestamp(day), 10] for day in days if day.month == month]
            data += [
                [timestamp(start - timedelta(days=1)), 9999],
                [timestamp(end + timedelta(days=1)), 9999],
            ]
            return httpx.Response(200, json={"series": data})

        client = await self.client(SmardClient, handler)
        result = await client.get_daily_window(4170, end_date=end)
        self.assertEqual(len(requests), 3)
        self.assertTrue(result["vollstaendig"])
        self.assertEqual(len(result["series"]), 14)
        self.assertEqual(result["von"], start.isoformat())
        self.assertEqual({value for _, value in result["series"]}, {10})
        self.assertEqual(result["series"][0][0], timestamp(start))
        self.assertEqual(result["series"][-1][0], timestamp(end))

    async def test_price_window_preserves_gaps_and_bounds_work(self):
        end = date(2026, 5, 14)
        start = end - timedelta(days=13)
        client = await self.client(
            SmardClient, lambda r: self.fail("Unexpected network")
        )
        with (
            patch.object(
                client,
                "get_available_timestamps",
                AsyncMock(return_value=[timestamp(start)]),
            ),
            patch.object(
                client,
                "get_chart_data",
                AsyncMock(
                    return_value={
                        "series": [
                            [timestamp(start - timedelta(days=1)), 999],
                            [timestamp(start), None],
                            [timestamp(end), -5],
                        ]
                    }
                ),
            ),
        ):
            result = await client.get_daily_window(4170, end_date=end)
        self.assertEqual(result["series"], [[timestamp(end), -5]])
        self.assertFalse(result["vollstaendig"])
        with (
            patch.object(
                client,
                "get_available_timestamps",
                AsyncMock(return_value=list(range(100))),
            ),
            patch.object(client, "get_chart_data", AsyncMock()) as get,
        ):
            with self.assertRaises(ValueError):
                await client.get_daily_window(4170, end_date=date(1970, 1, 1))
            get.assert_not_awaited()

    async def test_price_tool_marks_partial_and_empty_windows(self):
        tool = registered(
            energiepreise.register_energiepreise_tools, "get_energy_prices"
        )
        data = {
            "series": [[1000, 1.004], [2000, 1.005]],
            "von": "2026-09-17",
            "bis": "2026-09-30",
            "vollstaendig": False,
        }
        with patch.object(
            energiepreise._smard, "get_daily_window", AsyncMock(return_value=data)
        ):
            result = await tool()
        self.assertEqual(result["anzahl_tage_mit_daten"], 2)
        self.assertEqual(result["durchschnitt_14_tage"], round((1.004 + 1.005) / 2, 2))
        self.assertFalse(result["vollstaendig"])
        self.assertIn("hinweis", result)
        self.assertEqual(result["preis_timestamp"], 2000)
        data["series"] = []
        with patch.object(
            energiepreise._smard, "get_daily_window", AsyncMock(return_value=data)
        ):
            result = await tool()
        self.assertIn("error", result)
        self.assertIsNone(result["durchschnitt_14_tage"])

    @patch.object(settings, "bundestag_api_key", "test-key")
    async def test_bundestag_limits_all_methods_and_keeps_metadata(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={"documents": list(range(20)), "numFound": 200, "cursor": "next"},
            )

        client = await self.client(BundestagClient, handler)
        for method, args in (
            (client.search_drucksachen, ("Klima",)),
            (client.search_vorgaenge, ("Klima",)),
            (client.get_aktivitaeten, ()),
        ):
            result = await method(*args, limit=3)
            self.assertEqual(result["documents"], [0, 1, 2])
            self.assertEqual(result["numFound"], 200)
            self.assertEqual(result["cursor"], "next")
            for invalid in (0, -1, 101, True, 1.5):
                with self.assertRaises(ValueError):
                    await method(*args, limit=invalid)
        self.assertEqual(len(requests), 3)

    async def test_law_cache_refreshes_once_and_failed_refresh_does_not_extend_ttl(
        self,
    ):
        client = await self.client(
            GesetzeClient, lambda r: self.fail("Unexpected network")
        )
        fetch = AsyncMock(
            side_effect=[
                [{"titel": "old"}],
                [{"titel": "new"}],
                httpx.ConnectError("failure"),
                [{"titel": "recovered"}],
            ]
        )
        with (
            patch("src.clients.gesetze.monotonic", return_value=100) as clock,
            patch.object(client, "_fetch_index", fetch),
        ):
            first = await client._load_index()
            self.assertEqual((await client._load_index()), first)
            self.assertEqual(fetch.await_count, 1)
            clock.return_value = 100 + settings.law_index_cache_ttl
            results = await asyncio.gather(client._load_index(), client._load_index())
            self.assertEqual(results, [[{"titel": "new"}], [{"titel": "new"}]])
            self.assertEqual(fetch.await_count, 2)
            expiry = client._cache_expires
            clock.return_value = expiry
            with self.assertRaises(httpx.ConnectError):
                await client._load_index()
            self.assertEqual(client._cache_expires, expiry)
            self.assertEqual(await client._load_index(), [{"titel": "recovered"}])

    async def test_nina_total_timeouts_still_report_incomplete_feeds(self):
        client = await self.client(
            NinaClient, lambda r: self.fail("Unexpected network")
        )
        with patch(
            "src.clients.nina.bounded_get",
            AsyncMock(side_effect=TimeoutError("private-detail")),
        ):
            with self.assertRaises(IncompleteWarningsError) as result:
                await client.get_warnings()
        self.assertEqual(len(result.exception.failed_channels), 5)
        self.assertNotIn("private-detail", str(result.exception))

    async def test_http_accepts_limit_and_rejects_larger_streams(self):
        for body, accepted in ((b"12345678", True), (b"123456789", False)):
            stream = Chunks(body[:4], body[4:])

            def handler(request):
                self.assertEqual(request.headers["accept-encoding"], "identity")
                return httpx.Response(200, stream=stream)

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                with patch.object(settings, "http_max_response_bytes", 8):
                    if accepted:
                        response = await bounded_get(
                            client, "https://example.test/data"
                        )
                        self.assertEqual(response.content, body)
                    else:
                        with self.assertRaises(ResponseTooLarge):
                            await bounded_get(client, "https://example.test/data")
            self.assertTrue(stream.closed)

    async def test_http_rejects_large_declared_length_and_unexpected_encoding(self):
        for headers, error in (
            ({"content-length": "9"}, ResponseTooLarge),
            ({"content-encoding": "gzip"}, httpx.HTTPError),
        ):
            stream = Chunks(b"normal")
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, headers=headers, stream=stream)
                )
            ) as client:
                with (
                    patch.object(settings, "http_max_response_bytes", 8),
                    self.assertRaises(error),
                ):
                    await bounded_get(client, "https://example.test/data")
            self.assertTrue(stream.closed)

    async def test_http_redirect_body_is_not_read_and_origin_is_preserved(self):
        redirect_stream = Chunks(b"ordinary unused redirect body")

        def handler(request):
            if request.url.path == "/old":
                return httpx.Response(
                    302, headers={"location": "/new"}, stream=redirect_stream
                )
            return httpx.Response(200, json={"ok": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await bounded_get(
                client, "https://example.test/old", follow_redirects=True
            )
            self.assertEqual(response.json(), {"ok": True})
        self.assertTrue(redirect_stream.closed)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    302, headers={"location": "https://other.test/new"}
                )
            )
        ) as client:
            with self.assertRaises(httpx.HTTPError):
                await bounded_get(
                    client, "https://example.test/old", follow_redirects=True
                )

    async def test_http_total_timeout_closes_body(self):
        class SlowStream(Chunks):
            async def __aiter__(self):
                await asyncio.Event().wait()
                yield b""

        stream = SlowStream()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream))
        ) as client:
            with (
                patch.object(settings, "http_timeout", 0.01),
                self.assertRaises(TimeoutError),
            ):
                await bounded_get(client, "https://example.test/data")
        self.assertTrue(stream.closed)

    async def test_tool_errors_never_echo_exception_details_and_cancellation_propagates(
        self,
    ):
        marker = "PRIVATE_EXCEPTION_DETAIL"
        with self.assertLogs("src.tools.errors", level="WARNING") as logs:
            for error in (
                ValueError(marker),
                RuntimeError(marker),
                httpx.ConnectError(marker),
                httpx.ReadTimeout(marker),
                ResponseTooLarge(marker),
            ):
                self.assertNotIn(marker, safe_error(error))
        self.assertNotIn(marker, str(logs.output))
        for register, name, target, method, args in (
            (
                gesundheit.register_gesundheit_tools,
                "pollenflug",
                gesundheit._pollen,
                "get_forecast",
                (),
            ),
            (
                recht.register_recht_tools,
                "search_german_laws",
                recht._gesetze,
                "search",
                ("gg",),
            ),
        ):
            tool = registered(register, name)
            with patch.object(
                target, method, AsyncMock(side_effect=RuntimeError(marker))
            ):
                result = await tool(*args)
            self.assertIn("error", result)
            self.assertNotIn(marker, str(result))

        @safe_tool
        async def cancelled():
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await cancelled()


if __name__ == "__main__":
    unittest.main()
