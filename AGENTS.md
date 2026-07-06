# AGENTS.md — ISAAC Metadata Assistant

This repository contains the ISAAC Metadata Assistant prototype.

The project converts experiment metadata into validated, evidence-grounded official ISAAC v1.05 records. The assistant uses a draft-only evidence envelope during extraction, then exports schema-clean official ISAAC records plus sidecar evidence files.

Read this file before using agent workflows in this repository. Also read `CLAUDE.md`.

---

## 1. Core Principle

The official ISAAC schema is the source of truth.

Do not invent an alternative official record format.

Do not modify the official schema except by explicitly refreshing it from the upstream ISAAC repository with provenance documented.

Authoritative schema:

```text
schema/isaac_record_v1.json
```

Provenance:

```text
schema/PROVENANCE.md
```

Upstream:

```text
https://github.com/ISAAC-DOE/isaac-ai-ready-record
```

---

## 2. Agent Roles

### Fable 5

Fable 5 is the planner, orchestrator, reviewer, verifier, and final judge.

Fable should:

- plan each phase/slice
- define acceptance criteria
- dispatch focused subagents
- review all diffs
- run or verify deterministic checks
- enforce project invariants
- stop at approval gates
- summarize results clearly

Fable should not directly implement large production changes when focused subagents are available.

### Opus Subagents

Opus subagents are preferred for implementation slices unless the user says otherwise.

Use Opus for:

- careful parsing logic
- schema mapping
- export transformations
- data-governance-sensitive logic
- tricky validation behavior
- complex tests
- architecture-sensitive implementation

Each Opus subagent should receive a tight scope and clear acceptance criteria.

Subagent output must be reviewed before acceptance.

### Lighter Subagents

Use lighter subagents only for low-risk mechanical work, such as:

- grep audits
- simple documentation cleanup
- fixture renaming
- repetitive test generation
- dead import cleanup caused by current changes

Do not use lighter subagents for schema/export/truth-path logic unless explicitly approved.

---

## 3. Phase Workflow

Work one approved phase at a time.

Each phase follows:

1. Plan
2. Dispatch focused subagent
3. Review diff
4. Verify
5. Fix/iterate
6. Commit/push only if approved
7. Stop for approval before next phase

Do not run ahead.

Do not begin the next phase without explicit user approval.

Do not broaden the scope of a phase.

---

## 4. Slice Workflow

For every implementation slice:

1. State the slice goal.
2. State the files likely touched.
3. State what must not be touched.
4. Dispatch a focused subagent.
5. Review the diff.
6. Run verification.
7. Report.
8. Continue only if the slice passes.

Every slice must end with a report.

Do not wait until the end of a large phase.

---

## 5. Reporting Requirement

After every implementation slice and every phase, report:

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
- recommendation for next slice/phase

Reports should be specific but concise.

Do not dump full passing logs.

---

## 6. Current Phase State

Current phase:

```text
Phase 3 — XANES draft implementation
```

Current status:

- Phase 3 (Slices 3A + 3B) is COMPLETE, committed, and pushed (`dea4a7a`).
- Deterministic parsers (`extract/structured.py`, `extract/file_listing.py`) and the
  `extract/draft_builder.py` envelope assembler are in place; the synthetic XANES draft
  passes `validate_draft` (25 fields, 0 assets, 5 `pending[]` blockers).
- 60 tests pass. Truth-plane files were not touched.
- Phase 4 (synthetic complete → export → `validate_official` → sidecar → audit-clean) is
  NEXT but NOT yet approved — wait for explicit user approval before starting it.

Before continuing, run:

```bash
git status -sb
git diff --stat
git log --oneline -5
.venv/bin/pytest
```

---

## 7. Truth Plane

The truth plane decides official validity and exportability.

Truth-plane files:

- `schema/isaac_record_v1.json`
- `src/isaac_records/official.py`
- `src/isaac_records/draft_validator.py`
- `src/isaac_records/export.py`
- `src/isaac_records/audit.py`
- `src/isaac_records/cli.py`

