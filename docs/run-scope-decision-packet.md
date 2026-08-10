# Which fields belong to a Run, and which to the Experiment — the six that need a scientist

**Status:** open question for Angel (scientific) with Dean cc'd on the two that may be operational
rather than scientific. **Nothing is blocked from shipping by this** — the Run workspace works today
on the three fields it offers, of the five the backend will accept. What is blocked is *widening* it
beyond those five, to the six fields below, and the honest reason is written here rather than guessed
around.

**Date:** 2026-08-10. Every count and path list in §2, §4 and §5 is an output of the command printed
beside it. The counts that are not command outputs are cited to a `file:line` a reader can open — the
**three** entries of `RUN_FIELDS` (`apps/web/src/lib/runFields.ts:80-100`), and the sizes of the literal
test assertions in §7. Nothing here is recalled. *(An earlier revision claimed every number came from
"the command shown" while showing one command and stating four separate counts; that claim is the
`CLAUDE.md` §12 failure class this document is supposed to avoid.)*

---

## 1. Why there is a question at all

One Run becomes one ISAAC record (contract §1). So for every field the extractor can produce, the
system has to know whether two runs of one experiment may legitimately hold **different** values:

- **experiment-level** — entered once, every run reads it, and a run that needs its own value must
  record an *audited override*;
- **run-level** — belongs to the run alone, and the run workspace may offer a control for it.

`apps/api/isaac_api/workspace.py::field_level` answers this, and it has a third answer —
`LEVEL_UNCLASSIFIED` — which its own docstring states in capitals: `LEVEL_UNCLASSIFIED IS A REAL
ANSWER AND IS NOT AN OVERSIGHT` (`apps/api/isaac_api/workspace.py:536`). An unclassified field is
inherited by nobody and the run PATCH route refuses it with a typed 422, so a scientist is never
handed a control whose only outcome is a refusal. Leaving a field unclassified is not free, though —
§5 measures what it costs on export.

**Guessing is the thing this packet exists to avoid.** `CLAUDE.md` §5 forbids inferring a value
without evidence, and "whether two runs may differ in detector model" is a scientific judgement, not
an inference from the schema.

---

## 2. Where the fields stand today (measured)

```
PYTHONPATH=src:apps/api .venv/bin/python -c "
import collections
import isaac_api.workspace as ws
from isaac_records.extract import structured
paths = sorted({(v[0] if isinstance(v,(tuple,list)) else v) for v in structured.FIELD_MAP.values()})
by = collections.defaultdict(list)
for p in paths: by[ws.field_level(p)].append(p)
print(len(paths), {l: len(by[l]) for l in ('experiment','run','unclassified')})
for l in ('experiment','run','unclassified'): print(l, len(by[l]), by[l])
"
→ 25 {'experiment': 13, 'run': 5, 'unclassified': 7}
  experiment 13 ['sample.composition.CuO2_mass_fraction', 'sample.composition.sucrose_mass_fraction',
   'sample.geometry.pellet_diameter_mm', 'sample.material.formula', 'sample.material.name',
   'sample.material.provenance', 'sample.sample_form', 'system.facility.beamline',
   'system.facility.endstation', 'system.facility.facility_name', 'system.facility.organization',
   'system.facility.site', 'system.technique']
  run 5 ['context.environment', 'context.temperature_K', 'context.thermodynamics.atmosphere',
   'timestamps.acquired_end_utc', 'timestamps.acquired_start_utc']
  unclassified 7 ['system.configuration.detector_model', 'system.configuration.monochromator_crystal',
   'system.configuration.n_scans', 'system.configuration.proposal_id',
   'system.configuration.session_id', 'system.configuration.spectrometer_geometry',
   'timestamps.created_utc']
```

*(The path lists above are the command's own output, re-wrapped to fit the page; nothing is added to
them or removed.)*

