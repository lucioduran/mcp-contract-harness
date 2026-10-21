# Interoperability evidence

Transport: UTF-8 newline-delimited JSON-RPC over local stdio. Protocol: 2025-06-18.
Server: mcp-contract-harness 0.1.0. Client wrappers: 0.1.0.

| Scenario | Raw standard-library client | Python MCP 2.3.0 | TypeScript MCP 1.32.1 |
| --- | --- | --- | --- |
| Initialization and ready notification | Exercised | Exercised | Exercised |
| Server selects 2025-06-18 from another version | 2099-01-01 offered | 2025-11-25 offered | 2025-11-25 offered |
| Resources pagination, two pages, three unique resources | Exercised | Exercised | Exercised |
| Tools pagination, two pages, two unique tools | Exercised | Exercised | Exercised |
| Resource text read | Exercised | Exercised | Exercised |
| Tool success and execution error | Exercised | Exercised | Exercised |
| Invalid cursor (-32602) | Exercised | Exercised | Exercised |
| Unknown method (-32601) | Exercised | Not exercised | Not exercised |
| Unknown resource (-32002) | Exercised | Not exercised | Not exercised |
| Parse error (-32700) | Exercised | Not injected through SDK | Not injected through SDK |
| Pre-initialization rejection | Exercised | Not injected through SDK | Not injected through SDK |
| Cancellation notification, no response, subsequent ping | Explicit notification | AnyIO cancellation scope | AbortController |
| Unknown cancellation ignored | Exercised | Not exercised | Not exercised |
| Full negative envelope and limit matrix | In-process server tests | Not exercised | Not exercised |
| HTTP, subscriptions, sampling, GUI hosts | Unsupported or untested | Untested here | Untested here |

The SDKs start the recording proxy as their stdio server. The proxy starts the
same Python server module and records lines before forwarding them. Raw traffic
is recorded by the raw client itself. Files contain exact UTF-8 wire strings;
JSONL escaping is a storage representation, not a rewrite of the inner message.
There are no credentials, personal data, or external tool payloads in fixtures.

Each client asserts its own outcomes. A separate validator inspects all three
wire traces, checks correlation and cursor chains, rejects cancelled responses,
and requires a later answered ping. It rejects incomplete recordings rather than
quietly counting partial runs. SHA-256 detects subsequent byte changes; it does
not establish independent provenance or cryptographic authorship.

The baseline smoke test asks whether any successful initialize response exists.
It would accept each corrupted trace in the mutation regression suite, including
a response that names an unsupported version. The full trace validator rejects
all four tested corruption classes. This compares evidence validation depth, not
performance, and is not a competition between SDKs.

Sources: [Python SDK](https://github.com/modelcontextprotocol/python-sdk),
[TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk), and the
[versioned specification links](design.md#specification-anchors).
