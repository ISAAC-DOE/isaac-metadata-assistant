# Historical import semantics — conventions, operators, conflicts, signals (2026-09-22)

**What this is.** The design and the API contract for the historical-import changes made
on 2026-09-22, in response to two inputs: the domain owner's (Angel's) answers A–F,
relayed by the project owner, and the project owner's correction that **a filename
convention is not a scientist**. The per-question dispositions live in
[`docs/bl15-2-domain-questions-2026-09-16.md`](bl15-2-domain-questions-2026-09-16.md)
(§"RECONCILED 2026-09-22"); this document explains the model the build now implements
and what a UI can rely on.

**Provenance, stated because a repository cannot witness a conversation.** Angel's answers
reach this repository as an owner relay, the evidentiary class `DEC-47` records. No
transcript is committed. Only Krish can confirm the relay; only Angel the content.

**Disclosure boundary.** No measured value, note prose, instrument setting or person's
name from the real BL15-2 archive appears here. The figures in §4.2 are **aggregate
structural statistics** ("channel X non-zero in N of M scans", a share bound), which the
characterization document's §0 permits. Every example below is from the synthetic
fixture `tests/fixtures/bl15/semantics/multi_operator_corpus` (sample codes `ZZ1`–`ZZ3`,
the invented element `Zz`, years 2099/2100, invented operators).

**What did not change, and must not be read as changed.** The truth plane
(`schema/`, `official.py`, `draft_validator.py`, `export.py`, `audit.py`, `cli.py`) is
untouched. Official validation, export gating, the evidence sidecar, immutable
submissions, the no-guessing rule and the proposal-acceptance gate
(`409 human_actor_required` in every default deployment) are unchanged. No table and no
migration were added; `db_write.OWNED_TABLES` is unchanged. Nothing in this document
makes a value exportable.

---

## 1. Conventions, applicability, and the operator

### 1.1 A convention is not a person

The profile previously registered as `ssrl_bl152_angel` described **how a family of
BL15-2 HERFD electrochemistry filenames is written** — a vocabulary — and named it after
a scientist. That conflated two things: *which convention a filename follows* and *who
ran the measurement*. They vary independently. One scientist writes filenames in more
than one convention across a career; many scientists share one convention on a
beamline.

So the convention is renamed and the person is removed from its identity:

| | |
|---|---|
| id | `ssrl_bl152_herfd_echem_naming` |
| version | `1` |
| display name | "SSRL BL15-2 HERFD electrochemistry filename convention v1 — measured on the April 2025 IrOx beamtime archive" |
| alias | `ssrl_bl152_angel` — kept so a session persisted before the rename still resolves (`profiles.canonical_profile_id`, `profiles.profile_for`) |

The alias is lookup-only: nothing new is ever written under it.

### 1.2 Applicability: which convention reads which source

`bl15/applicability.py`. A **binding** says a convention applies at one of seven levels,
from least to most specific — of which **five are reachable in this build**
(`applicability.REACHABLE_SCOPES`): the build's default binding sits at
`acquisition_system`, and a recorded rule's selector places it at `experiment` (no
selector), `source_family` (source types), `run_subset` (legacy range, group tokens, stem
prefixes) or `source` (named files). `facility` and `beamline` are ordering constants only:
no selector can express them, because every source this build reads comes from one
facility and one beamline. *(An earlier revision presented all seven as available.)*

`facility` → `beamline` → `acquisition_system` → `experiment` → `source_family` →
`run_subset` → `source`

(`applicability.SCOPE_SPECIFICITY`. A source family — "all scan exports" — is ranked
below a run subset because it cuts across Runs; a named Run subset is the narrower claim.)

A binding carries a **selector** that says which sources it covers: a legacy-number range,
sample-group tokens, stem prefixes, source types, or named source paths. **A selector has
no operator field, and neither does a binding** — structurally there is no way to say
"read this person's files this way" (pinned by
`test_a_selector_has_no_operator_field_and_neither_does_a_binding`).

Resolution per source, deterministic:

1. The build's default binding (`build-default`, `acquisition_system` scope) always
   applies.
2. Every binding whose selector matches the source is a contender; **the most specific
   level wins**.
3. **A tie between two different conventions at the same level is an AMBIGUITY, never a
   choice** — the source is read under each, `applicability.ambiguity` says so, and
   nothing is chosen.
4. A binding reviewed against a convention version that is no longer registered is
   **stale**: it is reported (`applicability.stale_bindings`) and does not apply. It is
   never silently upgraded.

Every unit reports its own `applicability` — `profile_ids`, `profile_versions`, `scope`,
`basis` (`build_default` | `import_session_choice` | `confirmed_rule`), `binding_ids`,
`rule_refs`, `ambiguity`, `stale_bindings`.

### 1.3 The operator is provenance

People the notes name on a labelled line (`Operator:`, `Measured by:`, `Run by:`,
`Performed by:`, `Prepared by:`, `Contributor(s):` — rule
`bl15.notes.contributor_statement.v1`) are recorded **per measurement unit** as
`contributors`, each with `role: "provenance"` and `is_actor: false`, scoped to the
file-number rows of the section that names them. A person named before any sample
section is a beamtime-level contributor (`corpus_review.beamtime_contributors`).

