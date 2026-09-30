"""Offline regressions: python -m unittest discover -s tests -v."""

import unittest
from datetime import date
from time import monotonic
from unittest.mock import AsyncMock, patch

import httpx
from defusedxml.common import DTDForbidden

from src.clients.autobahn import AutobahnClient
from src.clients.brightsky import BrightSkyClient
from src.clients.bundestag import BundestagClient
from src.clients.destatis import DestatisClient
from src.clients.dwd_warnings import DwdWarningsClient
from src.clients.gesetze import GesetzeClient
from src.clients.nina import IncompleteWarningsError, NinaClient
from src.tools import dwd_warnungen, gesundheit, politik, recht, warnungen, wetter


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def registered(register, name):
    registry = ToolRegistry()
    register(registry)
    return registry.tools[name]


class Regressions(unittest.IsolatedAsyncioTestCase):
    async def client(self, cls, handler):
        client = cls()
        await client.close()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)
        return client

    async def test_roads_are_normalized_and_validated_before_network(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={})
        client = await self.client(AutobahnClient, handler)
        for method in ('get_roadworks', 'get_warnings', 'get_closures',
                       'get_charging_stations', 'get_webcams'):
            await getattr(client, method)(' a61 ')
            with self.assertRaises(ValueError):
                await getattr(client, method)('B1')
        self.assertEqual(len(requests), 5)
        self.assertTrue(all('/A61/services/' in r.url.path for r in requests))

    async def test_law_search_bounds_and_whitespace(self):
        client = await self.client(GesetzeClient, lambda r: self.fail('Unexpected network'))
        client._cache = [{'titel': 'Grundgesetz', 'abkuerzung': 'gg', 'url': 'url', 'link': 'link'}]
        client._cache_expires = monotonic() + 60
        self.assertEqual(len(await client.search(' GG ')), 1)
        for limit in (-1, 0, 51):
            with self.assertRaises(ValueError):
                await client.search('gg', limit)
        with self.assertRaises(ValueError):
            await client.search('   ')
        tool = registered(recht.register_recht_tools, 'search_german_laws')
        with patch.object(recht, '_gesetze', client):
            self.assertIn('error', await tool('gg', -1))
            self.assertIn('error', await tool(' ', 10))
            self.assertEqual((await tool('gg', 100))['anzahl_treffer'], 1)

    async def test_law_xml_encoding_and_dtd_policy(self):
        xml = '<?xml version="1.0" encoding="ISO-8859-1"?><items><item><title>Änderung</title><link>https://www.gesetze-im-internet.de/gg/xml.zip</link></item></items>'
        client = await self.client(GesetzeClient, lambda r: httpx.Response(200, content=xml.encode('latin1')))
        self.assertEqual((await client.search('Änderung'))[0]['titel'], 'Änderung')
        client = await self.client(GesetzeClient, lambda r: httpx.Response(200, content=b'<!DOCTYPE items><items/>'))
        with self.assertRaises(DTDForbidden):
            await client._load_index()
        self.assertIsNone(client._cache)

    async def test_coordinates_reject_partial_nonfinite_and_out_of_range(self):
        client = await self.client(BrightSkyClient, lambda r: self.fail('Unexpected network'))
        for lat, lon in ((52, None), (None, 13), (91, 13), (52, 181), (float('nan'), 13), (52, float('inf'))):
            with self.subTest(lat=lat, lon=lon):
                with self.assertRaises(ValueError):
                    wetter._resolve_coords('Berlin', lat, lon)
                with self.assertRaises(ValueError):
                    await client.get_alerts(lat, lon)
        self.assertEqual(wetter._resolve_coords(' Berlin ', None, None), (52.52, 13.405))
        self.assertEqual(wetter._resolve_coords('', 0, 0), (0, 0))
        tool = registered(wetter.register_wetter_tools, 'wetter_warnungen')
        with patch.object(wetter._brightsky, 'get_alerts', AsyncMock(return_value={'alerts': []})) as get:
            self.assertIn('error', await tool(lat=52))
            get.assert_not_awaited()
            self.assertEqual((await tool(lat=52, lon=13))['ort'], '52,13')
            self.assertEqual((await tool())['ort'], 'bundesweit')

    async def test_nina_partial_results_are_marked_incomplete(self):
        def handler(request):
            if '/mowas/' in request.url.path:
                return httpx.Response(200, json=[{'id': 'warning-1', 'payload': None, 'i18nTitle': None}])
            if '/dwd/' in request.url.path:
                return httpx.Response(503)
            return httpx.Response(200, json=[])
        client = await self.client(NinaClient, handler)
        with self.assertRaises(IncompleteWarningsError) as result:
            await client.get_warnings()
        self.assertEqual(result.exception.failed_channels, ['dwd'])
        self.assertEqual(len(result.exception.warnings), 1)
        tool = registered(warnungen.register_warnungen_tools, 'nina_warnungen')
        with patch.object(warnungen, '_nina', client):
            result = await tool()
        self.assertFalse(result['vollstaendig'])
        self.assertEqual(result['anzahl_warnungen'], 1)
        self.assertIn('error', result)

    async def test_nina_all_failed_and_successfully_empty_are_distinct(self):
        tool = registered(warnungen.register_warnungen_tools, 'nina_warnungen')
        for payload, complete in (([], True), ({'unexpected': 'format'}, False)):
            client = await self.client(NinaClient, lambda r: httpx.Response(200, json=payload))
            with patch.object(warnungen, '_nina', client):
                result = await tool()
            self.assertEqual(result['vollstaendig'], complete)
            self.assertEqual('error' in result, not complete)

    async def test_nina_ags_normalization_and_id_validation(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=[])
        client = await self.client(NinaClient, handler)
        await client.get_ags_warnings('09162')
        self.assertTrue(requests[0].url.path.endswith('/091620000000.json'))
        with self.assertRaises(ValueError):
            await client.get_ags_warnings('Munich')
        with self.assertRaises(ValueError):
            await client.get_warning_details('not a warning id')
        self.assertEqual(len(requests), 1)

    async def test_dwd_state_filter_does_not_match_other_state(self):
        data = {'warnings': {'1': [{'state': 'Sachsen', 'headline': 'A'},
                                  {'state': 'Sachsen-Anhalt', 'headline': 'B'}]}}
        client = await self.client(DwdWarningsClient, lambda r: httpx.Response(200, json=data))
        for region in ('Sachsen', ' SN '):
            result = await client.get_warnings(region)
            self.assertEqual([w['headline'] for w in result['warnungen']], ['A'])

    async def test_dwd_dedup_retains_different_severity_and_time(self):
        warning = {'headline': 'Frost', 'regionName': 'Berlin', 'level': 1, 'start': 100}
        data = {'warnungen': [warning, dict(warning), {**warning, 'level': 3}, {**warning, 'start': 200}]}
        tool = registered(dwd_warnungen.register_dwd_warnungen_tools, 'get_german_weather_warnings')
        with patch.object(dwd_warnungen._dwd, 'get_warnings', AsyncMock(return_value=data)):
            result = await tool()
        self.assertEqual(result['anzahl_warnungen'], 3)
        self.assertEqual(result['warnungen'][0]['level'], 3)

    async def test_bundestag_search_uses_title_and_current_term(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'documents': []})
        client = await self.client(BundestagClient, handler)
        await client.search_drucksachen('Klima')
        await client.search_vorgaenge('Klima')
        for request in requests:
            self.assertEqual(request.url.params['f.titel'], 'Klima')
            self.assertEqual(request.url.params['f.wahlperiode'], '21')
            self.assertNotIn('cursor', request.url.params)
        tool = registered(politik.register_politik_tools, 'bundestag_aktivitaeten')
        with patch.object(politik._bundestag, 'get_aktivitaeten', AsyncMock(return_value={'documents': [{'fundstelle': None}]})):
            self.assertEqual((await tool())['aktivitaeten'][0]['fundstelle'], '')

    async def test_pollen_accepts_documented_nrw_alias(self):
        tool = registered(gesundheit.register_gesundheit_tools, 'pollenflug')
        data = {'content': [{'region_name': 'Nordrhein-Westfalen', 'Pollen': {}}]}
        with patch.object(gesundheit._pollen, 'get_forecast', AsyncMock(return_value=data)):
            self.assertEqual((await tool(' NRW '))['anzahl_regionen'], 1)

    async def test_destatis_sparse_dense_and_rolling_period(self):
        requests = []
        data = {'id': ['geo', 'time'], 'size': [1, 2],
                'dimension': {'time': {'category': {'index': {'2023': 0, '2024': 1}}}},
                'value': {'0': 0, '1': 42}}
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=data)
        client = await self.client(DestatisClient, handler)
        self.assertEqual((await client.get_indicator('bevoelkerung'))['daten'], {'2023': 0, '2024': 42})
        self.assertEqual(requests[-1].url.params['sinceTimePeriod'], str(date.today().year - 4))
        self.assertEqual(requests[-1].url.params['unit'], 'NR')
        data['value'] = [0, None]
        data['dimension']['time']['category']['index'] = ['2023', '2024']
        self.assertEqual((await client.get_indicator('bevoelkerung', 2023))['daten'], {'2023': 0})
        self.assertEqual(requests[-1].url.params['time'], '2023')
        self.assertNotIn('sinceTimePeriod', requests[-1].url.params)
        with self.assertRaises(ValueError):
            await client.get_indicator('bevoelkerung', 0)
        data['size'] = [2, 2]
        with self.assertRaises(ValueError):
            await client.get_indicator('bevoelkerung')


if __name__ == '__main__':
    unittest.main()
