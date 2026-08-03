# Engineering notes — Standalone Validator upload package

Internal. Fully truthful, including where the package does not do what its filenames imply.

## 1. What these files are

18 hand-generated QA fixtures for the app's Standalone Validator
(Governance & Safety → Validator → *Upload JSON File* / paste box → `POST /api/validate/record`).

They are **generated test fixtures**, not records. They were produced by a short script from two
inputs and nothing else:

- `schema/isaac_record_v1.json` — the vendored official ISAAC v1.05 schema, verbatim from public
  upstream (`schema/PROVENANCE.md`).
- `tests/fixtures/official/*.json` — the 10 public upstream example records, verbatim from the public
  upstream `examples/` directory (same provenance file). Only
  `ex_situ_xanes_cuo2_record.json` was read closely, as a shape reference for a characterization
  record.

**Data boundary: none.** No database connection was opened at any point while producing this package.
Nothing was read from, derived from, or informed by any production or production-derived record store.
Field *names* come from the public schema; every field *value* was written by hand here. No
field-presence or missingness pattern was copied from anywhere — the presence patterns are the
deliberate defect injections listed in §4.

Two deliberate content decisions, both governance-driven:

- The optional `attribution` block is **omitted from all 18 files**, so no person, group, ORCID or
  account is named as the origin of any value.
- Every record carries, in `sample.material.notes` and `measurement.qc.notes`, the sentence
  *"Constructed by hand for validator exercise. Values are illustrative and carry no measurement
  provenance."* Values are physically reasonable for a Cu K edge (edge at ~8979 eV, arctangent step
  plus a white line and damped oscillations above the edge) but assert no measurement.
- Vocabulary constraint honoured: the strings `synthetic`, `demo`, `fixture`, `test data`, `mock`,
  `fake`, `sample data`, `dummy`, `scenario`, `seeded` appear in **no** record JSON and in **no**
  filename in the package. Verified:
  ```
  cd <qa-package> && grep -rniE "synthetic|demo|fixture|test data|mock|fake|sample data|dummy|scenario|seeded" .
  # exit 1 — no matches
  ```
  (Those words appear only in this engineering file, as prose about the package.)

## 2. Commands actually run

Schema inspection (Draft 2020-12 structure, conditionals, closed objects, `minItems`):

```
cd /Users/krishverma/Documents/ISAAC
.venv/bin/python -c "import json; s=json.load(open('schema/isaac_record_v1.json')); print(list(s.keys())); print(s['required']); print(s['additionalProperties'])"
.venv/bin/python -c "import json; s=json.load(open('schema/isaac_record_v1.json')); [print(json.dumps(a,indent=1)) for a in s['allOf']]"
# plus a recursive walk printing every object schema and whether additionalProperties is false,
# and every minItems / minLength / minProperties occurrence
```

Generation, then verification of all 17 JSON files against the repository's own official validator:

```
.venv/bin/python <scratchpad>/gen.py        # writes the 18 files
.venv/bin/python <scratchpad>/verify.py     # loops the *.json files through validate_official
```

`verify.py` uses exactly the call the task specified, unmodified — `validate_official`'s signature is
`validate_official(record: dict, root: Path) -> OfficialReport`, matching the task's snippet, so no
adaptation was needed. The literal single-file form was also run and is reproducible:

```
cd /Users/krishverma/Documents/ISAAC
.venv/bin/python -c "
import json,sys
from pathlib import Path
from isaac_records.official import validate_official
p=Path(sys.argv[1]); rec=json.loads(p.read_text())
r=validate_official(rec, Path('.'))
print(p.name, 'OK' if r.ok else 'FAIL')
print(r.render())
" <file>
```

Independent cross-check through the CLI on two files, confirming the same verdict and the expected
exit codes:

```
.venv/bin/isaac validate <qa-package>/complete-valid-record.json --official   # PASS, exit 0
.venv/bin/isaac validate <qa-package>/repairable-record.json    --official   # FAIL 1 error, exit 1
```

Route/contract inspection (read only, nothing started):

```
grep -rn "MAX_VALIDATE_RECORD_BYTES\|validate/record" apps/api/isaac_api/*.py
# apps/api/isaac_api/routes.py:1617 MAX_VALIDATE_RECORD_BYTES = 512 * 1024
# apps/api/isaac_api/routes.py:1620 @router.post("/validate/record")
# read routes.py:1384-1403 (_read_bounded_body) and 1653-1705 (post_validate_record)
# read apps/web/src/components/RecordValidator.tsx and apps/web/src/components/VerdictCard.tsx
# read apps/web/src/lib/api.ts:449-461 (validateRecord)
```

