# Design and scope

This is a deliberately small independent server implementation, not an SDK wrapper.
It implements MCP 2025-06-18 over UTF-8 newline-delimited stdio. A session owns
initialization state, outstanding request tasks, and opaque catalog cursors.
The immutable in-memory catalog contains original fictional operational notes.
No URI is interpreted as a filesystem path or fetched over the network.

The event loop processes envelopes in input order. Initialization and notifications
are processed before later requests; tool operations run as cancellable tasks.
Cancellation removes pending work without a response. Completed and unknown IDs
are ignored. EOF cancels remaining tasks and exits. Writes are serialized by the
single event loop. The bounded input reader uses a worker thread for portability.

The wire limit is 64 KiB including the newline. Oversized messages close the
session with a diagnostic on stderr. At most 32 operations may be outstanding.
Request IDs must be unique for the session. A 10,000-request session budget bounds
ID retention. These are implementation limits, not requirements of MCP.

Resources and tools are paginated independently with server-selected page sizes.
Cursors identify catalog positions, are accepted only for their operation, and
are not a security boundary. Clients must neither parse nor persist them.
The server exposes no subscriptions, list-change notifications, prompts, sampling,
elicitation, HTTP, authentication, or filesystem roots.

Two read-only tools provide text search and delayed resource lookup. The delay
is bounded to 2 seconds and exists to make cancellation observable, not to
simulate meaningful compute or produce a throughput claim. Invalid tool arguments
and missing tool data are execution errors (`isError: true`). Unknown tool names,
invalid cursors, and malformed protocol parameters are JSON-RPC errors.

# Specification anchors

- [Lifecycle and negotiation](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)
- [Stdio framing](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [Pagination](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination)
- [Cancellation](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation)
- [Resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)
- [Tools and errors](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

These are published versioned specifications, read before implementation. This
project does not claim full MCP conformance or compatibility with untested hosts.
