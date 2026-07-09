# Product context — ISAAC Metadata Assistant (UI handoff)

Orientation for a future UI design session. **No UI is being built now.** This document explains what
the product is, who uses it, what exists today, and where a UI would help — so a designer can design
against reality, not a wish list. The deterministic CLI and its docs are the source of truth; if this
page ever drifts from them, the code and [`../architecture.md`](../architecture.md) win.

Companion handoff docs: [validation-audit-warning-model.md](validation-audit-warning-model.md) (how to
display the three signals) and [data-governance-and-safety.md](data-governance-and-safety.md) (what a UI
must block or warn about). Ground-truth references: repo [`../../README.md`](../../README.md),
[`../cli.md`](../cli.md), [`../architecture.md`](../architecture.md), [`../mentor-brief.md`](../mentor-brief.md).

---

## The product problem

A synchrotron catalysis experiment leaves its metadata scattered across a campaign spreadsheet, beamline
web forms, lab notes, and a file archive. Turning that into a clean, machine-readable record that matches
the DOE-BES **ISAAC** "AI-ready record" standard (v1.05) is slow and error-prone.

The tempting shortcut — let an AI just *fill in* the record — is the wrong move for science. A plausible
but **invented** hash, unit, or peak energy is worse than a blank: it looks trustworthy and isn't. So the
assistant is built around one rule:

> **No guessing. No invented values. No finalized field without evidence or user confirmation.**

It drafts fast, **cites evidence for every value**, and leaves everything unsupported explicitly blank as a
question for a human. "Evidence-first" is not a feature bolted on top — it is the product.

## Target users

This is a research prototype, so keep personas grounded. Three roles interact with it:

- **The operator / intern.** Runs the pipeline: points the assistant at source files, works through the
  blockers, exports the record. Wants low friction and a clear "what do I still need to answer?" view. Today
  they do this on a command line.
- **The scientist confirming values.** Supplies the things the system refuses to guess — file `sha256`
  hashes, the reduced spectrum, at least one descriptor, the absorption edge. Wants to see *what* is being
  asked and *why*, and to answer without touching anything they shouldn't. "I don't know" must be a safe,
  first-class answer that leaves the field honestly missing.
- **The mentor / reviewer auditing honesty.** Checks that the record is schema-valid, that every value has
  evidence, and that nothing was fabricated. Wants to trace any field back to its source and to trust that
  the tool never marked something valid on its own. This is the audience the evidence trail exists for.

None of these roles wants the AI to *decide science*. They want it to draft, cite, refuse, and get out of
the way of the human judgment calls.

## The current CLI prototype

What exists today is a working, **synthetic-data-only** prototype (`v0.1.0`): a local Python CLI plus a set
of Claude authoring skills wrapped around a deterministic core. It is **not** a web app, **not** an MCP
server, and **not** just a Claude prompt.

The end-to-end flow (all deterministic except where a human answers):

```
synthetic XANES metadata (campaign sheet + file listing)
  → evidence-grounded draft        (each field carries {value, status, evidence[]})
  → missing-field blockers          (things the system refuses to guess, surfaced as pending[])
  → human-confirmed completion      (answers stored as user_confirmation evidence; "I don't know" is allowed)
  → official record + evidence sidecar   (records/<ULID>.json + records/<ULID>.evidence.json)
  → official schema validation      (PASS/FAIL against ISAAC v1.05 — the hard gate)
  → evidence audit                  (sidecar coverage: every evidence path resolves to a real field)
  → optional advisory warnings      (non-gating soft-warnings, e.g. ⚠ [NO_LINKS])
  → Graphify memory / query          (optional: find related docs/records, navigate, "what changed?")
  → optional Claude-assisted workflow (the five slash skills drive the same CLI; never decide validity)
```

Concretely:

- **Pipeline + CLI.** `isaac {validate, export, audit, new-id}`, with a global `--root`. `validate <target>`
  runs draft (`--draft`) or official (`--official`) checks; `--warnings` adds advisory soft-warnings on
  official records. `export <draft>` is doubly gated (no-guessing **and** official schema) and writes
  nothing if either fails. `audit` re-validates every record and reports sidecar coverage. Full reference:
  [`../cli.md`](../cli.md). There is **no** `isaac draft`/`complete`/`query` subcommand — those are Claude
  skills, not CLI commands.
- **Claude skills.** `/isaac-draft`, `/isaac-complete`, `/isaac-validate`, `/isaac-export`, `/isaac-query`
  are an operator layer that drives the CLI, asks the blocker questions, and explains results. They never
  mark something valid on their own and never invent a value.