They are never the basis for choosing how to read a file, and renaming every operator
changes no applicability (pinned by
`test_renaming_every_operator_changes_no_parsing_choice`). A contributor is also never an
*actor*: the actor of an ISAAC action is established only through a trusted boundary,
which this build does not have.

`contributor_statement` is registered with `needs_domain_review` and a candidate official
home of `attribution.contributors`; the build does **not** write it there, because
mapping a notes line to that block's `role` enum is a judgement nobody has made.

---

## 2. The conflict model — answer E

**No universal source hierarchy.** Each source has a *role* that says what kind of claim it
makes (`bl15/resolution.py`, `ROLE_MEANINGS`):

| role | what it is |
|---|---|
| `planned_acquisition` | a macro's `newfile` target — what was planned |
| `instrument_header` | a scan header (`#F`, `#D`, …) — what the acquisition system recorded |
| `human_label` | a filename — what a person called it |
| `retrospective_note` | the final notes — what a person later wrote about it |
| `absence_of_a_source` | a source that should exist and does not |
| `other_source` | anything else |

Every disagreement is carried in **four layers**, and each layer is labelled on the wire:

| layer | what it holds | authority |
|---|---|---|
| **Source fact** | every reading, verbatim, with its source, locator and role | the sources |
| **Normalized reading** | a reading after a documented normalization rule | the rule |
| **Suggested resolution** | ISAAC's recommendation, or why it has none | **non-authoritative** |
| **Scientist-confirmed resolution** | a reviewed convention rule choosing a reading | authoritative for *reading* the import; a record field still goes forward only as a **proposal** |

**When ISAAC may suggest** (`resolution.recommend`), only from independent evidence:

* a **repeated pattern** — the same disagreement resolved the same way across at least
  three contiguous units (`MIN_PATTERN_MEMBERS = 3`);
* the **final notes** — a notes row for that file number whose words match one reading;
* the **neighbouring sequence** — adjacent units agreeing with one reading.

A macro and a header that agree are **one causal chain and count once**: the header
records what the macro asked for, so their agreement is not two witnesses. Evidence
pointing both ways yields `status: "none"` and no value.

**When ISAAC may never suggest:** two distinct acquisitions under one legacy number
(`duplicate_legacy_number`, Q16). The recommendation is `status: "forbidden"`; the notes'
support for one reading is still **shown**, with `counts: false`. A scientist-confirmed
resolution choosing one is refused with `422 resolution_forbidden`.

**What a confirmation does.** A `conflict_resolution` rule (§3) marks the conflict or
candidate `review_status: "resolved"` and **keeps every reading**. For a field candidate
whose sources disagreed, the chosen value travels on a **derived candidate**
`<candidate_id>::resolved`, which is an ordinary field candidate: if the build has a write
route for its path it can be sent to review as a proposal, and **accepting that proposal
keeps its trusted-actor gate**. A resolution must choose one of the stated readings; an
invented value is refused (`422 not_a_reading`).

**The derived candidate is exactly what an agreeing candidate would be** — two
corrections made after an independent review, which together mean a resolution opens no
route a value could not already take:

* its **value** is the one the sources would have produced had they agreed on the chosen
  reading (`bl15.reconstruct.value_of_reading`): the normalised value when the evidence
  stating that reading carries one, else the literal **exactly as written**. The first
  version regex-coerced the comparison string, so `'060'` became `60` and `'500 cycles'`
  became `500`;
* its **proposability** is the mapping registry's: a concept the registry does not let
  become a proposal (`sample_name` → `sample.material.name`, `acquisition_method` →
  `system.technique`, `sample_preparation` → `sample.material.provenance`, …) stays
  unsendable after it is resolved. A resolved acquisition timestamp is proposed as the
  literal the header states — the same value the pre-existing agreeing path sends.

`DEC-42` (a document disagreeing with *itself*: sample-specific evidence wins) is a
different rule and is unchanged.

---

### 2.1 Per-scan variation is not a conflict — `bl15.mapping.cardinality.v2`

> **v2, 2026-09-23, after an independent review.** v1 kept a measurement-level reading
> (a macro's plan, a file-level header) in a group of its own, so a plan and the header's
> recording of the SAME, only scan read as variation; and it took a scan export's `_00N`
> file index to be SPEC scan `N`, which nothing establishes. v2: every measurement-level
> reading is compared with every scan's (for `acquisition_target`, on the stem alone); a
> scan is established only by the source's own `#S` line (a SPEC number used twice in one
> file, or an export naming no single scan, stays unestablished and is compared with
> everything); a per-scan concept varies only across two or more established scans; and
> `counting_time`, `scan_command`, `energy_grid` and `emission_energy` are back to one
> value per measurement until the domain owner answers **Q21** in
> `docs/bl15-2-domain-questions-2026-09-16.md`. The v1 text below is kept as the record
> of what v1 did; the table and counts are v2's.

