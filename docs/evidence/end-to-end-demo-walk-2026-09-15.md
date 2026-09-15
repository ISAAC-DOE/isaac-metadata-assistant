# The product's own record, created and exported end to end — measured 2026-09-15

A walk of the path a scientist actually takes, over HTTP against a locally-served
build (`uvicorn` + `vite`, `mode: synthetic-only`, a fresh `ISAAC_UI_WORKSPACE`),
with every step's result recorded. Nothing here is a fixture or a seed: the
record is created through `POST /api/experiments`, which is the product's own
Create Experiment path.

This exists because "the flow works" is a claim, and the last time it was tested
this way (2026-08-19) it turned out a record created through that path **could
not be completed or exported by any route**. That is the finding this walk is
the regression check for.

## What was verified

| Step | Call | Result |
|---|---|---|
| 1. Create | `POST /api/experiments` | `200`, record id minted |
| 2. Add a run | `POST /api/experiments/{id}/runs` | `200`, `Run 1` |
| 3. Capture notes | `POST /api/experiments/{id}/transcript` | `200` — **2 notes, 1 candidate, 1 proposal** |
| 4. Answer the blockers | `POST /api/experiments/{id}/runs/{run}/answers` | `200`, **pending 3 → 0** |
| 5. Export | `POST /api/experiments/{id}/export` | **`ok: true`**, official report **`ok: true`, 0 errors** |
| 6. Validate independently | `.venv/bin/isaac validate <record> --official` | **`PASS — valid against official ISAAC schema v1.05`** |

The export wrote both artifacts — `<ULID>.json` and `<ULID>.evidence.json` — and
the exported record carries what was entered: `series_id: averaged_spectrum`,
one descriptor (`xanes_inflection_energy`, `8981.4 eV`), and `qc.status: valid`.

**Step 6 is the one that matters most**, because it is the truth path answering
independently of the API that produced the file.

## The proposal the transcript minted

One sentence of dictation produced a durable proposal with its provenance intact:

```
target_field_path : timestamps.acquired_start_utc
proposed_value    : 2026-09-15T02:00:00Z
rule              : "in the sentence 'Acquisition started 2026-09-15T02:00:00Z.',
                     a start word and a full UTC instant appear in one clause;
                     the instant is taken …"
excerpt / offsets : the source sentence, with start_char and end_char
note_id / run_id  : the note it came from, and the run it belongs to
state             : open
```

Nothing was written to the record. A proposal is a request for a human decision.

## Two things that DO NOT work, and are not defects

**1. Accepting a proposal answers `409`, by design and by configuration.**

```
POST /api/experiments/{id}/proposals/{proposal_id}/review
  {"action":"accept","confirmed_by_user":true,"accepted_from":"candidate"}
→ 409 human_actor_required
  trust: untrusted, reason: no_verifier_configured
  "This operation records who performed it, and this deployment cannot establish
   who is calling: no trusted authentication boundary is configured, so nothing
   checked. Nothing was written."
```

This is `CLAUDE.md` §15's documented behaviour — the acceptance route refuses in
**every default-configured deployment**, including the hosted one, because no
trusted authentication boundary exists (Dean reconfirmed the ClusterIP bypass,
2026-08-12). No application change can close it. It is exercised in CI through
the deterministic fixture verifier, and end to end in `playwright.trusted.config.ts`
under `ISAAC_EDGE_TRUST_VERIFIER=test_fixture`.

**Consequence for a demo:** the proposal can be shown being *minted*, with its
rule and excerpt. It cannot be shown being *accepted* on the hosted app. The
values get into the record through the answer/edit routes instead, which is what
step 4 does.

**2. A transcript with no run chosen mints no proposals.**

Measured: `run_id: null` gives `candidates: []`. All five `READABLE_FIELD_PATHS`
resolve to run scope, so with no run the candidate loop is skipped whole. The
capture panel states this; the first version of that copy said the opposite and
was corrected on 2026-09-11.

## A defect this walk found, and where it was fixed

