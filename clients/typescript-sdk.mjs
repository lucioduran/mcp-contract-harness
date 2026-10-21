import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const python = process.env.MCP_PYTHON || "python";
const trace = process.argv[2];
if (!trace)
  throw new Error("Usage: node clients/typescript-sdk.mjs TRACE_PATH");
const transport = new StdioClientTransport({
  command: python,
  args: ["-m", "clients.wire_proxy", trace],
});
const client = new Client({ name: "typescript-reference", version: "0.1.0" });
const checks = [];
try {
  await client.connect(transport);
  checks.push("version_negotiation");
  for (const kind of ["resources", "tools"]) {
    const items = [];
    const cursors = new Set();
    /** @type {string | undefined} */
    let cursor;
    do {
      if (kind === "resources") {
        const page = await client.listResources({ cursor });
        items.push(...page.resources);
        cursor = page.nextCursor;
      } else {
        const page = await client.listTools({ cursor });
        items.push(...page.tools);
        cursor = page.nextCursor;
      }
      if (cursor !== undefined) {
        assert(!cursors.has(cursor));
        cursors.add(cursor);
      }
    } while (cursor !== undefined);
    assert.equal(items.length, kind === "resources" ? 3 : 2);
    checks.push(`${kind}_pagination`);
  }
  const resource = await client.readResource({
    uri: "notes://station/arrival",
  });
  assert("text" in resource.contents[0]);
  assert.match(resource.contents[0].text, /docking/);
  checks.push("resource_read");
  const result = await client.callTool({
    name: "search_notes",
    arguments: { query: "battery" },
  });
  assert.deepEqual(
    JSON.parse(
      String(/** @type {{text: string}[]} */ (result.content)[0].text),
    ),
    ["notes://station/power"],
  );
  checks.push("tool_success");
  const error = await client.callTool({
    name: "search_notes",
    arguments: { query: "" },
  });
  assert.equal(error.isError, true);
  checks.push("tool_execution_error");
  await assert.rejects(client.listResources({ cursor: "bad" }), {
    code: -32602,
  });
  checks.push("invalid_cursor");
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 100);
  try {
    await assert.rejects(
      client.callTool(
        {
          name: "read_note",
          arguments: { uri: "notes://station/power", delay_ms: 400 },
        },
        undefined,
        { signal: abort.signal },
      ),
    );
  } finally {
    clearTimeout(timer);
  }
  await new Promise((resolve) => setTimeout(resolve, 600));
  await client.ping();
  checks.push("cancellation_and_session_alive");
} finally {
  await client.close();
}
const lock = JSON.parse(readFileSync("package-lock.json", "utf8"));
console.log(
  JSON.stringify({
    client: "official-typescript-sdk",
    version: lock.packages["node_modules/@modelcontextprotocol/sdk"].version,
    checks,
  }),
);