**Added after a measurement, the same day.** On the synthetic multi-operator corpus the
reconstruction reported **43** field disagreements, and **36 were not disagreements**:
each scan export names its own scan index (`acquisition_target`), a `#L` line lists
several detector columns (`detector_column`), a `#P` line gives several motors
(`motor_position`), and each file's name carries its own tokens (`unknown_token`). On the
mini corpus all **12** were of that kind. `acquisition_target` also reached the screen
as a Python dict repr.

Every concept now has a **cardinality** in the registry (`bl15.mapping.CONCEPT_CARDINALITY`,
served as `mapping.concepts[].cardinality`), stated per concept and never inferred:

| cardinality | compared only within | concepts |
|---|---|---|
| `per_measurement` (default) | the whole measurement | every concept not listed below — including `filter` and `acquisition_timestamp`, on purpose |
| `per_scan` | the same scan (established by the source's own `#S`) | `acquisition_target` — v1 also listed `counting_time`, `scan_command`, `energy_grid`, `emission_energy`; v2 reverted them |
| `per_scan_item` | the same column or motor of the same scan | `detector_column`, `motor_position` |
| `per_source` | the same token of the same file | `unknown_token` |

The scan and item come from the readers as structured fields (`SourceEvidence.scan`,
`.item` — the SPEC scan number on the source's own `#S` line, in the acquisition file
and in each scan export alike; a `#L` column position, a `#P` motor name, a filename
token position), never from parsing a locator. ~~the `_00N` index of a scan export~~ —
v1; withdrawn in v2.

* Values that differ **across** scans are kept as `reconstruction.candidates[].variation`
  — one row per scan/item/file: `{scan, item, source, value, source_ids, locators}` —
  with `variation_basis`, `variation_scans` and, when windowed at 24 rows,
  `variation_total`. `agreement` is `varies`; `review_status` is what the mapping says
  (never `sources_conflict`).
* Two sources disagreeing about the **same** scan (or item), or any disagreement about a
  per-measurement concept, is still a conflict, and its `disagreement` rows carry only the
  disputed readings.
* `filter` stays per-measurement: a scan header's `filter` motor disagreeing with the
  filename's filter index is a real question. `acquisition_timestamp` stays
  per-measurement: it feeds `timestamps.acquired_start_utc`, one value per run.
* **A macro's statement about another measurement is not this measurement's evidence**
  (`bl15.reconstruct._evidence_for_unit`): a nine-block macro gave every unit it declared
  all nine declared targets. A statement naming no measurement still applies. One mini
  candidate disappears as a result — `…_again::unknown_token`, whose only reading was
  the macro file's OWN name token (`runsynth`), which says nothing about that
  measurement (101 → 100 candidates).

Result (re-measured under v2, 2026-09-23 — identical to v1 on these two corpora, which
state no macro plan for any of the reverted quantities): multi-operator **43 → 7** field
conflicts (6 `filter`, 1 `acquisition_timestamp`; 36 now vary by scan); mini **12 → 0**
(12 vary by scan). The structural conflicts (`bl15.relate`) are unchanged: 10 and 5.

### 2.2 One field, one proposal; no local time in a UTC field (2026-09-23)

`acquisition_timestamp` (the SPEC `#D` line) and `acquisition_epoch` (the `#E` line) both
target `timestamps.acquired_start_utc`, and each was proposed — two open proposals for one
field, never compared. Now (`bl15.reconstruct._reconcile_same_field`, also applied after a
resolution): proposable readings of one field that agree (for a `*_utc` field, the same
instant) become ONE proposal and the rest stay as witnesses; readings that disagree become
one conflict on the first. And a time that names no zone is never proposed into a `*_utc`
field (`hist.CANDIDATE_NOT_PROPOSABLE_LOCAL_TIME`, in the reconstruction and in
`_bound_candidate`, so a resolved candidate cannot either): the `#D` ctime string is the
instrument's local clock. The epoch-derived UTC instant stays proposable — it is a named,
deterministic conversion. Ready-to-send counts drop accordingly: mini 10 → 4, multi-operator
17 → 9 (the `#D` values, and — see §2.3 — the alignment scan's epoch).

### 2.3 The Add stage predicts what the batch does (2026-09-23)

A run-owned value read from a measurement that is not a Run (an alignment scan, a standard)
is marked not proposable when the import is read
(`hist.CANDIDATE_NOT_PROPOSABLE_NOT_A_RUN`), so it is never counted "ready". The session
view publishes `send_plan` — `{sendable, not_sent: {id: error}, no_run_when_creating_runs}`
— computed by `hist.batch_partition`, the SAME function `POST …/add-to-experiment`
partitions with, so the Add stage's prediction and the batch's report are one
categorisation (`test_import_send_plan.py` holds it as a property over both corpora).

## 3. Reviewed convention rules — learning without silent promotion

`isaac_api/convention_rules.py`. A rule records **how to read sources**, never a value.

### 3.1 Kinds

| kind | body | effect |
|---|---|---|
| `profile_binding` | `profile_id`, `profile_version` | a convention applies to the selector's sources (§1.2, basis `confirmed_rule` or `import_session_choice`) |
| `conflict_resolution` | one of `conflict_id` / `candidate_id` with `chosen_value`; **or** `conflict_kind` + `chosen_source_role` (recurring) | §2. A recurring rule applies wherever exactly one reading has that role, within the selector |
| `signal_assignment` | `assignments: [{channel, element, edge?}]` (≤ 8; channels from the acquisition system's candidates) | confirms which Vortex channel belongs to which element — what makes a dual-element Run confirmable (§4) |

### 3.2 Scopes — "apply only here / to this Experiment / to this convention"

| scope | stored in | durable? | applies to |
|---|---|---|---|
| `import` | the import session | **no** — sessions are not durable (`SESSION_DURABILITY_DISCLOSURE`) | this import only |
| `experiment` | the record's state document, key `convention_rules` | as durable as the record | imports targeting that record |
| `profile` | the record's state document, key `convention_rules` | as durable as the record | imports targeting that record; **offered** (not applied) to imports targeting any other record |

**No scope is global, and nothing is promoted silently.** A `profile`-scoped rule shows up
in another experiment's import under `rules.reusable_from_other_experiments`, each with
what it *would* match (`matches.units`) and how many units it *would* change
(`difference_count`), and `applied_here: false`. It applies there only when a scientist
records a new rule for that experiment with `derived_from` naming it.

**A convention-scoped resolution or channel assignment records its convention.** The
convention is derived from the measurements the rule addresses (the candidate's or
conflict's unit, or the units a recurring rule's selector reaches) and stored as the
rule's `profile_id`/`profile_version`, so `version_is_current` means something. When
those measurements are read under more than one convention, a `profile`-scoped rule is
refused (`422 convention_not_determinable`). Elsewhere it is offered only to an import
with measurements read under that convention, and matches only those; an import with
none is not offered it at all, counted as `rules.reusable_scan.not_offered_other_convention`.
*(Before a review found it, such rules recorded no convention and were offered to every
experiment.)*

**The suggestion scan is bounded and says so.** `rules.reusable_scan` carries
`experiments_listed`, `experiments_scanned`, `cap` (200), `truncated`,
`listing_complete` and `order` (`most_recently_created`), so a short list is never read
as "no other experiment has a rule".

**The destination record's rules only.** An import is always minted from a reading under
the destination record's own rules: when add-to-experiment (or the single-candidate
proposal operation) names a record the session was not last read for, or whose active
rules have changed since, the session is re-read for that record first
(`reread_for_target: true`), so a resolution, binding or channel assignment confirmed on
record A can never shape a proposal minted on record B. *(A review reproduced exactly
that leak before this was added.)*

### 3.3 Versions, supersession and attribution

* A rule is **never edited or deleted.** `supersedes` names an active rule of the same kind
  in the same place; the new rule is its next `version`. Every rule ever recorded is kept.
* A binding is tied to the convention **version** it was reviewed against;
  `version_is_current` is false when that version is no longer registered, and the binding
  is then stale (§1.2).
* `confirmed_by` is `unattributed` with `confirmed_trust_basis: "unattributed"` in every
  deployment of this build, and the pairing is enforced: an unattributed actor with any other
  basis, or a named actor with the unattributed basis, is refused (`actor_basis_mismatch`).
  *(An earlier revision of this line said `null`; the wire has always carried the string, and
  the string is right: it is the project's one sentinel for "no trusted actor" —
  `activity.TRUST_BASIS_UNATTRIBUTED`, itself reused from `submissions` — carried by every
  activity event's `actor_trust_basis` and every proposal's `trust_basis`. A rule is recorded
  by the same kind of act, so it uses the same pair.)*
* `is_official_field_value: false` and `is_evidence: false` on every rule.
* Recording an `experiment`/`profile` rule appends one activity event —
  `convention_rule_recorded`, object type `convention_rule`, channel `historical_import`.

### 3.4 Persistence, and why there is no table

Rules and run origins live in the experiment state document, beside `proposals`, `notes`
and `activity` — the `DEC-49` pattern. Two new top-level keys:

* `convention_rules` — the record's rules; omitted when empty; included in the
  authoritative signature.
* `historical_run_origins` — `{run_id: {acquisition_identity, archive_name,
  acquisition_path, content_sha256, stem, legacy_number, import_id, recorded_utc}}`;
  omitted when empty; included in the authoritative signature.

Both are read with `.get` and a default, so a document written before them hydrates to
empty; both are outside `draft`, so export cannot see them. Unreadable stored rules are
preserved untouched and counted (`unreadable_entries`), never rendered.

---

## 4. The HERFD primary-signal selector — answer C

`bl15/signals.py`, id `bl15.signals.herfd_primary_signal_selector.v1`.

**Angel's answer is a rule, not a column:** `vortDT` is generally the HERFD Vortex
channel; in dual-element work `vortDT` and `vortDT2` may belong to different elements;
one can be empty while the other carries signal. So the selector reads what each
candidate channel carries **in each Run** and applies a fixed decision table. "Generally
`vortDT`" is carried as the acquisition system's `domain_note` for a reviewer and is
**never a tie-breaker** — using it as one would be a hard-coded hierarchy, and wrong in
exactly the dual-element case.

### 4.1 Channel liveness

For each scan and each candidate channel (`vortDT`, `vortDT2`, `vortDT3`, `vortDT4`):

* **edge significance** `z = (mean of last decile − mean of first decile) / sqrt((pre + post) / k)`,
  `k = max(3, n // 10)` — a Poisson edge step in standard deviations;
* **share** of the Run's candidate-channel counts.

A channel is **live** when its edge fraction (share of the Run's scans with `z ≥ edge_z_min`)
is at least `live_edge_fraction_min` **and** its share exceeds `empty_share_max`; **empty**
when its share is at most `empty_share_max` and its edge fraction is below the minimum;
otherwise **ambiguous**; **absent** when no scan carries the column.

### 4.2 Thresholds, and their measured basis

| threshold | default | basis (aggregates, measured 2026-09-22 over the real archive: 904 scans with data, 92 measurement units) |
|---|---:|---|
| `edge_z_min` | 5.0 | At 5 every sample-measurement unit's `vortDT` shows an edge in ≥ half its scans and no sample unit's `vortDT2` shows one in any scan. At 3 a few `vortDT2` scans cross; at 10 a second `vortDT` unit drops below one half. |
| `live_edge_fraction_min` | 0.5 | Every sample-measurement unit's `vortDT` is at or above one half; the only unit below is the alignment scan (0.200). |
| `empty_share_max` | 0.05 | `vortDT2`'s per-unit share never exceeds 0.0397 and `vortDT`'s is never below 0.9603 — nothing falls between. |

Also measured: `vortDT3`, `vortDT4`, `vort` and `vort2` are all-zero in all 837 scans that
carry them. `vortDT3`/`vortDT4` remain candidates anyway, because a channel empty in this
archive is not thereby never the signal. The thresholds are a replaceable input
(`SelectorThresholds`), and **every selection records the thresholds and basis it was
computed under**, so two selections under different thresholds cannot be confused.

### 4.3 Element evidence

The element a Run measures is established from, in order of specificity: a filename
element token, the method macro's symbol (`^([A-Z][a-z]?)(K|L1-3|M1-5)_…$`, rule
`bl15.signals.method_symbol_names_element_and_edge.v1`, which also yields the edge), and
the shared readme's element line (`bl15.signals.readme_element.v1`). Two sources naming different elements is a **conflict**, not a
choice.

### 4.4 The decision table

| channels | element | status | reason code |
|---|---|---|---|
| no candidate column | — | `unresolved` | `no_candidate_channel` |
| none live | — | `unresolved` | `no_live_channel` |
| any ambiguous | — | `unresolved` | `channel_liveness_ambiguous` |
| two or more live | — | `unresolved` | `multiple_live_channels` |
| exactly one live, rest empty/absent | none established | `unresolved` | `target_element_not_established` |
| exactly one live | conflicting | `unresolved` | `conflicting_element_evidence` |
| exactly one live | exactly one | **`proposed`** (non-authoritative) | `single_live_channel_and_established_element` |
| a confirmed `signal_assignment` rule applies and every assigned channel is live | — | **`confirmed`** | `confirmed_signal_assignment_rule` |
| a confirmed rule applies but an assigned channel is empty here | — | `needs_review` | `confirmed_rule_contradicted_by_channel_contents` |
| a confirmed rule applies, no assigned channel is empty, but one is AMBIGUOUS here | — | `needs_review` | `confirmed_rule_channel_liveness_ambiguous` |

A dual-element Run (both `vortDT` and `vortDT2` live) is `unresolved` until a scientist
confirms a `signal_assignment` naming both channels with their elements; then it is
`confirmed` with both assignments. **The selection never writes a record field**
(`writes_a_record_field: false`): the official `measurement.series[].channels[]` needs
values this build does not carry, and `Q12` forbids expanding the scan grid.

**Deliberately not used:** the energy window. Checking that a scan brackets the element's
edge needs an edge-energy reference this build does not carry, and reading it off the
macro's grid literal would be interpreting that literal. Every selection says so
(`evidence_not_used`).

---

## 5. Temperature — answer B

`DEC-43` is **superseded** (struck in place in `bl15/nominal.py`, the mapping registry and
the decision register). **No temperature is inserted or proposed automatically.**

* A source's words — "room temperature", "RT" (case-sensitive, word-bounded), a
  `Temp:` label — are read as a `temperature_statement`: kept verbatim at placement level
  4 in the extended context, `normalized_value: null`, never converted.
* A numeric **nominal** value can come only from a **reviewed, versioned rule** naming its
  convention — `ntp_style_293_15_K` (293.15 K) or `satp_style_298_15_K` (298.15 K), both
  cited in [`docs/evidence/temperature-convention-research-2026-09-22.md`](evidence/temperature-convention-research-2026-09-22.md).
  The offer is labelled nominal/inferred, `measured: false` (derived, cannot be stored as
  true), `requires_confirmation: true`, and reaches a record only as a proposal.
* **`REVIEWED_NOMINAL_RULES == ()`. No rule is enabled**, so `nominal_offers` is `[]` in
  every default deployment. Enabling one is a recorded decision that must fail
  `test_there_is_no_enabled_reviewed_rule_and_adding_one_fails_here` first.

---

## 6. Data Quality Notes — answer F

`measurement.qc.status` is **never written from notes.** Every free-text `Notes` cell in a
notes table is read verbatim as a **Data Quality Note** (registry label "Data Quality
Notes", concept `quality_note`), bound to its file number (locator
`line N table T row R column \`Notes\` (file number F)`), with `normalized_value: null` and
`writes_qc_status: false`. An untabbed continuation line inside a row is part of that
cell. A remark the reader cannot bind to a measurement is listed as unbound.

On add-to-experiment, each bound note can be captured as a **run note** on the matching
Run (source kind `historical_source_line`), exactly once per acquisition and locator
however many times the archive is imported: the `client_request_key` is derived from the
acquisition identity, the source path and the locator — never the legacy number, and
never the import session. *(The first version included the import id, so a second import
of the same archive captured every remark again; measured 6 → 12 before the fix.)* When a
remark is bound by a legacy number that two acquisitions share (the Run-32 shape), it is
attached to both runs and **each stored note says so**. Nothing classifies the words.

**Where a Notes cell ends.** An untabbed line directly under a Notes cell is that cell's
continuation only when another row of the table follows; under the LAST row it is the
prose after the table and is read as itself (a temperature statement, an operator line…).
Measured over the real notes before the change: 4 of 23 cells span lines, none in a last
row.

---

## 7. Run identity — answer D (Run 32)

Every measurement unit carries an **acquisition identity**:
`<archive>:<acquisition_path>@<content sha256>`. It is never the legacy number alone.

* Two acquisitions under one legacy number keep **distinct identities**, are both flagged
  `legacy_number_shared: true`, become **distinct Runs**, and neither is preferred.
* The first time a Run is made from an acquisition, its origin is recorded in
  `historical_run_origins`. A re-run of add-to-experiment finds each Run **by identity**
  (`matched_by: "acquisition_identity"`), even if two Runs' labels have been made equal.
* Label matching survives only as a fallback for Runs made before origins existed, and
  only when the label is unique in the import and the Run has no recorded origin
  (`matched_by: "label_before_origins_existed"`). Anything else creates a new Run rather
  than guessing.

---

## 8. Capabilities

### 8.1 `historical_file_ingestion` — disabled by default

`isaac_api/capabilities.py`. **Disabled in every shipped configuration**; the reason is
`governance_not_approved` (gate `EXT-13`). `POST /api/uploads` stays **403 regardless**.

Enabling is configuration only, and opens one path: set
`ISAAC_HISTORICAL_FILE_INGESTION=staging_directory` **and**
`ISAAC_HISTORICAL_STAGING_ROOT=<a directory>`. Each direct child directory (at most 50)
becomes an archive named `staged:<name>`; names are validated as a single path segment,
so traversal is refused. The staging root's path is never served. A source added this way
carries `provenance.staged: true`. No Dockerfile or workflow sets either variable (pinned).

`reason` names what is wrong: `governance_not_approved` (the mode is not set),
`staging_root_not_configured` (no root named), `staging_root_missing`,
`staging_root_not_a_directory`, `staging_root_is_symlink`, or `staging_root_unreadable`.
**`/api/health` reads configuration plus ONE `stat` and access check of the root** — it
never lists the directory and never opens a file, and every `OSError` becomes
`enabled: false` rather than an exception, so an unreadable root can never change the
readiness probe's status. The detail block (`GET /api/imports`, each session's
`capabilities`) additionally lists that one directory's entries by name; a listing that
fails reports `staging_root_unreadable`. *(The first version listed the root on every
health read, and a `chmod 000` root made the probe answer 500.)*

### 8.2 Proposal-acceptance preflight

`capabilities.proposal_acceptance()` (served on `/api/health` as `proposal_acceptance`,
projected to `{available, reason}`) runs **the same verifier resolution** the acceptance
route runs, against a sentinel that is not a request, and reports `available`, `reason`
(`no_verifier_configured` by default), `refusal_error` (`human_actor_required`) and
`refusal_status` (409). It never exposes a subject. `test_the_preflight_reason_is_the_reason_the_accept_route_actually_returns` drives a real proposal to the accept route and asserts the `409`'s own `reason` equals the banner's. A UI can therefore say *before* a click
that acceptance will be refused, and why — using the identical decision, not a copy of it.

---

## 9. Activity

* **The activity history is now an MCP read**: tool `isaac_list_activity` (scope READ,
  read-only) over `GET /api/experiments/{id}/activity`. What unblocked it: the `action`,
  `channel` and `object_type` filters are now `Literal`s built from the model's own
  frozensets, so the tool schema gets closed enums and the MCP layer's unbounded-string
  refusal is satisfied without widening its reviewed map. `run_id` is bounded
  (`maxLength` 128) on the route.
* An off-vocabulary filter is now refused by the framework's own validation (`422`, which
  names the allowed values) before the handler runs; the handler's
  `unknown_activity_filter` branch remains as defence-in-depth.
