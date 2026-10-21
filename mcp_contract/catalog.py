"""Immutable sample data and read-only operations."""

from typing import Any

DOCUMENTS = (
    ("arrival", "Arrival checklist", "Confirm station identity before docking."),
    ("power", "Power reserve", "Keep the reserve battery above forty percent."),
    ("radio", "Radio check", "Test the station radio at the start of each shift."),
)
RESOURCES = [
    {"uri": f"notes://station/{slug}", "name": name, "mimeType": "text/plain"}
    for slug, name, _ in DOCUMENTS
]
TEXTS = {f"notes://station/{slug}": text for slug, _, text in DOCUMENTS}
TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_notes",
        "description": "Search fictional station notes without side effects.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 200}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "read_note",
        "description": "Read a note with an optional bounded cancellation-test delay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uri": {"type": "string"},
                "delay_ms": {"type": "integer", "minimum": 0, "maximum": 2000},
            },
            "required": ["uri"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
]


def tool_result(text: str, *, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": error}
