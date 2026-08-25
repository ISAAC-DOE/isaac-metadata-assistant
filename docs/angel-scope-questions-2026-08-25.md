# Six fields need a scientist's answer — ISAAC Metadata Assistant

**For:** Angel (scientific domain owner). **From:** Krish Verma. **Date:** 2026-08-25.
**Measured against:** `main` = `625e4d1`.

**Nothing in this project is blocked on your answer.** No slice is waiting, no deadline
depends on it, and "we don't know yet" is a real answer that costs nothing new. This
document exists because the alternative to asking is guessing, and guessing a scientific
fact into a metadata standard is the one thing this assistant is built not to do.

**One question, asked six times:**

> *May two measurement runs of the same experiment legitimately hold **different** values
> for this field?*

Answer `same for the whole experiment` / `can differ per run` / `don't know` for each. One
word per field is enough — no prose needed.

---

## 1. The six questions

The official ISAAC schema v1.05 puts all six in one place: `system.configuration`. It is
the schema's **designated open extension namespace**, and this is the whole of what the
schema says about any of them (there is no per-field description and no per-field type —
see §3.1):

> *"THE designated open extension namespace: instrument/station/beamline-specific
> configuration that does not generalize across facilities (slits, pass energies, GC
> columns, channel IDs, logbook fields...). Anything that DOES generalize belongs in a
> schema field — request one."*

So the schema is deliberately silent on scope. It tells us these fields are allowed to
exist; it does not tell us whether they describe a whole experiment or a single scan.
That is the gap only a scientist can close.

### Group A — four instrument settings

| Field | The question |
|---|---|
| **`detector_model`** | If a detector is swapped or a second detector is used partway through an experiment, is that still *one* experiment with two runs — or is it a different experiment? If it can, ISAAC needs a way to record that divergence run by run. |
| **`monochromator_crystal`** | Same shape. Would you change the mono crystal (e.g. between Si(111) and Si(311)) within a single experiment and still consider the runs part of one dataset? |
| **`spectrometer_geometry`** | Same shape. Is the geometry (e.g. Von Hámos, Rowland) fixed for the duration of an experiment in practice, or is it something that can change between runs? |
| **`n_scans`** | This one may be a naming problem rather than a scope problem. Is "number of scans" **the count for one measurement condition** (so each run has its own), or **a total for the experiment**? If the former, does it need a clearer name in ISAAC? |

*ISAAC currently reads all four from a `Configurations` section of a campaign metadata
sheet — measured, §3.2. The bracketed examples above are illustrative prompts, not claims
about your instruments.*

### Group B — two administrative identifiers

These are **not** instrument settings, and the difference matters (§2).

| Field | The question |
|---|---|
| **`proposal_id`** | What does an SSRL proposal cover? Can a single experiment — as a scientist would define an experiment — span **two** proposals? If not, this belongs to the experiment. |
| **`session_id`** | What does a beamtime session cover? Can a single experiment span **two** sessions (e.g. a run on Monday and a continuation on Wednesday, same sample, same question)? If it can, this has to be recordable per run — otherwise the records lose which runs happened when. |

*ISAAC currently reads both from a `Campaign Info` section of the same sheet — measured, §3.2.*

**These two may not be yours at all.** If proposal and session scope is facility
bookkeeping rather than a scientific judgement, the right answer may be Dean's, or a
pointer to whoever owns SSRL's proposal/session definitions. Saying "ask someone else" is
a useful answer.

### What each answer would change, in one table

The consequence is the same shape for all six.

| Your answer | What ISAAC would do | What it costs if it turns out to be wrong |
|---|---|---|
| **Same for the whole experiment** | Entered once on the record; every run inherits it; a run that genuinely differed records an audited *override* that keeps the displaced value visible. | Recoverable. A run that actually differed gets an override. |
| **Can differ per run** | Each run gets its own field on the Run screen; each run's exported record carries its own value. | Harder. The same value gets re-typed on every run, and nothing compares the entries, so a typo in one run silently produces a wrong record. |
| **Don't know** | Nothing changes — which is not neutral: today all six are **dropped** from every exported record of any experiment that has runs (§3.3). | The values a scientist entered vanish from the published records, silently, and the records still validate. |

The override machinery in the first row is real and shipped — `POST
…/runs/{id}/overrides` plus a scientist-facing control, merged in PR #122 (`a69c9d7`,
2026-08-11, confirmed an ancestor of `625e4d1` by `git merge-base --is-ancestor`). That is
why a "same for the whole experiment" answer is the cheaper one to be wrong about. **It is
not an argument for defaulting everything to experiment-level** — an override is meant to
be a deliberate, audited act, not routine data entry.

