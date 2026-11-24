"""MCP server (stdio) — Jayah tools for any MCP client. stdlib only.

Run::

    python3 -m tattva_swarm.mcp_server

Tools exposed:

* ``jayah_status``         — honest backend snapshot (key / tiers / sandbox)
* ``jayah_route``          — one prompt through the tiered router
* ``jayah_memory_add``     — store a note in the local memory (SQLite + FTS5)
* ``jayah_memory_search``  — full-text search over local memory
* ``jayah_swarm_run``      — run the logical swarm engine (Rust core if built)
* ``jayah_code_run``       — run a command in the hardened Docker sandbox

Protocol: JSON-RPC 2.0 over stdio, newline-delimited (MCP 2024-11-05).
stdout carries protocol messages only; diagnostics go to stderr.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Callable

from . import __version__

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "jayah", "version": __version__}
INSTRUCTIONS = (
    "Jayah — deterministic runtime security for AI agents: tiered routing to "
    "your own OpenAI-compatible backend, local-only memory, deterministic "
    "logical worker swarms, and a hardened code sandbox. Nothing runs on the "
    "host; failures are reported honestly."
)

# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


def _tool_status(args: dict) -> tuple[dict, bool]:
    import os

    from .backend import load_env_file, jayah_home
    from .router import tier_models
    from .sandbox import backend_status

    load_env_file()
    key = os.environ.get("JAYAH_API_KEY", "").strip()
    base = os.environ.get("JAYAH_BASE_URL", "").strip()
    out = {
        "status": "ok",
        "api_key": f"set (len={len(key)})" if key else "missing — set JAYAH_API_KEY",
        "base_url": base or "missing — set JAYAH_BASE_URL",
        "tiers": tier_models(),
        "research_tier": "enabled" if os.environ.get("TAVILY_API_KEY", "").strip() else "disabled (TAVILY_API_KEY missing)",
        "sandbox": backend_status(),
        "jayah_home": str(jayah_home()),
        "protocol": PROTOCOL_VERSION,
        "version": __version__,
    }
    return out, False


def _tool_route(args: dict) -> tuple[dict, bool]:
    prompt = str(args.get("prompt", "")).strip()
    if not prompt:
        return {"status": "error", "error": "missing required argument: prompt"}, True
    from .router import route

    out = route(prompt, tier=str(args.get("tier", "auto")))
    return out, out.get("status") != "ok"


def _tool_memory_add(args: dict) -> tuple[dict, bool]:
    text = str(args.get("text", "")).strip()
    if not text:
        return {"status": "error", "error": "missing required argument: text"}, True
    from .memory import Memory

    mem = Memory()
    try:
        entry_id = mem.add(
            text,
            kind=str(args.get("kind", "note")),
            source="mcp",
            tags=list(args.get("tags") or []) or None,
        )
        return {"status": "ok", "id": entry_id, "note": "stored locally; nothing left this machine"}, False
    finally:
        mem.close()


def _tool_memory_search(args: dict) -> tuple[dict, bool]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"status": "error", "error": "missing required argument: query"}, True
    from .memory import Memory

    mem = Memory()
    try:
        rows = mem.search(query, limit=int(args.get("limit", 5)))
        return {"status": "ok", "query": query, "count": len(rows), "results": rows}, False
    finally:
        mem.close()


def _tool_swarm_run(args: dict) -> tuple[dict, bool]:
    workers = max(1, int(args.get("workers", 100_000)))
    steps = max(1, int(args.get("steps", 6)))
    seed = int(args.get("seed", 7))
    modulus = max(2, int(args.get("modulus", 97)))
    threads = int(args.get("threads", 0))

    from .sandbox import find_engine_binary

    engine = find_engine_binary()
    if engine:
        argv = [engine, "run-swarm", "--workers", str(workers), "--steps", str(steps),
                "--seed", str(seed), "--modulus", str(modulus)]
        if threads > 0:
            argv += ["--threads", str(threads)]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
            payload = json.loads([ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1])
            payload["implementation"] = "rust"
            return payload, False
        except Exception as exc:  # noqa: BLE001 — fall through to the python reference
            sys.stderr.write(f"[jayah-mcp] rust swarm failed ({exc}); using python reference\n")

    from .engine import SwarmConfig, run_swarm

    report = run_swarm(SwarmConfig(workers=workers, steps=steps, seed=seed, solve_modulus=modulus))
    out = report.to_dict()
    out["implementation"] = "python"
    return out, False


def _tool_code_run(args: dict) -> tuple[dict, bool]:
    command = str(args.get("command", "")).strip()
    if not command:
        return {"status": "error", "error": "missing required argument: command"}, True
    from .sandbox import CodeEngineError, run_code

    try:
        result = run_code(
            command,
            image=args.get("image"),
            timeout_s=float(args.get("timeout_s", 30)),
            allow_network=bool(args.get("allow_network", False)),
            workdir=args.get("workdir"),
        )
    except CodeEngineError as exc:
        return {"status": "error", "error": str(exc)}, True
    return result.to_dict(), False


TOOLS: list[dict[str, Any]] = [
    {
        "name": "jayah_status",
        "description": "Honest snapshot of the Jayah stack: API key presence, tier models, code-engine backends. Never fabricates.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "jayah_route",
        "description": "Route one prompt through the tiered router (small/normal/reasoning/heavy/research).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The user prompt to route and answer."},
                "tier": {"type": "string", "enum": ["auto", "small", "normal", "reasoning", "heavy", "research"], "default": "auto"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jayah_memory_add",
        "description": "Store a note in the local persistent memory (SQLite + FTS5). Data never leaves the machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "kind": {"type": "string", "default": "note"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jayah_memory_search",
        "description": "Full-text search over the local memory (FTS5, operator-safe quoting).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jayah_swarm_run",
        "description": "Run the deterministic logical swarm engine (Rust core when built, python reference otherwise). Same config -> same checksum.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workers": {"type": "integer", "minimum": 1, "default": 100000},
                "steps": {"type": "integer", "minimum": 1, "default": 6},
                "seed": {"type": "integer", "default": 7},
                "modulus": {"type": "integer", "minimum": 2, "default": 97},
                "threads": {"type": "integer", "minimum": 0, "default": 0},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "jayah_code_run",
        "description": "Run one command inside the hardened Docker sandbox (no network by default, memory/CPU caps, wall-clock timeout). Code never runs on the host.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run inside the sandbox image."},
                "image": {"type": "string", "description": "Container image (default python:3.12-slim or JAYAH_SANDBOX_IMAGE)."},
                "timeout_s": {"type": "number", "default": 30},
                "allow_network": {"type": "boolean", "default": False},
                "workdir": {"type": "string", "description": "Optional host dir mounted at /work (rw)."},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
]

_HANDLERS: dict[str, Callable[[dict], tuple[dict, bool]]] = {
    "jayah_status": _tool_status,
    "jayah_route": _tool_route,
    "jayah_memory_add": _tool_memory_add,
    "jayah_memory_search": _tool_memory_search,
    "jayah_swarm_run": _tool_swarm_run,
    "jayah_code_run": _tool_code_run,
}

# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------


def _result(mid: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": payload}


def _error(mid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle_message(msg: dict) -> dict | None:
    """Handle one JSON-RPC message; return a response dict, or None for notifications."""
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        return _result(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })
    if method == "ping":
        return _result(mid, {})
    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = str(params.get("name", ""))
        args = params.get("arguments") or {}
        handler = _HANDLERS.get(name)
        if handler is None:
            return _result(mid, {
                "content": [{"type": "text", "text": f"unknown tool: {name!r}"}],
                "isError": True,
            })
        try:
            payload, is_err = handler(args)
        except Exception as exc:  # noqa: BLE001 — surface, never fake
            payload, is_err = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}, True
        return _result(mid, {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
            "isError": is_err,
        })

    if mid is None:
        return None  # notification we don't handle (e.g. notifications/initialized)
    return _error(mid, -32601, f"method not found: {method}")


def main() -> int:
    sys.stderr.write(f"[jayah-mcp] serving over stdio (protocol {PROTOCOL_VERSION}, v{__version__})\n")
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write("[jayah-mcp] dropped non-JSON line\n")
            continue
        response = handle_message(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
