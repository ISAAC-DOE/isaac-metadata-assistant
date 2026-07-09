# UI handoff package — start here

This is the entry point for a future **Claude Design** session on the ISAAC Metadata Assistant. It
orients a designer who has never seen the project, then points to the rest of the package for depth.
**No UI is being built now.** This is a design handoff only.

## What ISAAC Metadata Assistant is

ISAAC Metadata Assistant turns scattered experiment metadata (campaign spreadsheets, file listings,
eventually web-form screenshots and notes) into validated, evidence-grounded **official ISAAC
records** (DOE-BES "AI-ready record" standard, v1.05). Its defining rule is **no guessing**: every
finalized field must carry evidence or an explicit human confirmation, or it stays honestly blank.
The assistant drafts fast and cites everything; it never invents a scientific value, unit, hash, or
timestamp to make a record look more complete than the evidence supports.

## Current prototype status (honest, as of commit `af89217`)

**Exists today:**

- A deterministic Python CLI (`isaac validate | export | audit | new-id`) plus five Claude authoring
  skills (`/isaac-draft`, `/isaac-complete`, `/isaac-validate`, `/isaac-export`, `/isaac-query`).
- A reproducible synthetic XANES demo (`scripts/run_synthetic_demo.py`) that regenerates the
  committed sample record byte-for-byte: 26 evidenced fields, 5 blockers refused-then-answered, a
  **PASS** against official ISAAC v1.05, evidence audit `26/26`, and exactly one non-gating advisory
  warning (`⚠ [NO_LINKS]`).
- An optional Graphify memory/query layer (project memory, relationship lookup, navigation) that is
  explicitly excluded from the truth path.
- CI (GitHub Actions) running 105 passing tests on every push, including a test that the
  deterministic core never imports Graphify.

**Does not exist today:**

- No web UI. No MCP server. No upstream portal-validator parity (`portal/validation.py` is not
  vendored — the two local advisory checks are a heuristic seam, not the real portal).
- No real-data pipeline — only synthetic fixtures are processed; real/private data is
  approval-gated and out of scope for this handoff.
- No license decision yet — this is a research prototype; public visibility grants no reuse rights.

## What Claude Design is being asked to design

A **local-first web UI over the existing deterministic core** — a "scientific record workbench"
that makes the CLI's state visible and lowers operator friction. The UI's job is **visibility and
lower friction, never new authority**: the command line already decides validity, exportability, and
completeness correctly. This is a **design exercise only** — visual direction, layout, and
high-fidelity mockups. No implementation, no code, no dependency choices happen in this session.

## Key user workflow (the synthetic demo happy path)

1. Load the synthetic demo (clearly labeled fake, safe, year-2099 fixture data).
2. Draft assembly — fields appear with per-field evidence (source file, locator, quote).
3. Blockers surface — the 5 things the system refuses to guess (hashes, spectrum pointer, a
   descriptor) presented as honest "needs a human" questions, not errors.
4. Human completion — the operator answers each blocker; "I don't know" is a safe, first-class
   answer that leaves a field honestly missing.
5. Export — the draft becomes an official record (`records/<ULID>.json`) plus an evidence sidecar
   (`records/<ULID>.evidence.json`), doubly gated (no-guessing + official schema).
6. Validate — the hard verdict: **PASS/FAIL** against official ISAAC v1.05.
7. Audit — evidence coverage (`evidence N/N`), a separate, non-gating signal.
8. Advisory warnings — non-gating soft notes (e.g. `⚠ [NO_LINKS]`) that never change the verdict.
9. Assistant / memory questions — optional Claude + Graphify help, always labeled with its source,
   never authoritative over the deterministic result.

## Reading order / doc index

Read `claude-design-brief.md` first — it is the self-contained brief meant to open a Claude Design
session. The rest of this package is reference depth behind it.

| Order | Doc | One-line description |
|---|---|---|
| 1 | [`claude-design-brief.md`](claude-design-brief.md) | The copy-paste brief for a Claude Design session — start a design conversation with this. |
| 2 | [`product-context.md`](product-context.md) | What the product is, who uses it, what exists, current limitations, terminology glossary. |
| 3 | [`user-workflows.md`](user-workflows.md) | Step-by-step flows (synthetic demo, future upload, Claude-assisted, error/governance states) mapped to real commands. |
| 4 | [`screens.md`](screens.md) | The 13 screens: purpose, primary actions, key content, states, and what not to show, per screen. |
| 5 | [`design-system.md`](design-system.md) | Visual/interaction direction — feel, typography, color semantics, the three-signal grammar, hard don'ts. |
| 6 | [`ai-assistant-and-graphify.md`](ai-assistant-and-graphify.md) | How the assistant and Graphify behave in the UI — propose→confirm→evidence, freshness, refusal styling. |
| 7 | [`validation-audit-warning-model.md`](validation-audit-warning-model.md) | The three deterministic signals (validation/audit/warnings), why they must never collapse into one badge. |
| 8 | [`data-governance-and-safety.md`](data-governance-and-safety.md) | Synthetic-only default, real-data gating, local-first, what a UI must block or warn about. |
| 9 | [`technical-architecture.md`](technical-architecture.md) | Draft proposal for a future backend/API wrapping the core — paper design, nothing implemented. |

## Hard constraints / non-goals

This is a **design handoff, not a build ticket**. The following hold across every doc in this
package:

- No implementation happens now — no code, no scaffolding, no dependency choices.
- No real or private data is used anywhere in the design process; only the synthetic corpus.
- The AI assistant and Graphify gain **no new authority** — they explain and navigate, never
  validate, never decide export, never mark a record valid/invalid.
- The deterministic core (schema, validators, export, audit, CLI) is unchanged and out of scope.
- The UI must never invent a value, never offer an "export anyway" or "force" path, and never let a
  warning or a graph answer override the hard validation gate.

## Design north star

The product's whole identity is its refusal to guess — that refusal, not a feature list, is what a
scientist has to trust. The UI should read as a precise instrument, not a magic box: calm,
evidence-first, with the deterministic verdict visually dominant on every screen and the assistant
visually subordinate everywhere. Make the honest "not done yet" and "I don't know" states look
dignified and expected, not like failure — that is the product working exactly as intended.
