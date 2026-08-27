# `system.domain` needs a scientist's answer — ISAAC Metadata Assistant

**For:** Angel (scientific domain owner). **From:** Krish Verma. **Date:** 2026-08-27.
**Measured against:** `main` = `7668bf8`, except §3.3, **re-measured 2026-08-27 at the branch
HEAD that carries this page** — see the two corrections there.

**This is a successor to [`angel-scope-questions-2026-08-25.md`](angel-scope-questions-2026-08-25.md),
not a replacement.** That document asks one question about six `system.configuration.*`
fields. Those six remain **unresolved** and are still worth answering; nothing here
supersedes them, and §4 restates their status so this page can be forwarded on its own.

**Nothing in this project is blocked on your answer.** No slice is waiting. "Leave it as
it is" is a real answer and is the option ISAAC has **decided on**, for the reason in §3.
~~"is in fact the option ISAAC has already implemented"~~ — **CORRECTED 2026-08-27, before
sending, and corrected in place because a present-tense implementation claim is exactly what a
reader acts on.** Nothing implements it yet: the branch carrying this document touches neither
`apps/api/isaac_api/inferability.py` nor any `system.domain` write path, so §3.3's trap is the
live behaviour. See §3.4.

> **IMPLEMENTATION STATUS, IN ONE PLACE, BECAUSE THIS PAGE ASSERTED THE OPPOSITE IN FOUR OF
> THEM.** Everything §3.4 and §4 describe as *"ask the scientist"* is a **decision that has been
> taken and NOT YET BUILT**. What runs today is §3.3: `system.domain` has no write path at all,
> and a record that names a technique cannot be exported and cannot be un-blocked from inside the
> product. Re-derive rather than trusting this box —
> `git log --oneline 7668bf8..HEAD -- apps/api/isaac_api/inferability.py` is empty.

---

## 1. The question

The official ISAAC schema v1.05 declares `system.domain` as a two-value enum:

```json
{ "type": "string", "enum": ["experimental", "computational"] }
```

and it declares `system` as requiring **both** `domain` and `technique`:

```
$ .venv/bin/python -c "
import json; s=json.load(open('schema/isaac_record_v1.json'))
print(s['properties']['system']['required'])"
['domain', 'technique']
```

So the moment a record says *anything* about the system — a technique, a facility, an
instrument — the schema also requires it to say whether the work was experimental or
computational.

**The question is one sentence:**

> *Should ISAAC derive `system.domain` automatically from the technique, or should it ask
> the scientist?*

And, only if your answer is "derive it":

> *Which of the 37 techniques in the schema's `system.technique` enum are `computational`?*

---

## 2. Why this cannot be answered by reading the schema

The schema enumerates 37 techniques and says nothing at all about which of them are
computational:

```
$ .venv/bin/python -c "
import json; s=json.load(open('schema/isaac_record_v1.json'))
t=s['properties']['system']['properties']['technique']['enum']
print(len(t)); print(t)"
37
['XAS', 'HERFD-XAS', 'XES', 'RIXS', 'XPS', 'XRF', 'XRD', 'SAXS', 'WAXS', 'PDF',
 'neutron_reflectometry', 'neutron_diffraction', 'SANS', 'cyclic_voltammetry',
 'chronoamperometry', 'chronopotentiometry', 'EIS', 'linear_sweep_voltammetry',
 'TEM', 'SEM', 'AFM', 'STM', 'DFT', 'ab_initio_MD', 'classical_MD',
 'kinetic_monte_carlo', 'microkinetic_modeling', 'machine_learning_potential',
 'GC', 'HPLC', 'ICP_MS', 'ICP_OES', 'NMR', 'mass_spectrometry', 'FTIR',
 'Raman', 'UV_Vis']
```

A technique→domain map is a **37-entry scientific classification that exists nowhere in
this repository and nowhere in the official schema.** Authoring one would mean this
software deciding a scientific fact, which is the one thing it is built not to do.

**Some entries are obvious and some are genuinely not.** `XAS` is experimental; `DFT` is
computational. But `machine_learning_potential` can be fitted to experimental data and
then used computationally, and `microkinetic_modeling` is modelling built on measured
rate constants. Whether those are `computational` records, `experimental` records, or a
case the two-value enum does not cleanly cover is a judgement, not a lookup. **It is
precisely the handful of hard cases that makes the map a scientific decision rather than
a clerical one** — a map that is right for 31 of 37 and silently wrong for 6 is worse
than no map, because every record it touches still validates.

---