One engineering caveat, stated so it does not look like a hidden preference: a **"can
differ per run"** answer needs one extra decision on our side, because a guard test
(`test_every_run_writable_path_resolves_to_a_typed_node_in_the_official_schema`,
`apps/api/tests/test_run_api.py:1316`) requires every per-run-writable path to resolve to a
schema-declared type, and none of the six does — `system.configuration` declares no
`properties` at all (§3.1). That is our problem to solve, not a reason to prefer the other
answer.

---

## 2. The one distinction that matters

**`proposal_id` and `session_id` are administrative identifiers. The other four are
settings of a physical instrument.** Grouping all six as "the instrument and detector
settings" under-states what is being dropped, and this application made exactly that
mistake in its own user-facing copy until it was corrected.

Two independent pieces of evidence, both from source rather than from prose:

1. **The campaign sheet already separates them.** The four instrument settings are rows in
   a `Configurations` section; the two identifiers are rows in a `Campaign Info` section,
   alongside facility, beamline and technique — measured, §3.2.
2. **The correction is recorded in the code.** `apps/web/src/lib/mcpConnectContent.ts`
   carries the finding in the comment above the copy it fixed:

   > *"A reader who accepted 'instrument and detector settings' would not expect the
   > proposal a record belongs to, or the beamtime session it was taken in, to be dropped
   > from a record exported per run; those are exactly the fields somebody looks for when
   > reconciling a run against a beamtime schedule."*

Why it changes the question rather than just the wording: for the four instrument
settings, "can two runs differ?" is a question about **what happens at the beamline**. For
the two identifiers, it is a question about **how the facility defines a proposal and a
session** — a different kind of fact, held by different people, and possibly not a
scientific judgement at all.

---

## 3. What is true today — measured, not asserted

Everything in this section is the output of a command. §3.5 gives the one script that
produces §3.1 – §3.4 in a single run, so a reader can re-measure rather than trust this
page. All of it was run against a clean checkout of `main` = `625e4d1`.

### 3.1 ISAAC has not classified any of them, and the schema declares nothing at these paths

```
$ .venv/bin/python -c "
import json
cfg = json.load(open('schema/isaac_record_v1.json'))['properties']['system']['properties']['configuration']
print(sorted(cfg.keys()), 'properties' in cfg)
print(json.load(open('schema/isaac_record_v1.json'))['properties']['system'].get('required'))"
['description', 'type'] False
['domain', 'technique']
```

`system.configuration` declares a `type` and a `description` and **no `properties`** — so
the schema declares no type and no description for any of the six individually, and
`configuration` is not a required member of `system`. Anything this document says about a
field's *type* (e.g. `n_scans` is an integer) comes from ISAAC's own extractor, **not** from
the schema.

And ISAAC's own classifier returns a third answer — neither level — for all six. Verbatim
output of section `== 1.` of the §3.5 script:

```
== 1. how ISAAC classifies each ==
  detector_model                                 unclassified
  monochromator_crystal                          unclassified
  spectrometer_geometry                          unclassified
  n_scans                                        unclassified
  proposal_id                                    unclassified
  session_id                                     unclassified
```

`unclassified` is a deliberate state, not an oversight — `apps/api/isaac_api/workspace.py`,
`field_level`'s docstring says so in capitals and points at this question.

### 3.2 Where the values come from today

The only producer is the deterministic extractor, `src/isaac_records/extract/structured.py`,
which maps a named sheet row to an official path:

```
$ PYTHONPATH=src:apps/api .venv/bin/python -c "
from isaac_records.extract import structured
for k, v in sorted(structured.FIELD_MAP.items()):
    if v[0].startswith('system.configuration.'): print(repr(k), '->', v)"
'detector_model' -> ('system.configuration.detector_model', <class 'str'>)
'monochromator_crystal' -> ('system.configuration.monochromator_crystal', <class 'str'>)
'n_scans' -> ('system.configuration.n_scans', <class 'int'>)
'proposal_id' -> ('system.configuration.proposal_id', <class 'str'>)
'session_id' -> ('system.configuration.session_id', <class 'str'>)
'spectrometer_geometry' -> ('system.configuration.spectrometer_geometry', <class 'str'>)
```

And the sheet itself splits them into two sections — this is the §2 distinction, in the
committed synthetic fixture (`SYN-`/`2099` values are deliberately fake):

