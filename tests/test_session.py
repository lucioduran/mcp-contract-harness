import asyncio
import json
import unittest

from mcp_contract import PROTOCOL_VERSION
from mcp_contract.server import MAX_PENDING, MAX_REQUESTS, Session

INIT = {
    "protocolVersion": PROTOCOL_VERSION,
    "capabilities": {},
    "clientInfo": {"name": "tests", "version": "0.1.0"},
}


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.messages = []
        self.session = Session(self.messages.append)
        self.counter = 0

    async def asyncTearDown(self):
        await self.session.close()

    async def request(self, method, params=None, rid=None):
        self.counter += 1
        msg = {
            "jsonrpc": "2.0",
            "id": rid if rid is not None else self.counter,
            "method": method,
        }
        if params is not None:
            msg["params"] = params
        await self.session.receive(json.dumps(msg).encode())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return self.messages[-1]

    async def notify(self, method, params=None):
        await self.session.receive(
            json.dumps(
                {"jsonrpc": "2.0", "method": method, "params": params or {}}
            ).encode()
        )

    async def ready(self):
        await self.request("initialize", INIT)
        await self.notify("notifications/initialized")

    async def test_negotiation_and_lifecycle(self):
        self.assertEqual((await self.request("ping"))["result"], {})
        self.assertEqual((await self.request("tools/list"))["error"]["code"], -32000)
        await self.notify("notifications/initialized")
        self.assertEqual(self.session.state, "new")
        result = await self.request(
            "initialize", {**INIT, "protocolVersion": "2099-01-01"}
        )
        self.assertEqual(result["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(
            result["result"]["capabilities"], {"tools": {}, "resources": {}}
        )
        self.assertEqual(
            (await self.request("resources/list"))["error"]["code"], -32000
        )
        await self.notify("notifications/cancelled", {"requestId": 3})
        await self.notify("notifications/initialized")
        self.assertEqual(self.session.state, "ready")
        self.assertEqual(
            (await self.request("initialize", INIT))["error"]["code"], -32600
        )

    async def test_invalid_initialization_recoverable(self):
        for field, value in [
            ("protocolVersion", 2),
            ("capabilities", []),
            ("clientInfo", {}),
            ("clientInfo", None),
        ]:
            result = await self.request("initialize", {**INIT, field: value})
            self.assertEqual(result["error"]["code"], -32602)
        await self.ready()
        self.assertEqual(self.session.state, "ready")

    async def test_pagination_and_invalid_cursors(self):
        await self.ready()
        for method, key, count in [
            ("resources/list", "resources", 3),
            ("tools/list", "tools", 2),
        ]:
            first = (await self.request(method))["result"]
            second = (await self.request(method, {"cursor": first["nextCursor"]}))[
                "result"
            ]
            self.assertNotIn("nextCursor", second)
            self.assertEqual(len(first[key] + second[key]), count)
            self.assertEqual((await self.request(method))["result"], first)
            for cursor in [
                None,
                4,
                [],
                "bad",
                "catalog-t-1" if key == "resources" else "catalog-r-2",
            ]:
                self.assertEqual(
                    (await self.request(method, {"cursor": cursor}))["error"]["code"],
                    -32602,
                )
        self.assertEqual(
            (await self.request("resources/templates/list"))["result"],
            {"resourceTemplates": []},
        )
        self.assertEqual(
            (await self.request("resources/templates/list", {"cursor": "bad"}))[
                "error"
            ]["code"],
            -32602,
        )

    async def test_resource_reads_and_errors(self):
        await self.ready()
        result = await self.request(
            "resources/read", {"uri": "notes://station/arrival"}
        )
        self.assertEqual(
            result["result"]["contents"][0]["text"],
            "Confirm station identity before docking.",
        )
        for uri in [None, [], 3]:
            self.assertEqual(
                (await self.request("resources/read", {"uri": uri}))["error"]["code"],
                -32602,
            )
        for uri in [
            "file:///etc/passwd",
            "https://example.org",
            "notes://station/missing",
        ]:
            self.assertEqual(
                (await self.request("resources/read", {"uri": uri}))["error"]["code"],
                -32002,
            )
        self.assertEqual(
            (await self.request("resources/subscribe"))["error"]["code"], -32601
        )

    async def test_tool_results_and_execution_errors(self):
        await self.ready()
        for query, expected in [
            ("BATTERY", ["notes://station/power"]),
            ("missing", []),
        ]:
            result = (
                await self.request(
                    "tools/call",
                    {"name": "search_notes", "arguments": {"query": query}},
                )
            )["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(json.loads(result["content"][0]["text"]), expected)
        for args in [
            {},
            {"query": ""},
            {"query": "x" * 201},
            {"query": 1},
            {"query": "a", "extra": 1},
            [],
        ]:
            result = await self.request(
                "tools/call", {"name": "search_notes", "arguments": args}
            )
            self.assertTrue(result["result"]["isError"])
        for args in [
            {},
            {"uri": []},
            {"uri": "bad"},
            {"uri": "bad", "extra": 1},
            *(
                {"uri": "notes://station/power", "delay_ms": d}
                for d in [True, -1, 2001, 1.5, "1"]
            ),
        ]:
            result = await self.request(
                "tools/call", {"name": "read_note", "arguments": args}
            )
            self.assertTrue(result["result"]["isError"])
        result = await self.request(
            "tools/call",
            {"name": "read_note", "arguments": {"uri": "notes://station/power"}},
        )
        self.assertFalse(result["result"]["isError"])
        for name in [None, [], "write_note"]:
            self.assertEqual(
                (await self.request("tools/call", {"name": name}))["error"]["code"],
                -32602,
            )

    async def test_cancel_and_races(self):
        await self.ready()
        await self.request(
            "tools/call",
            {
                "name": "read_note",
                "arguments": {"uri": "notes://station/power", "delay_ms": 2000},
            },
            rid="slow",
        )
        self.assertIn("slow", self.session.pending)
        await self.notify("notifications/cancelled", {"requestId": "slow"})
        await asyncio.sleep(0)
        self.assertNotIn("slow", self.session.pending)
        self.assertFalse(any(m["id"] == "slow" for m in self.messages))
        for rid in ["slow", "unknown", [], True, None]:
            await self.notify("notifications/cancelled", {"requestId": rid})
        await self.notify("notifications/cancelled", [1])
        await self.notify("unknown")
        self.assertEqual((await self.request("ping"))["result"], {})

    async def test_cancel_before_task_start_and_close(self):
        await self.ready()
        await self.session.receive(b'{"jsonrpc":"2.0","id":"x","method":"ping"}')
        await self.notify("notifications/cancelled", {"requestId": "x"})
        self.assertNotIn("x", self.session.pending)
        await self.session.receive(b'{"jsonrpc":"2.0","id":"y","method":"ping"}')
        await self.session.close()
        self.assertFalse(self.session.pending)

    async def test_envelopes_and_parse_errors(self):
        for wire, code in [
            (b"{", -32700),
            (b"\xff", -32700),
            (b'{"a":NaN}', -32700),
            (b'{"a":1,"a":2}', -32700),
            (b"[]", -32600),
            (b"null", -32600),
            (b"{}", -32600),
            (b'{"jsonrpc":"2.0","id":true,"method":"ping"}', -32600),
            (b'{"jsonrpc":"2.0","id":null,"method":"ping"}', -32600),
            (b'{"jsonrpc":"2.0","id":1,"method":3}', -32600),
        ]:
            await self.session.receive(wire)
            self.assertEqual(self.messages[-1]["error"]["code"], code)
        self.assertEqual((await self.request("ping", []))["error"]["code"], -32602)
        await self.request("ping", rid="same")
        self.assertEqual(
            (await self.request("ping", rid="same"))["error"]["code"], -32600
        )

    async def test_resource_limits(self):
        await self.ready()
        for i in range(MAX_PENDING):
            await self.session.receive(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": f"busy{i}",
                        "method": "tools/call",
                        "params": {
                            "name": "read_note",
                            "arguments": {
                                "uri": "notes://station/power",
                                "delay_ms": 2000,
                            },
                        },
                    }
                ).encode()
            )
        self.assertEqual((await self.request("ping"))["error"]["code"], -32001)
        await self.session.close()
        self.session.seen = set(range(MAX_REQUESTS))
        self.assertEqual(
            (await self.request("ping", rid="over"))["error"]["code"], -32001
        )