- **Graphify.** An optional memory/query layer (project memory, relationship/similar-record lookup, "what
  changed?", documentation search). It gives *leads*, never *truth* — it cannot validate, export, or fill a
  scientific value. See [`../architecture.md`](../architecture.md) "The two planes".
- **CI.** GitHub Actions runs the test suite, the synthetic demo, official validation, advisory warnings,
  and the audit on every push/PR. 105 tests pass, including one that the truth core never imports Graphify.
- **Reproducible demo.** `.venv/bin/python scripts/run_synthetic_demo.py` regenerates the committed sample
  record byte-for-byte: 26 evidenced fields, 5 blockers refused-then-answered, PASS against v1.05, audit
  clean (`evidence 26/26`), exactly 1 advisory warning. See [`../demo.md`](../demo.md).

## Why a UI would help

A UI's job here is **visibility and lower friction, never new authority.** The command line already does the
work correctly; what it hides is state that humans need to see:

- **Evidence, made visible.** Every value already has a source in the sidecar. A UI can show "this number
  came from `mock_campaign.csv`, cell X" inline instead of asking a reviewer to open a JSON file.
- **Blockers, made obvious.** The five refused blockers are the heart of the product. A UI can present them
  as a clear "you must answer these before export" list rather than lines in a terminal.
- **Validation states, made legible.** PASS/FAIL, audit coverage, and advisory warnings are three different
  signals that are easy to conflate in text. A UI can give each its own visual treatment (see
  [validation-audit-warning-model.md](validation-audit-warning-model.md)).
- **Lower operator friction.** Fewer memorized commands and flags; a guided path from files to record.
- **Mentor-reviewable.** A read-only view of "what was extracted, confirmed, and refused" makes the honesty
  story reviewable without a checkout.

What a UI must **not** do: decide validity, invent a missing value, treat a warning as a failure, or let
Graphify authorize anything. Those boundaries are load-bearing and are covered in the companion docs.

## Current implemented capabilities (honest)

- Deterministic extraction from a structured campaign sheet (`.csv`/`.xlsx`) and a raw file listing, with
  per-field evidence and precise locators.
- Draft assembly in the evidence-envelope format (`{value, unit?, status, evidence[]}`), plus `implicit[]`
  rule-based inferences and `pending[]` blockers for anything unsupported.
- No-guessing draft validation (refuses a finalized field with no evidence, an asset with no `sha256`, a
  descriptor with a null value).
- Completion that applies human answers as `user_confirmation` evidence and never invents.
- Schema-gated export → official ISAAC v1.05 record **plus** an evidence sidecar; no `--force`.
- Official schema validation and an evidence audit (schema re-check + sidecar coverage).
- A non-gating advisory soft-warning seam (`--warnings`, two local heuristic codes).
- An optional Graphify memory/query plane with a routed query cookbook and a freshness helper.
- 105 passing tests and green CI on the full synthetic pipeline.

## Current limitations (honest)

- **Synthetic data only.** No real SLAC/SSRL or private-data pipeline; real data is approval-gated.
- **One path.** Single XANES / characterization path — no electrochemistry / performance / theory domain.
- **No upstream portal parity.** The real `portal/validation.py` is **not** vendored; the local warnings are
  two heuristics, not the portal.
- **Extraction is structured-only.** LLM-assisted extraction of screenshots/PDFs/notes/web-form dumps is
  *designed*, not implemented.
- **Advisory AI review is a placeholder.** `review.py` is a no-op interface, wired into nothing.
- **No web app, no MCP server.** (This handoff is the pre-work for the first UI.)
- **License pending;** the evidence sidecar is an **assistant convention, not an official ISAAC standard**
  (open mentor decision D1).

## Terminology glossary

| Term | Meaning |
|---|---|
| **Draft** | An assistant authoring artifact (`drafts/<name>.draft.json`). Not an official record. |
| **Evidence envelope** | The per-field draft shape `{value, unit?, status, evidence[]}` — where a value lives *with* its source while authoring. |
| **Pending blocker** | An entry in `draft.pending[]`: a value the system knows it needs but refuses to guess (e.g. a `sha256`). |
| **Completion answer** | A human's response to a blocker, stored as `user_confirmation` evidence. "I don't know" leaves the field missing. |
| **Official record** | A schema-clean ISAAC v1.05 record (`records/<ULID>.json`), produced only by `isaac export`. |
| **Evidence sidecar** | `records/<ULID>.evidence.json` — maps official JSON-paths to their source evidence. An assistant audit artifact, **not** part of the official ISAAC record format. |
| **ULID** | The record id (`record_id`), a sortable unique id printed by `isaac new-id`. |
| **Official schema v1.05** | `schema/isaac_record_v1.json`, vendored verbatim from upstream — the authority on record shape and vocabulary. |
| **No-guessing validation** | `draft_validator.py` — gates authoring; every finalized field needs evidence or confirmation. |
| **Official validation** | `official.py` / `isaac validate --official` — the deterministic PASS/FAIL that also gates export. |
| **Evidence audit** | `isaac audit` — re-validates records and reports sidecar coverage (`evidence N/N`). Not a validity re-vote. |
| **Advisory warning** | `⚠ [CODE]` from `--warnings` — non-gating soft note; never blocks export, never means invalid. |
| **Truth plane** | The deterministic, Graphify-free core that decides validity and export. |
| **Memory plane** | Graphify + docs + query routing — context and navigation, never truth. |
| **Graphify** | The optional knowledge-graph memory/query layer. Returns leads to verify, never verdicts. |
| **Freshness** | Whether the Graphify graph is up to date vs. tracked sources (`fresh` / `stale` / `missing`). |

## What must not be overclaimed (UI-copy guidance)

These are the specific claims a UI must never imply — in labels, tooltips, empty states, or marketing copy:

- The AI does **not** create scientific truth. It drafts and cites; humans confirm; the schema decides shape.
- Graphify does **not** validate. A graph answer never establishes validity, required fields, or a value.
- Zero advisory warnings does **not** mean portal acceptance. The upstream portal validator is not vendored.
- Real data is **not** supported. Only synthetic fixtures are processed today; real data is approval-gated.
- Upload is **not** production-ready. There is no upload path yet; any future one is governance-gated.
- Missing fields are **not** inventable. A blank stays blank until a human confirms it.
- The evidence sidecar is **not** an official ISAAC standard — it is an assistant convention (decision D1).
- The license is **not** decided. This is a research prototype; public visibility grants no reuse rights.
