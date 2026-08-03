# Validator upload QA package

Eighteen record files for exercising the **Standalone Validator**
(Governance & Safety → Validator tab → *Upload JSON File*), which posts the raw body to
`POST /api/validate/record` and renders the official-schema verdict.

Two audiences, three documents:

| File | Audience | Contents |
|---|---|---|
| `UPLOAD-GUIDE.md` | the person doing the QA run | per-file: what to do, expected verdict, expected visible issue, repair action |
| `MANIFEST.json` | machine-readable | per-file schema paths, intended outcome, **measured** validator result, expected HTTP status |
| `ENGINEERING-NOTES.md` | engineering | provenance, every substitution made, every expected-vs-measured divergence, commands run |
| `isaac-validator-qa-files.zip` | download convenience | the 18 files + guide + manifest. Deliberately **excludes** `ENGINEERING-NOTES.md` and this README, which are internal |

## What these files are

Generated QA fixtures. They were written by hand against
[`schema/isaac_record_v1.json`](../../schema/isaac_record_v1.json) — the official ISAAC v1.05 schema,
vendored verbatim from public upstream (see [`schema/PROVENANCE.md`](../../schema/PROVENANCE.md)) —
using [`tests/fixtures/official/ex_situ_xanes_cuo2_record.json`](../../tests/fixtures/official/ex_situ_xanes_cuo2_record.json)
as a **shape** reference. That file is likewise a verbatim copy of a public upstream example.

Nothing here is derived from the 30 production-derived records in the SLAC test database. No database
connection was opened while producing them. No field-presence pattern, missingness pattern, title,
value, or attribution was taken from that corpus. Every value is illustrative and each record says so
in its own `notes`. The optional `attribution` block is omitted from all eighteen files, so no person
or account is named.

These are not, and must not be presented as, user-created records or real measurements.

## Two files are expected to PASS when their names say they should not

This is the point of the package, not a mistake in it.

- **`invalid-date-time.json`** — a required `timestamps.created_utc` of `not-a-date`. The official
  validator does not enforce JSON Schema `format`, for two independent reasons: `official.py` builds
  its validator with no `format_checker`, **and** `date-time` is not in the installed checker registry
  (`jsonschema` is pinned without the `format` extra, so `rfc3339-validator` is absent). Arming only
  one of the two changes nothing. Measured verdict: **PASS, 0 errors**.
- **`empty-measurement-series.json`** — `measurement.series` present and empty. The entire v1.05
  schema declares exactly one `minItems` (on `uncertainty.bounds`), so no other array has a minimum
  length. Measured verdict: **PASS, 0 errors**.

Both are kept unaltered as evidence. Neither was "fixed" by injecting a second defect, which would
have destroyed its diagnostic value. `MANIFEST.json` records them with
`measured_matches_intent: false`.

The related third case is documented in `ENGINEERING-NOTES.md` and is **not** one of the eighteen
files: `measurement.qc.evidence` carries the schema description *"REQUIRED in practice when
status != valid"*, but `qc.required` lists only `status` — so a record may declare its own data
`failed`, give no reason, and validate clean.

## Reproducing the measured results

```bash
.venv/bin/isaac validate qa/validator-upload-package/complete-valid-record.json --official   # exit 0
.venv/bin/isaac validate qa/validator-upload-package/repairable-record.json    --official   # exit 1
```
