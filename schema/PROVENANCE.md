# Vendored official ISAAC schema

`isaac_record_v1.json` is copied **verbatim** from the official ISAAC standard and is the
authoritative schema this project validates exported records against. It is not ours to edit.

- **Source:** https://github.com/ISAAC-DOE/isaac-ai-ready-record — `schema/isaac_record_v1.json`
- **Commit:** `a1cb1c861f3e6eb506da33f27196b43312f240f6` (short `a1cb1c8`, 2026-10-25, "Merge pull
  request #288 from changzhiai/fix-manifest")
- **Git blob of the file at that commit:** `4a92cfa27f062a6ed7608efb20a37f56abe2d6ea`
  (re-derive with `git hash-object schema/isaac_record_v1.json`)
- **Version:** 1.05 (`isaac_record_version` const in the file; unchanged from the previous vendoring)
- **Vendored:** 2026-11-16 (previously 2026-07-06 from branch `main`, git blob
  `4dac85c7f78a1bebc6a3b028e71d11208ab94618`)
- **Why this commit:** it is the commit the local import pins for the offline portal check
  (`apps/api/isaac_api/local_import/portal.PINNED_COMMIT`) and the one the portal vocabulary
  snapshot was taken at (`apps/api/isaac_api/data/PORTAL_VOCABULARY_PROVENANCE.md`). The website,
  the skill's pinned validator and the portal therefore validate against the same schema document.
  Approved by the project owner on 2026-11-16.
- **Why vendored:** hermetic, offline validation and reproducible tests. The official
  validator (`portal/validation.py`) additionally emits a soft-warning tier we do not yet reuse.

## What changed from the July vendoring

The newer document is a strict superset of the July one (same `isaac_record_version`, 1.05):
no field path removed, and 57 added by a walk of `properties` / `items` / `allOf` / `if` /
`then` (274 → 331 paths; the count depends on the walk, so re-derive rather than quote it), for
example `attribution.produced_by`, `context.temperature_basis`, `context.modulation`,
`context.reaction`, `system.session` and `descriptors.outputs[].completeness`. Three existing
constraints are widened:

- `context.temperature_K` is `number | null`; a `context.allOf` rule requires
  `temperature_basis: not_reported` when it is null (and null when the basis is `not_reported`);
- `context.electrochemistry.cell_type` gains `not_reported`;
- `system.technique` gains 8 values (37 → 45).

Every record valid under the July document stays valid under this one.

## How it was obtained

The upstream repository was not reachable from this machine on 2026-11-16 (GitHub returned 404
for it), so the file was taken from the pinned clone that `scripts/install_portal_validator.sh`
lays out (`~/.cache/isaac/portal-validator/a1cb1c8/src`), after checking that the clone's `HEAD`
is the commit above, that `git fsck --full` reports no corruption, and that the working-tree file is
byte-identical to the commit's blob (`git cat-file -p HEAD:schema/isaac_record_v1.json | cmp -`).
A git blob id is a content hash, so the blob id above identifies the exact bytes upstream holds at
that commit.

## Refresh

```bash
COMMIT=<full upstream sha>
curl -fsSL https://raw.githubusercontent.com/ISAAC-DOE/isaac-ai-ready-record/$COMMIT/schema/isaac_record_v1.json \
  -o schema/isaac_record_v1.json
.venv/bin/pytest tests/test_official.py   # confirms all vendored examples still validate
```

Pin a commit, not a branch, and keep it the same commit as `local_import/portal.PINNED_COMMIT`
so the website and the portal check validate against one document.

If the upstream `isaac_record_version` changes, update `EXPECTED_VERSION` in
`src/isaac_records/official.py` and re-vendor the examples in `tests/fixtures/official/`.

The example records under `tests/fixtures/official/` are likewise copied verbatim from the
upstream `examples/` directory at the same commit (14 files at `a1cb1c8`; the July vendoring had
10) and serve as golden must-validate fixtures.