## 3. What ISAAC does today, and the defect that prompted this

### 3.1 There is one derivation rule, and it does not use technique at all

ISAAC already derives `system.domain` in one narrow case. The rule keys on how the record
was **sourced**, not on what technique it used:

`src/isaac_records/extract/draft_builder.py:99-119` — when `meta.source_type == "facility"`:

> *"A facility-source record is by definition an experiment: the enum is
> experimental|computational and a physical facility is never computational."*

It is stored with `"status": "inferred"` and a derivation-rule evidence entry, never as a
verified value.

**That rule is sound and is not what this question is about.** It covers records built by
the extractor from a facility spreadsheet. It says nothing about a record a scientist
creates in the product, which has no `meta.source_type`.

### 3.2 The same rule exists twice, with opposite confirmation postures

`apps/api/isaac_api/inferability.py:650-701` wraps the same rule. Its docstring says it
wraps the derivation *"unchanged"* — **and that word is measurably wrong.** It returns
`requires_user_confirmation=True` and explains *"It still requires your confirmation
before it is stored"*, where `draft_builder` stores the value directly.

This is a documentation defect rather than a product defect, because
`inferability.system_domain` **has no production caller** — the module's own docstring
says so, and its public entry point can only ever return `NEEDS_USER_INPUT` or
`NOT_INFERABLE`. ~~"It is corrected in the same change that ships this document."~~ —
**CORRECTED 2026-08-27: it is NOT YET corrected.** No change on the branch carrying this document
touches `inferability.py`. It is recorded here so that a reader who finds both expressions knows
which one runs — `draft_builder`'s, which stores the value directly.

### 3.3 The defect: the product accepts an input that makes a record un-exportable

Measured end-to-end over HTTP (FastAPI `TestClient` on `create_app()`, a fresh
`ISAAC_UI_WORKSPACE`), on an experiment created through `POST /api/experiments` with one run.
**Re-measured 2026-08-27 at this branch's HEAD, and two of the three rows are corrected below —
the original table was right about the outcome and wrong about the detail in both.**

| step | result |
|---|---|
| write `system.technique = "XAS"` with user-confirmation evidence, via `POST .../runs/{id}/overrides` | **`200`** — accepted |
| write `system.domain = "experimental"` — all five write routes, each measured | **`422` from every one of them.** The **status** generalises; the typed `error` does **not** — see the table below |
| `POST /export`, before the technique write | **`ok: false`** — `[{"path": "$", "message": "'descriptors' is a required property"}]` |
| `POST /export`, after the technique write | **`ok: false`** — **two** errors: `{"path": "$", "message": "'descriptors' is a required property"}` **and** `{"path": "system", "message": "'domain' is a required property"}` |

**Correction 1 — the typed error was true of one route in five.**
~~"**`422 not_overridable`** — *'This address cannot hold a run override.'*"~~ was quoted as
though it were the answer from all five. It is the answer from the override route alone; the
other four answer `422 unrecognized_field`. Measured, one row per route:

| route | status | `error` |
|---|---|---|
| `POST /api/experiments/{id}/runs/{run_id}/overrides` | `422` | `not_overridable` |
| `POST /api/experiments/{id}/answers` | `422` | `unrecognized_field` |
| `POST /api/experiments/{id}/edit` | `422` | `unrecognized_field` |
| `POST /api/experiments/{id}/runs/{run_id}/answers` | `422` | `unrecognized_field` |
| `POST /api/experiments/{id}/runs/{run_id}/edit` | `422` | `unrecognized_field` |

The narrative claim is unaffected — every route refuses, and the record stays trapped — but the
quoted body was evidence for a stronger, more specific statement than the measurement supported.
**The same false generalisation is in the message of commit `8994525`**, which is pushed and
cannot be edited; this table is the correction of record.

**Correction 2 — the export row quoted one of two errors, and the one it quoted is not the
first.** `'descriptors' is a required property` is present **before** the technique write and has
nothing to do with `system.domain`. Two things follow, and they cut in opposite directions, so
both are stated: the un-exportability of a *fresh* record is **not** caused by this defect; and
`descriptors` is **separately open and IS answerable** — it is a live blocking question
(`id: "descriptor"`) that the guided completion flow asks and a scientist can clear.
`system.domain` is the one that cannot be cleared, by anything, from inside the product. The
table as originally printed implied the domain error was the whole output and the sole cause.

So a scientist who records the technique they used has, by that act, added a blocker they cannot
clear, with no control anywhere in the product that can clear it. `system.domain` has **no write
path at all**.