* **`system` is a channel no write site records.** It is in the vocabulary (so a filter
  may name it) and served as `channels_without_a_write_site` on both activity reads, so a
  surface does not imply `system` events exist. A test asserts no module writes it.

---

## 10. API contract, for the UI

All shapes below are additive unless marked **changed**.

### 10.1 New endpoints

**`POST /api/imports/{import_id}/rules`** — record one reviewed rule and re-read the import.

```json
{
  "kind": "profile_binding | conflict_resolution | signal_assignment",
  "scope": "import | experiment | profile",
  "experiment_id": "<required unless scope is import>",
  "selector": {"legacy_range": [6, 8], "group_tokens": [], "stem_prefixes": [],
               "source_types": [], "source_paths": []},
  "body": {"...": "per kind, §3.1"},
  "supersedes": "<optional active rule id>",
  "derived_from": "<optional id from rules.reusable_from_other_experiments>",
  "source_examples": [{"...": "≤ 5, optional"}]
}
```

* `experiment`/`profile` scope requires the **record's** `If-Match` (`428` omitted,
  `400` malformed, `412` stale) and returns a new `ETag`.
* Response: `{"rule": <rule>, "import": <session view>}` (+ `experiment_version` for
  record-stored rules).
* `422` errors (each `{"error", "message", …}`). From the route: `invalid_body` (not a
  JSON object), `unrecognized_field` (a body key the route does not accept),
  `missing_experiment_id`, `unknown_reusable_rule`, `unknown_conflict` (a `conflict_id`
  this import does not hold), `unknown_disagreement` (a `candidate_id` that is not a
  disagreeing candidate), `not_a_reading` (with `readings`). From the rule validator:
  `unknown_kind`, `unknown_scope`, `unknown_profile`, `profile_version_mismatch`,
  `convention_not_determinable` (a `profile`-scoped resolution or channel rule whose
  measurements are not all read under one convention), `resolution_forbidden`,
  `resolution_target_required`, `unknown_source_role`, `unknown_acquisition_system`,
  `unknown_channel`, `invalid_element`, `invalid_edge`, `invalid_assignments`,
  `invalid_selector`, `unknown_rule` (a `supersedes` naming no active rule), and the
  generic `missing_field` / `wrong_type` / `too_long` / `too_many_rules`. *(An earlier
  revision omitted `invalid_body`, `unknown_conflict` and `unknown_acquisition_system`;
  `test_the_documented_rule_refusals_are_every_one_the_route_can_emit` now pins the list.)*