Step 4 was answered first with `[{"energy_eV": 8979.0, "mu": 0.412}]`. The
answers route **accepted it** — pending fell 3 → 1 and the question read as
answered — and export then refused:

```
series has no series_id — cannot key its evidence   (once per entry)
```

So a scientist could answer every question and hold a record that cannot be
exported, with the reason surfacing only at the end.

`schema/isaac_record_v1.json` requires `series_id`, `independent_variables` and
`channels` on every series item. `seriesShapeError` in
`apps/web/src/components/StructuredValueEntry.tsx` required only "a list of
objects", so the UI accepted it too. **It now gates on `series_id`** — the key
whose absence produced the refusal above — and
`src/__tests__/structured-value-schema-parity.test.ts` asserts that whatever this
form demands is a **subset** of what the schema requires, so the form can never
invent a requirement of its own (`CLAUDE.md` §1 makes the schema the authority).

**Requiring all three here was built and then narrowed, and the cost is why.**
The strict version turned **13 tests red across three files** — none of them
about series validation: prefill, Confirm arming, DOM ids, bounded pending,
refused corrections. Each would have had to carry full schema detail it does not
care about. Every real fixture and canonical seed already carries all three
(checked across `tests/fixtures/**`), so the strict gate blocked no shipped data;
it only made incidental scaffolding verbose. That is a signal the gate was at the
wrong layer. The other two keys are enforced by **official validation at export**,
which names each one precisely — measured in this same walk, on
`channels[0].unit` and on three enum values.

**The underlying asymmetry is NOT closed, and is named rather than implied:**
`src/isaac_records/complete.py:239-240` skips evidence for a series with no
`series_id` (`if series_id is None: continue`) and accepts the answer, while
`draft_validator.py:592` makes the same absence an export error. An API caller
can still reach that. Closing it is a truth-path change, which `CLAUDE.md` §13
puts behind its own slice and its own review.

## Payload shapes, since three attempts were refused before one passed

The refusals were precise and each one named what to fix, which is worth
recording as product behaviour rather than as friction:

- `{"segments": [...]}` → `422 unrecognized_field`, "Nothing was written", naming `segments`.
- `{"answers": [...]}` (a list) → `422 invalid_body`, "`answers` must be a JSON object mapping an answer key to its value. Nothing was written and no question moved."
- Answering `qc` on the **record** → `409 belongs_to_a_run`: "A spectrum, a QC verdict, a descriptor and an asset hash belong to the run that measured them, so answering them here would write a value no exported record reads."
- Using the experiment's ETag on a run route → `409 stale_write`. A run route takes the **run's** ETag.
- Invented enum values (`kind: scalar`, `source: measured`, `role: absorption`) → official validation named each with the allowed set.

Working shapes:

```jsonc
// POST /api/experiments/{id}/transcript
{"text": "...", "finalized": true, "run_id": "<run>"}

// POST /api/experiments/{id}/runs/{run}/answers   (If-Match: the RUN's etag)
{"confirmed_by_user": true, "answers": {
  "qc": {"status": "valid", "note": "..."},
  "series": [{"series_id": "averaged_spectrum",
              "independent_variables": [{"name": "energy", "unit": "eV", "values": [...]}],
              "channels": [{"name": "mu", "unit": "dimensionless",
                            "role": "primary_signal", "values": [...]}]}],
  "descriptor": {"name": "xanes_inflection_energy", "kind": "absolute",
                 "source": "manual", "value": 8981.4, "unit": "eV",
                 "uncertainty": {"sigma": 0.3, "unit": "eV", "basis": "repeat scans"}}
}}
```

## Limits of this evidence

- **Local, not hosted.** This is a locally-served build. `/krish` sits behind an
  Authentik edge this environment cannot authenticate to, so nothing here is a
  statement about the hosted deployment. Hosted QA remains `PENDING (Krish)`.
- **Synthetic throughout.** No production-derived record was read, and no
  database was contacted.
- **One path.** Historical Import, CSV reconciliation, and the guided walkthrough
  were not exercised here.
