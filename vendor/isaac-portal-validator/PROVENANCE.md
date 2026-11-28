# Vendored upstream portal validator — provenance

The offline portal check (`isaac bundle validate`, `apps/api/isaac_api/local_import/portal.py`) runs the
official ISAAC portal's own `portal/validation.validate_record_full`. The minimum it needs ships here, with the
upstream record contract the skill quotes, so a scientist's install works from this repository alone; nothing is
cloned.

| | |
|---|---|
| Upstream repository | `ISAAC-DOE/isaac-ai-ready-record` (https://github.com/ISAAC-DOE/isaac-ai-ready-record) |
| Commit | `a1cb1c861f3e6eb506da33f27196b43312f240f6` (pinned as `a1cb1c8`; "Merge pull request #288 from changzhiai/fix-manifest", 2026-10-25) |
| Taken from | a clean checkout of that commit (`git status --porcelain` empty), 28 Nov 2026 |
| Modified | **nothing**: every file below is byte-identical to the upstream file at that commit |
| Layout | upstream's relative layout is kept, so `portal/validation.py` finds `../schema` and `../data` as upstream does |

## Files

| Path (under `a1cb1c8/`) | sha256 | Why it is needed |
|---|---|---|
| `portal/validation.py` | `d72ac41d5a60cd3f2ecf0fc453dcbf2b58973eb3426521f0635fdc7545ff44f8` | `validate_record_full` and `outcome` themselves |
| `portal/ontology.py` | `5841f95b36be72ae15ef04c549c1decea77ed39fbf19af245a36ea02b4cd9d8c` | imported by `validation.py` at load time; its `validate_record_vocabulary`, `validate_semantic_integrity` and `load_vocabulary` are the vocabulary and semantic layers |
| `schema/isaac_record_v1.json` | `7e61cb0041b7537ae506ec8561c212e5d849868757f2d4741888ce3b24ef8c20` | read by `validation.py` at import (`SCHEMA_PATH`); also the local export target schema |
| `data/vocabulary.json` | `7d60a2f0383b936ac055c309596e2ba9afe9fb9a1b893fe217f88e7a52b8d0f8` | read by `validation.py` at import (`VOCAB_PATH`) and by `ontology.load_vocabulary` |
| `data/record_contract.json` | `eff30021b0a5c821fcfda924a2a41b6b7ed7f4993b8f45c89b7edf17713d427b` | **not read by validation**: the upstream record contract ("what belongs in a record") that the skill quotes to the scientist (`SKILL.md` rule 7, `reference/records-and-validation.md`) |

`apps/api/isaac_api/local_import/portal.py` holds the same five sha256 values (`VENDORED_SHA256`) and treats
the vendored copy as **unavailable** (never a pass) when any of these five files differs, or when the folder holds
any other file or folder (`__pycache__` and Finder's `.DS_Store` aside): the runner puts `portal/` first on
Python's path, so an extra `portal/validation/__init__.py` or `portal/jsonschema.py` would be imported in place of
the real code. Compiled files are never read from or written to this folder: the runner starts Python with `-B`
and a fresh, empty `-X pycache_prefix`, so a stale or planted `__pycache__/*.pyc` here is ignored.
`scripts/install_portal_validator.sh` checks every row of this table before installing anything.

An older install's full upstream checkout in `~/.cache/isaac/portal-validator/<commit>/src` is **no longer run**:
its `portal/` folder holds some twenty importable modules (`ontology.py` imports `database` when present), so five
hashes could not establish what would execute. Only that install's venv (the packages, no ISAAC code) may still be
used as the interpreter.

`schema/isaac_record_v1.json` here is **byte-identical** to this repository's own `schema/isaac_record_v1.json`
(same sha256), which `schema/PROVENANCE.md` records as taken from the same commit.

## What was left out, and why it is not needed

Measured by reading every import and file read in `validation.py` and `ontology.py`:

- `ontology.py` tries `from database import ...` inside `try/except ImportError`. `portal/database.py` is not
  vendored, so the import fails and the vocabulary comes from `data/vocabulary.json`. In the full checkout the
  import succeeds, but no database is configured (the runner passes only `PATH` and `HOME`), so
  `ontology._use_database()` is `False` there too (measured) and the vocabulary comes from the same file.
- `ontology.py` imports `yaml`, `git` (GitPython) and `requests` at module load. They are used only by the wiki
  sync and term-proposal functions, which `validate_record_full` never calls, but the imports must succeed, so
  the packages are installed (the `portal` extra in `pyproject.toml`). No network call is made.
- `data/record_contract.json` and `data/manifests/` are read only by `portal/api.py` and `portal/discovery.py`
  (the web portal), never by `validation.py` or `ontology.py`. The contract is shipped anyway because the skill
  quotes it; the manifests (the contract's earlier versions) are not.
- Everything else at that commit (the Flask/Streamlit app, slide deck, screenshots, examples, governance docs,
  tests, tools) is not used by validation.

Verified: `validate_record_full` run from this copy and from the full checkout, each in an isolated
interpreter (`python -I`, environment reduced to `PATH`/`HOME`), on 17 synthetic records (14 that pass, 3 that
are rejected) printed byte-identical output.

## Licence

The upstream repository has no licence file at this commit. It belongs to the same organization as this
repository (`ISAAC-DOE`). The project owner (Krish) decided on 28 Nov 2026 to ship this copy with the skill.

## Refreshing to another commit

1. Check out the new upstream commit cleanly (`git status --porcelain` empty).
2. Re-read `portal/validation.py` and `portal/ontology.py` for new imports and file reads; add any file they need,
   keeping the relative layout.
3. Copy the files into `vendor/isaac-portal-validator/<new-short-sha>/`, remove the old folder, and update this
   file (commit, date, file table with new sha256 values).
4. Update `PINNED_COMMIT`, `VENDORED_COMMIT` and `VENDORED_SHA256` in `apps/api/isaac_api/local_import/portal.py`
   and `PIN` in `scripts/install_portal_validator.sh` (it expects at least 5 table rows), and the `portal` extra in `pyproject.toml` if the
   imports changed.
5. Compare the new schema with `schema/isaac_record_v1.json` (see `schema/PROVENANCE.md`), and run the portal
   tests (`apps/api/tests/test_local_import_vendored_portal.py`).
