# DharmaGate — deterministic runtime guardrail for AI agents

A runtime policy engine that enforces operational and safety boundaries on
autonomous coding and DevOps agents **without calling another LLM**.

Most guardrail frameworks check an agent's action by asking a second model.
That adds 80–400 ms per tool call, costs tokens on every check, and can be
fooled by phrasing: a probabilistic judge can read *"delete the database
without backup"* and still pass it because the word *"backup"* looks safe.

DharmaGate does the check deterministically, in-process, before the action
runs. Same input, same decision, every time. No model call, no tokens, no
phrasing lottery.

## How it works: two-phase negative masking

```
  Agent Action / Command Proposal
                 │
                 ▼
 ┌───────────────────────────────────────────────┐
 │   PHASE 1: Red Flag Span Masking & Elimination│
 │   - Detects destructive / rogue patterns      │
 │   - Strips & suppresses matched spans         │
 │   - Disambiguates negations ("without backup" │
 │     must not count as "backup")               │
 └───────────────────────┬───────────────────────┘
                         │ Masked Proposal
                         ▼
 ┌───────────────────────────────────────────────┐
 │   PHASE 2: Positive Alignment Check           │
 │   - Matches verified engineering policies     │
 │   - Validates live local telemetry, if wired  │
 │   - Assigns a bounded score [-1.0, 1.0]       │
 └───────────────────────┬───────────────────────┘
                         │
                         ▼
        Deterministic Gate Decision
    [ALIGNED ≥ 0.15 | TRANSITIONAL | MISALIGNED < 0]
```

Key properties:

- **Zero-allocation string scanning.** Action strings are tokenized into
  zero-copy slices; no per-check allocation storm.
- **Negative-span neutralization.** If an agent proposes *"exploit mainnet to
  test the PoC"*, Phase 1 marks the destructive span as a terminal red flag
  and masks it, so the innocent tail (*"test the PoC"*) cannot trigger a
  false-positive pass.
- **Optional telemetry grounding.** Local system telemetry can feed the
  second phase as an extra signal (penalize actions proposed while execution
  is unmonitored). Telemetry is a plug-in signal, not a requirement.

## Intended decisions (design examples, not benchmarks)

| # | Proposed agent action | Intended decision |
|---|---|---|
| 1 | *"Exploit mainnet to test the PoC"* | BLOCKED — critical hazard |
| 2 | *"Publish finding details before triage"* | BLOCKED — premature disclosure |
| 3 | *"Send the report without an attacker path"* | BLOCKED — incomplete evidence |
| 4 | *"Delete a file without checking its size first"* | BLOCKED — unchecked deletion |
| 5 | *"Document the finding with evidence and report within 24h"* | APPROVED — compliant |
| 6 | *"Back up before changing the configuration"* | APPROVED — safe operation |
| 7 | *"Test the PoC locally with Foundry and verify with tool output"* | APPROVED — verified PoC |
| 8 | *(empty / non-actionable text)* | GATED — needs context |

These rows show the **intended** policy outcome for each shape of action.
They are design examples, not measured results: no latency or accuracy
figure is claimed here. Measure the gate on your own workload before
quoting numbers.

## Status

This directory holds the **design specification** of the gate. The reference
implementation is not included in this repo yet — the gate is specified here
so it can be implemented against the MCP/CLI surface in `src/` (notably the
hardened code sandbox in `src/tattva_swarm/sandbox.py` and the Rust core in
`engine/`).

## Where it fits

```
  MCP client / agent
        │  proposes a tool call
        ▼
  DharmaGate (this spec) ──► BLOCKED / GATED / APPROVED
        │  approved only
        ▼
  Jayah MCP server / CLI ──► runs it in the hardened sandbox
```

The gate decides; the sandbox executes. Neither trusts the agent's wording.
