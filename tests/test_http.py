"""Offline checks for the container's stateless HTTP transport."""

import os
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from src.server import main, mcp


class ContainerHTTP(unittest.TestCase):
    def test_container_transport(self):
        with (
            patch.dict(
                os.environ, {"MCP_TRANSPORT": "streamable-http", "PORT": "8000"}
            ),
            patch.object(mcp, "run") as run,
        ):
            main()
        options = run.call_args.kwargs
        self.assertEqual(options.pop("transport"), "streamable-http")
        self.assertEqual(options.pop("port"), 8000)
        app = mcp.streamable_http_app(**options)
        headers = {"Accept": "application/json, text/event-stream"}
        with TestClient(app, base_url="http://localhost:8000") as client:
            self.assertEqual(client.get("/healthz").text, "ok")
            initialize = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
            )
            self.assertEqual(initialize.status_code, 200)
            self.assertNotIn("mcp-session-id", initialize.headers)
            headers["MCP-Protocol-Version"] = initialize.json()["result"][
                "protocolVersion"
            ]
            listing = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )
            self.assertEqual(len(listing.json()["result"]["tools"]), 16)
            call = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "get_energy_prices",
                        "arguments": {"type": "gas"},
                    },
                },
            )
            self.assertEqual(call.status_code, 200)
            self.assertIn("Gaspreise", str(call.json()))
            rejected = client.post(
                "/mcp", headers={**headers, "Host": "untrusted.example"}, json={}
            )
            self.assertEqual(rejected.status_code, 421)

    def test_unknown_transport_fails(self):
        with patch.dict(os.environ, {"MCP_TRANSPORT": "invalid"}):
            with self.assertRaises(ValueError):
                main()