Format-enforcement diagnosis:

```
.venv/bin/python -c "from jsonschema import FormatChecker; print(sorted(FormatChecker().checkers))"
# ['date','email','idn-email','idn-hostname','ipv4','ipv6','regex','time','uuid']  -> no 'date-time'
.venv/bin/python -c "import importlib.util; print(importlib.util.find_spec('rfc3339_validator'))"
# None
```

## 3. Substitutions — where the official schema lacks the concept the filename implies

### 3.1 `missing-evidence.json`

**The official schema has no per-field evidence requirement, and no per-field evidence envelope at
all.** A full recursive walk of the schema finds no `evidence` construct attached to a value. The
`{value, status, evidence}` envelope is a draft-layer construct in this project, and field-level
evidence is carried in a separate evidence sidecar (`records/<ULID>.evidence.json`) precisely because
the official record cannot hold it.

**Substitution:** the nearest structure the official schema *does* require alongside an asserted
value is `uncertainty`, which sits in the same `required` list as `value` at
`/properties/descriptors/properties/outputs/items/properties/descriptors/items/required`
(`["name","kind","source","value","uncertainty"]`), and whose `basis` sub-field records provenance
(`reported` / `digitization_estimate` / `assumed` / `not_reported`). The file keeps the descriptor's
`value` (8979.4 eV) and removes its `uncertainty` block. Measured: FAIL, 1 error,
`descriptors.outputs.0.descriptors.0 — 'uncertainty' is a required property`.

**Related finding, deliberately NOT used as the defect.** The schema's own description of
`measurement.qc.evidence` says it is *"REQUIRED in practice when status != valid"*. That is prose
only. Measured directly:

```
qc = {"status": "compromised"}   # no evidence
-> PASS
```

So the one field in the whole schema literally named `evidence` is unenforced whenever it matters
most. Worth raising separately; it is not what this file tests, because a file that passes would not
have exercised the "evidence missing ⇒ FAIL" path the filename promises.

### 3.2 `missing-confirmation.json`

**The official schema has no "confirmation" concept.** Nothing in it is named `confirm`, `confirmed`
or `confirmation`. `needs_confirmation` and user-confirmation requests are draft-layer constructs in
this project, not official-record constructs.

**Substitution:** the closest real official construct is `measurement.qc.status` — the record's
required affirmation of its own quality state, enum
`["valid","compromised","failed","pending"]` at
`/properties/measurement/properties/qc/properties/status`. The file leaves the `qc` block present
with its `evidence` and `notes` and removes only the required `status`. Measured: FAIL, 1 error,
`measurement.qc — 'status' is a required property`.

### 3.3 No substitution needed for `missing-conditional-information.json`

A real conditional exists and was used. Enumerated from the schema:

- **Four top-level `if`/`then` conditionals**, `/allOf/0` … `/allOf/3`.
  - `/allOf/0` — `if record_type == "evidence"` ⇒ `then required: ["descriptors"]`. **This is the one
    exercised.**
  - `/allOf/1` — `record_domain == "performance"` with `context.electrochemistry` ⇒
    `electrochemistry.control_mode` required.
  - `/allOf/2` — `control_mode == "galvanostatic"` ⇒ `current_setpoint_mA_cm2` required.
  - `/allOf/3` — `control_mode == "potentiostatic"` ⇒ `potential_setpoint_V` required.
- **Three further nested conditionals** at
  `/properties/context/properties/electrochemistry/properties/potential_vs_RHE/allOf/0..2`.
- **No `dependentRequired` anywhere** in the schema.
- **Exactly one `oneOf`**, at
  `/properties/descriptors/properties/outputs/items/properties/descriptors/items/properties/relative_to/oneOf`
  — a string-or-object choice, not a required-field branch.
- **No `anyOf`** anywhere.

Every conditional except `/allOf/0` is electrochemistry-specific and therefore unreachable from a
characterization record, so `/allOf/0` is not a convenience choice — it is the only conditional this
record shape can trigger.

### 3.4 `unknown-field.json` — closed-path claim verified, not assumed

