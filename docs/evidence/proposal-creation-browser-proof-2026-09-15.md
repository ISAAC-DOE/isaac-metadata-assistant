# Creating an ingestion proposal from the website — browser proof, 2026-09-15

**What this closes.** The project owner reported: *"in terms of the experiment data ingestion
proposals — there's no way to actually add an ingestion proposal. I understand maybe it's not
hooked up to the backend, maybe it's blocked."* The implementing slice proved the route over HTTP
but reported **"No real-browser render of the form"** as a named gap. This document closes that
gap, and only that gap.

**Who measured it.** The orchestrator, not the implementer — I did not write any of the code under
test. Read the numbers as an independent check, not as a self-report.

## The premise the owner supposed, and what was actually true

He supposed the capability might be backend-blocked. It is not, and neither was it missing from
the client. Measured at `dbf9d121`:

* `POST /api/experiments/{id}/proposals` is registered and documented.
* `api.createProposal` **already existed** in `lib/api.ts`, with a **live caller** —
  `UnmappedNotesPanel`'s *"Propose a Value from This Note"*, shipped 2026-09-03.

So the defect was **discoverability**, not capability: that control sits inside one note's
collapsed action row and is **unreachable on a record with no notes**, which is precisely the state
the owner was in. The proposals panel itself carried a committed rule against having a create
control — *"a review surface that manufactured the queue it reviews would be reviewing itself"* —
which is the rule the owner ran into. It is now struck in place, not deleted.

## Setup

| | |
|---|---|
| branch under test | `feat/v2-propose` (`407bfbe4`), served from a throwaway worktree |
| backend | local `uvicorn`, fresh `ISAAC_UI_WORKSPACE`, `mode: synthetic-only` |
| record | created through `POST /api/experiments`, one run, five run fields filled |
| browser | real Chromium, driven live |

**Notes on the record at the start: zero.** That matters — it is the state in which the
pre-existing control was unreachable.

## What the browser showed

1. **`New Proposal` is present on the Experiment Data workspace** of a record holding no notes.
2. Opening it offers the guided pathway rather than a raw field-path box: *Cite a note this record
   already holds* / **Write a source note now**, with the second selected because there are none.
3. The target picker is populated from the server's own `target_field_paths` — **19 options** — and
   renders a human label with the dotted path demoted beside it, never instead of it
   (`Temperature — context.temperature_K`).
4. Choosing `sample.composition.CuO2_mass_fraction` made a **`Run this value is about`** control
   appear, because that target is run-scoped per the server's own split — not because a run happens
   to exist.
5. **`Store This Proposal` was DISABLED while no run was chosen**, and became enabled once one was.
   That is the negative control holding in a real browser and not only in jsdom.

## What the server held afterwards

```
proposals: 1
  target_field_path : sample.composition.CuO2_mass_fraction
  proposed_value    : 0.42
  run_id            : 01M2K017T5Z7Q5CG61PWHS5ZDG
  state             : open
  verified          : false
  is_evidence       : false
  is_field_value    : false
  status            : ingestion_proposal
notes: 1   "Beamline logbook, 2026-01-31: sample was CuO pellet."
```

**The three things that had to be true, and were:** the proposal is inert (`is_field_value:
false`, and the record's own field is unchanged); the scientist's verbatim words are stored as a
**note**, so they survive whether or not the proposal is ever accepted; and one act created both,
in one write.

## What this does NOT show

* **Nothing about acceptance.** Accepting a proposal answers `409 human_actor_required` in every
  default deployment, because no trusted authentication boundary exists (`EXT-01`). That is a
  configuration fact and no application change can close it. **Creation and acceptance must never
  be conflated**, and this proof is only about the first.
* **Nothing hosted.** `/krish` sits behind an Authentik edge this environment cannot authenticate
  to. Hosted QA remains `PENDING (Krish)`.
* **Nothing about narrow widths or 200% zoom.** `resize_window` reports success while the rendered
  viewport does not follow, and no CDP method can drive true browser zoom.

## One cosmetic defect found while measuring, not fixed here

The label humanizer renders `sample.geometry.pellet_diameter_mm` as **"Pellet Diameter Mm"**. The
unit suffix is title-cased as though it were a word. It is cosmetic, it is in the picker only, the
dotted path beside it is correct, and it is recorded rather than fixed because it belongs with the
humanizer and not with this proof.