**`GET /api/experiments/{experiment_id}/convention-rules`** — read-only.
`{experiment_id, rules: [<rule> + {active}], total, active_count, unreadable_entries,
kinds, scopes, durability, experiment_version}`, with the record's `ETag`.

A `<rule>` is `{rule_id, kind, scope, version, body, selector, experiment_id, import_id,
profile_id, profile_version, supersedes, derived_from, confirmed_utc, confirmed_by
("unattributed"), confirmed_trust_basis ("unattributed"), source_examples, version_is_current,
is_official_field_value (false), is_evidence (false)}`.

### 10.2 `GET /api/imports/{import_id}` — session view additions

* `rules.reusable_scan` — `{experiments_listed, experiments_scanned, cap, truncated,
  listing_complete, order, not_offered_other_convention}` (§3.2).
* `profiles` — every registered convention (`profile_id`, `profile_version`,
  `display_name`, `aliases`, `measured_on`, `is_default`, `unexercised_recognizers`).
* `rules` — `{target_experiment_id, import, import_durability, import_unreadable,
  experiment, experiment_rules_as_of_version, experiment_durability,
  reusable_from_other_experiments: [{rule, from_experiment_id, from_experiment_title,
  applied_here: false, how_to_reuse, matches: {units, stems}, differences,
  difference_count, version_is_current}], reuse_policy}`.
