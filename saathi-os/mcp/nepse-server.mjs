#!/usr/bin/env node
/**
 * NEPSE MCP server — stdio transport. JSON-RPC 2.0, no new dependency.
 *
 * The protocol layer only: it frames messages and routes `tools/call` into the
 * pure handlers in `lib/mcp/tools.js`. Every decision about what an answer means
 * lives there, so the transport can be replaced without touching semantics.
 *
 * READ-ONLY. No tool mutates anything, and the server never writes to disk.
 * Portfolio state arrives as a call argument and is discarded when the call
 * returns — this process stores nobody's positions.
 */
import { createInterface } from "node:readline";

import {
  MCP_PROTOCOL_VERSION, MCP_SERVER_NAME, MCP_SERVER_VERSION,
  TOOL_SCHEMAS, callTool, createHandlers,
} from "../lib/mcp/tools.js";

// No dataset is loaded by default: the server starts inert and answers with
// typed refusals rather than connecting to anything on launch.
const handlers = createHandlers({});

const send = (msg) => process.stdout.write(JSON.stringify(msg) + "\n");
const reply = (id, result) => send({ jsonrpc: "2.0", id, result });
const fail = (id, code, message) => send({ jsonrpc: "2.0", id, error: { code, message } });

function handle(msg) {
  const { id, method, params } = msg || {};
  switch (method) {
    case "initialize":
      return reply(id, {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: { tools: {} },
        serverInfo: { name: MCP_SERVER_NAME, version: MCP_SERVER_VERSION },
      });
    case "tools/list":
      return reply(id, { tools: TOOL_SCHEMAS });
    case "tools/call": {
      const out = callTool(handlers, params?.name, params?.arguments);
      // MCP content blocks. `isError` reflects the handler's own verdict rather
      // than a thrown exception, so a typed refusal reads as a refusal.
      return reply(id, {
        content: [{ type: "text", text: JSON.stringify(out, null, 2) }],
        isError: out?.ok === false,
      });
    }
    case "notifications/initialized":
      return; // no response for notifications
    default:
      if (id !== undefined) fail(id, -32601, `unknown method: ${method}`);
  }
}

createInterface({ input: process.stdin }).on("line", (line) => {
  const text = line.trim();
  if (!text) return;
  let msg;
  try {
    msg = JSON.parse(text);
  } catch {
    return fail(null, -32700, "parse error");
  }
  try {
    handle(msg);
  } catch (e) {
    // A handler fault must not kill the session or leak a stack trace.
    if (msg?.id !== undefined) fail(msg.id, -32603, String(e?.message || e).slice(0, 200));
  }
});