### 3.4 What ISAAC has decided to do about it, and why it is not the answer to this question

**The decision taken:** ISAAC **asks the scientist**, offering the schema's own two
values, and stores the answer as a user-confirmed value. That is not a scientific decision
by the software — the scientist is the authority and the enum is the schema's. It un-traps
the record and invents nothing.

**Implementation status, stated rather than implied — corrected 2026-08-27.**
~~"the change that implements it ships alongside this document"~~ — **NO CODE ON THIS BRANCH
IMPLEMENTS IT.** §3.3's trap is the live behaviour and remains so until a separate change ships.
This is the decision; it is not a description of a deployed product, and it is not a description
of an unmerged branch either. The correction was found by an independent audit, not by the
author, and the disclaimer as originally written was itself part of the problem twice over: it
said the change "ships alongside", which reads as *merged with*, and it sat here in §3.4 while
§1, the §4 table and §6 each carried the same claim without it. Verify rather than trust:
`git log --oneline 7668bf8..HEAD -- apps/api/isaac_api/inferability.py` is empty, and no file on
this branch touches a `system.domain` write path.

**ISAAC deliberately does not derive the value from the technique**, and that is the
decision this page is asking you about. Leaving it as "ask the scientist" is a perfectly
good outcome — it is simply one more question per record.

---

## 4. What each answer would change

**None of these is built yet.** Every row below describes what ISAAC *would* do; the column
headed *"What ISAAC would do"* is future tense on purpose, including for the row marked as the
decision taken. What runs today is §3.3. (This caveat is repeated here, and in §6, because an
earlier revision of this page carried it only in §3.4 while three other sections asserted the
opposite.)

| Your answer | What ISAAC would do | What it costs if it turns out to be wrong |
|---|---|---|
| **Ask the scientist** *(the decision taken; **not implemented** — see §3.4)* | One extra question, once per record, from a two-value list. Stored as a user-confirmed value with evidence. | Low. A wrong answer is one scientist's error on one record, visible in the evidence trail and correctable. |
| **Derive it from technique** | We would store your 37-entry map, apply it automatically, and mark the value `inferred` rather than `verified` — the same posture `draft_builder` already uses — so a scientist can still see and override it. | Higher, and quiet. A misclassified technique produces a wrong `domain` on **every** record using it, and the record still validates, so nothing surfaces the error. |
| **Derive it, but only for the unambiguous techniques** | Same as above for the ones you name; the rest fall back to the question. | Lowest of the two derivation options. It needs you to name which are unambiguous, which is the actual work. |
| **Don't know / not my call** | Nothing changes. The question stays, and this page stays open. | Nothing. This is a real answer. |

If you do want a map, the useful reply is just a list — *"these N are computational, the
rest are experimental"* — or the reverse, whichever is shorter. No prose needed.

---

## 5. The six `system.configuration.*` fields are still open

Restated so this page can be forwarded alone. Full detail, with the same measured-not-
asserted discipline, is in
[`angel-scope-questions-2026-08-25.md`](angel-scope-questions-2026-08-25.md).

One question, asked six times: *may two measurement runs of the same experiment
legitimately hold **different** values for this field?*

| Field | Group | Status |
|---|---|---|
| `system.configuration.detector_model` | instrument setting | **unclassified, unresolved** |
| `system.configuration.monochromator_crystal` | instrument setting | **unclassified, unresolved** |
| `system.configuration.spectrometer_geometry` | instrument setting | **unclassified, unresolved** |
| `system.configuration.n_scans` | instrument setting | **unclassified, unresolved** |
| `system.configuration.proposal_id` | administrative identifier | **unclassified, unresolved** |
| `system.configuration.session_id` | administrative identifier | **unclassified, unresolved** |

The 2026-08-25 page notes that the two administrative identifiers may not be a scientific
judgement at all, and that *"ask someone else"* is a useful answer for them.

---

## 6. How to reply

Any of these is a complete answer:

- *"Ask the scientist — don't derive it."*
- *"Derive it: these are computational — DFT, …"* (a list is enough)
- *"Not my call — ask <name>."*
- *"Don't know."*

And, separately, the six fields above: one word each, or *"still don't know"*.

**One last status note, so it is on the page you are most likely to reply from:** the
*"ask the scientist"* behaviour this page describes is a **decision, not a shipped feature**. As
of this page's date `system.domain` has no write path in the product at all (§3.3). Your answer
does not unblock it and nothing is waiting on you — but nor should you read anything here as a
description of what the software does today.
