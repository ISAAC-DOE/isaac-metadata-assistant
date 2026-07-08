# `isaac` CLI reference

The deterministic command-line interface for the ISAAC Metadata Assistant. It is **LLM-free**:
`validate`, `export`, and `audit` never call a model and never touch the Graphify knowledge graph.
The Claude slash skills (`/isaac-draft`, `/isaac-complete`, …) are an authoring layer *on top of*
this CLI — the CLI is the source of truth for validity and export.

For the full end-to-end demo narrative see [`demo.md`](demo.md). This page is the command reference.

---

## Setup assumptions

All examples assume the project virtual environment exists and the package is installed:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Installation registers the `isaac` entry point (`[project.scripts]` in `pyproject.toml`). Invoke it
either through the venv (`.venv/bin/isaac …`) or as `isaac …` with the venv activated. This page
uses the explicit `.venv/bin/isaac` form.

The CLI locates the repo root by walking up from the current directory until it finds
`schema/isaac_record_v1.json`. Run it from anywhere inside the repo, or pass `--root <path>`
explicitly. If no schema is found (and the command is not `new-id`), the CLI exits `2`.

---

## Command list

| Command | Purpose | Role |
|---|---|---|
| `isaac validate <target>` | Validate a draft (no-guessing checks) or a record (official schema) | Core |
| `isaac export <draft>` | Transform a draft → official record + evidence sidecar (gated) | Core |
| `isaac audit` | Validate every record in `records/` against the official schema | Core |
| `isaac new-id` | Print a fresh ULID `record_id` | Core helper |

Global option: `--root ROOT` (repo root; default walks up from cwd to find `schema/`).

