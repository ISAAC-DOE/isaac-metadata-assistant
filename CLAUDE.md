# ISAAC Metadata Assistant — Project Instructions

This repository contains the ISAAC Metadata Assistant prototype.

Project goal: turn experiment metadata into validated, evidence-grounded official ISAAC records using the official ISAAC v1.05 schema. The assistant helps draft, complete, validate, export, query, and review records while preserving a strict no-guessing policy.

Read this file before working in the repository. Also read `AGENTS.md` for agent workflow and phase execution rules.

---

## 1. Source of Truth

The official ISAAC schema is the authority on record structure, required fields, and vocabulary.

Authoritative schema:

```text
schema/isaac_record_v1.json
```

Schema provenance:

```text
schema/PROVENANCE.md
```

Upstream source:

```text
https://github.com/ISAAC-DOE/isaac-ai-ready-record
```

The official schema is vendored for offline, deterministic validation. It is not ours to casually edit. If it needs to be refreshed, do so from the upstream ISAAC repository and update `schema/PROVENANCE.md`.

Exported records must validate against the official schema.

Use:

```bash
.venv/bin/isaac validate <record> --official
```

Do not invent an alternative official record format.

---

## 2. Two Planes: Truth vs. Memory

The project has two separate planes.

### Truth Plane

The truth plane decides validity, exportability, and official record shape.

It includes:

- `schema/isaac_record_v1.json`
- `src/isaac_records/official.py`
- `src/isaac_records/draft_validator.py`
- `src/isaac_records/export.py`
- `src/isaac_records/audit.py`
- `src/isaac_records/cli.py`
- tests that enforce schema validation, export gating, sidecar path resolution, and no Graphify imports

The truth plane must be deterministic and Graphify-free.

If a graph answer, LLM answer, note, or memory conflicts with the schema, validator, export behavior, audit result, or tests, the deterministic source wins.

### Memory / Query Plane

The memory/query plane helps with context, relationships, and project navigation.

It includes:

- Graphify
- docs
- query routing
- project memory
- similar-record lookup
- documentation search
- prior experiment/document queries
- contextual drafting help

Graphify is central for memory and query, but never central for truth.

Graphify can suggest context. It cannot authorize export.

---

## 3. Validation Stack

Validation and review happen in this order:

1. Draft no-guessing validation using `draft_validator.py`
2. Official ISAAC schema validation using `official.py`
3. Official `portal/validation.py` soft-warning tier, when integrated
4. AI scientific consistency review using `review.py`, advisory only
5. Human review for ambiguous science or policy decisions

Stage 4 is advisory only. It must never:

- mark records officially valid or invalid
- mutate records silently
- override official schema validation
- override portal validation
- block export unless an explicit user-approved policy later wires it in

The official schema and deterministic validators remain authoritative.

---

## 4. Drafts vs. Official Records

Drafts and official records are different.

### Drafts

Drafts are assistant authoring artifacts. They may use an evidence envelope format such as:

```json
{
  "value": "...",
  "status": "verified",
  "evidence": []
}
```

Drafts may contain:

- missing values
- `needs_confirmation`
- user-confirmation requests
- evidence entries
- implicit values
- extraction notes

Drafts are not official ISAAC records.

Drafts may live in:

```text
drafts/
tests/fixtures/
```

### Official Records

Official records are schema-clean ISAAC records.

They must:

- validate against `schema/isaac_record_v1.json`
- use official ISAAC field structure
- avoid custom evidence envelopes
- avoid arbitrary assistant-only fields
- be generated through `isaac export`

Official generated records live in:

```text
records/
```

Never hand-edit official records in `records/` unless explicitly instructed. The normal path is draft → export.

### Evidence Sidecars

The official schema does not support arbitrary per-field evidence wrappers. This assistant preserves field-level evidence in sidecar files:

```text
records/<ULID>.json
records/<ULID>.evidence.json
```

The sidecar maps official JSON paths to evidence entries.

