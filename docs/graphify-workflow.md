# Graphify workflow (memory / query layer)

**Audience:** anyone operating the repo — how to build, query, refresh, and *safely interpret*
the optional Graphify memory layer.
**Rule that never bends:** Graphify returns **leads, not truth**. The deterministic pipeline and
the official ISAAC schema decide what is valid, exportable, and complete. Graphify only helps a
person find *where* something lives, *how* pieces connect, and *what* to read next.

> This is the operational how-to. For a reviewer-facing narrative demo see
> [`query-demo.md`](query-demo.md); for routed question patterns ("which source owns this
> question?") see [`query-cookbook.md`](query-cookbook.md); for the concept→file map see
> [`project-memory-map.md`](project-memory-map.md).

Graphify is **optional**. This repo does **not** vendor it, and the entire deterministic
record-building pipeline (draft → export → validate → audit) runs correctly with Graphify
entirely absent. If `graphify-out/graph.json` is missing, the memory layer is simply unavailable
— answer deterministic questions normally and offer to build the graph.

---

## 1. What Graphify is for here — and what it must never decide

| Use Graphify for (memory / navigation) | Do **not** use Graphify for (truth / policy) |
|---|---|
| project memory — related docs, records, fixtures | official schema validation → `isaac validate --official` |
| architecture navigation — "how is `export.py` wired?" | export decisions → `isaac export` (doubly gated) |
| "where is X explained / where does it live?" | required fields / vocabulary authority → `schema/isaac_record_v1.json` |
| relationships — "what connects to this module/sample/field?" | audit truth (completeness, sidecar coverage) → `isaac audit` |
| "what changed / how did we get here?" as *context* | filling any missing scientific value (sha256, spectrum, descriptor, edge) → stays `pending`, answered by a human, never guessed |
| documentation and cross-experiment leads | data-governance decisions → [`data-governance.md`](data-governance.md) + the latest human decision |

The truth plane is Graphify-free **by construction** — the test `test_core_never_imports_graphify`
(in `tests/test_export.py`) structurally enforces that export/validation/audit never import
Graphify. If a graph answer ever conflicts with the schema, a validated record, or the audit,
**the deterministic source wins** and the assistant should say so.

---

## 2. Commands (verified in this environment)

`graphify` is a CLI installed **outside** this repo (here at `~/.local/bin/graphify`). Command
availability depends on your local Graphify installation and setup — the repo does not ship it, so
document nothing you have not confirmed with `graphify --help` on your machine. The subcommands
below were verified this way.

| Command | What it does | Flags that matter |
|---|---|---|
| `graphify query "<question>"` | BFS traversal of `graph.json` from semantically-matched start nodes; returns related nodes + edges, each with a source location | `--budget N` (cap output tokens, default 2000), `--graph <path>` (default `graphify-out/graph.json`); also `--dfs`, `--context C` |
| `graphify explain "<node label>"` | Node card: source location, type, community, degree, every connection | `--graph <path>` |
| `graphify path "<A>" "<B>"` | Shortest path between two **exact** node labels | `--graph <path>` |
| `graphify affected "<X>"` | Reverse-impact traversal — which nodes depend on `X` | `--relation R` (repeatable), `--depth N` (default 2), `--graph <path>` |
| `graphify update <path>` | Re-extract changed files and update the graph (manifest-based, **no LLM needed**) | `--force` (overwrite even if the rebuild has fewer nodes) |
| `graphify check-update <path>` | Report whether a semantic re-extraction is pending (cron-safe) | — |

```bash
# Ask where something lives / how it connects (leads, not a prose answer):
graphify query "Where is the evidence sidecar explained?"
graphify query "how is export wired?" --budget 1200

# Inspect one node's wiring (needs an exact node label):
graphify explain "export.py"

# How are two nodes connected?
graphify path "export.py" "official.py"

# What depends on a module?
graphify affected "export.py"

# Point at a graph in a non-default location:
graphify query "..." --graph /path/to/graphify-out/graph.json
```

Refresh is a single command (see §5): `graphify update .`. Do **not** run `update`, `watch`,
`add`, or `extract` as part of answering a question — those rewrite `graphify-out/`; the freshness
policy below says when a refresh is warranted.

---

## 3. What `graphify-out/` contains

Everything under `graphify-out/` is a **derived artifact** rebuilt from the repo's own files:

| File | What it is |
|---|---|
| `graph.json` | the extracted knowledge graph (nodes + edges); what `query`/`explain`/`path`/`affected` read |
| `manifest.json` | per-file bookkeeping — mtime + `ast_hash` + `semantic_hash` for each tracked file; how `update`/`check-update` know what changed |
| `GRAPH_REPORT.md` | human-readable architecture report |
| `graph.html` | interactive graph visualization |
| `cache/` | extraction cache |
| `cost.json` | extraction cost/token bookkeeping |

(Plus internal marker files such as `.graphify_root` / `.graphify_python` / `.graphify_labels.json`.)

---

## 4. Why `graphify-out/` is gitignored and can be sensitive

`graphify-out/` is **gitignored and must never be committed**. Two reasons:

1. **It is derived and machine-specific.** It is regenerated from the source files on demand;
   committing it would add churn and drift, and it is not a source of truth.
2. **A derived artifact inherits the sensitivity of its inputs.** The graph embeds file names,
   code, docstrings, and extracted text from whatever was indexed. If real or private material
   were ever indexed, the graph — and `GRAPH_REPORT.md`, `graph.html`, `cache/` — would contain
   that content and would be **SENSITIVE**, exactly like the raw inputs.

**Current policy:** Graphify operates on the repo's own source, docs, and **synthetic-safe**
fixtures only. Indexing any real or private artifact (e.g. anything real under `examples/`, which
is itself gitignored) requires **explicit approval first** — see [`data-governance.md`](data-governance.md).
Sending real experiment data to an LLM is not allowed by default, and `graphify update` re-extracts
without an LLM, but the resulting graph would still embed whatever it was pointed at.

---

## 5. Freshness policy (smart, not every-request)

The graph is a **point-in-time snapshot**. It can silently go stale after doc/code commits — in
this repo the graph was last built **2026-07-06** while the working tree moved on afterward, so
any sample output in this doc is **illustrative**, not a live read.

**Do not refresh on every request.** Refresh only when it actually helps:

- **Refresh when:** tracked source material changed since the last graph build; after major
  docs/code/schema/skill changes; before an important demo or review.
- **No refresh needed for:** conceptual questions, generated `/tmp` output, `graphify-out/` itself,
  or `.venv`/caches — none of these are tracked source material.

**Tracked source material** (the inputs whose changes should trigger a refresh):
`README.md`, `CLAUDE.md`, `AGENTS.md`, `pyproject.toml`, `docs/`, `schema/`, `src/`, `scripts/`,
`tests/`, `.claude/skills/`.

**Decision procedure on a Graphify-backed request:**

1. If `graphify-out/graph.json` is **missing** → the memory layer is unavailable; build it with
   `graphify update .` (or proceed with deterministic sources only).
2. If tracked sources changed **since** the graph build → refresh with `graphify update .`.
3. If the graph is **fresh** → use it as-is.
4. If **unsure** → say the graph may be stale and verify important claims against the actual files.

### Dependency-free staleness check

Run this from the repo root. It compares tracked source files against the graph's build time and
stops at the first file that is newer:

```bash
find README.md CLAUDE.md AGENTS.md pyproject.toml docs schema src scripts tests .claude/skills \
  -type f -not -path '*__pycache__*' -newer graphify-out/graph.json -print -quit
```

- **Prints nothing** → no tracked file is newer than the graph → the graph is **fresh**; use as-is.
- **Prints a path** → at least that file is newer than the graph → the graph is **stale** → run
  `graphify update .`.

It needs only `find`, no helper script. It assumes `graphify-out/graph.json` exists; if that file
is missing, skip the check and build with `graphify update .` (step 1 above). Verified in this repo
on 2026-07-08: with the graph built 2026-07-06, the command prints a tracked path (a doc newer than
the graph), correctly flagging the graph as stale.

---

## 6. Interpreting output safely

Graphify returns **leads**, not finished answers, and the extraction is lossy. Treat every result
as a pointer to verify:

1. **Read the source locator on each node** — `NODE export.py [src=src/isaac_records/export.py loc=L1 …]`.
   Every lead points at a real file and line.
2. **Open the cited file and confirm** the claim is actually there before stating it.
3. **For truth/policy questions** (valid? required? complete? exportable? what's the roadmap?),
   ignore the graph and run the deterministic check or read the owning doc (see §1 and
   [`query-cookbook.md`](query-cookbook.md)).
4. **If the graph and a deterministic source disagree**, the deterministic source wins — and the
   graph may be stale (see §5).

**Known caveats:**

- **`query` start-node matching is imperfect.** Traversal can start from an adjacent-but-not-exact
  node and surface neighboring results. For example, `graphify query "What does the synthetic demo
  prove?"` in this repo starts from nodes like `provenance` / `review.py` / synthetic fixtures
  rather than landing directly on [`demo.md`](demo.md) — useful leads toward the demo neighborhood,
  but you still open [`demo.md`](demo.md) to get the actual answer.
- **`explain` / `path` need an exact node label** (a file, function, or extracted entity), not a
  free-text concept. `graphify explain "no-guessing policy"` returns *"No node matching …"*. For
  concept questions, use `query`, or read the doc directly.
- **Dangling / collapsed semantic edges.** The graph can contain edges collapsed or dropped from an
  AST/semantic ID mismatch (see the caveat in `CLAUDE.md` §7). Spot-check important edges against
  the source.
- **Output is budget-capped.** `query` truncates at `--budget` tokens (default 2000) and tells you
  when nodes were cut; narrow the question or raise the budget rather than trusting a truncated view.

### Illustrative node card (from the 2026-07-06 graph — verify against source)

```text
$ graphify explain "export.py"
Node: export.py   Source: src/isaac_records/export.py L1   Type: code   Community: 14   Degree: 22
  <-- cli.py [imports_from]        --> validate_official() [imports]
  <-- audit.py [imports_from]      --> official.py [imports_from]
  --> transform() [contains]       --> draft_validator.py [imports_from]
  --> export_draft() [contains]    --> validate_draft() [imports]
  --> build_sidecar() [contains]   ... and more

$ graphify path "export.py" "official.py"
Shortest path (1 hops):
  export.py --imports_from [EXTRACTED]--> official.py
```

That card shows the truth-plane wiring at a glance — `cli.py` and `audit.py` call into `export.py`,
and `export.py` gates on `validate_official` + `validate_draft` — but it is a **lead**: open
`src/isaac_records/export.py` to confirm before relying on it.

---

*Reviewer demo of these commands:* [`query-demo.md`](query-demo.md). *Which source owns which
question:* [`query-cookbook.md`](query-cookbook.md). *Concept → file map:*
[`project-memory-map.md`](project-memory-map.md).