```
$ grep -nE 'proposal_id|session_id|detector_model|monochromator_crystal|spectrometer_geometry|n_scans' \
    tests/fixtures/synthetic/mock_campaign.csv
8:Campaign Info,proposal_id,SYN-2099-000,,fake proposal id
9:Campaign Info,session_id,2099_run_000,,fake beamline session
25:Configurations,monochromator_crystal,Si(311),,
26:Configurations,spectrometer_geometry,Von_Hamos,,
27:Configurations,detector_model,Pilatus_100K,,
30:Configurations,n_scans,6,,
```

**There is no way for a scientist to type any of the six into the product.** Every write
surface refuses them, and the refusals are typed and honest rather than silent (`== 2.`
in §3.5):

| Surface | Result |
|---|---|
| `POST /api/experiments/{id}/answers` | `422 unrecognized_field` |
| `POST /api/experiments/{id}/edit` | `422 unrecognized_field` |
| `PATCH /api/experiments/{id}/runs/{run_id}` | `422 unrecognized_field` |
| `POST …/runs/{run_id}/overrides` | `422 not_overridable` |
| `POST /api/uploads` | `403` — upload is approval-gated |
| **control:** a run-level path (`context.temperature_K`) on the same PATCH route | **`200`** |

Verbatim output of section `== 2.` of the §3.5 script:

```
== 2. can a scientist TYPE one? every write surface, one probe each ==
  POST .../answers            -> 422 unrecognized_field
  POST .../edit               -> 422 unrecognized_field
  PATCH .../runs/{id}         -> 422 unrecognized_field
  POST .../overrides          -> 422 not_overridable
  POST /api/uploads           -> 403 Real or private data upload is approval-
  CONTROL: a run-LEVEL path on the same route -> 200
```

The control matters: the same route accepts a classified field, so the refusal is about
these six specifically and not about the request being malformed.

The values therefore reach a record today only through the committed worked-example sheet
(and the offline `isaac draft` CLI). In the application, `build_draft` is called with the
committed fixture paths and nothing else:

```
$ grep -rn "build_draft(" apps/api/isaac_api/*.py
apps/api/isaac_api/routes.py:1451:    draft = build_draft(ws.CSV_PATH, ws.LISTING_PATH)
apps/api/isaac_api/workspace.py:3790:    return build_draft(CSV_PATH, LISTING_PATH)
apps/api/isaac_api/workspace.py:3797:    return apply_answers(build_draft(CSV_PATH, LISTING_PATH), partial)
apps/api/isaac_api/workspace.py:3802:    return apply_answers(build_draft(CSV_PATH, LISTING_PATH), copy.deepcopy(load_demo_answers()))
apps/api/isaac_api/workspace.py:3815:    return apply_answers(build_draft(CSV_PATH, LISTING_PATH), answers)
```

### 3.3 On export, they survive a record with no runs and are dropped from a record with runs

One ISAAC record is published per run. The worked example that carries all six, exported
twice — once as-is, once after adding a single run (`== 3.` in §3.5):

```
== 3. what happens on export, with and without a Run ==
  runs=0 export ok=True
     record  system.configuration key present = True -> {"proposal_id": "SYN-2099-000", "session_id": "2099_run_000", "monochromator_crystal": "Si(311)", "spectrometer_geometry": "Von_Hamos", "detector_model": "Pilatus_100K", "n_scans": 6}
     record  system.technique     = "HERFD-XAS"  (experiment-level control)
     record  context              = {"environment": "ex_situ", "temperature_K": 298, "thermodynamics": {"atmosphere": "air"}}  (run-level control)
     sidecar carries the six      = 6 / 6
  runs=1 export ok=True
     record  system.configuration key present = False (the key is ABSENT, not null)
     record  system.technique     = "HERFD-XAS"  (experiment-level control)
     record  context              = {"environment": "ex_situ", "temperature_K": 298, "thermodynamics": {"atmosphere": "air"}}  (run-level control)
     sidecar carries the six      = 0 / 6
```

**Read the two control rows.** An experiment-level field and a run-level field both survive
adding a run. The six do not, precisely because they are neither: an unclassified field is
inherited by nobody.

They are also absent from the **evidence sidecar**, so the loss is not recoverable from the
audit artifact either — and all six were `verified`, each with an evidence entry, on the
record beforehand:

```
$ PYTHONPATH=src:apps/api .venv/bin/python -c "
import os, tempfile; os.environ['ISAAC_UI_WORKSPACE'] = tempfile.mkdtemp()
import isaac_api.workspace as ws
sid, _ = ws.create_tutorial_session()
f = ws.load_experiment(ws.SEED_READY_ID, session_id=sid).draft['fields']
for k in ('detector_model','monochromator_crystal','spectrometer_geometry','n_scans','proposal_id','session_id'):
    e = f['system.configuration.' + k]
    print('%-24s %-14r %-10s evidence=%d' % (k, e['value'], e['status'], len(e['evidence'])))"
detector_model           'Pilatus_100K' verified   evidence=1
monochromator_crystal    'Si(311)'      verified   evidence=1
spectrometer_geometry    'Von_Hamos'    verified   evidence=1
n_scans                  6              verified   evidence=1
proposal_id              'SYN-2099-000' verified   evidence=1
session_id               '2099_run_000' verified   evidence=1
```

### 3.4 The record with the six missing is still a valid official ISAAC record

```
== 4. and the record with the six missing still validates ==
  official ISAAC v1.05 validation ok = True
```

This is the reason the question is worth asking rather than leaving: because
`system.configuration` is optional and open, nothing downstream flags the loss. A record
that lost its detector model, its mono crystal and its proposal id passes official
validation and looks complete.

The two facts in §3.3 are pinned by tests, so this page cannot go quietly stale:

```
$ PYTHONPATH=src:apps/api .venv/bin/pytest apps/api/tests/test_run_seeding.py -k six_unclassified -q
2 passed, 20 deselected, 1 warning in 0.89s
```

### 3.5 The one script behind §3.1 – §3.4

Sections `== 1.` to `== 4.` above are its verbatim output. Run it from the repository
root at `625e4d1`. It touches no database and no network; it
creates a throwaway workspace in a temporary directory.

```python
# PYTHONPATH=src:apps/api .venv/bin/python <this file>
import json, os, tempfile
os.environ["ISAAC_UI_WORKSPACE"] = tempfile.mkdtemp()
os.environ.pop("ISAAC_UI_API_KEY", None)
from fastapi.testclient import TestClient
from isaac_api.app import create_app
import isaac_api.workspace as ws

SIX = ["system.configuration.detector_model", "system.configuration.monochromator_crystal",
       "system.configuration.spectrometer_geometry", "system.configuration.n_scans",
       "system.configuration.proposal_id", "system.configuration.session_id"]

print("== 1. how ISAAC classifies each ==")
for p in SIX:
    print("  %-46s %s" % (p.split(".")[-1], ws.field_level(p)))

c = TestClient(create_app())
P = "system.configuration.detector_model"

print("== 2. can a scientist TYPE one? every write surface, one probe each ==")
e = c.post("/api/experiments", json={"title": "probe"}).json()["id"]
V = lambda: c.get("/api/experiments/%s" % e).json()["version"]
r = c.post("/api/experiments/%s/answers" % e, json={"answers": {P: "Vortex ME4"}, "confirmed_by_user": True},
           headers={"If-Match": '"%s"' % V()})
print("  POST .../answers            ->", r.status_code, r.json().get("error"))
r = c.post("/api/experiments/%s/edit" % e, json={"answers": {P: "Vortex ME4"}, "confirmed_by_user": True},
           headers={"If-Match": '"%s"' % V()})
print("  POST .../edit               ->", r.status_code, r.json().get("error"))
rid = c.post("/api/experiments/%s/runs" % e, json={"label": "A"},
             headers={"If-Match": '"%s"' % V()}).json()["run"]["id"]
RV = lambda: c.get("/api/experiments/%s/runs/%s" % (e, rid)).headers["etag"]
r = c.patch("/api/experiments/%s/runs/%s" % (e, rid), json={"fields": {P: "Vortex ME4"}, "confirmed_by_user": True},
            headers={"If-Match": RV()})
print("  PATCH .../runs/{id}         ->", r.status_code, r.json().get("error"))
r = c.post("/api/experiments/%s/runs/%s/overrides" % (e, rid),
           json={"address": "field:" + P, "value": "Vortex ME4", "confirmed_by_user": True},
           headers={"If-Match": RV()})
print("  POST .../overrides          ->", r.status_code, r.json().get("error"))
r = c.post("/api/uploads", files={"file": ("s.csv", b"a,b\n1,2\n", "text/csv")})
print("  POST /api/uploads           ->", r.status_code, r.json().get("reason", "")[:40])
r = c.patch("/api/experiments/%s/runs/%s" % (e, rid),
            json={"fields": {"context.temperature_K": 300}, "confirmed_by_user": True},
            headers={"If-Match": RV()})
print("  CONTROL: a run-LEVEL path on the same route ->", r.status_code)

print("== 3. what happens on export, with and without a Run ==")
for add_run in (False, True):
    cc = TestClient(create_app())
    sid = cc.post("/api/tutorial/sessions").json()["session_id"]
    H = {"X-Isaac-Tutorial-Session": sid}
    X = ws.SEED_READY_ID
    v = lambda: cc.get("/api/experiments/%s" % X, headers=H).json()["version"]
    if add_run:
        cc.post("/api/experiments/%s/runs" % X, json={"label": "300 K"},
                headers=dict(H, **{"If-Match": '"%s"' % v()}))
    ok = cc.post("/api/experiments/%s/export" % X, headers=dict(H, **{"If-Match": '"%s"' % v()})).json()["ok"]
    exp = ws.load_experiment(X, session_id=sid)
    for u in exp.export_units():
        rec = json.loads(u.record_path().read_text())
        side = u.record_path().with_suffix(".evidence.json").read_text()
        print("  runs=%d export ok=%s" % (len(exp.runs), ok))
        present = "configuration" in rec["system"]
        print("     record  system.configuration key present =", present,
              ("-> " + json.dumps(rec["system"]["configuration"])) if present else "(the key is ABSENT, not null)")
        print("     record  system.technique     =", json.dumps(rec["system"].get("technique")), " (experiment-level control)")
        print("     record  context              =", json.dumps(rec.get("context")), " (run-level control)")
        print("     sidecar carries the six      =", sum(p.split('.')[-1] in side for p in SIX), "/ 6")

print("== 4. and the record with the six missing still validates ==")
import pathlib
from isaac_records.official import validate_official
rep = validate_official(json.loads(exp.export_units()[0].record_path().read_text()), pathlib.Path.cwd())
print("  official ISAAC v1.05 validation ok =", rep.ok if hasattr(rep, "ok") else rep["ok"])
```

