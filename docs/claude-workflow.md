# Working with the assistant through Claude (operator walkthrough)

**Audience:** reviewers and scientists who want to see *how a person actually uses* the ISAAC
Metadata Assistant — the conversation, not just the code. It is the companion to
[`docs/demo.md`](demo.md): that doc runs the deterministic pipeline from a terminal;
this doc shows the same work happening as a **chat with Claude** driven by five slash skills.

Nothing here changes what is true. Every validity, completeness, and export decision is still
made by the deterministic CLI. The assistant's job is to *drive that CLI, explain its output,
and refuse to guess* — never to decide correctness itself.

---

## 1. The mental model: two planes

The system keeps **what is true** separate from **what we remember**.

| Plane | Owns | Who decides | Tools |
|---|---|---|---|
| **Truth** | Is a record valid? complete? exportable? what value is allowed? | The vendored official ISAAC schema + deterministic validators/export | `isaac validate` · `isaac export` · `isaac audit` |
| **Memory** | Where is this? how is it wired? what's related? what changed? | Graphify (a derived graph) + docs + git | `/isaac-query` → `graphify …`, docs, `git log` |

The assistant may consult memory for context, but **memory can never authorize an export or
override the schema.** If the graph and the schema disagree, the schema wins and the assistant
says so out loud.

## 2. The assistant vs. the CLI

- **The CLI is the source of truth.** `isaac validate`, `isaac export`, and `isaac audit` are
  deterministic, LLM-free, and Graphify-free. Their exit codes are the verdict.
- **The assistant is an operator, not a judge.** It maps messy inputs to the right official
  fields, runs the CLI, reads back the result, and asks *only* the questions the CLI says are
  blocking. It never marks something valid on its own, never fills a value the CLI didn't get
  from a source or from you, and never edits an exported record by hand.

## 3. The five skills at a glance

| Skill | Use it to… | Runs | Assistant must **not**… |
|---|---|---|---|
| `/isaac-draft` | Turn source files into an evidence-tagged **draft** | `build_draft` → `drafts/<name>.draft.json` → `isaac validate` | invent values or a schema path; ask completion questions yet |
| `/isaac-complete` | Answer **only** what blocks export | asks each `pending[]` blocker; `apply_answers` stores replies as evidence | invent a sha256/number; ask optional questions |
| `/isaac-validate` | Check a draft or a record and explain it | `isaac validate [--official] [--warnings]` | soften, add, or overrule findings |
| `/isaac-export` | Finalize a draft into an **official record + sidecar** | `isaac export` (gated twice) | export while blocked; hand-edit the record |
| `/isaac-query` | Ask about records, schema, history, or relationships | routes to schema / audit / git / Graphify | let Graphify decide validity or a missing value |

> There is no `/isaac-audit` skill. Auditing is a pure CLI check — `isaac audit` — that the
> assistant runs directly (see §6).

## 4. What the assistant must never do (the guardrails)

These hold in every skill, every step:

1. **Never guess a scientific value, unit, hash, URI, path, timestamp, or interpretation.** If a
   value isn't in a source and you didn't confirm it, it stays `missing` or `pending`.
2. **Never claim "valid" without having just run the CLI** in this session.
3. **Never let Graphify (or any AI summary) decide validity, required fields, vocabulary, or a
   missing value.** Those are truth-plane questions.
4. **Never hand-edit `records/`.** The only way in is `draft → export`.
5. **Always name the source** of a fact — schema, audit, sidecar, git, or graph — so you can
   check it.

## 5. Scripted walkthrough (what a live demo looks like)

This is the same synthetic XANES case as [`docs/demo.md`](demo.md), told as a conversation. The
numbers (26 fields, 5 blockers, the record id) are the real output of
`scripts/run_synthetic_demo.py`. Data is a **fake year-2099 SSRL session** — no real facility data.

### Step 1 — `/isaac-draft`: extract, don't guess

> **You:** `/isaac-draft` on the campaign sheet and the raw file listing.

The assistant classifies the record (`record_type`, `record_domain`, `source_type`), maps each
value to its **official** JSON-path, and builds the draft deterministically.

> **Assistant (says):** "Built `drafts/xanes.draft.json`: **26 evidenced fields, 0 assets, 5
> blockers**. Each field cites where it came from. Five things I *know are needed but refuse to
> invent* are parked in `pending[]`: three file `sha256`s, the reduced spectrum, and at least one
> descriptor. The draft passes no-guessing validation. Next: `/isaac-complete` to supply those
> five."

What just happened, and what did **not**: the assistant did *not* ask you anything yet, and it
left `assets` empty rather than fabricate hashes.

### Step 2 — `/isaac-validate`: read the draft honestly

> **You:** `/isaac-validate`

> **Assistant:** runs `isaac validate drafts/xanes.draft.json`, shows the report verbatim.
> "Draft OK — no-guessing checks pass. The 5 `pending[]` items are surfaced, not errors: they're
> the exact questions completion will ask. Nothing here is safe to export until they're answered."

