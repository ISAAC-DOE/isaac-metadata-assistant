> ## SUPERSEDED IN PART — 2026-08-05
>
> **Q19 has been ANSWERED and APPROVED.** The approval was **relayed by the project owner; no direct
> agent-to-owner communication occurred.** The durable record is
> [`docs/evidence/2026-08-05-q19-q20-authorization.md`](evidence/2026-08-05-q19-q20-authorization.md),
> and its machine-readable form — including the twelve constraints attached to the approval — is
> [`apps/api/isaac_api/authorization.py`](../apps/api/isaac_api/authorization.py).
>
> **Q20 is still unanswered.** The two were deliberately not bundled (see the line below), so Q19's
> approval says nothing about arming `format` enforcement.
> `authorization.Q20_FORMAT_ENFORCEMENT_APPROVED` is `False` and the validator stays format-blind.
>
> **What this means for the text below.** The "Consequence while unanswered" bullet for Q19, and the
> "Ambiguous / no answer → runner stays unbuilt" row in the outcome table, are **no longer the
> current state**: the datastore-backed verification mode is built, and
> `verification.VERIFICATION_MODES` now derives from the approval flag. Everything else here —
> the wording of the question, the reasoning behind it, and the whole of Q20 — stands unchanged and
> is deliberately **not deleted**: the question as put is what was approved, so it remains the
> authoritative statement of scope.
>
> Nothing here reopens per-record display, which remains closed by default.

# Authorization packet for Dean — Q19 and Q20

**Status: NOT SENT.** No approved workflow permits agent-to-Dean communication. This file exists so
Krish can send it; nothing in it has been transmitted. *(Superseded in part — see the 2026-08-05
note above: Q19 was subsequently answered and the answer relayed.)*

**Both questions are independent decisions and should not be bundled into one answer.**

Consequence while unanswered:

- **Q19 unanswered** → the private 30-record mutation runner stays **unbuilt**, not even in a disabled
  form. The mutation harness continues to run on the public upstream corpus and on generated fixtures.
- **Q20 unanswered** → `format` enforcement stays **off**. The characterization tests shipped in
  `tests/test_truthpath_characterization.py` stand as the permanent record of the behaviour and of why
  it was left alone.

**No database connection was opened during the session that produced this packet.**

---

## Q19 — the mutation-harness disclosure question

> Following on from G3: `GET /api/runtime/database/recon` already reads all 30 records' full `data`
> JSON into pod memory and runs our v1.05 validator over them, emitting only the aggregates you
> enumerated. We would like to extend that to a **validator test harness**: clone each record in
> memory, apply a fixed catalog of deterministic mutations (remove a required field, inject an invalid
> enum token, remove evidence), run our workflow engine, discard every clone. Zero writes, zero DDL,
> no new access path, no per-record output.
>
> **The disclosure question we cannot answer ourselves.** Whether a mutation is *applicable* to a
> record is a fact about that record's structure. So "removing field X was applicable to 12 of 30
> records" discloses that 12 records populate X — a field-presence map over the corpus, close to the
> `by_instance_path` aggregate we withdrew and are already asking you about. Over 30 rows an
> applicability count of 1 is a single-record fact, and we have **no minimum-cell-size suppression
> anywhere** in the code.
>
> We see one clean line and want your ruling on it: **mutations targeting UNCONDITIONALLY required
> fields, counted over the passing subset only, are safe** — if a record validates, the schema entails
> the field is present, so the count is identically `records_passing_full_schema`, which you already
> authorized. Both qualifiers matter: a field required only under `if`/`then` or `oneOf` has
> record-derived applicability, and if any record *fails* full-schema validation then a count below the
> corpus size discloses which failing records lack that field. **Mutations targeting optional fields
> (evidence, descriptors, links, conditional blocks) are not safe** — there, applicability *is* the
> disclosure.
>
> Three questions: **(a)** Is that line right? **(b)** May we publish per-mutation-category counts for
> required-field mutations only, with everything else reduced to a single global pass/fail boolean?
> **(c)** If any optional-field breakdown is acceptable, what minimum cell size should apply?

Source: `docs/superpowers/plans/2026-08-02-corpus-validation-authorization.md:190-217`.

**Why not the shorter, more obvious phrasing.** The audit at `:183-188` anticipates it and rejects it:
it "would get a yes to a question he did not understand." A per-mutation count over 30 rows *is*
per-record output; it does not distinguish required from optional fields; it leaves "aggregate"
granularity undefined; and asked cold it cannot be connected to G3.

