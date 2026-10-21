"""Reference client using the separately maintained official Python SDK."""

import argparse
import asyncio
import importlib.metadata
import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError


async def run(trace):
    checks = []
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "clients.wire_proxy", trace]
    )
    async with (
        stdio_client(server) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        assert init.protocol_version == "2025-06-18"
        checks.append("version_negotiation")
        for method, key, expected in [
            (session.list_resources, "resources", 3),
            (session.list_tools, "tools", 2),
        ]:
            items, cursor, cursors = [], None, set()
            while True:
                page = await method(params=types.PaginatedRequestParams(cursor=cursor))
                items.extend(getattr(page, key))
                cursor = page.next_cursor
                if cursor is None:
                    break
                assert cursor not in cursors
                cursors.add(cursor)
            assert len(items) == expected
            checks.append(f"{key}_pagination")
        resource = await session.read_resource("notes://station/arrival")
        assert "docking" in resource.contents[0].text
        checks.append("resource_read")
        result = await session.call_tool("search_notes", {"query": "battery"})
        assert json.loads(result.content[0].text) == ["notes://station/power"]
        checks.append("tool_success")
        result = await session.call_tool("search_notes", {"query": ""})
        assert result.is_error
        checks.append("tool_execution_error")
        try:
            await session.list_resources(
                params=types.PaginatedRequestParams(cursor="bad")
            )
        except MCPError as exc:
            assert exc.code == -32602
        else:
            raise AssertionError("Invalid cursor accepted")
        checks.append("invalid_cursor")
        with anyio.move_on_after(0.1) as scope:
            await session.call_tool(
                "read_note", {"uri": "notes://station/power", "delay_ms": 400}
            )
        assert scope.cancel_called
        await anyio.sleep(0.6)
        await session.send_ping()
        checks.append("cancellation_and_session_alive")
    return {
        "client": "official-python-sdk",
        "version": importlib.metadata.version("mcp"),
        "checks": checks,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.trace))))
