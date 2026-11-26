# Fill first, review at the end (design, 2026-11-25)

Status: **decided by the project owner (Krish), 2026-11-25.** This document says how it is built.

## Why

A beamline scientist answered every blocking question of a real BL15-2 beamtime on the question site:
24 cards, 23 of them with a suggestion, every suggestion correct. Each one rested on evidence the
import already held:
- a file header (the emission spectrometer motor);
- the readme;
- the folder name;
- a logbook line, quoted and checked.

His verdict: the skill should find this itself, "without further input, which is the whole point of
the skill".

The owner's decision:
- **Don't ask obvious or inferred questions.**
- Fill those values from the evidence, and ask only:
  - what the skill does not know (nothing states it, or the sources disagree);
  - what needs the scientist's qualitative judgment.
- **At the end, the scientist reviews the final records** and changes anything.
- Shortest time to a record, without giving up accuracy.

## What changes, and what does not

**The truth plane is unchanged:** `schema/`, `src/isaac_records/*`, `isaac validate` and `isaac export`.
- `draft_validator.py` already accepts `status: "inferred"` when the value has evidence and a stated
  derivation `rule`.
- `records.py` already writes one such field (`context.temperature_basis = "not_reported"`, DEC-76).
- CLAUDE.md §5 ("A field may be inferred only by a documented/stored rule") is satisfied by
  construction: every fill below names its registered rule and carries its evidence.

**What changes is the importer's policy.**
- Today:
  - only `scientist_confirmed` values are eligible (`bundle.eligibility_for_official_record`);
  - an AI reading lifts a value to `needs_review` and never higher (`bundle.derive_value_state`);
  - the skill's rules 2, 4 and 9 forbid recording anything the scientist did not say in the session.
- After:
  - a value that a **registered fill rule** supports becomes `filled`;
  - `filled` is eligible, composes into the draft as `inferred`, and is not asked;
  - the end review is where the scientist sees it.

## The new value state

`filled` joins `bundle.VALUE_STATES` (bundle format **1.18.0**):

| From | Becomes |
|---|---|
| a scientist decision | as today: `scientist_confirmed` / `rejected` / … A decision always wins over a fill |
| no decision, and a fill rule applies (below) | `filled` |
| otherwise | as today |

A few rules about the state itself:
- **A fill rule never applies to a `conflicting` value.** If the sources disagree, the scientist is
  asked.
- `filled` is never a parser `extracted_state`. The validator re-derives it, as it does every state,
  and refuses a stored `filled` it cannot re-derive.
- **Eligibility:** `scientist_confirmed` OR `filled`, plus a value, plus a write route.
- **Composition:** a filled value goes into the draft as
  `{"value": v, "status": "inferred", "evidence": [<the witnesses>, {"derivation": {"rule": <rule id>, ...}}]}`.
- **The sidecar** therefore names the rule for each filled field.

## Fill rules (v1)

Each rule has an id, the evidence it needs, and the cases where it does not apply. A rule applies only
when its evidence **agrees across every target it fills**. One dissenting witness means no fill, and the
value is asked.