### Step 3 — `/isaac-complete`: answer only the blockers

> **You:** `/isaac-complete`

The question set is **exactly** `draft["pending"]` — one question per blocker, verbatim. Nothing
optional, nothing from memory.

> **Assistant (asks, batched):**
> 1. "sha256 of `…/xanes_reduction_v2.ipynb`?"
> 2. "sha256 of `…/CuO2_merged.xdi`?"
> 3. "sha256 of `…/raw/`?"
> 4. "Point me to the reduced spectrum (`.xdi`) so `measurement.series` can be built."
> 5. "Give at least one descriptor (e.g. XANES inflection-point energy + uncertainty)."

You answer (in the demo these come from the committed answers fixture). Each answer is stored as
`user_confirmation` evidence *next to* the deterministic evidence, and the blocker leaves
`pending`. If you say "I don't know," the field stays honest-missing — the assistant will not
fill it.

> **Assistant:** "0 blockers remaining, 3 assets resolved. Ready to `/isaac-export`."

### Step 4 — `/isaac-export`: gated finalization

> **You:** `/isaac-export`

> **Assistant:** runs `isaac export`. "Gated twice — no-guessing checks, then the **official
> v1.05 schema** on the produced record. **PASS.** Wrote
> `records/01JQZ0SYNTHXANESDEMO000000.json` (validates against the official schema) and its
> evidence sidecar `…​.evidence.json`. The official record has no room for per-field provenance,
> so the sidecar maps each official JSON-path back to its source — that's where 'no guessing'
> stays auditable after export. Want me to `git add records/ && commit` this ULID?"

If export were **blocked**, the assistant would show the report and route you back: draft-level
failures → `/isaac-complete`; schema-mapping failures → fix the draft's field paths. There is no
override flag, and the assistant will not invent one.

### Step 5 — advisory warnings (optional, non-gating)

> **You:** `/isaac-validate` the record `--official --warnings`

> **Assistant:** "**PASS** against the official schema (that's the verdict). The `--warnings` flag
> also ran a **local** advisory seam and printed soft-warnings (e.g. `NO_LINKS`). These are
> informational only — they **do not** change validity or block export, and they are **not** the
> full official portal soft tier (that validator isn't vendored here). See
> [`docs/portal-warnings.md`](portal-warnings.md)."

### Step 6 — `/isaac-query`: ask about the record or the project

> **You:** "Which records fail validation or lack a sidecar?" → **truth** → assistant runs
> `isaac audit`, reports from that.
>
> **You:** "Where did this record's beamline come from?" → **truth** → assistant reads the
> record's evidence sidecar.
>
> **You:** "How is `export.py` wired?" / "Which docs explain the sidecar?" → **memory** →
> assistant uses `graphify explain` / `graphify query`, then **cites and opens the file** the
> graph pointed at before trusting it.

The routing rule the assistant follows every time: *valid / required / complete / what-value* →
deterministic source; *where / related / how-connected / what-changed* → Graphify, spot-checked.
Full routing table: [`.claude/skills/isaac-query/SKILL.md`](../.claude/skills/isaac-query/SKILL.md)
and the reviewer demo [`docs/query-demo.md`](query-demo.md).

## 6. How the deterministic CLI stays the source of truth

Everything the assistant "decides" is really the CLI deciding:

- **Validity** is `isaac validate`'s exit code, not the assistant's opinion.
- **Exportability** is `isaac export`'s two gates (no-guessing, then official schema).
- **Completeness / dangling evidence** is `isaac audit` — it re-validates every record against the
  official schema **and** checks that each sidecar evidence entry resolves to a real field
  (`evidence 26/26` = 0 dangling). The assistant runs it and reports its output; it does not
  compute audit results itself.

Because these run offline and never import Graphify, the whole draft → export → validate → audit
path works with the memory plane completely absent.

## 7. Where Graphify and portal warnings fit

- **Graphify (memory):** great for "where / related / how is this wired / what changed"; used by
  `/isaac-query` and, best-effort and non-blocking, by `/isaac-export` to refresh the graph after
  a successful export. If Graphify is missing or fails, the export already succeeded and is never
  rolled back. Graphify is **leads, not answers** — always confirmed against the cited file.
- **Portal warnings (advisory):** `isaac validate --official --warnings` adds non-gating
  soft-warnings *after* the hard schema verdict. Useful as a hint; never a gate. Not upstream
  portal parity.

## 8. See also

- [`docs/demo.md`](demo.md) — the same case as a reproducible **terminal** run with expected output.
- [`docs/architecture.md`](architecture.md) — the pipeline + module map.
- [`docs/query-demo.md`](query-demo.md) — the Graphify memory/query plane for reviewers.
- [`docs/portal-warnings.md`](portal-warnings.md) — the advisory soft-warning seam in detail.
- Skill sources: [`.claude/skills/isaac-*`](../.claude/skills/) — the exact instructions each skill follows.