---

## Q20 — format enforcement

This did not exist when Q19 was drafted.

### The finding, with every number measured

ISAAC's official validator has never enforced JSON Schema `format`. The vendored v1.05 schema declares
`"format": "date-time"` in **six** places, **two of them required**:

| JSON path | required |
|---|---|
| `timestamps.created_utc` | **yes** |
| `descriptors.outputs.generated_utc` | **yes** |
| `timestamps.acquired_start_utc` | no |
| `timestamps.acquired_end_utc` | no |
| `timestamps.last_updated_utc` | no |
| `context.electrochemistry.potential_vs_RHE.conversion.converted_utc` | no |

All six accept `not-a-date`. Such a record passes validation, reaches export-ready, and is written
verbatim into an exported official record — the record's own `created_utc` reads `not-a-date`.

**There are two independent causes, and fixing either alone changes nothing.** Measured as a 2×2 on
`qa/validator-upload-package/invalid-date-time.json`:

```
neither cause fixed                  -> 0 errors
format_checker=FormatChecker() only  -> 0 errors      <-- a one-line "fix" changes NOTHING
date-time checker registered only    -> 0 errors
BOTH fixed                           -> 1 error: "'not-a-date' is not a 'date-time'"
```

- **Cause 1** — `src/isaac_records/official.py` builds `Draft202012Validator(schema)` with no
  `format_checker=`. Under Draft 2020-12, `format` is an annotation unless a checker is attached.
- **Cause 2** — `pyproject.toml` pins plain `jsonschema`, not `jsonschema[format]`, so
  `rfc3339-validator` is absent and `date-time` is **not in the checker registry at all**. Measured
  registry: `date, email, idn-email, idn-hostname, ipv4, ipv6, regex, time, uuid`. Note `date` *is*
  present (stdlib) while `date-time` is not — so the gap is specific, not a blanket absence.

All ten public upstream example records conform to canonical RFC3339, so arming enforcement is
provably safe for the public corpus. This looks like our configuration defect, not upstream intent.

### Why this is Dean's decision and not ours

`apps/api/isaac_api/db_recon.py` runs this **same** `validate_official` over the 30 production-derived
rows and reports `records_passing_full_schema`. Arming format enforcement changes what that number
means, and could change its value — for his data, without his involvement, via what would look like a
local bug fix. His own guide calls full schema conformance for those rows "expected but unverified."

### The message

> We found that our official validator has never enforced JSON Schema `format`. The ISAAC v1.05 schema
> declares `"format": "date-time"` in six places, two of them required fields, and our validator
> accepts `not-a-date`, an empty string, and the literal `TBD` in all of them — including a field whose
> schema description explicitly forbids placeholder strings. Such a record validates, becomes
> export-ready, and is exported verbatim. All ten public upstream examples conform to real RFC3339, so
> this appears to be our configuration defect rather than an upstream intent.
>
> There are two independent causes and fixing either alone changes nothing, which is worth stating
> because a one-line change would look like a fix and would not be one: our validator passes no format
> checker, **and** we pin `jsonschema` without the `format` extra, so `date-time` is not even in the
> checker registry.
>
> We have not changed anything, because the fix reaches your data.
> `GET /api/runtime/database/recon` runs this same validator over the 30 seeded records and reports
> `records_passing_full_schema`. If we arm format enforcement, that figure changes meaning and may
> change value — and your guide notes full schema conformance for these rows is expected but
> unverified.
>
> **(d)** Do you want us to arm `format` enforcement in the ISAAC validator?
> **(e)** If yes: may we report, as a one-off, how many of the 30 records contain a non-RFC3339
> `date-time` — a single corpus-wide count, no paths, no ids, no values? We read this as within
> "validation totals", but it is a total under a validator we would have just changed, so we would
> rather ask than assume.
> **(f)** Do you know whether the official portal validator enforces `format`? If it does, records
> ISAAC currently marks PASS would be rejected on submission, which would make this a divergence rather
> than a local defect.

---

## Two related findings that are NOT Dean's decision, recorded so they are not conflated with Q20

Both concern the upstream schema, which is vendored verbatim and **is not ours to edit**
(`schema/PROVENANCE.md`). So neither can be fixed by making `validate_official` stricter — that would
create a second authoritative validator. Both are application-truthfulness work on our side.