| | count | paths |
|---|---|---|
| **experiment-level** | 13 | everything under `sample` (7), everything under `system.facility` (5), and `system.technique` |
| **run-level** | 5 | `context.environment`, `context.temperature_K`, `context.thermodynamics.atmosphere`, `timestamps.acquired_start_utc`, `timestamps.acquired_end_utc` |
| **unclassified** | 7 | the six `system.configuration.*` below, plus `timestamps.created_utc` |

**The denominator is `FIELD_MAP`** — the 25 distinct official dotted paths
`extract/structured.FIELD_MAP` maps to, which is also what the run PATCH route's allowlist is derived
from. Stating the basis matters, because two paths a reader may expect in the experiment-level row are
deliberately not in it:

- **`system.domain` is not in `FIELD_MAP`.** It is added by `build_draft` as a deterministic
  derivation (`src/isaac_records/extract/draft_builder.py:99-114`), so it belongs to a different
  denominator — a `build_draft` walk counts more fields than 25. It *is* experiment-level by
  `EXPERIMENT_LEVEL_FIELD_PATHS`; it is simply not one of the 13 the command prints.
- **`system.instrument` is emitted by nothing.** It is a real official schema path and a prefix in
  `EXPERIMENT_LEVEL_FIELD_PATHS`, and the code says so in as many words: the current deterministic
  extractor never emits it (`apps/api/isaac_api/workspace.py:443-447`).

An earlier revision of this table listed both, which made the experiment-level row enumerate 15 items
under a count of 13.

The Run workspace currently offers **three** of the five run-level fields — the three entries of
`RUN_FIELDS` (`apps/web/src/lib/runFields.ts:80-100`). The other two
(`context.thermodynamics.atmosphere`, `timestamps.acquired_end_utc`) are a deliberate presentation
choice recorded in that file (`:29-40`), not a classification question, and can be offered without
asking anyone.

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

## 4. The actual question — six fields, and what each answer would cost if it is wrong

For each: **may two runs of one experiment legitimately hold different values?**

**Three facts apply to all six, so they are stated once here rather than repeated in every row.**

*First: the official schema declares no per-field description and no per-field type for any of them.*
`system.configuration`'s own keys are exactly `description` and `type`; it declares no `properties`:

```
.venv/bin/python -c "
import json
cfg = json.load(open('schema/isaac_record_v1.json'))['properties']['system']['properties']['configuration']
print(sorted(cfg.keys()), 'properties' in cfg)
"
→ ['description', 'type'] False
```

The one description it carries is namespace-level, and it is the whole of what the official schema
says about these six: *"THE designated open extension namespace: instrument/station/beamline-specific
configuration that does not generalize across facilities (slits, pass energies, GC columns, channel
IDs, logbook fields...). Anything that DOES generalize belongs in a schema field — request one."*

*Second, and it follows: the **type** shown in the table is NOT schema truth.* It is the coercer
`FIELD_MAP` applies (`src/isaac_records/extract/structured.py:66-67` and `:86-89`). Do not cite it as
schema-declared — the schema declares nothing at these paths.

*Third: all six behave identically after extraction.* Each is extracted from its named sheet row into
`fields["<path>"]` and then classified `unclassified` — inherited by nobody, refused by the run PATCH
route with a typed 422, and absent from every record a run exports (§5). What differs per field is
only where the mapping is documented, which the table cites.

