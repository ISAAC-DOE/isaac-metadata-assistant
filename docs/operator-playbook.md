# Operator playbook

For a technical user or a Claude-assisted operator who wants the shortest **safe** route from
files to an official ISAAC record. This page is a practical fast-path; deep dives live in the
linked docs — read those before relying on any one command in a real review.

---

## 1. What you're trying to do

Turn safe/synthetic experiment metadata into a schema-valid **official ISAAC v1.05 record** plus
an **evidence sidecar**, without guessing. The invariant that governs everything below: **the
deterministic CLI decides validity and exportability — Claude and Graphify never do.** Anything a
source doesn't support stays `missing`/`pending`, never invented. See
[`architecture.md`](architecture.md) for the full pipeline + module map.

## 2. One-command synthetic demo (start here)

Reproduces build → complete → export → validate → audit on committed fake fixtures, and
regenerates the committed sample record byte-for-byte:

```bash
.venv/bin/python scripts/run_synthetic_demo.py
.venv/bin/isaac validate /tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.json --official
.venv/bin/isaac audit --records-dir /tmp/isaac-demo
```

Validate the `.json` record, not the `.evidence.json` sidecar — the sidecar is an assistant
artifact and will fail official validation. Full walkthrough + expected output:
[`demo.md`](demo.md).

## 3. Manual CLI workflow

Honesty note: there is **no** `isaac draft` or `isaac complete` subcommand. Drafting and
completing are authoring steps — done via the Claude skills, the demo driver, or by editing
`drafts/<name>.draft.json` directly. The CLI owns validate/export/audit:

```bash
.venv/bin/isaac validate drafts/<name>.draft.json --draft   # no-guessing check, surfaces pending[] blockers
.venv/bin/isaac export drafts/<name>.draft.json             # doubly gated: no-guessing, then official schema
.venv/bin/isaac validate records/<ULID>.json --official
.venv/bin/isaac audit                                       # official re-validation + sidecar coverage
```

Never hand-edit `records/` — it is immutable via the CLI; re-export from the draft instead. Full
reference: [`cli.md`](cli.md).

## 4. Claude-assisted workflow

Pipeline order: `/isaac-draft` → `/isaac-validate` → `/isaac-complete` → `/isaac-export` →
`/isaac-validate --official --warnings` → `isaac audit` (direct CLI — there is no `/isaac-audit`
skill). The skills drive the same CLI underneath; they never mark something valid on their own and
never invent a value. Full scripted walkthrough: [`claude-workflow.md`](claude-workflow.md).

## 5. Which skill/tool when

| Situation | Use |
|---|---|
| Have source files, want a draft | `/isaac-draft` |
| Draft has open `pending[]` blockers | `/isaac-complete` |
| "Is this valid?" (draft or record) | `/isaac-validate` or `isaac validate` |
| Finalize draft → official record + sidecar | `/isaac-export` or `isaac export` |
| "Which records fail / lack a sidecar?" | `isaac audit` (direct CLI) |
| "Where does X live / what's related?" | `/isaac-query` → Graphify leads, then open the file |
| Fresh ULID | `isaac new-id` |

Rule of thumb: truth questions → CLI/schema; navigation questions → Graphify; scripted UX →
skills.

## 6. Validation, audit, and warnings

Three signals, three different jobs — don't conflate them:

- **PASS/FAIL** from `isaac validate --official` is the deterministic verdict, and it's the same
  gate that decides export.
- **`evidence N/N`** from `isaac audit` is sidecar coverage (every evidence path resolves to a
  real field) — not a re-vote on validity.
- **`⚠ [CODE]` lines** from `--warnings` are advisory, non-gating, and never block export.

Caveat: absence of local warnings is **not** upstream portal sign-off — the real
`portal/validation.py` is not vendored here. See [`cli.md`](cli.md) and
[`portal-warnings.md`](portal-warnings.md).

## 7. Graphify / query flow

Memory/navigation only — never truth. Check freshness before trusting a graph answer:

```bash
python scripts/check_graphify_freshness.py        # from the repo root
```

Prints exactly one of `fresh` / `stale` / `missing` and exits `0`/`1`/`2`. Or, dependency-free
(copied verbatim from [`graphify-workflow.md`](graphify-workflow.md) so the two stay identical):

```bash
find README.md CLAUDE.md AGENTS.md pyproject.toml docs schema src scripts tests .claude/skills \
  -type f -not -path '*__pycache__*' -newer graphify-out/graph.json -print -quit
```

Refresh with `graphify update .` only when a tracked source changed **and** the answer depends on
it — not for every request. Graceful degradation: if the graph is missing, stale, or the CLI
errors, answer from the files directly, say the memory layer was unavailable, and never fabricate
graph output. Details: [`graphify-workflow.md`](graphify-workflow.md) and
[`query-safety-checklist.md`](query-safety-checklist.md).

## 8. Missing fields / completion

Blockers come only from `draft["pending"]` — nothing optional, nothing from memory. Every answer
is stored as `user_confirmation` evidence next to the deterministic evidence. "I don't know" leaves
the field honestly missing; never fabricate a sha256, URI, number, or descriptor value. For enum
fields, present the allowed values straight from `schema/isaac_record_v1.json`.

## 9. What not to do

- Never guess a scientific value, unit, hash, URI, path, timestamp, or interpretation.
- Graphify is not a validator — it never decides validity, required fields, vocabulary, or a
  missing value.
- Never hand-edit `records/`.
- Never claim "valid" without having just run the CLI in this session.
- Always name your source (schema, audit, sidecar, git, or graph) so it can be checked.

## 10. Real data

Synthetic-only by default. Real or sanitized SLAC/SSRL artifacts, or any private data, require
**explicit written data-governance approval** naming the artifacts and the boundary before they
touch git, an LLM, or any external service. Never index real or private data into Graphify.
`examples/` is gitignored and treated as sensitive. Full rules:
[`data-governance.md`](data-governance.md).

## 11. Troubleshooting

- **Schema-root error / exit 2.** Run from inside the repo, or pass `--root <path>`.
- **Accidentally validated the `.evidence.json` sidecar.** Validate the `.json` record instead —
  the sidecar is not an official record.
- **Export fails official validation.** Fix the draft's `fields` paths and re-export; there is no
  override flag.
- **"Record already exists."** Records are immutable — use a new ULID or `--records-dir`.
- **Graph stale/missing, or `graphify` CLI absent.** Run the freshness helper (§7); answer from the
  files directly.
- **Audit failures.** Re-export from the corrected draft; do not hand-edit `records/`.

## 12. Current limitations

Single XANES / characterization path; synthetic data only. No upstream portal parity — only a
local, non-gating advisory seam. No web UI, no MCP server, no electrochemistry/performance domain
yet. License pending. See the [`../README.md`](../README.md) status section and
[`mentor-decisions.md`](mentor-decisions.md) for the open decisions that gate what comes next.
