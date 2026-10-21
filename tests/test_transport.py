import asyncio
import io
import json
import queue
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from clients.raw import RawClient, run
from mcp_contract.server import MAX_LINE, main, serve


class TransportTests(unittest.TestCase):
    def test_raw_live_contract(self):
        result, trace = run()
        self.assertEqual(len(result["checks"]), 13)
        self.assertGreater(len(trace), 30)

    def test_transport_framing_limits_and_eof(self):
        for payload, code, diagnostic in [
            (b'{"jsonrpc":"2.0","id":1,"method":"ping"}', -32700, ""),
            (b"x" * (MAX_LINE + 1), None, "64 KiB"),
            (b"", None, ""),
            (b"{\n", -32700, ""),
        ]:
            with self.subTest(payload_length=len(payload)):
                stdin, stdout, stderr = io.BytesIO(payload), io.BytesIO(), io.StringIO()
                with (
                    patch("sys.stdin", SimpleNamespace(buffer=stdin)),
                    patch("sys.stdout", SimpleNamespace(buffer=stdout)),
                    patch("sys.stderr", stderr),
                ):
                    asyncio.run(serve())
                if code:
                    self.assertEqual(
                        json.loads(stdout.getvalue())["error"]["code"], code
                    )
                else:
                    self.assertEqual(stdout.getvalue(), b"")
                self.assertIn(diagnostic, stderr.getvalue())

    def test_main_and_broken_pipe(self):
        with (
            patch("mcp_contract.server.serve", new=lambda: None),
            patch("asyncio.run", side_effect=BrokenPipeError),
        ):
            main()

    def test_live_server_eof_and_size_limit(self):
        result = subprocess.run(
            [sys.executable, "-m", "mcp_contract.server"],
            input=b"x" * (MAX_LINE + 1),
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"64 KiB", result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_no_notification_response(self):
        client = RawClient()
        try:
            client.initialize()
            client.notify("notifications/unknown")
            with self.assertRaises(queue.Empty):
                client.receive(timeout=0.05)
            self.assertEqual(client.request("ping")["result"], {})
        finally:
            client.close()

    def test_client_refuses_unsupported_server_version(self):
        client = RawClient()
        try:
            with patch.object(
                client, "request", return_value={"result": {"protocolVersion": "wrong"}}
            ):
                with self.assertRaisesRegex(ValueError, "Unsupported"):
                    client.initialize()
        finally:
            client.close()

    def test_client_repeated_cursor_and_response_id(self):
        client = RawClient()
        try:
            with patch.object(
                client,
                "request",
                return_value={"result": {"resources": [], "nextCursor": "same"}},
            ):
                with self.assertRaisesRegex(ValueError, "repeated cursor"):
                    client.list_all("resources/list", "resources")
            with patch.object(client, "receive", return_value={"id": "wrong"}):
                with self.assertRaisesRegex(ValueError, "response ID"):
                    client.request("ping")
        finally:
            client.close()