| Field · type (from the `FIELD_MAP` coercer, **not** the schema) | Current extractor behaviour | If YES (run-level) | If NO (experiment-level) | Consequence if the answer is wrong | Recommendation |
|---|---|---|---|---|---|
| `system.configuration.detector_model` · `str` | `docs/extraction.md:132` — open namespace, no canonical slot; coerced `str` | the run workspace can offer it; a run that swapped detectors records its own value | entered once; a run that differs must file an audited override | **Experiment-level while detectors were in fact swapped** → every run's record names the one detector, and there is today no way to record the divergence: `Experiment.set_run_override` exists (`apps/api/isaac_api/workspace.py:2528`) but **no HTTP route reaches it** (`apps/web/src/components/RunCard.tsx:464` records the same). **Run-level while the detector never changed** → the same string is re-entered on every run and nothing checks that the entries agree. | **None.** A scientific judgement with no evidence in this repository (`CLAUDE.md` §5); it is the question being asked. |
| `system.configuration.monochromator_crystal` · `str` | `docs/extraction.md:132` — open namespace; coerced `str` | same | same | **Experiment-level while the crystal was changed mid-experiment** → every run's record names one crystal, so a run taken after the change is recorded with the optic it was not taken with, and the record gives a reader no way to tell. **Run-level while it never changed** → re-entered per run, with no cross-run check. | **None.** A scientific judgement with no evidence in this repository (`CLAUDE.md` §5); it is the question being asked. |
| `system.configuration.spectrometer_geometry` · `str` | `docs/extraction.md:131` — open namespace; coerced `str` | same | same | Same shape as the two above. It is additionally the one of the six that `field_level`'s prose omitted until this change (§6), so anyone who checked the docstring rather than the extractor would not have known it was in question at all. | **None.** A scientific judgement with no evidence in this repository (`CLAUDE.md` §5); it is the question being asked. |
| `system.configuration.n_scans` · `int` | `docs/extraction.md:133` — open namespace, no canonical slot; coerced `int` — the only non-`str` of the six | the run workspace can offer it and each run records its own count — which is what "number of scans **for this run**" reads like, though reading like it is not evidence | entered once; one value for the whole set | **Experiment-level while it varies** → every run reports the same count, exported as a definite integer, so a shared value is indistinguishable in the record from a measured one. **Run-level while it is one number for the set** → re-entered per run, and two runs may silently disagree about a count that describes the whole set. | **None.** The name reads per-run, and reading like it is not evidence (`CLAUDE.md` §5). |
| `system.configuration.proposal_id` · `str` | `docs/extraction.md:133` — open namespace, no canonical slot; coerced `str` | each run carries its own proposal id | entered once, inherited by every run | **Experiment-level while one experiment spans two proposals** → every run's record carries the first id, and which runs belonged to the second is unrecoverable from the records. **Run-level while a proposal always covers the whole experiment** → the id is re-typed per run, so a typo in one run yields a record attributed to a proposal that does not exist, with nothing comparing it against its siblings. | **No evidence-backed recommendation.** A stated *expectation* of experiment-level — see the note below the table; it is offered to be corrected and is not acted on. Nothing in this repository says what scope an SSRL proposal covers (search below). |
| `system.configuration.session_id` · `str` | `docs/extraction.md:133` — open namespace, no canonical slot; coerced `str` | each run carries its own session id | entered once, inherited by every run | **Experiment-level while one experiment spans two sessions** → every run's record carries the first id, and which runs belonged to the second is unrecoverable from the records. **Run-level while a session always covers the whole experiment** → the id is re-typed per run, with the same unchecked-typo consequence as `proposal_id`. | **No evidence-backed recommendation.** A stated *expectation* of experiment-level — see the note below the table; it is offered to be corrected and is not acted on. Nothing in this repository says what scope an SSRL session covers (search below). |

**The two expectations are stated so they can be corrected, and they are not acted on.** `proposal_id`
and `session_id` look administrative rather than scientific — a proposal or a session plausibly covers
a visit rather than a scan — which is why Dean is cc'd: if they are facility bookkeeping, the answer
may be his rather than Angel's, and if a single experiment can span two proposals or two sessions at
SSRL, the expectation is simply wrong. It is recorded as an expectation and not as a recommendation
because this repository holds no evidence either way:

```
rg -n --text -i --glob '!docs/run-scope-decision-packet.md' \
  -e 'proposal[ _-](covers|spans|scope|per)' -e 'one proposal' -e 'per proposal' \
  -e 'session[ _-](covers|spans|scope)' -e 'per session' \
  docs/ schema/ src/ apps/api/isaac_api/ apps/web/src/
→ 19 matching lines in 15 files. Every one is about the app's own browser/tutorial
  session scope (e.g. "one independent copy per session") or about an Assistant staged
  "proposal" — a suggested field value. NOT ONE states the scope of an SSRL proposal or
  an SSRL beamtime session. This document is excluded from the search because it now
  contains the only proposal-scope sentences in the repository, which would otherwise
  make the search find itself.
```

**A "we do not know yet" is an acceptable answer** and is better than a guess. A field left
unclassified keeps behaving exactly as it does today: refused by the run PATCH route with a typed
422, inherited by nobody, and offered nowhere in the UI. That is not cost-free, though — §5 measures
what it costs.

---

## 5. What each answer unlocks, so the cost of leaving it open is visible

- **run-level** → the field joins `RUN_WRITABLE_FIELD_PATHS` (derived at import time from `FIELD_MAP`
  intersected with `field_level`, `apps/api/isaac_api/routes.py:2661-2665`) and can appear in the Run
  card. No new *product* machinery — but two committed tests encode today's answer and one of them
  cannot simply be updated; see §7 step 3.
- **experiment-level** → the field becomes inheritable, appears in a run's *Inherited from Experiment*
  panel, and becomes eligible for the override path. `Experiment.set_run_override` already exists and
  is tested; **no HTTP route reaches it yet**, so overrides are a separate slice regardless of this
  answer.
- **unclassified (status quo)** → six extracted fields stay invisible in the Run workspace, and they
  are **exported only when the record has no runs**. On the fan-out path **they are dropped from every
  run's record** — the same provenance loss §3 records for `created_utc`, by the same mechanism.
  Measured:

```
PYTHONPATH=src:apps/api .venv/bin/python -c "
import isaac_api.workspace as ws
from isaac_records.extract import structured
six = sorted(p for p, _c in structured.FIELD_MAP.values() if p.startswith('system.configuration.'))
env = lambda: {'value': 'X', 'status': 'verified', 'evidence': []}
fields = {p: env() for p in six} | {'sample.sample_form': env()}
exp = ws.Experiment(id='EXP1', title='probe', created_utc='2026-01-01T00:00:00Z',
                    source={}, draft={'fields': fields})
def show(tag):
    units = exp.export_units()
    f = units[0].draft.get('fields', {})
    print(tag, 'records=%d' % len(units),
          'six present=%d/6' % sum(p in f for p in six),
          'sample.sample_form present=%s' % ('sample.sample_form' in f))
show('no runs :')
exp.add_run(label='A'); exp.add_run(label='B')
show('two runs:')
"
→ no runs : records=1 six present=6/6 sample.sample_form present=True
  two runs: records=2 six present=0/6 sample.sample_form present=True
```

  With no runs, `export_units` returns one unit carrying `self.draft` itself
  (`apps/api/isaac_api/workspace.py:2660-2661`), so all six are in the exported record. With runs it
  returns one unit per run carrying `resolved_run_draft(run)` (`:2662-2670`), and `resolved_run_draft`
  composes the run's own draft plus **experiment-level** addresses only — an unclassified field is
  neither, which is why `sample.sample_form` survives the fan-out and the six do not. No
  experiment-level record is written alongside them: a record with runs exports one record per run,
  and `record_id` on the response is `null` (`apps/api/isaac_api/routes.py:3627-3629`;
  `apps/api/tests/test_export_fan_out.py:222`).

  **This is a reachable path, not a hypothetical one.** `POST /experiments/{id}/runs` is an ordinary
  ungated route (`apps/api/isaac_api/routes.py:2916`, handler `post_run` at `:2941`) and the run
  test-suite asserts it returns `201` (`apps/api/tests/test_run_api.py:128-136`). So the cost of the
  status quo is not "nothing is lost"; it is six extracted, evidenced fields dropped from every record
  of any experiment that has runs. An earlier revision of this bullet said *"they are still exported at
  the experiment level; nothing is lost"* — false on that path, and a contradiction of the provenance
  loss §3 records for the identical mechanism.