* `capabilities` — `{historical_file_ingestion, proposal_acceptance}`, computed by the
  same functions as `/api/health`.
* `archive.units_page.rows[]` gain `acquisition_identity`, `legacy_number_shared`,
  `applicability` (§1.2), `signal_selection` (§4: `status`, `reason_code`,
  `reason`, `primary_channel`, `assignments[]`, `authority`, `rule_ref`, `channels[]`
  (per channel: `liveness`, `share`, `edge_fraction`, `scans_present`,
  `scans_with_edge`, `reason`), `elements[]`, `thresholds` (with `basis`),
  `evidence_not_used`, `writes_a_record_field: false`, `selector_id`, `system_id`),
  `data_quality_notes[]` (`text`, `source_path`, `locator`, `file_number`, `label`,
  `writes_qc_status: false`), `contributors[]` (`name`, `label`, `section`,
  `source_path`, `locator`, `role: "provenance"`, `is_actor: false`).
* `archive.relationships.units[].conflicts[]` and `.corpus_conflicts[]` gain
  `conflict_id`, per-reading `source_role` / `source_role_meaning` / `layer`,
  `recommendation` (`status`: `suggested` | `none` | `forbidden`, `value`, `why`,
  `supports[]` with `counts`, `authority: "non_authoritative"`), `resolution` (or null)
  and `review_status` (`needs_review` | `sources_conflict` | `resolved`).
  `archive.relationships.conflict_model` states the four layers, the roles and
  `source_hierarchy: null`.
