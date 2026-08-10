# Which fields belong to a Run, and which to the Experiment — the six that need a scientist

**Status:** open question for Angel (scientific) with Dean cc'd on the two that may be operational
rather than scientific. **Nothing is blocked from shipping by this** — the Run workspace works today
on five fields. What is blocked is *widening* it, and the honest reason is written below rather than
guessed around.

**Date:** 2026-08-10. Every number here was measured by the command shown; none is recalled.

---

## 1. Why there is a question at all

One Run becomes one ISAAC record (contract §1). So for every field the extractor can produce, the
system has to know whether two runs of one experiment may legitimately hold **different** values:

- **experiment-level** — entered once, every run reads it, and a run that needs its own value must
  record an *audited override*;
- **run-level** — belongs to the run alone, and the run workspace may offer a control for it.

`apps/api/isaac_api/workspace.py::field_level` answers this, and it has a third answer —
`LEVEL_UNCLASSIFIED` — which its own docstring calls *"a real answer and not an oversight"*. An
unclassified field is inherited by nobody and the run PATCH route refuses it with a typed 422, so a
scientist is never handed a control whose only outcome is a refusal.

**Guessing is the thing this packet exists to avoid.** `CLAUDE.md` §5 forbids inferring a value
without evidence, and "whether two runs may differ in detector model" is a scientific judgement, not
an inference from the schema.

---

## 2. Where the fields stand today (measured)

```
PYTHONPATH=src:apps/api .venv/bin/python -c "
import isaac_api.workspace as ws
from isaac_records.extract import structured
paths = sorted({(v[0] if isinstance(v,(tuple,list)) else v) for v in structured.FIELD_MAP.values()})
print(len(paths), {l: sum(1 for p in paths if ws.field_level(p)==l) for l in ('experiment','run','unclassified')})
"
→ 25 {'experiment': 13, 'run': 5, 'unclassified': 7}
```

| | count | paths |
|---|---|---|
| **experiment-level** | 13 | everything under `sample`, plus `system.domain`, `system.facility.*`, `system.instrument`, `system.technique` |
| **run-level** | 5 | `context.environment`, `context.temperature_K`, `context.thermodynamics.atmosphere`, `timestamps.acquired_start_utc`, `timestamps.acquired_end_utc` |
| **unclassified** | 7 | the six `system.configuration.*` below, plus `timestamps.created_utc` |

The run workspace currently offers **three** of the five run-level fields
(`apps/web/src/lib/runFields.ts`); the other two are a deliberate presentation choice recorded in
that file, not a classification question, and can be offered without asking anyone.

---

## 3. `timestamps.created_utc` does NOT need a scientific answer — evidence, not opinion

It is on the unclassified list, and it can come off it without troubling anyone:

- the official schema makes `timestamps.created_utc` **required** (`schema/isaac_record_v1.json`,
  `properties.timestamps.required == ["created_utc"]`, and it carries **no description**);
- the exporter already supplies it — `src/isaac_records/export.py:149-151`, *"created_utc is required
  by the schema — default to now"*, via `setdefault`;
- unclassified fields are not inherited (`Experiment.resolved_run_draft` composes the run's own draft
  plus **experiment-level** addresses only), so an extracted value at experiment level does not reach
  a run's export draft and the exporter's default takes effect.

It is a **record-creation stamp, not an inherited scientific value**. No scientist has to rule on it.

**One consequence worth a moment, and it is not part of the question below:** if a source sheet
records a creation time, that value is currently dropped on the fan-out path and replaced by the
export time. That is a small provenance loss, it is a records decision rather than a scientific one,
and it is logged here so it is not discovered later as a surprise.

---

## 4. The actual question — six fields, one sentence each

For each: **may two runs of one experiment legitimately hold different values?**

| Field | Type | If YES (run-level) | If NO (experiment-level) |
|---|---|---|---|
| `system.configuration.detector_model` | string | the run workspace can offer it; a run that swapped detectors records its own | entered once; a run that differs must file an audited override |
| `system.configuration.monochromator_crystal` | string | same | same |
| `system.configuration.spectrometer_geometry` | string | same | same |
| `system.configuration.n_scans` | integer | per-run, which is what "number of scans **for this run**" reads like — but reading like it is not evidence | one value for the set |
| `system.configuration.proposal_id` | string | *(we expect NO — a proposal covers a visit, not a scan)* | entered once, inherited by every run |
| `system.configuration.session_id` | string | *(we expect NO for the same reason)* | entered once, inherited by every run |

**The two parenthesised expectations are stated so they can be corrected, and they are not acted on.**
`proposal_id` and `session_id` look administrative rather than scientific, which is why Dean is cc'd:
if they are facility bookkeeping, the answer may be his rather than Angel's — and if a single
experiment can span two proposals or two sessions at SSRL, our expectation is simply wrong.

**A "we do not know yet" is an acceptable answer** and is better than a guess. A field left
unclassified keeps behaving exactly as it does today: refused by the run PATCH route with a typed
422, inherited by nobody, and offered nowhere in the UI.

---

## 5. What each answer unlocks, so the cost of leaving it open is visible

- **run-level** → the field joins `RUN_WRITABLE_FIELD_PATHS` (derived, in `apps/api/isaac_api/routes.py`)
  and can appear in the Run card. No new machinery.
- **experiment-level** → the field becomes inheritable, appears in a run's *Inherited from Experiment*
  panel, and becomes eligible for the override path. `Experiment.set_run_override` already exists and
  is tested; **no HTTP route reaches it yet**, so overrides are a separate slice regardless of this
  answer.
- **unclassified (status quo)** → six extracted fields stay invisible in the Run workspace. They are
  still exported at the experiment level; nothing is lost, and nothing is offered.

---

## 6. One documentation defect found while measuring this

`workspace.py::field_level`'s docstring enumerates **five** `system.configuration.*` fields —
`detector_model`, `monochromator_crystal`, `n_scans`, `proposal_id`, `session_id`. The extractor emits
**six**: `spectrometer_geometry` is missing from that list. The behaviour is correct (the prefix test
covers it); only the prose undercounts. Recorded here and fixed in the same change as this file.

---

## 7. How to answer

A one-line reply per field is enough — `run`, `experiment`, or `unknown`. No prose is needed. Whoever
implements the answer must:

1. add the path to `EXPERIMENT_LEVEL_FIELD_PATHS` or `RUN_LEVEL_FIELD_PATHS` in `workspace.py`;
2. quote this document and the answer in the commit, since the classification is a recorded human
   judgement and not a derivation;
3. leave anything answered `unknown` exactly where it is.
