# Guesses fill, colour-coded review, answers carry over (28 Nov 2026)

Follows `docs/fill-first-design-2026-11-25.md` (slices 1–4, DEC-96–99). Owner: Krish. Scientist user: Angel, who
runs the skill himself on his own computer in the week of 1 Dec 2026.

## Why

Angel (25 Nov): the skill should find the obvious metadata from the folder name, sample names and logbook "without
further input, which is the whole point of the skill". On the reference beamtime after slice 4, 9 of the 10 blocking questions ask
a sample's material or form, and for every one where the skill had a guess, the guess matched Angel's answer. The
guesses could not fill because only `stated` readings fill (DEC-97).

Krish (28 Nov), the owner's direction this design implements:
- Inferred readings and other guesses are filled and the record is ready to send, but each guess is easy to tell
  apart and stays the scientist's decision: confirm it, change it, or leave it.
- Green means done and certain. A guess is never green. Colours: **green** = read word for word from the files, or
  answered / reviewed by the scientist; **yellow** = the skill's guess or deduction; **red** = needed and unknown.
- Two outputs: the ISAAC record itself, and a way for the scientist to go through every field of every record and
  see at a glance whether it looks right.
- Before submitting, a final check: "these N values are guesses, submit anyway?"
- An answer fills every other question it applies to: in the same beamtime, for related samples, and in later
  beamtimes.
- Never making up values stays: every guess carries evidence (a quoted line, a file, an earlier answer).

## Goals

1. **Guesses fill (yellow).** A new value state `guessed`, distinct from `filled` (rule-certain, green). Sources:
   - an AI reading of strength `inferred` whose quote is checked to exist in the cited file and which names this
     target (new rule `isaac.fill.reading_inferred.v1`);
   - an answer carried over from a related sample or an earlier beamtime (goal 4);
   - rule fills that are deductions rather than reads (per-rule table below).
   A guess never fills from a bare sample label as a material name (the slice 2 failure: 62 wrong values), never
   over a conflict, never over any scientist decision.
2. **Colour per value, everywhere.** One function maps every value's state to green / yellow / red; the review
   listing, status, the review page and the final check all use it.
   - green: `scientist_confirmed`, a parser-exact read, a stated quote-checked reading, folder + header agreement.
   - yellow: `guessed`, and `filled` values whose rule is a deduction (group from the folder PI name, organization
     from the facility).
   - red: a value the record needs that is missing, conflicting, or deferred.
   The per-rule assignment is in code next to `FILL_RULES` and tested; the builder decides edge cases and lists them.
3. **The review page (second output).** `isaac bundle review <bundle> --html` writes one local, self-contained page
   (`<bundle>/review/index.html`, no network, never uploaded): one section per record, every field with its colour,
   value, where it came from (quote + file + line, or "your answer", or "earlier beamtime X"), and the processed
   curve's plot when there is one, plus the scan keep/drop reasons. A summary at the top: counts per colour, the red
   items first. Plain colleague wording, no ids. Changes are made by telling Claude (the skill turns them into
   decisions) and the page is regenerated.
4. **Answers carry over.**
   - Same beamtime: an answer already covers every target in its scope. New: an answer about one sample is offered
     as a yellow guess to sibling samples whose evidence is the same (the same describing logbook line, or the
     same label family), never as green.
   - Earlier beamtimes: the opt-in local answer memory (`answer_memory.py`) fills yellow instead of only hinting,
     matched by the existing scopes (facility/beamline, same sample, same group). Opt-in stays.
   - Processing-method answers stay in the versioned protocol, not the memory.
5. **Final check before submit.** The upload step (dry run today) lists the yellow values, grouped by field with
   counts, and needs the scientist's explicit yes, bound to exactly that list (digest), like `review --accept`.
   Records with red values that the record needs do not upload. The skill says it in one plain question.
6. **Fewer stops.**
   - Record groups the grouping rule proposes with no problem are taken as the grouping (yellow, reviewable)
     instead of waiting for a confirmation; problem groups are still asked.
   - The potential scale (vs RHE etc.) becomes a must-answer question when potentials exist and nothing states it:
     potentials are a goal of the records, and a wrong scale is a scientific error.

## Slices

- **5a — built** as bundle format **1.22.0**, fill rule set 4 (`DEC-100`; contract §9 "What 1.22.0 added"): goal 1 for
  inferred readings (the value state `guessed`, rule `isaac.fill.reading_inferred.v1`, with the label-as-material and
  environment classes refused by rule), goal 2 (`bundle.value_colour` and its per-rule table; review, status and the
  final check use it), goal 5 (the final check in `bundle upload --dry-run`, `--guesses-ok <digest>`, the
  `submit_with_guesses` decision), and the potential-scale half of goal 6. The official schema has no record-level note,
  so the final check says the portal copy will not show which values were guesses.
- Later: goal 3 (the review page, `bundle review --html`), goal 4 (answers carry over), and the record-groups half of
  goal 6.

## Non-goals

- No change to the truth plane (`schema/`, `src/isaac_records/*`). The official record has no per-field status
  and `export_draft` refuses `needs_confirmation`, so a guess composes into the draft as `inferred` with the
  derivation rule naming it a guess; the guess marking lives in the draft, the evidence sidecar and the review
  page. If the official schema has a record-level free-text note, the guessed fields are listed there; if not, the
  final check says plainly that the portal copy will not show which values were guesses.
- No rebuild of Angel's question site (he has answered on it).
- No real data in the repo; synthetic fixtures only.

## Anti-goals

- A guess that looks green anywhere.
- A guess without evidence the scientist can see.
- More questions than before, or a final check that lists unchanged values as changed.

## Measuring it

`scripts/replay_fill_accuracy.py` against Angel's answers on the reference beamtime, plus another beamtime folder's own
metadata sheet as a second answer key: green-wrong must stay 0; yellow-wrong is reported and kept low; blocking
questions after the environment convention and the potential scale: target 0–2. A fresh session (only the skill and
the raw folder) is scored the same way.

## Approaches considered

- **A. Guesses fill as yellow with a final check (chosen by Krish).** Fastest to records, keeps the scientist's
  decision, shows every guess.
- B. One combined "samples table" question with the guesses pre-filled. Fewer wrong values reach the record, but
  still a stop before records; Krish preferred filling.
- C. Guesses fill green and rely on the end review. Rejected: green would no longer mean certain.