The sidecar is an assistant audit artifact unless mentors approve it as an official ISAAC convention.

---

## 5. No-Guessing Rules

Never invent or guess:

- scientific values
- units
- sha256 hashes
- URIs
- file paths
- raw-data pointers
- descriptor values
- uncertainty values
- QC status
- links
- timestamps from nowhere
- scientific interpretations

If a value is not supported by evidence:

- leave it missing
- mark it `needs_confirmation`
- ask a targeted question
- or keep it out of the exported official record

Every non-null finalized draft field must have evidence or user confirmation.

A field may be inferred only by a documented/stored rule. Scientific judgment is not an inference unless supported by evidence or user confirmation.

Absorbing element and edge for the XANES path are currently treated as implicit/sidecar-only unless the official schema provides a native field. Do not force them into the official record if the schema has no valid path.

---

## 6. Data Governance

Treat `examples/` as potentially sensitive. It is gitignored for a reason.

Rules:

- Never commit real SLAC/SSRL/private artifacts.
- Never commit private Excel files, screenshots, PDFs, raw data, raw file listings, or private notes.
- Never send real experiment data to external services unless the user explicitly confirms that it is allowed.
- Synthetic fixtures must be unmistakably fake.
- Public official ISAAC schema/examples may be committed if provenance is documented.
- If unsure whether a file is safe, stop and ask.

For any phase touching input artifacts, report:

- what files were read
- whether they were synthetic or real
- whether any model/LLM saw the content
- whether anything under `examples/` was staged
- `git status --short`
- `git check-ignore` results for generated examples files when relevant

---

## 7. Graphify Memory Plane

This repository may have a local Graphify graph at:

```text
graphify-out/
```

Graphify is the memory/query/context plane.

Use Graphify for:

- project memory
- relationship search
- similar-record lookup
- prior experiment/document queries
- contextual drafting help
- documentation search
- “what changed?” history
- “how is this connected?” questions
- architecture navigation before editing unfamiliar code

Do not use Graphify for:

- official schema validation
- export decisions
- required-field enforcement
- vocabulary authority
- audit truth
- data-governance decisions

If `graphify-out/graph.json` exists, use Graphify before answering architecture/codebase questions.

Recommended commands:

```bash
graphify query "<question>"
graphify explain "<concept>"
graphify path "<A>" "<B>"
```

Use `graphify-out/wiki/index.md` if present for broad navigation.

