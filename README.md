# Jayah — deterministic runtime security for AI agents

**The brake pedal for AI agents.** Jayah is the open-core SDK, CLI and MCP
server that stops unsafe agent actions before they run — deterministically,
locally, with no extra LLM call.

Agents fail in two expensive ways: they do something destructive, or they
call another model to check whether they are about to do something
destructive. Jayah fixes both: a deterministic gate decides in-process, and
whatever is approved runs inside a hardened sandbox. Nothing runs on the
host. Failures are reported honestly — never fabricated.

This is the public open-core of TattvaSwarm. The full private system stays
private; this repo holds the parts you can run: **SDK, CLI and MCP server**,
plus the Rust core and the DharmaGate guardrail spec.

## Install — one command

```bash
pip install git+https://github.com/deliciosoradha/jayah-public.git
```

Optional: build the Rust core (faster swarm engine, hardened code runner):

```bash
bash engine/build.sh
```

Python 3.10+, zero required dependencies. The core is stdlib-only by design.

## Configure your backend (2 minutes)

Jayah routes LLM calls to **your own** OpenAI-compatible endpoint — a local
Ollama/vLLM server or any hosted compatible API. Copy the template and fill
in your endpoint:

```bash
cp .env.example .env
```

```env
JAYAH_BASE_URL=http://localhost:11434/v1
JAYAH_API_KEY=
JAYAH_MODEL_FAST=your-fast-model
JAYAH_MODEL_REASONING=your-reasoning-model
JAYAH_MODEL_HEAVY=your-heavy-model
```

No backend configured? The local parts still work — memory, swarm engine and
sandbox need no model. LLM-backed commands fail honestly with the exact
reason instead of inventing an answer.

## Quickstart

```bash
jayah doctor                       # env + backend health check (never fakes OK)
jayah route "summarize this repo"   # route one prompt through the tiered router
jayah memory add "deploy freeze on Fridays" --tags policy
jayah memory search "deploy freeze"
jayah swarm run tasks.json          # parallel workers -> verify -> synthesize
jayah code run "python3 -m pytest -q"   # run code in the hardened sandbox
jayah mcp                           # serve the MCP tools over stdio
```

## MCP — plug it into your client

Claude Desktop / Cursor / any MCP client (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "jayah": {
      "command": "jayah-mcp",
      "env": {
        "JAYAH_BASE_URL": "http://localhost:11434/v1",
        "JAYAH_MODEL_FAST": "your-fast-model"
      }
    }
  }
}
```

Tools exposed: `jayah_status`, `jayah_route`, `jayah_memory_add`,
`jayah_memory_search`, `jayah_swarm_run`, `jayah_code_run`.

## The deterministic brake: DharmaGate

Before an approved action runs, the DharmaGate policy (see
[`agent-guardrails/`](agent-guardrails/README.md)) checks it in two phases:

1. **Red-flag span masking** — destructive patterns are detected and masked,
   so a dangerous phrase cannot hide behind innocent words
   (*"delete the database **without backup**"* must not pass because it
   contains *"backup"*).
2. **Positive alignment check** — the masked proposal is matched against
   verified engineering policies and scored in `[-1.0, 1.0]`.

Decision: `ALIGNED` runs, `TRANSITIONAL` needs context, `MISALIGNED` is
blocked. Same input, same decision, every time.

## What is verified, what is not

- **Verified by construction:** determinism. Run the same swarm config twice
  and compare checksums — identical config always yields the identical
  checksum, in the Python reference and in the Rust core.
- **Not claimed here:** no GPU benchmarks, no latency figures, no accuracy
  percentages. The DharmaGate table in `agent-guardrails/` shows intended
  decisions, not measured results. Measure before you quote.

## What is NOT in this repo

- No token, no chain, no cloud account. There is nothing to buy and no
  wallet to connect.
- No papers, GPU kernels or benchmarks — those live in the private system.
- No telemetry leaves your machine: memory is a local SQLite file, the usage
  ledger is a local JSONL file, and the sandbox runs code in a container, not
  on your host.

## Layout

```
src/tattva_swarm/     Python SDK: router, CLI, MCP server, memory, sandbox,
                      conductor (task graphs), learning gate, LangChain adapter,
                      optional Qdrant context provider
engine/               Rust core (std-only): deterministic swarm engine +
                      hardened code runner — `tattva-engine`
agent-guardrails/     DharmaGate — deterministic runtime guardrail spec
```

## License

Apache-2.0. See [`LICENSE`](LICENSE).

Project site: https://radhikachain.xyz
