# Vendored official ISAAC schema

`isaac_record_v1.json` is copied **verbatim** from the official ISAAC standard and is the
authoritative schema this project validates exported records against. It is not ours to edit.

- **Source:** https://github.com/ISAAC-DOE/isaac-ai-ready-record — `schema/isaac_record_v1.json`
- **Version:** 1.05 (`isaac_record_version` const in the file)
- **Vendored:** 2026-07-06, from branch `main`
- **Why vendored:** hermetic, offline validation and reproducible tests. The official
  validator (`portal/validation.py`) additionally emits a soft-warning tier we do not yet reuse.

## Refresh

```bash
curl -fsSL https://raw.githubusercontent.com/ISAAC-DOE/isaac-ai-ready-record/main/schema/isaac_record_v1.json \
  -o schema/isaac_record_v1.json
.venv/bin/pytest tests/test_official.py   # confirms all vendored examples still validate
```

If the upstream `isaac_record_version` changes, update `EXPECTED_VERSION` in
`src/isaac_records/official.py` and re-vendor the examples in `tests/fixtures/official/`.

The example records under `tests/fixtures/official/` are likewise copied verbatim from the
upstream `examples/` directory and serve as golden must-validate fixtures.