Use `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/explain/path are insufficient.

Known caveat: Graphify may contain dangling/collapsed semantic edges from AST/semantic ID mismatch. Treat Graphify as helpful context, not guaranteed truth. Spot-check important graph claims against source files, schema, and tests.

Never commit `graphify-out/`.

After large uncommitted architectural/code changes, run `graphify update .` if safe and useful. If a git hook already updates the graph after commit, manual update is only needed for large uncommitted changes.

---

## 8. Slash Skills

Available project-local skills:

- `/isaac-draft`
- `/isaac-complete`
- `/isaac-validate`
- `/isaac-query`
- `/isaac-export`

Do not add new slash commands unless explicitly approved.

Current command boundaries:

- `/isaac-draft`: extract into draft format with evidence
- `/isaac-complete`: ask only validator/export-blocking questions
- `/isaac-validate`: explain draft/official validation results
- `/isaac-query`: route query to schema/docs/audit/git/Graphify depending on question type
- `/isaac-export`: deterministic export to official ISAAC record + evidence sidecar

---

## 9. Query Routing

Use the correct source for the question.

| Question type | Source |
|---|---|
| Is this official record valid? | `isaac validate` / official schema |
| What fields are required? | official schema |
| What vocabulary values are allowed? | official schema / official docs |
| Which records are incomplete? | deterministic audit |
| What changed recently? | git log / docs / Graphify for memory |
| What is related to this sample/record/topic? | Graphify |
| What prior docs mention this concept? | Graphify / docs |
| Is this scientifically suspicious? | advisory review / human review, not official validation |

Graphify can suggest context; it cannot authorize export.

---

## 10. Phase Workflow

Work phase-by-phase. Do not run ahead.

Each phase should follow this loop:

1. Plan the slice.
2. Dispatch the appropriate subagent for focused implementation.
3. Review the diff against project invariants.
4. Run verification.
5. Fix/iterate if checks fail.
6. Commit/push only when the phase instructions allow it.
7. Stop at the approval gate before the next phase.

For this project:

- Fable 5 is the orchestrator, planner, reviewer, and verifier.
- Opus subagents are preferred for implementation slices unless explicitly told otherwise.
- Keep slices small, reviewable, testable, and committable.
- Do not begin the next phase without explicit user approval.
- Do not broaden scope during a phase.

---

## 11. Current Phase Context

Current state:

- The deterministic truth/export/validation/audit core and the synthetic XANES draft→export→sidecar→audit flow are in place and passing.
- Current repository status is summarized in README.md and docs/mentor-brief.md; see git history for the exact commit state.
- Start any further phase only after explicit user approval.

Do not treat this note as a work authorization — confirm the actual head, branch, and status with the commands below before continuing.

Before continuing, verify repo state with:

```bash
git status -sb
git diff --stat
git log --oneline -5
.venv/bin/pytest
```

---

## 12. Reporting Cadence

After every implementation slice and every phase, provide a report. Do not wait until the end of a large phase.

Each report must include:

- files changed
- what was implemented
- what was intentionally not changed
- verification commands/results
- test results
- safety/data-governance checks
- whether truth/export/validation paths were touched
- whether Graphify was used or updated
- commit hash if committed
- push status
- blockers or deferred items
- recommendation for the next slice/phase

This applies to all future phases.

---

## 13. Truth Path Protection

The truth/export/validation path consists of:

- `schema/isaac_record_v1.json`
- `src/isaac_records/official.py`
- `src/isaac_records/draft_validator.py`
- `src/isaac_records/export.py`
- `src/isaac_records/audit.py`
- `src/isaac_records/cli.py`
- tests that enforce official validation, export gating, sidecar resolution, and no Graphify import

Do not modify the truth path during extraction/query/review work unless explicitly required.

If the truth path is touched, the report must say:

- why it was touched
- what changed
- what tests cover it
- whether exported record behavior changed
- whether official schema compliance changed

The deterministic core must remain Graphify-free.

---

## 14. Development Commands

Use the project virtual environment.

Common commands:

```bash
.venv/bin/pytest
.venv/bin/isaac validate <path> --official
.venv/bin/isaac validate <path> --draft
.venv/bin/isaac export <draft>
.venv/bin/isaac audit
git status -sb
git diff --stat
git log --oneline -5
git check-ignore <path>
```

Keep output concise:

- report command and result
- do not paste huge passing logs
- on failures, show the failing test/file and first useful error lines

This is a Python package/prototype, not a Next.js app. Do not run unrelated build/deploy commands.

---

## 15. Scope Discipline

Current MVP scope:

- single XANES / characterization path
- synthetic data first
- real/sanitized data later only with explicit approval
- official ISAAC schema validation
- evidence sidecar
- optional Graphify memory/query

Out of scope unless explicitly approved:

- performance/electrochemistry domain support
- simulation/theory/derived domain support
- portal validator integration beyond evaluation
- real SLAC/SSRL data processing
- new slash commands
- Graphify as truth layer
- advisory AI review implementation beyond isolated placeholder

---

## 16. Resume Protocol

After interruption or context reset:

1. Read `CLAUDE.md`.
2. Read `AGENTS.md`.
3. Check latest roadmap/plan docs if present.
4. Run `git status -sb`.
5. Run `git log --oneline -5`.
6. Reconcile claimed progress with actual repo state.
7. Announce the verified state.
8. Continue only from verified facts.

Never guess what was completed.