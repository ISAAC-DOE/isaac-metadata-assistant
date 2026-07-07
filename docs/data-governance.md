# Data governance

**Synthetic only by default. Never commit real or private experimental data.**

This prototype was built for a domain — synchrotron beamline metadata (SLAC/SSRL) — with real data
governance obligations. The repository is deliberately structured so that a demo can be run, tested,
and reviewed end-to-end **without any real data ever entering git or an LLM**. This document is the
authoritative statement of those rules for contributors and reviewers. The project instructions
(`CLAUDE.md` §6, `AGENTS.md` §10) are the upstream source; this page restates them for GitHub
readers.

---

## Synthetic data is the safe default

The committed demo uses **synthetic** XANES-style metadata: a fake **year-2099** CuO / Cu K-edge
session. The year-2099 session date is intentional — it makes the data unmistakably not real. Every
scientific value in the demo traces to a committed synthetic fixture; nothing is guessed by the
system, and no real SLAC/SSRL data is involved.

Synthetic, safe-to-commit assets:

- `tests/fixtures/synthetic/` — the mock campaign sheet, raw scan listing, and simulated
  human-completion answers that drive the demo.
- `docs/samples/` — the committed official record + evidence sidecar produced by the demo.
- `tests/fixtures/official/` — the official ISAAC golden example records, copied verbatim from the
  public upstream standard (public, provenance-documented — see `schema/PROVENANCE.md`).

To generate more fake artifacts locally, run `python scripts/make_synthetic_examples.py`; it
populates `examples/` with clearly-synthetic mock artifacts.

---

## Real data must never be committed

Real SLAC/SSRL artifacts and any private data must stay out of git. This includes:

- real experiment spreadsheets (Excel campaign/configuration/file-list sheets)
- beamline web-form screenshots
- narrative or proposal PDFs
- raw data files and **raw file listings** (e.g. `ls -R` output of a real campaign folder)
- private notes, internal identifiers, or any personally/institutionally sensitive content
- secrets, API keys, credentials, tokens, `.env` files, production dumps

If you are unsure whether a file is safe to commit, **stop and ask the project owner** before
staging it.

---

## `examples/` policy

`examples/` is where **real** input artifacts go when someone runs the assistant on actual data. It
is gitignored by design:

```gitignore
examples/*
!examples/README.md
```

Everything under `examples/` is ignored **except** `examples/README.md`. Real artifacts placed here
stay local and are never committed. `/isaac-draft` reads from this directory; extraction evidence
cites these files by name and locator, so filenames matter — but the files themselves never leave
your machine through git.

> Note: `git check-ignore examples/` returns nothing because the *directory* is not ignored — the
> pattern ignores its *contents* (`examples/*`). Verify a specific file with
> `git check-ignore examples/<file>`.

---

## `graphify-out/` policy

`graphify-out/` is a **derived** knowledge graph rebuilt from the repo. It is gitignored and must
never be committed. It is part of the memory/query plane, never the truth plane — it can be deleted
and regenerated at any time and never decides record validity.

---

## What may and may not be committed

| May commit | Must **not** commit |
|---|---|
| Synthetic fixtures (clearly fake) | Real experiment data of any kind |
| The committed synthetic sample under `docs/samples/` | Real records or real evidence sidecars |
| The public official schema + golden examples (with provenance) | Private spreadsheets, screenshots, PDFs, raw data, raw file listings |
| Source code, tests, docs | Secrets, keys, credentials, tokens, `.env` |
| `pyproject.toml`, config | `graphify-out/`, `examples/*` (except its README), `.venv/`, caches |

---

## LLM / Claude use on real data

**Sending real or private artifacts to an LLM (including Claude) is not allowed by default.** The
deterministic core (`isaac validate` / `export` / `audit`) is LLM-free and can process data with no
model involvement. The Claude authoring skills are an assistant layer; using them on real artifacts
means real data is read by a model, which requires explicit approval first.

Real or sanitized data may only be used — in git, in an LLM, or in any external service — with
**explicit written approval** from the project owner. When a task does touch input artifacts, report:
what files were read, whether they were synthetic or real, whether any model saw the content,
whether anything under `examples/` was staged, `git status --short`, and relevant `git check-ignore`
results.

---

## Evidence sidecar caution

The evidence sidecar (`records/<ULID>.evidence.json`) is a traceability artifact: it maps official
JSON-paths to their **source** — file names, sheet/cell or page locators, URIs, and sha256 hashes.
For the synthetic demo this is all fake and safe. **If real data is ever used, the sidecar can
contain identifying provenance** (real file paths, archive URIs, hashes). Review any sidecar built
from real data before sharing it, and treat it with the same governance as the underlying artifacts.

---

## If sensitive data is committed by accident

See [`../SECURITY.md`](../SECURITY.md). In short: do not simply delete it in a new commit (the
history still contains it). Notify the project owner immediately, rotate any exposed secrets, and
coordinate a history rewrite before the branch is shared or pushed.