Truth-plane rules:

- deterministic only
- Graphify-free
- official schema is authority
- export is gated
- no override
- no guessed values
- all official records validate against v1.05

Do not modify truth-plane files unless the approved phase requires it.

If touched, explain:

- why
- what changed
- what tests cover it
- whether official exported behavior changed

---

## 8. Memory / Query Plane

Graphify is central for memory and query.

Use Graphify for:

- architecture navigation
- project memory
- relationship search
- similar-record lookup
- documentation search
- prior experiment/document queries
- contextual drafting help
- “what changed?” history

Graphify is not truth.

Do not use Graphify to decide:

- validity
- exportability
- required fields
- vocabulary authority
- audit status

If `graphify-out/graph.json` exists, use Graphify before answering architecture/codebase questions.

Suggested commands:

```bash
graphify query "<question>"
graphify explain "<concept>"
graphify path "<A>" "<B>"
```

Never commit `graphify-out/`.

Known caveat: Graphify may have dangling/collapsed semantic edges. Treat graph output as context that must be checked against source/schema/tests.

---

## 9. Draft and Evidence Rules

Drafts may use the assistant envelope:

```json
{
  "value": "...",
  "status": "verified",
  "evidence": []
}
```

Official records may not.

Every non-null finalized draft field must have evidence or user confirmation.

Unsupported values must be:

- missing
- `needs_confirmation`
- asked as a targeted question
- or excluded from official export

Never invent:

- values
- sha256
- URI
- file path
- descriptor result
- uncertainty
- QC status
- timestamp
- scientific interpretation

Absorbing element and edge for the XANES path are implicit/sidecar-only unless a valid official schema path exists.

---

## 10. Data Governance

`examples/` is gitignored and may contain sensitive data.

Never commit:

- real SLAC/SSRL data
- screenshots
- private Excel files
- PDFs
- raw files
- raw file listings
- private notes
- credentials
- tokens
- Graphify outputs

Safe to commit:

- synthetic fixtures that are clearly fake
- public official ISAAC schema/examples with provenance
- docs
- tests
- source code

For phases touching input artifacts, report:

- whether files were synthetic or real
- whether any model/LLM saw the content
- whether anything under `examples/` was staged
- gitignore checks
- git status

If unsure, stop and ask.

---

## 11. Development Commands

Use the virtual environment.

```bash
.venv/bin/pytest
.venv/bin/isaac validate <path> --official
.venv/bin/isaac validate <path> --draft
.venv/bin/isaac export <draft>
.venv/bin/isaac audit
```

Useful git checks:

```bash
git status -sb
git diff --stat
git log --oneline -5
git check-ignore <path>
```

Do not run unrelated web/build/deploy commands. This is a Python prototype, not a Next.js app.

---

## 12. Commit and Push Discipline

Follow the active phase instructions.

General rules:

- review the diff before commit
- run required tests before commit
- verify no sensitive files are staged
- verify generated/private artifacts are ignored
- commit only scoped phase work
- push only if the phase cadence allows it
- stop after the phase and wait for approval

If the user asks to bundle slices into one phase commit, do not commit intermediate slices.

---

## 13. Scope Boundaries

Current MVP:

- single XANES / characterization path
- synthetic artifacts now
- real/sanitized artifacts later only with explicit approval
- official schema validation
- evidence sidecar
- optional Graphify memory/query

Out of scope unless approved:

- performance/electrochemistry domain support
- simulation/theory/derived domain support
- real SLAC/private data processing
- portal validator integration beyond evaluation
- new slash commands
- Graphify as truth layer
- advisory AI review beyond placeholder

---

## 14. Resume Protocol

After interruption:

1. Read `CLAUDE.md`.
2. Read `AGENTS.md`.
3. Run `git status -sb`.
4. Run `git log --oneline -5`.
5. Check latest roadmap/phase docs.
6. Reconcile docs with repo state.
7. Announce verified state.
8. Continue only from verified state.

Never guess or fake progress.