| Rule id | Fills | Evidence it needs | Does not apply when |
|---|---|---|---|
| `isaac.fill.parser_exact.v1` | any writable field whose value is `candidate_extracted` | a deterministic reader read it from the files, or a stored convention rule did (today's `candidate_extracted`) | the value is `conflicting`; the reader marked it a suggestion only; or it was read from a file-name token while a naming question for that beamtime is open (counter positions, an unknown token), because a misread naming convention would fill every run wrongly |
| `isaac.fill.reading_stated.v1` | the field a reading pass names | an `ai_interpretations` entry of strength `stated` whose every quote passed `check-readings`, whose quote itself states the value (DEC-97: the number in the field's own unit, the list member, every significant word), and whose value its field accepts | another reading or a file value disagrees for any target; a sample's own label as its material; a beamtime reading on a run-level or sample field |
| ~~`isaac.fill.reading_inferred.v1`~~ **removed (DEC-97)** | — | — | never built: a replay on a real beamtime showed an inference from indirect quotes filling 13 wrong environments (two quotes that state no environment); an inference is a judgment, so the scientist is asked and the reading stays a suggestion |
| `isaac.fill.domain_from_acquisition.v1` | `system.domain = experimental` | every run is a beamline acquisition file (SPEC/XDI/XDC reader) | any file is a calculation output |
| `isaac.fill.facility_from_folder.v1` | `system.facility.facility_name` and `.beamline` (the two a facility hint suggests), every run | the folder name's facility word (right before its BL token) and BL token, and the SPEC fingerprint, name the same facility and beamline; the run's own header lines carry the fingerprint; the value is the fingerprint's spelling (`SSRL`, `BL15-2`) | they disagree; only one of them is there; the fingerprint matches several beamlines; the folder states no branch the fingerprint states (then only the facility is filled); a reading or answer names another facility or beamline; a scientist rejects any facility, beamline or organization fill (beamtime-wide) |
| `isaac.fill.organization_from_facility.v1` | `attribution.produced_by.organization`, the beamtime | the facility `facility_from_folder` identified (the scientist's answer, 2026-11-25: the producing organisation is the facility named in the beamtime folder) | no facility is identified so; the facility is disputed (a reject included); a reading or answer names another organization |
| `isaac.fill.group_from_folder_pi.v1` | `attribution.produced_by.group`, the beamtime: "<full name> group" when exactly one full name ending in the folder's surname is at a labelled position (`PI:`, `Users:`, `Group:`, "group of …", a contributor), else "<Surname> group" as the folder writes it | the folder is `<FACILITY>_<BEAMLINE>_<YYYY-MM>_<Surname>_<project>`, the token looks like a surname, and a SECOND source agrees: the readme's month header (`# 2031-01_Surname`), a SPEC `#F` data path, a contributor, or a labelled full name; a PI line takes precedence over a users or group line | the token is no surname (an acronym, a number, an element symbol or formula, a technique, project, housekeeping or lab word); the folder alone; the readme header, a data path or a labelled line names another person (two candidate PIs); the bundle was imported before the import kept the readme's header lines; a reading or answer names another group |
| `isaac.fill.environment_from_held_potential.v1` | `context.environment`, per run, with the convention the scientist gives ONCE for the beamtime (`set_environment_convention`: `operando`, `in_situ`, or `per_run`, which fills nothing) | the run's own files give a potential set-point (a deterministic file-name or header reading with a value, sources agreeing), something shows it was electrochemical (a valued electrolyte, pH, cell type, reaction or control mode of the run or the beamtime, an answer to one, a checked stated reading of one, or a quote-checked reading of any strength whose quote names chronoamperometry, chronopotentiometry or a potentiostat), and the scientist answered the beamtime's convention question; the answer is bound to the runs it was asked about, and runs that qualify later are said (status, and the question re-opens as optional). A per-beamtime convention, not a universal rule: one real beamtime's scientist says operando for such runs, another real beamtime's sheet says in situ. The potential scale plays no part | a reference, standard or alignment run; an environment word, open circuit, dry, as-is or no electrolyte in the run's own name; anything saying open circuit or no electrolyte; any environment candidate for the run; a stated reading, answer or file value giving another environment; the set-point conflicting, contradicted, rejected or disputed |
| `isaac.fill.record_groups.v1` | the proposed record grouping | the proposal comes from grouping rules, with no open grouping disagreement | a disagreement or a split/merge question is open for that group |

**Scan selection is unchanged.** The skill already decides keep or drop by `isaac.xas.scan_decision.v1`,
and those decisions appear in the end review.

## Still asked

- **Missing values:** a required field that no file, reading or rule supports.
- **Conflicts:** a field where the sources disagree, once per field across the beamtime, with the
  exceptions listed.
- **Qualitative judgment:**
  - the potential scale (RHE or the reference electrode) when nothing states it;
  - a dose question the dose rule cannot settle;
  - an absorber where the scanned range allows two edges;
  - anything the scientist chose to defer.

## The end review

`isaac bundle review <dir>`:
- runs after `build-records`;
- prints every filled value in the built records, grouped by field;
- for each value, shows:
  - how many records carry it;
  - one quote;
  - its rule;
  - the scan keep/drop decisions, with their reasons and curves.

The scientist then:
- **answers "looks right"**: `isaac bundle review <dir> --accept --by "<name>"` records one `review`
  decision over the listed fills at this bundle version. They become `scientist_confirmed`, with basis
  `reviewed_final_records`.
- **or changes lines**: an ordinary `decide`, then `build-records` again.

**Export does not wait for the review.** A record with unreviewed fills exports with those fields
`inferred`. `bundle status` says "N values filled, not yet reviewed", and the skill always ends with the
review.

## The skill

SKILL.md:
- Rules 2, 4 and 9 are rewritten: fill what a rule supports, ask only what is missing, conflicting or a
  judgment call, and end with the review.
- Step 4 (the reading pass) becomes a checklist of the fields a logbook usually answers:
  - samples, material and form;
  - electrolyte;
  - potentials and their scale;
  - cycling;
  - environment;
  - scan notes;
  - who produced the data.

  It reports what it found for each one.
- Step 7 asks only what remains after the fills.
- A new last step is the review.

The question site shows only what remains.

## Accuracy

- **Synthetic tests** cover each rule's apply and not-apply cases.
- **A replay** runs the import and the stored readings of the real beamtime above, outside the repo,
  and compares every filled value with the scientist's 24 answers. Target: all match, and nothing he
  answered is left asked except where the files disagree.
- **The same replay on the other beamtimes' answered workbooks:** no fill may contradict an answer a
  scientist gave there.

## Review findings adopted (independent Opus review, 2026-11-25)

The review read the code, not just this design. Every change below is adopted:

1. **Evidence shape.** `draft_validator.py` accepts a derivation only as an entry
   `{"source_type": "derivation", "rule": "<rule id>", ...}`; a different shape fails export.
   - Copy `records.py`'s `temperature_basis` precedent.
   - The sidecar keeps only `evidence`, so this entry is the only mark that a field was inferred.
2. **Merged groups.** A filled value composes only when every measured run of the group has the same
   filled or confirmed value. `compose_group` writes `status: "inferred"` whenever any contributing
   value is filled.
3. **DEC-69 stands.** A reading scoped to the whole beamtime never fills a run-level field:
   `RUN_ONLY_PATHS`, environment, reaction, cell type. Only readings scoped to the runs they name do.
4. **Corrections stay possible.** A filled target stays addressable by `decide`, by workbook import
   and by site import, so a correction is recorded and wins.
5. **Exclusions from `parser_exact`:**
   - a convention rule resolved on another beamtime;
   - a file-name-token reading while no counter decision exists;
   - `potential_setpoint_V` composes only beside a confirmed or filled scale, and the scale stays a
     question unless a file or logbook line states it (DEC-88's gate kept);
   - local-clock start times;
   - `control_mode`, until `control_mode_by_run` counts filled values the same way;
   - any candidate with a `contradicts` witness.
6. **Readings must be checkable later.** `annotate --from-readings --apply` stores on each
   interpretation:
   - the quote-check result;
   - the checked file's `content_sha256`;
   - a reading-pass id.

   `reading_stated` fills only from entries whose check passed. An entry without the block (older
   bundles, `annotate --target`) never fills.
7. **Record groups stay one bulk question** for now (Step 5's "confirm these M together?"). Filling
   groups needs a new group status that touches processing and regrouping. That is deferred, and it is
   the next candidate for moving into the end review.
8. **Format upgrade.** `filled` is added to the schema enum, and fills apply only at format ≥ 1.18.0.
   An older bundle re-derives as STALE, not INVALID, and every moved value is logged in
   `eligibility_rederived`. The hosted page's state counts include `filled`.
9. **Answer memory** never learns a review decision or a fill as a scientist's answer.
10. **The end review binds each item:** target id, value, rule id, and a hash of its evidence (the
    clock-zone binding pattern). Any later change to a bound item returns it to `filled`.
11. **Decisions superseded explicitly** in the decision log:
    - DEC-84 (AI readings never above `needs_review`);
    - DEC-87 (AI reads are suggestions);
    - DEC-88 (facility hints only; that decision's set-point gate is kept);
    - DEC-68;
    - contract §4.2 and the §6 eligibility rule;
    - `bundle.AUTHORITIES`;
    - SKILL.md rules 2, 4, 5, 8 and 9.

## Slices

1. **Format 1.18.0 and the `filled` state.**
   - Items 1, 2, 4, 5, 8 and 9 above.
   - The rules `parser_exact` and `domain_from_acquisition`; the instrument-configuration technique
     rule also counts as `parser_exact`.
   - Questions skip filled values; contract and decision-log entries.
2. **Reading fills.** Item 6, plus `reading_stated` and `reading_inferred` with item 3's scope guard.
   These are the rules that answer material, form and environment from the logbook.
   *Built as bundle format 1.19.0, fill rule set 2 (`DEC-97`; contract §9 "What 1.19.0 added"). Revised after a
   real-beamtime replay: `reading_inferred` is NOT built (an inference is a judgment, so it is asked), a stated
   reading fills only when its quote states the value, and a sample's own label is never its material.*
3. **Folder and people.**
   - Facility from the folder and fingerprint when they agree.
   - Organization = the identified facility (the scientist's answer).
   - Group from the folder's PI token plus a checked reading that gives the full name.
   *Built as bundle format 1.20.0, fill rule set 3 (`DEC-98`; contract §9 "What 1.20.0 added"), with one rule added:
   the environment from the held potential, as a per-beamtime convention the scientist answers once (one question,
   which covers each run's own environment question meanwhile). Revised from the first plan: the group is filled as
   "<Surname> group" when no single labelled full name is in the files (the owner: asking "is this the X group?" of a
   folder that names X wastes the scientist's time), but only beside a second source that agrees. This supersedes
   SKILL.md's "never name the group from the folder name"; SKILL.md itself is rewritten in slice 4.*
4. **The end review** (item 10), `bundle status`, SKILL.md and the question site.
5. **The replay harness**, run after every slice. Its script lives in the repo; real paths are given as
   arguments.