---

## 6. Two documentation defects found while measuring this

**One, fixed in this change.** On `origin/main`, `workspace.py::field_level`'s docstring enumerated
**five** `system.configuration.*` fields — `detector_model`, `monochromator_crystal`, `n_scans`,
`proposal_id`, `session_id`. The extractor emits **six**: `spectrometer_geometry` was missing from
that list. The behaviour was always correct (the prefix test covers the whole namespace); only the
prose undercounted. It is corrected in the same change as this file, so at this commit the docstring
names six (`apps/api/isaac_api/workspace.py:539-541`).

**Two, recorded and NOT fixed here, because it is a code change and this is a docs-only change.** The
export route's description says a record with no runs is *"every record this API can currently
create"* (`apps/api/isaac_api/routes.py:3631`). Read in a sentence about export behaviour, that tells
a reader the fan-out branch is unreachable through the API. It is not: `POST
/experiments/{id}/runs` is an ordinary ungated route and the suite asserts a `201` from it (see §5).
Charitably the phrase means only that a *newly created* record starts with no runs, which is true —
but as written it is the sentence that made the false claim in §5 easy to believe. Worth a one-line
fix in whichever slice next touches `routes.py`.

---

## 7. How to answer

A one-line reply per field is enough — `run`, `experiment`, or `unknown`. No prose is needed.

Whoever implements the answer must:

1. add the path to `EXPERIMENT_LEVEL_FIELD_PATHS` or `RUN_LEVEL_FIELD_PATHS` in `workspace.py`;
2. **update the two artifacts that encode today's answer, or CI fails on either answer.**
   `test_every_field_map_path_the_real_extractor_emits_is_classified_or_knowingly_not`
   (`apps/api/tests/test_run_domain_model.py:349`) asserts a literal seven-item unclassified list
   (`:363-371`), so it breaks the moment any of the six leaves it; and `field_level`'s own docstring
   enumerates the six by name (`apps/api/isaac_api/workspace.py:539-541`), so it goes stale at the
   same moment;
3. **for a `run` answer specifically, expect two further failures, both measured.**
   `test_the_run_writable_paths_are_derived_from_the_extractor_field_map`
   (`apps/api/tests/test_run_api.py:1195`) pins `RUN_WRITABLE_FIELD_PATHS` as a literal five-member
   set (`:1214-1220`) — an ordinary update. The second is not:
   `test_every_run_writable_path_resolves_to_a_typed_node_in_the_official_schema` (`:1223`) walks
   every writable path through the schema's `properties` and asserts a declared `type`, which
   **fails** for all six, because `system.configuration` declares no `properties` at all:

```
.venv/bin/python -c "
import json
node = json.load(open('schema/isaac_record_v1.json'))
for seg in 'system.configuration.detector_model'.split('.'):
    props = node.get('properties')
    if not isinstance(props, dict):
        print('no properties at the segment before %r' % seg); break
    node = props[seg]
"
→ no properties at the segment before 'detector_model'
```

   That test is not one to relax: its own docstring explains that the official schema cannot enumerate
   a closed path set inside an open namespace. A `run` answer therefore also needs a decision about
   how an open-namespace path is admitted to the writable set, and that decision is a separate slice.
   The prose counts that state the current five would need updating too —
   `apps/web/src/lib/runFields.ts:5` ("Three fields") and `:10-12` ("CLOSED SET OF FIVE"),
   `apps/api/isaac_api/routes.py:2693-2694` ("All five members … `string` or `number` scalars"), and
   `apps/web/src/components/RunCard.tsx:282` ("the backend accepts five");
4. quote this document and the answer in the commit, since the classification is a recorded human
   judgement and not a derivation;
5. leave anything answered `unknown` exactly where it is — and read §5 first, because "leave it" has a
   measured cost on the fan-out path.
