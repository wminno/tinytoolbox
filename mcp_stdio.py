#!/usr/bin/env python3
"""Minimal stdio wrapper for tinytoolbox.

Speaks MCP over stdio (initialize / tools/list / tools/call) and proxies to
the SAME tool functions as the production server by calling the Flask app
in-process (app.test_client) — no duplicate business logic, no separate billing
path. Rate limits and key accounting stay server-side.

Run: python3 mcp_stdio.py [--key KEY]   (key: trial or paid; same keys as web)
"""
import json
import sys
from urllib.parse import quote

from app import app, _mcp_tool_call, MCP_TOOLS, MCP_PROTOCOL_VERSION, _get_key


def _key() -> str:
    if "--key" in sys.argv:
        return sys.argv[sys.argv.index("--key") + 1]
    return _get_key() or "trial"


def handle(req: dict):
    rid, method = req.get("id"), req.get("method")
    params = req.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tinytoolbox", "version": "1.1.2"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": MCP_TOOLS}
    if method == "tools/call":
        name = params.get("name")
        res = _mcp_tool_call(name, params.get("arguments") or {}, _key())
        return res if res is not None else {"error": f"unknown tool: {name}"}
    return None


def main():
    key = _key()
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(req, dict) or "id" not in req:
            continue
        result = handle(req)
        resp = {"jsonrpc": "2.0", "id": req["id"]}
        if result is None:
            resp["error"] = {"code": -32601, "message": f"method not found: {req.get('method')}"}
        else:
            resp["result"] = result
        out.write(json.dumps(resp) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
