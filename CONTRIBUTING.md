# Contributing

The ISAAC Metadata Assistant is a research prototype. Contributions should stay **small, scoped, and
verified**. This guide covers local setup, the checks to run, and the repo hygiene rules. The
project's working conventions live in `CLAUDE.md` and `AGENTS.md`; read those before larger work.

---

## Dev setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

That installs the deterministic core plus the `isaac` CLI entry point. Python **3.10+** is required
(`pyproject.toml`). Runtime dependencies are intentionally minimal: `jsonschema`, `python-ulid`,
`openpyxl`. Do not add dependencies for trivial tasks — justify any new one.

## Test

```bash
.venv/bin/pytest -q          # 80 tests: golden records validate, export is gated, core stays Graphify-free
```

Tests are the fast feedback loop and part of the truth plane. Keep them green.

## Run the synthetic demo

```bash
.venv/bin/python scripts/run_synthetic_demo.py                          # build → complete → export
.venv/bin/isaac validate /tmp/isaac-demo/01JQZ0SYNTHXANESDEMO000000.json --official
.venv/bin/isaac audit --records-dir /tmp/isaac-demo
```

The demo regenerates the committed sample (`docs/samples/`) byte-for-byte. See [`docs/demo.md`](docs/demo.md)
for the full walkthrough and [`docs/cli.md`](docs/cli.md) for the command reference.

---

## Repo hygiene

- **No generated or private data in git.** `graphify-out/` and `examples/*` (except its README) are
  gitignored — keep it that way. Never commit real SLAC/SSRL data. See
  [`docs/data-governance.md`](docs/data-governance.md).
- **Records are export-generated.** Do not hand-edit files under `records/`; produce them via
  `isaac export`. Only clearly-synthetic samples (e.g. `docs/samples/`) belong in git.
- **The truth plane stays deterministic and Graphify-free.** `src/isaac_records/`
  (`official`, `draft_validator`, `export`, `audit`, `cli`) must not import Graphify — a test
  enforces this. Graphify and docs are the memory/query plane only.
- **Keep numbers honest.** If you change the test count or CLI behaviour, update the docs that quote
  it (README, `docs/`).

## Commit expectations

- Scope each commit to one logical change; don't mix unrelated work.
- Review `git diff --stat` and the changed files before committing.
- Never stage secrets, private data, `examples/*`, `graphify-out/`, `.venv/`, or caches.
- Run `pytest` before committing anything that touches code.

## Docs update expectations

- Update `README.md` and the relevant `docs/` page when behaviour, commands, or counts change.
- Don't overclaim. If something is a placeholder, a local seam, or synthetic-only, say so.

---

## Adding a future phase safely

This repo is developed **phase-by-phase** with an approval gate between phases (`CLAUDE.md` §10,
`AGENTS.md` §6). For each phase:

1. State the goal, the files likely touched, the files that must **not** be touched, and acceptance
   criteria.
2. Make the smallest correct change; do not broaden scope mid-phase.
3. Run verification: `pytest`, the synthetic demo, and the relevant `isaac` commands.
4. If the truth/export/validation/audit path is touched, say why and what tests cover it.
5. Report changed files, verification results, and data-governance checks.
6. Commit only what the phase authorizes; stop at the gate and wait for approval before the next
   phase.