The extra property is placed at `sample.material`, and
`/properties/sample/properties/material/additionalProperties` is `false` — verified by the recursive
walk, not inferred. For the record, the schema is closed at 37 object positions (measured), including the
document root, `timestamps`, `sample`, `sample.material`, `system`, `system.facility`,
`system.instrument`, `context`, `measurement`, `measurement.qc`, every `series` / `channels` /
`independent_variables` item, every `assets` item, every `links` item, `descriptors`, every descriptor
item, `uncertainty`, `at`, `generated_by`, `computation` and `attribution`.

The deliberately **open** namespaces — where an extra key would have made the file vacuous — are
`system.configuration`, `sample.composition`, `sample.geometry`, `sample.library`,
`context.thermodynamics`, `context.simulation_assumptions`, `measurement.processing`,
`measurement.processing.recipe_link`, `measurement.series[].conditions`, `assets[].citation` and
`assets[].caption_highlights`. Note that `measurement.processing` is open *and* the schema says so in
prose ("block intentionally not locked yet"), so an unknown key there is currently accepted by design.

### 3.5 Class overlap between files 9 and 18, stated rather than hidden

`invalid-controlled-value.json` (enum violation at `system.technique`) and `repairable-record.json`
(enum violation at `measurement.qc.status`) share a defect class. This is intentional: file 9 is the
diagnosis case with the full 37-value vocabulary dumped into the error message, file 18 is the
repair-loop case chosen for the shortest possible correct hand edit (`OK` → `valid`). If a
distinct-class repairable file is wanted later, the natural candidate is the `record_id` ULID pattern
`^[0-9A-Z]{26}$` (lowercase → uppercase), which was rejected here only because it makes the human
retype 26 characters.

## 4. Defect injection map

Each file is `complete-valid-record.json` with the listed change and a distinct `record_id`.

| # | File | Change |
|---|---|---|
| 1 | `complete-valid-record.json` | baseline, none |
| 2 | `missing-required-information.json` | delete top-level `source_type` |
| 3 | `missing-nested-information.json` | delete `timestamps.created_utc` |
| 4 | `missing-conditional-information.json` | delete `descriptors` (record_type stays `evidence`) |
| 5 | `invalid-date-time.json` | `timestamps.created_utc = "not-a-date"` |
| 6 | `empty-measurement-series.json` | `measurement.series = []` |
| 7 | `missing-evidence.json` | delete `descriptors.outputs[0].descriptors[0].uncertainty` |
| 8 | `missing-confirmation.json` | delete `measurement.qc.status` |
| 9 | `invalid-controlled-value.json` | `system.technique = "XANES"` |
| 10 | `invalid-field-type.json` | `context.temperature_K = "297.5"` (string) |
| 11 | `unknown-field.json` | add `sample.material.purity_percent = 99.99` |
| 12 | `multiple-issues.json` | delete `record_domain`; `context.temperature_K = "ambient"`; add `system.instrument.serial_number` |
| 13 | `unicode-and-escaping.json` | free-text fields + `tags` rewritten with non-ASCII and escapes; written UTF-8, `ensure_ascii=False` |
| 14 | `large-valid-record.json` | `measurement.series` replaced with 2600 points × (1 independent variable + 2 channels) |
| 15 | `malformed-json.json` | file 1 truncated mid-`measurement`, brackets left open |
| 16 | `unsupported-file.txt` | plain text, not JSON |
| 17 | `duplicate-of-complete-valid-record.json` | `shutil.copyfile` of file 1 — byte-identical, same `record_id` |
| 18 | `repairable-record.json` | `measurement.qc.status = "OK"` |

`multiple-issues.json` is exactly 3 errors, verified. Removing `record_domain` also makes `/allOf/1`'s
`if` fail, so no conditional error is added and the count does not drift to 4.

## 5. Expected vs. measured divergences

Two files pass when their filename says they should fail. Both were predicted, both are confirmed, and
**neither was "fixed"**: adding a second, unrelated defect to force a red card would destroy exactly
the diagnostic value the file exists for. They are kept as evidence of a gap.

### 5.1 `invalid-date-time.json` — intended FAIL, measured **PASS**

`timestamps.created_utc` is required and declared `"format": "date-time"`; it carries `"not-a-date"`
and validates clean. **Two independent causes, both verified:**

1. `validate_official` builds `Draft202012Validator(json.loads(...))` with **no** `format_checker`
   (`src/isaac_records/official.py:64-66`). Under JSON Schema 2020-12, `format` is an annotation and
   asserts nothing unless a checker is supplied. Correct per spec; the record is still nonsense.