---

## 4. What is *not* being asked

- **Not a schema change.** `system.configuration` is the official schema's designated open
  namespace and these six already live there legitimately. Nothing here proposes editing
  the ISAAC schema, and if any of the six *should* become a first-class schema field, that
  is a separate conversation with the ISAAC schema owners, not this one.
- **Not a deadline.** There is no date attached and no work waiting. Since this question
  was first written down (2026-08-10) the application has gained per-run overrides
  (`RunInheritedPanel.tsx`), revision history (`RevisionHistoryPanel.tsx`), a submission
  lifecycle (`submission_store.py`), explicit conflict resolution (`conflict_resolution.py`)
  and run comparison (`RunCompare.tsx`) — all five modules present at `625e4d1` — none of
  which needed an answer.
- **Not a request for a recommendation to rubber-stamp.** This project deliberately holds
  **no** recommendation on any of the six. Nothing in the repository is evidence about
  beamline practice, so any preference stated here would be a guess wearing a
  recommendation's clothes.
- **Not all-or-nothing.** The six can be answered independently, and any of them can be
  answered "don't know". A field left unanswered keeps behaving exactly as §3 describes.
- **Not a claim that the current behaviour is acceptable.** It is the honest default, not
  a good outcome. §3.3 is what it costs.

---

## 5. Provenance of this document

This supersedes [`docs/run-scope-decision-packet.md`](run-scope-decision-packet.md)
(2026-08-10, re-measured 2026-08-18 and 2026-08-19) as the document to send. That file is
**not** withdrawn — it holds the engineering detail, the implementation checklist for
whoever acts on an answer, and the record of two earlier corrections — but it had grown to
452 lines of programme history (`wc -l`, before the pointer this change adds to it) behind
three stacked revision preambles, and it is not a document to put in front of a domain
expert.

**Two things in the older packet are out of date, and are corrected rather than repeated:**

1. It says the scientist-facing override UI is *"open and under review — do not read this
   bullet as claiming it has shipped"* (§4.1, §5). **It has shipped**: PR #122 merged as
   `a69c9d7` on 2026-08-11 (`git merge-base --is-ancestor a69c9d7 625e4d1` → true), and
   `apps/web/src/components/RunInheritedPanel.tsx` renders the override control. This makes
   an "experiment-level" answer cheaper to be wrong about than that packet's §4 table
   assumes.
2. It reports the fan-out result as `exported record system.configuration -> null`. The key
   is **absent from the exported record**, not present-and-null — an artefact of reading it
   with `.get()`. Measured in §3.3.

Its substantive conclusions all re-measure as correct at `625e4d1`, including the
classification, the drop on export, and the absence of any evidence in this repository
about SSRL proposal or session scope.

