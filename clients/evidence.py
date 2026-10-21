"""Validate recorded exchanges independently of the server implementation."""

import json
from pathlib import Path


def inspect_trace(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    sent, replies, cancelled, initialized = {}, {}, set(), False
    pages = {"resources/list": [], "tools/list": []}
    negotiated = False
    errors, tool_success, tool_error, resource_read = set(), False, False, False
    last_method = None
    for row in rows:
        if row["direction"] not in {"client_to_server", "server_to_client"}:
            raise ValueError("Unknown trace direction")
        wire = row["wire"]
        if not wire.endswith("\n") or "\n" in wire[:-1]:
            raise ValueError("Invalid stdio framing")
        try:
            message = json.loads(wire)
        except json.JSONDecodeError:
            if row["direction"] == "client_to_server":
                continue
            raise ValueError("Invalid server JSON") from None
        if message.get("jsonrpc") != "2.0":
            raise ValueError("Wrong JSON-RPC version")
        if row["direction"] == "client_to_server":
            method = message.get("method")
            if method == "notifications/initialized":
                if not negotiated:
                    raise ValueError("Ready before negotiation")
                initialized = True
            elif method == "notifications/cancelled":
                rid = message["params"]["requestId"]
                if rid in sent and rid not in replies:
                    cancelled.add(rid)
            elif "id" in message:
                rid = message["id"]
                if rid in sent:
                    raise ValueError("Reused request ID")
                sent[rid] = message
                last_method = method
        else:
            rid = message.get("id")
            if rid is None:
                if message.get("error", {}).get("code") != -32700:
                    raise ValueError("Unexpected uncorrelated error")
                errors.add(-32700)
                continue
            if rid not in sent or rid in replies or rid in cancelled:
                raise ValueError("Unexpected, duplicate, or cancelled response")
            replies[rid] = message
            method = sent[rid]["method"]
            if "error" in message:
                errors.add(message["error"]["code"])
                continue
            result = message["result"]
            if method == "initialize":
                if result["protocolVersion"] != "2025-06-18":
                    raise ValueError("Wrong negotiated version")
                if result["capabilities"] != {"resources": {}, "tools": {}}:
                    raise ValueError("Unexpected capabilities")
                negotiated = True
            elif method in pages:
                if not initialized:
                    raise ValueError("Catalog before ready")
                pages[method].append((sent[rid].get("params", {}), result))
            elif method == "resources/read":
                resource_read = (
                    result["contents"][0]["text"]
                    == "Confirm station identity before docking."
                )
            elif method == "tools/call":
                if result.get("isError"):
                    tool_error = True
                elif sent[rid]["params"]["name"] == "search_notes":
                    tool_success = json.loads(result["content"][0]["text"]) == [
                        "notes://station/power"
                    ]
    for method, count in [("resources/list", 3), ("tools/list", 2)]:
        key = method.split("/")[0]
        chain = pages[method]
        if len(chain) != 2:
            raise ValueError("Missing catalog page")
        first, second = chain
        if (
            second[0].get("cursor") != first[1].get("nextCursor")
            or "nextCursor" not in first[1]
            or "nextCursor" in second[1]
        ):
            raise ValueError("Broken cursor chain")
        items = first[1][key] + second[1][key]
        identities = [item["uri" if key == "resources" else "name"] for item in items]
        if len(identities) != count or len(set(identities)) != count:
            raise ValueError("Incomplete or duplicate catalog")
    if not (
        negotiated
        and initialized
        and resource_read
        and tool_success
        and tool_error
        and -32602 in errors
        and cancelled
        and last_method == "ping"
    ):
        raise ValueError("Missing required protocol evidence")
    for rid in sent.keys() - replies.keys():
        if rid not in cancelled:
            raise ValueError("Unanswered request")
    return {
        "messages": len(rows),
        "cancelled_requests": len(cancelled),
        "error_codes": sorted(errors),
        "protocol": "2025-06-18",
    }
