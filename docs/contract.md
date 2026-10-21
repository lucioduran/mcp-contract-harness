# Protocol contract

The server supports only protocol version `2025-06-18`. Initialization requests
for another version receive this supported version. A client that cannot use it
should disconnect. A ready notification follows successful negotiation.

| Condition | Result |
| --- | --- |
| Malformed JSON, UTF-8, duplicate keys, nonfinite JSON constants | -32700, null ID |
| Invalid envelope or request ID, repeated ID or initialization | -32600 |
| Invalid protocol parameter, cursor, or unknown tool | -32602 |
| Unknown method, including unadvertised subscription | -32601 |
| Operation before initialized notification | -32000, implementation-defined |
| Pending or total request budget exceeded | -32001, implementation-defined |
| Unknown resource URI | -32002, resource-not-found convention |
| Tool argument validation or missing note | Successful JSON-RPC result with isError true |
| Cancelled in-flight operation | No response; task cancelled |
| Unknown, late, or malformed cancellation notification | Ignored |
| Input exceeds 64 KiB including newline | Diagnostic on stderr and session closure |
| EOF | Pending tasks cancelled and process exits |

String and integer IDs are distinct; booleans, nulls, arrays, and fractional IDs
are invalid. IDs cannot be reused even after completion. Unknown notifications
have no response. The server sends no requests to clients, so it expects no
client responses. Invalid JSON-RPC response objects are outside this subset.

Read-only operations serve three literal UTF-8 text resources. URI strings are
looked up exactly, with no normalization, local file reads, network resolution,
or authorization inference. Search returns a text content block containing a
JSON array of matching resource URIs. A query without matches succeeds with an
empty array. Unexpected tool arguments are rejected. Optional request metadata
is tolerated. No server capability advertises subscriptions or list changes.

The Python and TypeScript SDK versions are development dependencies, not server
runtime dependencies. Their full dependency graphs are pinned in hash-checked
requirements and npm lock files. The Python lock uses universal platform markers.
