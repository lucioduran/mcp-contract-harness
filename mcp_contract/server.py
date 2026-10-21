"""Stdio transport and session state for MCP 2025-06-18."""

import asyncio
import json
import sys
from collections.abc import Callable
from typing import Any

from mcp_contract import PROTOCOL_VERSION, __version__
from mcp_contract.catalog import RESOURCES, TEXTS, TOOLS, tool_result

MAX_LINE = 65536
MAX_PENDING = 32
MAX_REQUESTS = 10000
Message = dict[str, Any]
RequestId = str | int


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def valid_id(value: object) -> bool:
    return type(value) in (str, int)


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON constant: {value}")


def unique_object(pairs: list[tuple[str, Any]]) -> Message:
    result: Message = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


class Session:
    def __init__(self, emit: Callable[[Message], None]):
        self.emit = emit
        self.state = "new"
        self.seen: set[RequestId] = set()
        self.pending: dict[RequestId, asyncio.Task[None]] = {}

    def error(self, rid: RequestId | None, code: int, message: str) -> None:
        self.emit(
            {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}
        )

    async def receive(self, line: bytes) -> None:
        try:
            msg = json.loads(
                line.decode("utf-8"),
                parse_constant=reject_constant,
                object_pairs_hook=unique_object,
            )
        except (ValueError, UnicodeError, RecursionError):
            self.error(None, -32700, "Parse error")
            return
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            self.error(None, -32600, "Invalid request")
            return
        if "id" not in msg:
            self.notification(msg)
            return
        rid = msg["id"]
        if not valid_id(rid):
            self.error(None, -32600, "Invalid request ID")
            return
        if not isinstance(msg.get("method"), str):
            self.error(rid, -32600, "Invalid method")
            return
        if rid in self.seen:
            self.error(rid, -32600, "Request ID already used")
            return
        if len(self.seen) >= MAX_REQUESTS:
            self.error(rid, -32001, "Session request limit reached")
            return
        self.seen.add(rid)
        params = msg.get("params", {})
        if not isinstance(params, dict):
            self.error(rid, -32602, "Parameters must be an object")
            return
        method = msg["method"]
        if method == "initialize":
            try:
                result = self.initialize(params)
                self.emit({"jsonrpc": "2.0", "id": rid, "result": result})
            except RpcError as exc:
                self.error(rid, exc.code, exc.message)
            return
        if method != "ping" and self.state != "ready":
            self.error(rid, -32000, "Session is not initialized")
            return
        if len(self.pending) >= MAX_PENDING:
            self.error(rid, -32001, "Too many pending requests")
            return
        self.pending[rid] = asyncio.create_task(self.respond(rid, method, params))

    def initialize(self, params: Message) -> Message:
        if self.state != "new":
            raise RpcError(-32600, "Session already initialized")
        info = params.get("clientInfo")
        if (
            not isinstance(params.get("protocolVersion"), str)
            or not isinstance(params.get("capabilities"), dict)
            or not isinstance(info, dict)
            or not isinstance(info.get("name"), str)
            or not isinstance(info.get("version"), str)
        ):
            raise RpcError(-32602, "Invalid initialization parameters")
        self.state = "negotiated"
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"resources": {}, "tools": {}},
            "serverInfo": {"name": "mcp-contract-harness", "version": __version__},
        }

    def notification(self, msg: Message) -> None:
        params = msg.get("params", {})
        if not isinstance(params, dict):
            return
        if msg.get("method") == "notifications/initialized":
            if self.state == "negotiated":
                self.state = "ready"
        elif msg.get("method") == "notifications/cancelled":
            rid = params.get("requestId")
            if valid_id(rid) and rid in self.pending:
                self.pending.pop(rid).cancel()

    async def respond(self, rid: RequestId, method: str, params: Message) -> None:
        try:
            result = await self.dispatch(method, params)
            self.emit({"jsonrpc": "2.0", "id": rid, "result": result})
        except RpcError as exc:
            self.error(rid, exc.code, exc.message)
        except asyncio.CancelledError:
            pass
        finally:
            self.pending.pop(rid, None)

    @staticmethod
    def page(method: str, params: Message) -> Message:
        key = "resources" if method == "resources/list" else "tools"
        items = RESOURCES if key == "resources" else TOOLS
        size = 2 if key == "resources" else 1
        token = "catalog-r-2" if key == "resources" else "catalog-t-1"
        if "cursor" not in params:
            offset = 0
        elif params["cursor"] == token:
            offset = size
        else:
            raise RpcError(-32602, "Invalid cursor")
        result: Message = {key: items[offset : offset + size]}
        if offset + size < len(items):
            result["nextCursor"] = token
        return result

    async def dispatch(self, method: str, params: Message) -> Message:
        if method == "ping":
            return {}
        if method in ("resources/list", "tools/list"):
            return self.page(method, params)
        if method == "resources/templates/list":
            if "cursor" in params:
                raise RpcError(-32602, "Invalid cursor")
            return {"resourceTemplates": []}
        if method == "resources/read":
            uri = params.get("uri")
            if not isinstance(uri, str):
                raise RpcError(-32602, "URI must be a string")
            if uri not in TEXTS:
                raise RpcError(-32002, "Resource not found")
            return {
                "contents": [{"uri": uri, "mimeType": "text/plain", "text": TEXTS[uri]}]
            }
        if method == "tools/call":
            return await self.call_tool(params)
        raise RpcError(-32601, "Method not found")

    async def call_tool(self, params: Message) -> Message:
        name = params.get("name")
        if not isinstance(name, str) or name not in {t["name"] for t in TOOLS}:
            raise RpcError(-32602, "Unknown tool")
        args = params.get("arguments", {})
        if not isinstance(args, dict):
            return tool_result("Arguments must be an object", error=True)
        if name == "search_notes":
            query = args.get("query")
            if (
                set(args) != {"query"}
                or not isinstance(query, str)
                or not 1 <= len(query) <= 200
            ):
                return tool_result(
                    "Expected a query of 1 to 200 characters", error=True
                )
            matches = [
                uri
                for uri, text in TEXTS.items()
                if query.casefold() in text.casefold()
            ]
            return tool_result(json.dumps(matches))
        uri, delay = args.get("uri"), args.get("delay_ms", 0)
        if (
            set(args) - {"uri", "delay_ms"}
            or not isinstance(uri, str)
            or type(delay) is not int
            or not 0 <= delay <= 2000
        ):
            return tool_result(
                "Expected uri and integer delay_ms from 0 to 2000", error=True
            )
        if uri not in TEXTS:
            return tool_result("Note not found", error=True)
        await asyncio.sleep(delay / 1000)
        return tool_result(TEXTS[uri])

    async def close(self) -> None:
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.pending.clear()


def write_message(msg: Message) -> None:
    sys.stdout.buffer.write((json.dumps(msg, ensure_ascii=True) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


async def serve() -> None:
    session = Session(write_message)
    try:
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                print("Message exceeds 64 KiB; closing session", file=sys.stderr)
                break
            if not line.endswith(b"\n"):
                session.error(None, -32700, "Unterminated message")
                break
            await session.receive(line)
    finally:
        await session.close()


def main() -> None:
    try:
        asyncio.run(serve())
    except (BrokenPipeError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
