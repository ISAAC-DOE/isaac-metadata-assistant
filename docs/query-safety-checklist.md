# Query safety checklist

A one-screen checklist — for humans and for Claude — on how to answer a project question safely:
when Graphify helps, when to ignore it, and which deterministic source owns the truth. Full
rationale is in [`graphify-workflow.md`](graphify-workflow.md) and [`query-cookbook.md`](query-cookbook.md);
this page is the quick reference.

## Before using Graphify

- Classify the question first: **truth/policy** (valid · required · complete · vocabulary · warning ·
  real-data) → deterministic source, **skip the graph**. **Memory/navigation** (where is X · how are
  these connected · what's related) → Graphify may help.
- Confirm the graph is usable: `graphify-out/graph.json` exists and `graphify` runs.

## When Graphify is fresh

- Use it for **leads only**. Every node carries `src=<file> loc=L<line>` — open that file and confirm
  before you claim anything.
- Name both sources in your answer (graph lead + the file you verified).

## When Graphify is stale

- Detect with the dependency-free check (from [`graphify-workflow.md`](graphify-workflow.md) §5):

  ```bash
  find README.md CLAUDE.md AGENTS.md pyproject.toml docs schema src scripts tests .claude/skills \
    -type f -not -path '*__pycache__*' -newer graphify-out/graph.json -print -quit
  ```

- Prints nothing → fresh. Prints a path → stale.
- Refresh (`graphify update .`) only when a tracked source changed **and** the answer depends on it.
  Otherwise disclose the caveat and verify the claim against the actual file.
- Never refresh because of `/tmp` output, `.venv`, caches, or `graphify-out/` itself — none are
  tracked source.

## When Graphify is unavailable

- Do **not** fail the task. Answer from the repo directly (grep/read, anchored by
  [`project-memory-map.md`](project-memory-map.md)).
- Say the memory layer was unavailable. **Never fabricate graph output.** Offer to build it.

## Validation questions

- "Is this record valid? / can this draft export?" → `.venv/bin/isaac validate <r> --official` ·
  `isaac export`. **Never Graphify.**

## Audit / evidence questions

- "Which records are complete? do sidecar paths resolve?" → `.venv/bin/isaac audit`. **Never
  Graphify.** A field's evidence lives in `records/<id>.evidence.json`.

## Warning questions

- "What does `NO_LINKS` mean?" → [`portal-warnings.md`](portal-warnings.md) +
  `src/isaac_records/portal_warnings.py`. Advisory / **non-gating** — never an invalidity verdict.

## Real-data questions

- "Can we use / index real data?" → [`data-governance.md`](data-governance.md) + the latest human
  decision. Real or sanitized data needs explicit **written** approval. **Never index real or private
  artifacts** (anything real under `examples/`) into Graphify.

## What not to claim

- Not "valid / invalid / complete" from a graph node — only the CLI decides that.
- Not a scientific value the graph "knows" — missing values stay `pending`, answered by a human,
  never guessed.
- Not that the graph is current without checking — say when it may be stale.
- Not a fabricated graph result when Graphify is absent.

## Truth-check commands

| Question | Command |
|---|---|
| Record valid? | `.venv/bin/isaac validate <record> --official` |
| Draft exportable? | `.venv/bin/isaac export <draft>` |
| Records complete / sidecars resolve? | `.venv/bin/isaac audit` |
| Advisory soft-warnings | `.venv/bin/isaac validate <record> --official --warnings` |
| Graph stale? | the `find … -newer graphify-out/graph.json` check above |