* `reconstruction.candidates[]` gain `distinct_sources`, `agreement`, `review_status`
  and `resolved_by_rule`; a resolved disagreement adds `<candidate_id>::resolved`.
  They also gain `variation`, `variation_basis`, `variation_total` and
  `variation_scans`, and `agreement` gains `varies` (§2.1).
* `corpus_review.evidence[]` gains `scan` and `item`; `mapping.concepts[]` gains
  `cardinality` (§2.1).
* `corpus_review` gains `profile_applicability` (`bindings`, `convention_counts`,
  `ambiguous_sources`, `selected_by_operator: false`, `rule`), `temperature` (`status`:
  `not_recorded` | `stated_in_source`, `statements[]` with `raw_literal` and
  `converted_to_a_number: false`, `automatic_value: null`, `automatic_proposal: false`,
  `nominal_rule_enabled_for: []`, `policy`, `superseded_decision`),
  `data_quality_notes` (`label`, `bound_to_a_measurement`, `unbound[]`,
  `writes_qc_status: false`, `policy`), `herfd_signal` (`acquisition_system`,
  `element_evidence[]`, `by_status`, `writes_a_record_field: false`),
  `beamtime_contributors[]`, `rules_applied[]`, and `evidence_readings_thinned` /
  `evidence_readings_cap_per_cell`.