### 1. An empty measurement series is officially valid

The entire v1.05 schema declares exactly **one** `minItems` (on `descriptors…uncertainty.bounds`, value
2) and one `minLength` (`tags` items). Measured: `measurement.series: []` → **PASS, 0 errors**; likewise
`assets: []` and `links: []`. A record can be officially valid while containing no measured data points.

Worse, and on our side: `src/isaac_records/export.py:83` guards the measurement block with
`if draft.get("series"):` — falsy. So an empty series makes the **entire `measurement` block vanish from
the exported record, including a QC verdict a human evidenced**, and the result still validates.
Measured on a real workspace draft:

```
A populated  -> ok: True,  'measurement' in record: True,  qc: valid
B series=[]  -> ok: True,  'measurement' in record: False
   the human-evidenced QC verdict is now: ABSENT
   official validation of that record: PASS
```

That is ours to fix and does not need Dean. What *would* need him is the domain question: **is a
metadata-only characterization record that points at raw assets but carries no reduced spectrum a
legitimate ISAAC record, and if so is `qc.status: "pending"` the intended way to say so** — given that
its description names only "intent records awaiting execution"?

### 2. `measurement.qc.evidence` is required in prose, not in schema

`qc.properties.evidence.description` reads *"REQUIRED in practice when status != valid: what is
compromised/failed and why. \"N/A\" defeats the purpose."* But `qc.required` lists only `status`.
Measured: `qc.status: "failed"` with no `evidence` → **PASS, 0 errors**.

**ISAAC already catches this**, and that is the important half: `portal_warnings.py` emits
`QC_NONVALID_WITHOUT_EVIDENCE`, and it reaches the UI through `AdvisoryChip` on Export Readiness and
Record Workbench. Measured:

```
qc=valid + evidence     -> [NO_LINKS]
qc=failed,   NO evidence -> [NO_LINKS, QC_NONVALID_WITHOUT_EVIDENCE @ measurement.qc.evidence]
qc=compromised, NO ev.   -> [NO_LINKS, QC_NONVALID_WITHOUT_EVIDENCE @ measurement.qc.evidence]
```

The remaining gap is narrow and ours: `POST /api/validate/record` — the Standalone Validator, the
surface in the manual QA package — calls `validate_official` **only**, never `portal_warnings`. So a
pasted record gets a bare green PASS with no advisory. Fixing that is application work needing no
authorization.

---

## What happens on each answer

| Dean's answer to Q19 | Action |
|---|---|
| Explicitly Authorized | Implement the private runner as its own reviewed slice. `workflow.py` has never run against a real record and needs its own code-safety review first. |
| Authorized With Output Restrictions | Same, with the output allowlist narrowed to exactly what he permits. |
| Ambiguous / no answer | Status quo. Runner stays unbuilt. Harness continues on the public corpus and generated fixtures. |
| Explicitly Disallowed | Record it; delete the proposal; keep the public-corpus harness. |

| Dean's answer to Q20 | Action |
|---|---|
| **(d) yes** | Arm BOTH causes in one change — `format_checker=` **and** the `jsonschema[format]` extra. Then re-measure the QA package: `qa/validator-upload-package/invalid-date-time.json` flips PASS → FAIL, which by design fails `tests/test_validator_qa_package.py` loudly and names the four documents to update. |
| **(d) no** | Leave it. The characterization tests are the permanent record. `invalid-date-time.json` stays in the QA package as the reproducer. |
| **(e)** | Governs whether a one-off corpus count may be reported. Absent a yes, report nothing. |
| **(f)** | If the portal enforces `format`, this is reclassified from a local defect to a divergence and becomes urgent. |

## Reproducing every number in this file

```bash
# the 2x2, the checker registry, and the six declarations
.venv/bin/python -c "
import json; from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
s=json.loads(Path('schema/isaac_record_v1.json').read_text())
r=json.loads(Path('qa/validator-upload-package/invalid-date-time.json').read_text())
print(sorted(FormatChecker().checkers))
print(len(list(Draft202012Validator(s).iter_errors(r))),
      len(list(Draft202012Validator(s, format_checker=FormatChecker()).iter_errors(r))))"

# the empty-series and qc findings
.venv/bin/isaac validate qa/validator-upload-package/empty-measurement-series.json --official   # exit 0
```