2. Even *with* a checker it would still pass in this environment. `FormatChecker()` here registers
   `date, email, idn-email, idn-hostname, ipv4, ipv6, regex, time, uuid` — **`date-time` is not among
   them**, because the optional `rfc3339-validator` dependency is not installed. Measured: adding
   `format_checker=FormatChecker()` produced **zero** errors on this file.

So enforcing `date-time` requires **both** a `format_checker` **and** a new dependency. A
one-line change to `official.py` would look like a fix and change nothing. Note the schema's own
description of `descriptors.outputs[].generated_utc` — *"Placeholder strings are not allowed"* — is
likewise unenforced for the same reason.

This touches the truth path and is therefore **not** something to change inside a QA-fixture task.
Raise it; do not patch it here.

### 5.2 `empty-measurement-series.json` — intended FAIL, measured **PASS**

`measurement.series` is required to be present and to be an array, but carries no `minItems`, so `[]`
satisfies it. Three readings of "empty series" were measured; **all three pass**:

| Variant | Measured |
|---|---|
| `measurement.series = []` | PASS ← shipped as the file |
| one series present, all `independent_variables[].values` and `channels[].values` = `[]` | PASS |
| one series present, the `values` keys omitted entirely | PASS |

The third is not even a numeric-emptiness question: `values` is absent from the items' `required`
lists, so a channel need not carry data at all.

The whole schema contains exactly **one** `minItems` — `uncertainty.bounds` (2) — and exactly **one**
`minLength` — `tags` items (1). Consequence to state plainly: **a record can be officially valid while
containing no measured data points whatsoever.**

## 6. HTTP contract, per file — derived from code, not from a running server

Nothing was started; this is read from `apps/api/isaac_api/routes.py` and
`apps/web/src/components/RecordValidator.tsx`.

Route behaviour (`post_validate_record`, `routes.py:1653-1705`):

- body parses as a JSON **object** → **200**, `{ok, summary, errors[], schema_version}`. An invalid
  record is a **200 with `ok: false`**, never an error status.
- body does not parse, or is not UTF-8 → **422** `{"error":"invalid_json"}`.
- body parses but is not a dict → **422** `{"error":"not_a_json_object"}`.
- body exceeds `MAX_VALIDATE_RECORD_BYTES = 512 * 1024` → **413** `{"error":"request_too_large"}`,
  aborted mid-stream by `_read_bounded_body` (`routes.py:1384-1403`).

**Important: the screen refuses before the request in three of these cases**, so several statuses are
unreachable through the UI:

- `RecordValidator.tsx:82-86` — file larger than 512 KB is refused at file-choose time.
- `RecordValidator.tsx:104-108` — text longer than 512 KB is refused at Validate time.
  ⇒ **413 is not reachable from the UI at all.**
- `RecordValidator.tsx:109-116` — `JSON.parse` runs client-side first; on failure the phase goes to
  `rejected` and **no request is made**.
  ⇒ **422 `invalid_json` is not reachable from the UI at all.**
- 422 `not_a_json_object` *is* reachable from the UI, but only for input that parses as a non-object
  JSON value (`42`, `"text"`, `[]`). No file in this package does that.

Also note `api.validateRecord` sends `JSON.stringify(parsed)` (`apps/web/src/lib/api.ts:449-454`) —
the browser re-serializes compactly, so the transmitted body is *smaller* than the file on disk. The
181 KB large file is therefore doubly safe against the 512 KB bound.

Per file:

| # | File | UI path | HTTP |
|---|---|---|---|
| 1 | `complete-valid-record.json` | validates | **200**, `ok: true` |
| 2 | `missing-required-information.json` | validates | **200**, `ok: false`, 1 error |
| 3 | `missing-nested-information.json` | validates | **200**, `ok: false`, 1 error |
| 4 | `missing-conditional-information.json` | validates | **200**, `ok: false`, 1 error |
| 5 | `invalid-date-time.json` | validates | **200**, `ok: true` (divergence §5.1) |
| 6 | `empty-measurement-series.json` | validates | **200**, `ok: true` (divergence §5.2) |
| 7 | `missing-evidence.json` | validates | **200**, `ok: false`, 1 error |
| 8 | `missing-confirmation.json` | validates | **200**, `ok: false`, 1 error |
| 9 | `invalid-controlled-value.json` | validates | **200**, `ok: false`, 1 error |
| 10 | `invalid-field-type.json` | validates | **200**, `ok: false`, 1 error |
| 11 | `unknown-field.json` | validates | **200**, `ok: false`, 1 error |
| 12 | `multiple-issues.json` | validates | **200**, `ok: false`, 3 errors |
| 13 | `unicode-and-escaping.json` | validates | **200**, `ok: true` |
| 14 | `large-valid-record.json` | validates (181,163 B < 512 KB) | **200**, `ok: true` |
| 15 | `malformed-json.json` | client-side `JSON.parse` fails | **no request** — would be 422 `invalid_json` if posted directly |
| 16 | `unsupported-file.txt` | filtered by `accept="application/json,.json"`; if forced, `JSON.parse` fails | **no request** — would be 422 `invalid_json` if posted directly |
| 17 | `duplicate-of-complete-valid-record.json` | validates | **200**, `ok: true` — identical to file 1 |
| 18 | `repairable-record.json` | validates | **200**, `ok: false`, 1 error; **200**, `ok: true` after the edit |

## 7. Notes on individual files

- **`duplicate-of-complete-valid-record.json`** — duplicate detection is **not** a property of this
  screen and its absence is not a defect. The route holds no store, writes nothing
  (`routes.py:1653-1666` docstring: read-only, body never written, content never logged) and compares
  nothing. Duplicate handling only becomes testable on a persisting import path; keep this file for
  that.
- **`multiple-issues.json`** — the three error paths are distinct (`$`, `context.temperature_K`,
  `system.instrument`), which also means `VerdictCard`'s `key={err.path}` does not collide. Error
  order is deterministic: `validate_official` sorts by `absolute_path` as a list of strings, so `$`
  (empty path) sorts first, then `context.*`, then `system.*`.
- **`large-valid-record.json`** — 181,163 bytes on disk. 2600 energy points, 8850.00 → 9629.70 eV at
  0.30 eV, plus normalized absorption and an i0 monitor channel: 7800 numbers. Size comes from data
  density, not padding. The curve is an arctangent edge step at 8979 eV + a Lorentzian white line +
  a damped sinusoid above the edge; the monitor drifts slowly downward.
- **`unicode-and-escaping.json`** — written with `ensure_ascii=False`, so real multi-byte UTF-8 is on
  the wire rather than `\uXXXX` escapes. Descriptor `name` values were kept plain ASCII deliberately:
  the schema constrains them with a regex that also rejects anti-patterns (`_magnitude`, `_ratio.`,
  `_normalized`, `current_fraction.`, `.partial_sum_`). `tags` were kept inside their `maxLength` 64
  and their `^\S(.*\S)?$` pattern.
- **`malformed-json.json`** — truncated at the `"measurement"` key. Measured locally:
  `json.JSONDecodeError: Expecting value: line 62 column 1 (char 1654)`.
- **`unsupported-file.txt`** — the `.txt` extension is the point; on macOS the native chooser can
  still be switched to all files. If that proves too awkward for the operator, pasting the text into
  the box exercises the identical refusal branch.

## 8. Findings to raise (none actioned here)

1. **`format` is unenforced project-wide** — no `format_checker`, and `date-time` is not even a
   registered checker without `rfc3339-validator`. Affects every `date-time` field: all four
   `timestamps.*` and `descriptors.outputs[].generated_utc`, whose own description says placeholder
   strings are not allowed.
2. **`measurement.series` has no `minItems`** — an officially valid record can carry zero measured
   points, by three different routes (§5.2).
3. **`measurement.qc.evidence` is unenforced when it matters** — the schema says "REQUIRED in practice
   when status != valid"; a record with `status: "compromised"` and no `evidence` was measured to
   pass.
4. **413 and 422 `invalid_json` are unreachable from the UI** — both are guarded client-side first.
   They are correct server behaviour and are covered by API-level tests, but no browser QA can observe
   them; testing them needs a direct request.
5. **`measurement.processing` is an open block by design** — an unknown key there is accepted today.
   The schema comment says the block is "intentionally not locked yet"; nothing in this package tests
   it, and nothing should assume it stays open.

Items 1–3 are truth-path observations. Any change to them touches
`src/isaac_records/official.py` or `schema/isaac_record_v1.json` and is out of scope for a
QA-fixture task — the schema is vendored from public upstream and is not ours to edit.