* **Changed:** `corpus_review.evidence_readings_dropped` now counts **only** readings not
  kept because a cell hit its distinct-literal cap. Repeated literals trimmed for the same
  measurement and concept are `evidence_readings_thinned`. Never sum them.

### 10.3 `POST /api/imports/{import_id}/add-to-experiment` — additions

* `data_quality_notes`: `{label, available, captured_as_run_notes, already_present,
  writes_qc_status: false}`.
* `run_origins_recorded`: integer.
* `reread_for_target`: boolean — the session was re-read under THIS record's rules before
  anything was minted (§3.2).
* `runs_already_present[]` gain `matched_by` (`acquisition_identity` |
  `label_before_origins_existed`) and `acquisition_identity`.
* **Changed:** `nominal_offers` is `[]` by default (it carried a 298 K offer under
  `DEC-43`).

### 10.4 Other reads

* `GET /api/health` gains exactly two keys each — the shape the frontend builds against:
  `"historical_file_ingestion": {"enabled": false, "reason": "governance_not_approved"}`
  and `"proposal_acceptance": {"available": false, "reason": "no_verifier_configured"}`
  (defaults shown). Both are **projections** of the full blocks below, never a second
  computation. `historical_file_ingestion.reason` is `governance_not_approved`, `null`
  when enabled, or `staging_root_not_configured` when an operator set the mode without
  a root (no shipped configuration does). `proposal_acceptance.reason` is `null` when
  available, else the exact `reason` the accept route's `409` carries
  (`no_verifier_configured` by default; `unverified_edge_traversal` etc. under other
  verifiers).
* The FULL capability blocks — `historical_file_ingestion` with `basis`,
  `governance_gate`, `uploads_route_open: false`, `path_when_enabled`,
  `staged_archive_count`, `staged_archive_limit`; `proposal_acceptance` with `basis`,
  `verifier_id`, `refusal_error`, `refusal_status`, `trust_basis_when_available` — are
  served by `GET /api/imports` (ingestion) and by every import session's
  `capabilities` (both).
* `GET /api/imports` gains `historical_file_ingestion` and `available_archives` (fixture
  names plus `staged:<name>` entries when enabled).
* `GET /api/experiments/{id}/activity` and `GET /api/activity/summary` gain
  `channels_without_a_write_site`.
* **Changed:** an off-vocabulary `action`/`channel`/`object_type` filter on the activity
  read is refused by framework validation (`422`, standard validation body listing the
  allowed values) rather than the handler's `unknown_activity_filter` body.

---

## 11. Not done, and open

* **Q6, Q7, Q8** are still Angel's. Their fields stay missing.
* **Energy-window evidence** for the HERFD selector would need a cited edge-energy table;
  none is committed, so the selector abstains.
* **Whether a nominal temperature rule should ever be enabled**, and under which
  convention, is a decision nobody has taken. None is.
* **Contributor role mapping** to `attribution.contributors[].role` is unmade;
  `contributor_statement` stays `needs_domain_review`.
* **Data Quality Notes become run notes**, which are as durable as the record. Whether a
  scientist should see them as a distinct note kind is a UI decision this build does not
  take.
* **Hosted QA** of any image carrying this work is `HOSTED QA PENDING (Krish)`.
