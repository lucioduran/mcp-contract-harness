# MCP Contract Harness

[![CI](https://github.com/lucioduran/mcp-contract-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/lucioduran/mcp-contract-harness/actions/workflows/ci.yml)

A read-only MCP server with independently implemented clients and inspectable wire evidence.

## Problem

A successful initialization does not establish that an MCP integration handles pagination, cancellation, or errors. This project tests those behaviors against a published protocol version and preserves the actual messages exchanged.

## Scope

Project 05 of the engineering evidence series. The server implements a bounded subset of [MCP 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18): stdio transport, lifecycle negotiation, resources, tools, pagination, ping, and cancellation. Three original fictional station notes are compiled into the server. Two tools search or read those notes without filesystem or network access.

The server uses only the Python standard library. Reference clients use an independent raw implementation, official Python SDK **2.3.0**, and official TypeScript SDK **1.32.1**. Dependencies are needed only for development and SDK interoperability checks. No model, API key, account, or paid service is required to run it.

## Quick start

Use Python **3.11.9**. From the repository root:

```sh
git clone https://github.com/lucioduran/mcp-contract-harness.git
cd mcp-contract-harness
python -m clients.raw
```

This starts a real server subprocess, executes 13 contract checks, closes it, and prints a JSON summary. To start the server for an MCP host, use `python -m mcp_contract.server`. It waits for newline-delimited JSON on stdin; stdout contains protocol messages only.

## Usage

Configure a stdio-capable host to run your Python executable with arguments `-m mcp_contract.server` and this repository as its working directory. Alternatively install the package with `python -m pip install .` and use the `mcp-contract-server` executable from any directory.

| Operation | Behavior |
| --- | --- |
| `resources/list` | Three resources across two pages |
| `resources/read` | Read a `notes://station/` URI from the fixed catalog |
| `resources/templates/list` | Empty template catalog |
| `tools/list` | Two tools across two pages |
| `search_notes` | Case-insensitive substring search; `query` is 1 to 200 characters |
| `read_note` | Read one note; optional integer `delay_ms` from 0 to 2000 |
| `ping` | Empty result, including before initialization |

Clients return opaque cursors unchanged. They do not assume a page size. Tool input or missing-note failures use `isError`; unknown tools and invalid cursors use JSON-RPC errors. See the [contract](docs/contract.md) for error codes and limits.

## Architecture

```text
Raw Python client    Official Python SDK    Official TypeScript SDK
       |                     |                        |
       |              recording proxy          recording proxy
       +---------------------+------------------------+
                             |
                    UTF-8 stdio JSON-RPC
                             |
                 lifecycle + bounded task registry
                             |
                 immutable notes + read-only tools
                             |
                  wire traces -> evidence checks
```

The server does not depend on either SDK. The recorder forwards actual bytes and stores each line with its direction. SDK clients share the recorder and test intent but use different upstream protocol implementations. The raw client has its own transport and pagination logic. See [design decisions and primary sources](docs/design.md).

## Reproduction

Install Python **3.11.9**, Node **24.8.0**, and npm **11.6.0**. Then:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
npm ci --ignore-scripts
python -m clients.reproduce run --output build/reproduced
python -m clients.reproduce verify --output build/reproduced
python -m clients.reproduce verify --output results/reference
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. Run from the repository root. Each run requires a new output directory and fails with exit code 2 on a process, protocol, or evidence error. Do not use Python's `-O` mode: client contract assertions are intentional.

[Recorded evidence](results/reference/report.json) includes exact versions, hardware, timestamp, code revision, source and lock hashes, per-client checks, and trace hashes. Source hashes identify the measured implementation even when later commits add documentation. Verification detects source drift and checks message semantics. It does not authenticate who ran the experiment. There is no random sampling, seed, learned model, train/test split, or performance benchmark. These are fixed correctness scenarios with zero paid API calls.

## Results

The recorded local run passed all three clients against the same server on an Intel Xeon W-3223 with Python 3.11.9 and Node 24.8.0.

| Client | Negotiation | Resource/tool pagination | Reads and tool results | Invalid cursor and tool error | Cancellation and later ping |
| --- | --- | --- | --- | --- | --- |
| Raw reference 0.1.0 | Pass, unsupported-version fallback | Pass | Pass | Pass | Pass |
| Python SDK 2.3.0 | Pass, 2025-11-25 to 2025-06-18 | Pass | Pass | Pass | Pass |
| TypeScript SDK 1.32.1 | Pass, 2025-11-25 to 2025-06-18 | Pass | Pass | Pass | Pass |

The raw client runs 13 scenarios. Each SDK client runs eight. The independent trace validator checks the cancellation message, absence of a cancelled response, complete cursor chains, and final ping response. [Detailed matrix and limitations](docs/interoperability.md) distinguish checks performed by each client. [Message fixtures](results/reference/) are actual recorded traffic, including negative requests.

An initialization-only smoke check is the baseline. The regression suite deliberately corrupts recorded traces by dropping a page, changing the negotiated version, duplicating a response, and injecting a cancelled response. All four are rejected by the trace validator. This is a fixed mutation test, not an estimate of defect detection in arbitrary servers.

## Testing

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy
npm run check
python -m coverage run --branch --source=mcp_contract -m unittest discover -v
python -m coverage report --fail-under=95
python -m clients.reproduce run --output build/test-run
python -m build
```

Tests cover lifecycle order, unsupported version negotiation, malformed UTF-8 and JSON, invalid IDs, parameters, cursor misuse, unknown methods and resources, execution errors, request limits, notification silence, cancellation races, EOF, framing limits, and trace corruption. Python strict type checks cover the server; TypeScript checks cover the JavaScript SDK client. Ruff and Prettier check formatting. CI runs the live clients and server checks on Linux, macOS, and Windows and uploads fresh traces and package artifacts. The server coverage gate is 95%; it is not coverage of upstream SDK code.

## Limitations

- This is a stdio subset, not a full conformance suite or certification. HTTP, OAuth, subscriptions, list-change events, prompts, sampling, elicitation, progress, and resource templates are unsupported.
- No Claude Desktop, ChatGPT, IDE integration, mobile host, or other GUI host has been tested. SDK compatibility does not establish host compatibility.
- The two SDKs are independently maintained implementations within the same official MCP ecosystem. The custom server and raw client share authorship and test assumptions.
- Cancellation tests use a deliberate 400 ms delay and observe silence for at least 600 ms before pinging. Unit tests additionally check task removal. These observations do not prove all scheduling races or absence of resource leaks under load.
- The server caps messages at 64 KiB, active requests at 32, and request IDs at 10,000 per session. Backpressure, exhaustive fuzzing, adversarial resource exhaustion, and performance under load are not evaluated.
- Tool annotations are descriptive hints. The actual implementation only reads compiled notes. This is not a security audit or a sandbox for arbitrary tools. No independent human review is claimed.
- Timings, memory, energy, and throughput are unmeasured. Local hardware and electricity costs are unmeasured. No paid APIs or hosted inference were used.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Keep protocol changes versioned, add meaningful negative tests, and record compatibility only for clients actually exercised. Report security issues as described in [SECURITY.md](SECURITY.md).

## License

Code, original fictional notes, tests, documentation, and recorded traffic use the [MIT license](LICENSE). Dependencies retain their upstream licenses. Specification text is linked, not redistributed.
