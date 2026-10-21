"""Independent standard-library client with exact wire recording."""

import argparse
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path


class RawClient:
    def __init__(self, command=None):
        self.process = subprocess.Popen(
            command or [sys.executable, "-m", "mcp_contract.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.inbox = queue.Queue()
        self.trace = []
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.next_id = 0

    def _read(self):
        for line in self.process.stdout:
            self.inbox.put(line)
        self.inbox.put(None)

    def send(self, message):
        line = json.dumps(message, separators=(",", ":")) + "\n"
        self.send_bytes(line.encode())

    def send_bytes(self, line):
        self.trace.append(
            {"direction": "client_to_server", "wire": line.decode("utf-8")}
        )
        self.process.stdin.write(line)
        self.process.stdin.flush()

    def receive(self, timeout=5):
        line = self.inbox.get(timeout=timeout)
        if line is None:
            raise EOFError("Server closed stdout")
        self.trace.append(
            {"direction": "server_to_client", "wire": line.decode("utf-8")}
        )
        return json.loads(line)

    def request(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        response = self.receive()
        if response.get("id") != self.next_id:
            raise ValueError("Unexpected response ID")
        return response

    def notify(self, method, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)

    def initialize(self, version="2025-06-18"):
        result = self.request(
            "initialize",
            {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "raw-reference", "version": "0.1.0"},
            },
        )["result"]
        if result["protocolVersion"] != "2025-06-18":
            raise ValueError("Unsupported negotiated protocol")
        self.notify("notifications/initialized")
        return result

    def list_all(self, method, key):
        params, items, cursors = {}, [], set()
        while True:
            result = self.request(method, params)["result"]
            items.extend(result[key])
            cursor = result.get("nextCursor")
            if cursor is None:
                return items
            if not isinstance(cursor, str) or cursor in cursors:
                raise ValueError("Invalid or repeated cursor")
            cursors.add(cursor)
            params = {"cursor": cursor}

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.reader.join(timeout=2)
        self.process.stdout.close()
        self.process.stderr.close()


def run():
    client = RawClient()
    checks = []
    try:
        assert client.request("tools/list")["error"]["code"] == -32000
        checks.append("pre_initialization_error")
        client.initialize("2099-01-01")
        checks.append("version_fallback")
        assert len(client.list_all("resources/list", "resources")) == 3
        assert len(client.list_all("tools/list", "tools")) == 2
        checks.extend(["resource_pagination", "tool_pagination"])
        assert (
            "docking"
            in client.request("resources/read", {"uri": "notes://station/arrival"})[
                "result"
            ]["contents"][0]["text"]
        )
        checks.append("resource_read")
        result = client.request(
            "tools/call", {"name": "search_notes", "arguments": {"query": "battery"}}
        )["result"]
        assert json.loads(result["content"][0]["text"]) == ["notes://station/power"]
        checks.append("tool_success")
        assert (
            client.request("resources/list", {"cursor": "invalid"})["error"]["code"]
            == -32602
        )
        assert client.request("absent")["error"]["code"] == -32601
        assert (
            client.request("resources/read", {"uri": "file:///etc/passwd"})["error"][
                "code"
            ]
            == -32002
        )
        checks.extend(["invalid_cursor", "unknown_method", "unknown_resource"])
        assert client.request(
            "tools/call", {"name": "search_notes", "arguments": {"query": ""}}
        )["result"]["isError"]
        checks.append("tool_execution_error")
        client.send_bytes(b"{broken\n")
        assert client.receive()["error"]["code"] == -32700
        checks.append("parse_error")
        client.send(
            {
                "jsonrpc": "2.0",
                "id": "cancel-me",
                "method": "tools/call",
                "params": {
                    "name": "read_note",
                    "arguments": {"uri": "notes://station/power", "delay_ms": 400},
                },
            }
        )
        client.notify(
            "notifications/cancelled",
            {"requestId": "cancel-me", "reason": "Contract test"},
        )
        try:
            client.receive(timeout=0.65)
        except queue.Empty:
            pass
        else:
            raise AssertionError("Cancelled request produced a response")
        assert client.request("ping")["result"] == {}
        checks.append("cancellation_no_response_and_session_alive")
        client.notify("notifications/cancelled", {"requestId": "unknown"})
        assert client.request("ping")["result"] == {}
        checks.append("unknown_cancellation_ignored")
        return {
            "client": "raw-reference",
            "version": "0.1.0",
            "checks": checks,
        }, client.trace
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    report, trace = run()
    if args.trace:
        args.trace.write_text("".join(json.dumps(row) + "\n" for row in trace))
    print(json.dumps(report))