`scripts/run_synthetic_demo.py` is a **demo-only** driver — it calls the same core functions but
adds no validation, schema, or export behaviour of its own. It is not part of the deterministic
core (see [Demo-only vs. core](#demo-only-vs-core)).

---

## `isaac validate`

```
isaac validate [--draft] [--official] [--warnings] <target>
```

Validates one JSON file. By default the CLI auto-detects: a file containing a top-level `meta` or
`fields` key is treated as a **draft**; anything else is treated as an **official record**. Force
the mode with `--draft` or `--official`.

| Flag | Effect |
|---|---|
| `--draft` | Force draft (no-guessing) validation |
| `--official` | Force official ISAAC v1.05 schema validation |
| `--warnings` | Also print non-gating advisory portal-style soft-warnings (official records only) |

**Draft validation** runs the no-guessing checks (`draft_validator.py`): it confirms every
finalized field is backed by evidence or user confirmation and surfaces `pending[]` blockers.
A draft with open blockers still validates — blockers are *surfaced*, never guessed.

```bash
.venv/bin/isaac validate drafts/xanes.draft.json --draft
```

**Official validation** checks the record against the vendored official schema:

```bash
.venv/bin/isaac validate records/01JQZ0SYNTHXANESDEMO000000.json --official
# PASS — valid against official ISAAC schema v1.05
```

**Advisory warnings** (`--warnings`) print *after* the hard official result and are never folded
into the exit code — they cannot gate validation or export:

```bash
.venv/bin/isaac validate records/01JQZ0SYNTHXANESDEMO000000.json --official --warnings
# PASS — valid against official ISAAC schema v1.05
#
# Advisory portal warnings (LOCAL seam — do NOT affect official validity or export):
#   ⚠ [NO_LINKS] links — record declares no relationships to other records (optional `links` block absent).
# (1 advisory warning(s) — non-gating)
```

`--warnings` on a draft does nothing but print a reminder that warnings apply to official records.
See [`portal-warnings.md`](portal-warnings.md) for what this seam is and is **not** (it is a local
heuristic seam, not upstream portal parity).

**Exit codes:** `0` valid · `1` invalid · `2` file not found / invalid JSON / no schema root.

### How to interpret validation output

Three signals, three different jobs — don't conflate them:

| Signal | Comes from | What it means |
|---|---|---|
| **PASS / FAIL** | `isaac validate --official` | The **deterministic verdict**. PASS = valid against the vendored official ISAAC v1.05 schema; FAIL = invalid. This is the hard gate that also gates export. |
| **`evidence N/N`** | `isaac audit` | Sidecar **coverage**, not a validity re-vote — every evidence path resolves to a real field (0 dangling). It adds provenance assurance on top of a PASS. |
| **`⚠ [CODE] …` lines** | `isaac validate --warnings` | **Advisory, non-gating.** A soft note a human may want to look at; it does not change the exit code and never blocks export. |

- A **warning does not mean the record is invalid** — a record can be officially valid, audit-clean, and still carry advisory warnings.
- **Absence of warnings does not prove upstream portal acceptance.** These are two local heuristics ([`portal-warnings.md`](portal-warnings.md)), **not** the upstream `portal/validation.py` (not vendored) — a clean local run is not a portal sign-off.
- Only `--official` (and the export gate it backs) decides validity; `audit` reports coverage; `--warnings` is context for a reviewer.

---

## `isaac export`

```
isaac export [--records-dir DIR] [--record-id ULID] <draft>
```

Transforms a draft into an official record plus an evidence sidecar. Export is **doubly gated**: it
runs the no-guessing draft checks *and* validates the transformed record against the official
schema. If either fails, **nothing is written**.

```bash
.venv/bin/isaac export drafts/xanes.draft.json
# PASS — valid against official ISAAC schema v1.05
#
# Exported record  → records/01J….json
# Evidence sidecar → records/01J….evidence.json
```

| Flag | Effect |
|---|---|
| `--records-dir DIR` | Write to `DIR` instead of `records/` |
| `--record-id ULID` | Use this ULID instead of generating a fresh one |

Records are **immutable via the CLI**: if `records/<ULID>.json` already exists, export is blocked
rather than overwriting it. The normal authoring path is **draft → export**; do not hand-edit files
under `records/`.

**Generated files** (see [Output artifacts](#output-artifacts)):

- `records/<ULID>.json` — the official ISAAC v1.05 record.
- `records/<ULID>.evidence.json` — the evidence sidecar (official JSON-path → source evidence).

**Exit codes:** `0` exported · `1` blocked (draft or schema failure, or record already exists) ·
`2` file not found / invalid JSON.

---

## `isaac audit`

```
isaac audit [--records-dir DIR]
```

Validates every record in `records/` (or `DIR`) against the official schema and reports evidence
sidecar coverage.

```bash
.venv/bin/isaac audit --records-dir /tmp/isaac-demo
# PASS  01JQZ0SYNTHXANESDEMO000000.json  (0 schema errors, evidence 26/26)
#
# 1 records audited, 0 failing official validation
```

**Exit codes:** `0` all records pass · `1` at least one record fails official validation.

---

## `isaac new-id`

```
isaac new-id
```

Prints a fresh ULID suitable for use as a `record_id`. No file I/O. Exit code `0`.

---

## Output artifacts

| Artifact | Written by | What it is |
|---|---|---|
| `records/<ULID>.json` | `isaac export` | Official ISAAC v1.05 record — validates against the vendored schema |
| `records/<ULID>.evidence.json` | `isaac export` | Evidence **sidecar**: maps official JSON-paths to their source evidence. An assistant audit artifact, **not** part of the official ISAAC record format |
| `drafts/<name>.draft.json` | `/isaac-draft` / `/isaac-complete` | Pre-export draft in the evidence-envelope format (`{value, status, evidence[]}`). Not an official record |

The official schema is `additionalProperties: false` and has no per-field provenance slot, which is
why evidence lives in the sidecar rather than inside the record.

---

## Common mistakes

- **Validating a sidecar as an official record.** `records/<ULID>.evidence.json` is an assistant
  artifact, not an ISAAC record — running `isaac validate <ULID>.evidence.json --official` will
  fail. Validate the `<ULID>.json` record, not its sidecar. (`isaac audit` already validates only
  the records and separately reports sidecar coverage.)
- **Validating a draft as a record (or vice-versa).** Drafts use the evidence-envelope format and
  will not pass official validation; official records will not pass draft checks. Let auto-detect
  work, or be explicit with `--draft` / `--official`.
- **Treating `--warnings` as a gate.** Advisory soft-warnings never change the exit code and never
  block export. They are context for a human reviewer.
- **Hand-editing `records/`.** Records are immutable via the CLI. Re-export from the draft instead.
- **Running outside the repo without `--root`.** If the CLI cannot find
  `schema/isaac_record_v1.json` by walking up from cwd, pass `--root <repo>` (or `cd` into the repo).

---

## Exit code summary

| Code | Meaning |
|---|---|
| `0` | Success / valid / all records pass |
| `1` | Invalid record, blocked export, or an audited record fails official validation |
| `2` | File not found, invalid JSON, or no official schema at the resolved root |

---

## Demo-only vs. core

| Command | Kind |
|---|---|
| `isaac validate` / `export` / `audit` / `new-id` | **Core** deterministic pipeline |
| `.venv/bin/python scripts/run_synthetic_demo.py` | **Demo-only** reviewer driver — regenerates the committed synthetic sample byte-for-byte and prints each pipeline stage. Adds no schema/validation/export logic of its own |
| `.venv/bin/python scripts/make_synthetic_examples.py` | **Demo-only** — populates `examples/` with clearly-fake mock artifacts so `/isaac-draft` can be exercised without real data |

Run the full demo, then verify its output with the core CLI:

```bash
.venv/bin/python scripts/run_synthetic_demo.py
.venv/bin/isaac validate /tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.json --official
.venv/bin/isaac audit --records-dir /tmp/isaac-demo
```
