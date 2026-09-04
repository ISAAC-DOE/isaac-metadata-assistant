# Persistent Ingestion Proposals — Behavioural Contract

**Status:** ~~design only ... Nothing here is authorized work~~ — **SUPERSEDED 2026-08-29, see §10.**
The project owner authorized application-side implementation on that date. This remains the contract
a slice must satisfy; it is the contract a later slice would have to satisfy, plus the places where the master
requirement conflicts with this repository and what to do instead.

**Every claim about existing code below carries `file:line`. Re-derive rather than quoting.**

---

## 0. The false premise this document corrects

A handoff document claims *"persistent ingestion proposals are confirmed absent; no proposal
survives a request anywhere."* **That is wrong in its first half and right in its second, and the
split is the whole design.**

What already exists, persisted and reviewable:

- `apps/api/isaac_api/notes.py` implements `Note` — states `unreviewed / mapped / kept / dismissed`
  (`notes.py:158-172`), acts `capture / map / edit / keep / dismiss` (`notes.py:174-185`),
  append-only `history` (`notes.py:369`), immutable capture fields (`notes.py:234-236`), and **no
  delete anywhere** (`notes.py:26`, `routes.py:10254-10259`).
- A note already carries the **target half** of a proposal: `candidate_field_path` +
  `candidate_rule` (`notes.py:355-359`), and a path with no rule is refused outright
  (`notes.py:410-419`) — *"an unexplained proposal is a guess wearing a field name."*
- Notes are **durable and authoritative**: serialised into the experiment state document at
  `workspace.py:2817`, hashed into the record signature at `workspace.py:1607`, so every note act
  moves `rev`, moves the `ETag`, and is CAS-guarded.
- Routes: `GET/POST /experiments/{id}/notes` (`routes.py:9885`, `:9959`), `GET .../notes/{id}`
  (`routes.py:10123`), `POST .../notes/{id}/review` (`routes.py:10161`, `If-Match` required).
  Mounted at `apps/web/src/screens/RecordWorkbench.tsx:690`.
- `apps/api/isaac_api/conflict_resolution.py` goes further still: `ConflictResolution` is a
  **persisted, human-decided object that carries a value** — `chosen_value`
  (`conflict_resolution.py:397`), `chosen_from: candidate|edited` (`:398`, vocabulary at `:173-180`),
  `trust_basis` + `subject` (`:404`), append-only history (`:406`), and a `revise` act that supersedes
  without deleting
  (`:180-184`).

What is **genuinely absent**, and is the actual gap:

1. A note carries **no proposed value**, deliberately (`notes.py:89-96`): *"A mapped note says 'this
   belongs there'; a person still says what the value is."*
2. There is **no accept-a-stored-value operation** anywhere.
3. `providers/extraction.py`'s `FieldCandidate` is a valued proposal that is **deliberately never
   stored** — *"A candidate nobody confirms leaves no trace at all"* (`extraction.py`, "HOW A
   CANDIDATE BECOMES A VALUE" block). `POST /api/experiments/{id}/transcript` (`routes.py:10738`)
   stores every segment as a Note (`routes.py:10925-10940`) and returns **unstored** `candidates`
   plus an `accept_contract` block (`routes.py:10968-10982`) naming
   `PATCH /experiments/{id}/runs/{run_id}` + `confirmed_by_user` + the run's `If-Match` as the only
   way a candidate becomes a value.

So the gap is exactly one thing: **the valued half of a proposal does not survive the request.**

---

## 1. Decision: a new sibling type, not an extension of `Note`

**Recommendation: a new module `apps/api/isaac_api/proposals.py` defining `IngestionProposal`,
modelled field-for-field on `conflict_resolution.ConflictResolution` rather than on `Note`.**

### The argument from code

1. **`Note`'s "no value" property is enforced by the absence of a field, not by a check.**
   `status` / `verified` / `is_evidence` / `is_field_value` are read-only properties returning
   constants on a `frozen=True, slots=True` dataclass (`notes.py:432-450`), and the module
   enumerates the five escape hatches that therefore fail, including
   `object.__setattr__(n, "verified", True)` (`notes.py:37-44`). Adding `proposed_value` adds a
   *field*, and `notes.py:31-35` says the shape **is** the enforcement. It would still be true that
   `is_field_value` returns `False`, but the sentence "a note cannot even represent a confirmed
   value" (`routes.py:9572-9575`) would stop being checkable by reading the class.

2. **`Note`'s immutability set is capture-shaped, and a proposal's is not.**
   `IMMUTABLE_NOTE_FIELDS` is `{id, experiment_id, captured_utc, source, text}` (`notes.py:234-236`)
   and `revise_note` is the single chokepoint enforcing it (`notes.py:570-597`). A proposal needs a
   *different* frozen set — `proposed_value`, `quote`, `rule`, `base_rev` — because the load-bearing
   immutable on a proposal is *what was proposed*, not *what was captured*.

3. **Adding `accept` to `NOTE_ACTIONS` is a wire-vocabulary change with four enforcement sites.**
   `NOTE_ACTIONS` is closed (`notes.py:183-185`), the review route enumerates the four acts in its
   refusal body (`routes.py:10254-10267`), the description transcribes them
   (`routes.py:10186-10214`), and `apps/web/src/test/apiFixtures.ts` transcribes that description
   verbatim under `test_contract_description_parity` (recorded at `routes.py:9666-9673`). A fifth
   act drags all four.

4. **The storage locations differ, and the difference matters.** Notes live in the experiment
   state document outside `draft` (`workspace.py:2817`) — which is precisely why *"no export path
   reads a note: `export_draft` reads `Experiment.draft`, and notes are not in it"*
   (`routes.py:9576-9577`, `workspace.py:2705-2707`). `ConflictResolution` lives **inside** the
   draft (`conflict_resolution.py:162`, `DRAFT_KEY = "conflict_resolutions"`) and its own
   docstring has to disclose the consequence: for a zero-run experiment the key travels into
   `submissions.content_signature`. A proposal should take the *note's* location, not the
   resolution's — see §7.

5. **Adding a field to `Note` changes how every already-persisted note hydrates.** Hydration
   returns a *pair* — `exp.notes, exp.unreadable_notes = _hydrate_notes(state.get("notes"))`
   (`workspace.py:3681`) — and `_hydrate_notes` files anything `Note.from_state` refuses into the
   second half, verbatim (`workspace.py:1468-1511`, `notes.py:495-509`). A new field alters what
   that refusal branch sees on rows written before it existed. A sibling type hydrates from an
   absent key to an empty list, at zero risk to any existing row — the same property
   `workspace.py:3678-3681` claims for notes themselves.

### The strongest counter-argument, stated rather than hidden

**`ConflictResolution` already carries a `chosen_value` and still reports `is_field_value: False`
(`conflict_resolution.py:525-528`).** So "carrying a value" demonstrably does *not* violate this
repository's invariant. The invariant is *never presenting as a confirmed field value*, not *never
holding one*. On that reading, adding `proposed_value` to `Note` would **complete** the design
rather than break it: the note already names the target and the rule, and the value is the missing
third of the same tuple.

That argument is good, and I do not think it wins — for reason (2) and (4) above, which are
mechanical rather than aesthetic. But a reviewer who prefers the extension should be told that the
architecture does not forbid it; the costs are the immutability set, the wire vocabulary, and the
storage location, not a principle.

**Composition rule either way:** a proposal **references a note**, never replaces one. The transcript
route already stores every segment as a note *including* segments that produced a candidate, and
says why: *"a candidate is not stored anywhere, so rejecting one — or failing to accept it — would
otherwise destroy the words behind it"* (`routes.py:10739-10747`). Proposals inherit that: the
verbatim words live on the note, the proposal carries `note_id`, and deleting a proposal (which
nothing does) could never destroy content.

---

## 2. Persisted shape

`IngestionProposal`, frozen + slotted, one entry in `state["proposals"]`.

| Requirement field | Verdict | Where |
|---|---|---|
| stable id | **new** `proposal_id`; mint exactly as `workspace.capture_note` mints a note id (`workspace.py:3175-3187`) | precedent `notes.py:340`, `conflict_resolution.py:372` |
| initiating principal | **reuse the shape, new on this type**: `trust_basis` + `subject`, with the paired invariant (`unattributed` ⇒ `subject is None`; a recognised basis ⇒ non-blank subject) | `conflict_resolution.py:404` (`subject`), `:498-517` (the paired invariant); `submissions.py:103`; `identity.py:265` |
| experiment id | **exists** | `notes.py:341` |
| optional run id | **exists**, and the rule travels with it: never inferred from the only run that happens to exist | `notes.py:349-352`, `conflict_resolution.py:390-392` |
| target scope | **derived, not stored** — `run_id is None` ⇒ record scope. Storing both is two sources for one fact | `conflict_resolution.py:392` |
| field path | **exists as a concept**, new field `target_field_path`; membership-gated, see §6 | `notes.py:355`, `routes.py:9613` |
| question key | **decline** — the answer routes are keyed to a record's *open blocking questions*, not to field paths. ~~which is exactly why all 25 mappable paths return `422 unrecognized_field` there (`notes.py:98-111`)~~ **— STRUCK 2026-08-29: MEASURED FALSE. `system.technique` IS one of the 25 and IS accepted by `POST /answers` via `_apply_record_fields` (`routes.py:3883`, called at `:5431` and `:6395`). The cited docstring is itself stale and is corrected separately. The DECISION survives — a proposal targets a path, a question key is a different address space — but this justification did not.** A proposal targets a path; a question key is a different address space |
| proposed value | **genuinely new here**; exists unstored at `extraction.py` `FieldCandidate.proposed_value`, and stored-but-not-applied at `conflict_resolution.py:397` |
| unit | ~~**new, optional, never derived.**~~ **DROPPED 2026-08-29 (§10, DEC-11): "optional, never derived" still permits a unit the source never stated, with nothing requiring the `rule` sentence to cover it. A unit not stated in the source IS a guess (CLAUDE.md §5). Dropping is simpler than constraining.** Original reasoning: `_apply_run_field` carries an existing envelope's `unit` forward and never re-derives it (`routes.py:7379-7383`); a proposal must not invent one |
| vocabulary | **derived, not stored.** The closed-enum set is read from the vendored schema at runtime by `_record_enum_fields` (`routes.py:3883`); transcribing it into a proposal creates a second copy free to drift |
| source type | **exists** — `NOTE_SOURCES` (`notes.py:195-209`). Reuse it, and **do not** borrow `isaac_records.models.SOURCE_TYPES`: `notes.py:78-87` and `extraction.py`'s equivalent block both refuse that, because widening the evidence type system is a §13 truth-core change |
| client instruction / transcript excerpt | **exists** as the note's verbatim `text` (`notes.py:342-345`). ~~New on the proposal: `quote`, `start_char`, `end_char`~~ — **`quote` REMOVED 2026-08-29 (§10, DEC-3). Store `note_id` + `start_char` + `end_char` ONLY and derive the excerpt on READ.** Storing the words a second time puts a copy of a scientist's verbatim text somewhere `_retention_disclosure` (`routes.py:10402-10430`) does not describe, and an edited or dismissed note would leave it stale. Offsets validated `0 <= start <= end <= len(note.text)` at create |
| model interpretation | **exists** — `candidate_rule`, *"the sentence, not an id"* (`notes.py:356-359`), required whenever a path exists (`notes.py:410-419`). Reuse as `rule`, required unconditionally |
| evidence refs | **new, and deliberately weak**: `note_id` only. A proposal **mints no evidence**. Evidence is minted at apply time by `routes._apply_run_field` (`routes.py:7375`) |
| uncertainty | **REFUSE — conflicts with the repository.** `FieldCandidate.__post_init__` runs `guards.check_candidate_provenance`, which raises on `confidence`, `probability` or `score` at any depth (`extraction.py`, "CONFIDENCE IS REFUSED, BY THE EXISTING RULE"). A stored uncertainty is a confidence score with a different name. **Recommended alternative:** the `rule` sentence already says what was and was not established |
| abstention | **not a proposal.** The transcript reader already emits `abstentions` separately from `candidates` (`routes.py:10963`), and an abstention has no value to propose. It stays a note plus a response-level list |
| potential conflict | **derived, not stored.** `conflict_resolution.state_of` (`:716`) and `conflict_report` (`:984`) compute it from current evidence. A stored flag would go stale the moment a second answer arrives |
| unmapped remainder | **exists, and is the whole point of `Note`.** Content with no confident home is a note; a proposal is only minted where a value *and* a target *and* a rule exist |
| base revision / ETag | **new** `base_rev`, **FOR THE AUDIT RECORD ONLY — it is NOT the acceptance precondition (§10, DEC-1).** `base_rev` is the RECORD's rev and moves on ANY act, so using it as the precondition is wrong in BOTH directions: every proposal on an active record becomes permanently un-acceptable, and the target itself goes unchecked. **The precondition is a new `target_digest`** over the current value AND evidence envelope at `target_field_path`, on `competing_digest`'s shape (`conflict_resolution.py:384`, `:716`). Machinery exists (`exp.etag()`, `_check_if_match`, `_save_versioned`, `stale_write`/412) |
| created time | **exists** — `captured_utc` (`notes.py:348`); on a proposal, `proposed_utc` |
| expiry | **DECLINE — conflicts with the repository.** Nothing in this build runs on a timer; there is no scheduler, no sweeper, no cron. A stored `expires_utc` that no process enforces is a promise the system cannot keep, and this repository's recurring finding is precisely *a surface claiming what it had not done*. **Recommended alternative:** `base_rev` staleness, derived on read exactly as `competing_digest` staleness is (`conflict_resolution.py:384`, `:716`) — a proposal whose `base_rev` is behind the record's current `rev` reads `stale`, and acceptance re-checks the target |
| review status | **partly exists**; see §3 |
| reviewer identity | **new**, on the accepting transition: `trust_basis` + `subject` again |
| edited accepted value | **exists as a modelled distinction** — `CHOSEN_FROM_CANDIDATE` vs `CHOSEN_FROM_EDITED` (`conflict_resolution.py:173-180`), with the reason *"'I picked the second citation' and 'all the citations are wrong and the value is this' are different claims"*. Reuse verbatim as `accepted_from` |
| applied revision | **new** — `applied_rev`, `applied_run_id`, `applied_via` (which of the three writers ran). Nothing equivalent exists |
| rejection reason | **exists** — `dismiss_note`'s `reason`, stored when given and absent when not, *"because a fabricated justification in an audit trail is worse than a missing one"* (`notes.py:713-724`) |
| supersession | **exists as a pattern** — `ACTION_REVISE` keeps the superseded value on the transition (`conflict_resolution.py:180-184`); `edit_note` keeps `superseded_text` (`notes.py:280`) |
| idempotency key | ~~**DECLINE for this feature.**~~ **REVERSED 2026-08-29 (§10, DEC-13), and the decline was answering a different question.** It argued that every write is *idempotent by content* — true of APPLYING, false of CREATING: two identical `POST .../proposals` mint two different `proposal_id`s, so a retrying MCP client DOES duplicate. Create accepts an optional `client_request_key`; inside `record_lock`, a key already present on this experiment returns the EXISTING proposal instead of minting a second. Exactly-once within a scope, with no uniqueness constraint, because every write to one experiment holds that lock. Original reasoning: The mechanism exists (`Idempotency-Key`, `malformed_idempotency_key` at `routes.py:13035`, `409 idempotency_key_conflict` at `routes.py:13430`) but it exists for **submission**, which is externally observable and non-repeatable. Every write here is already idempotent by content: `_apply_run_field`'s `already` check (`routes.py:7355-7371`) and `save_versioned`'s byte-stable no-op. A second idempotency scheme with no consumer is the trap `routes.py:9579-9584` warns about for validators |
| audit / provenance link | **exists** — append-only `history` of transitions (`notes.py:369`, `conflict_resolution.py:406`) plus `note_id` |

Constants that must be serialised on the wire, not merely held in the class — the rule
`FieldCandidate.to_dict` set and `Note.to_state` follows (`notes.py:467-473`):
`is_field_value: false`, `is_evidence: false`, `verified: false`, and `applied: <bool>`.

---

## 3. State machine — what is new and what is a rename

`NOTE_STATES` is `{unreviewed, mapped, kept, dismissed}` (`notes.py:170-172`).
`RESOLUTION_STATES` is `{absent, current, stale, deferred}` (`conflict_resolution.py:204-209`).

| Requested | Verdict |
|---|---|
| created / pending | **rename** of `unreviewed` (`notes.py:158`). One state, not two — "created" and "pending" name the same moment |
| partially reviewed | **reject.** A proposal is one value at one path. A batch is N proposals; "partial" has no referent on a single one. If the master requirement means "some of a transcript's candidates are done", that is a **count over proposals**, not a state on one |
| edited | **not a state.** `edit_note` deliberately leaves the review state alone — *"fixing a typo is not a triage decision, and silently marking an edited note as reviewed would clear it out of the queue"* (`notes.py:661-666`). Model it as `accepted_from: edited` (`conflict_resolution.py:176-178`) |
| accepted | **genuinely new** |
| applied | **genuinely new**, and it must be distinct from `accepted` only if the two can diverge — see §6, where the recommendation removes the divergence |
| rejected | **rename** of `dismissed` (`notes.py:168`). Keep the *semantics* exactly: a state reached by an explicit act, recorded in history, **never a delete** |
| expired | **do not model** — no enforcer exists (§2) |
| superseded | **genuinely new** as a state; the *mechanism* exists as `ACTION_REVISE` |
| conflicted | **not a proposal state.** Derived from the address, by `conflict_resolution.state_of` (`:716`) |

**Recommended set (5):** `open` · `accepted` · `rejected` · `superseded` · `withdrawn`,
~~plus two **derived, never stored** reads: `stale` (from `base_rev`) and `appliable` (from §6).~~
`accepted` is terminal-and-applied, because §6's recommendation makes acceptance-without-application
unconstructible.

**BOTH DERIVED READS AS NAMED HERE ARE WRONG, corrected 2026-09-01 and struck rather than edited,
because §4's parenthetical was struck for exactly this and §3 WAS MISSED — a partially-swept
correction is a failure this repository has published before.**

- **`stale` is not derived from `base_rev`.** §10 **DEC-1** supersedes it: the precondition is
  `target_digest`, and `base_rev` is *"kept, for the audit record only, and this module never
  compares"* it (`proposals.py:96`; see also `:84` "STALENESS IS ``target_digest``, AND ``base_rev``
  IS NOT", and `:331` "``base_rev`` is in the set because it is an audit anchor and never a
  comparison"). The distinction is the whole of DEC-1: the record's rev moves on every unrelated act,
  so using it would make every proposal on an active record permanently un-acceptable **while
  leaving the target itself unchecked** — wrong in both directions at once.
- **`appliable` was never implemented.** Measured at `7ff8194`:
  `grep -rla 'appliable' apps/api/isaac_api/ --include='*.py'` -> **0 files**.

**What is actually served as derived-and-never-stored** is `target_stale`, `still_current`,
`excerpt`, `attributed` and `accepted_by` — each re-derived on every read, each `null` rather than
`false` when it cannot be answered (the run was removed), which is a distinction no surface may
collapse. `applied` is stored, not derived, and is true only in state `accepted`.

Acts: `propose` (the opening entry, as `capture` is at `notes.py:180-182`) · `accept` · `reject` ·
`supersede` · `withdraw`. Every act appends; nothing is removed; `revise_note`'s history-extension
guard (`notes.py:588-596`) is copied, not re-derived.

**"Nothing is removed" is scoped to the proposal, not to its container, and that distinction is not
a loophole — it is already true of notes.** `POST /api/experiments/{id}/discard`
(`routes.py:3200`) removes a record and its runs; its own description says *"IT IS NOT A GENERAL
DELETE, AND IT CANNOT REACH HISTORY"*, it refuses a submitted record, and revision, submission and
published artifacts are never removed. Discarding a record **disposes of its proposals with it**,
exactly as it disposes of its notes, because they live inside the record's own state document
(§7). That is not a per-proposal delete and must never be described as one, and no operation in
this contract may be built that removes a proposal from a record that survives.

**A superseded proposal is entered by a person, never by the system.** `supersede` is an explicit
act with the same confirmation and CAS requirements as `accept`; nothing auto-supersedes on the
strength of a second proposal arriving. That mirrors `conflict_resolution`'s rule that nothing
inspects competing values and picks one (`conflict_resolution.py:35-38`).

---

## 4. Operations

All five are **record-scoped writes** into the experiment's own state document, so **all five take
the RECORD's `If-Match`, never a run's** — the rule `routes.py:9578-9584` already states for notes
and `conflict_resolution.py:66-70` restates for run-scoped decisions. There is deliberately **no
per-proposal validator**: a second concurrency scheme with no consumer is a trap.

| Operation | Shape | CAS | Refusals (existing typed codes) |
|---|---|---|---|
| List | `GET /api/experiments/{id}/proposals` | none; returns `ETag` | `404 experiment_not_found`; `422 unknown_cursor`; **`422 cursor_order_mismatch`** (added 2026-09-02, see below); `503 experiment_storage_unavailable` |
| Read one | `GET .../proposals/{proposal_id}` | none; returns `ETag` | `404 proposal_not_found` (new, modelled on `note_not_found`, `routes.py:9751-9767` — "the record was read successfully and holds no such thing") |
| Create | `POST .../proposals` | **required** | `422 unrecognized_field` (unknown body key, or a target outside the permitted set); `422 unknown_run`; `422 invalid_field_value`; `422 unrepresentable_value` (value JSON cannot round-trip); `422 unsupported_proposal` (model refusal relayed, never a 500 — `routes.py:10110-10115`); `422 too_many_proposals`; **`422 proposals_too_large`** (added 2026-08-30, see below); `428 precondition_required`; `400 malformed_if_match`; `412 stale_write`; `409 wildcard_precondition_refused` (`If-Match: *`) |
| Review | `POST .../proposals/{id}/review` — `{confirmed_by_user, action: accept\|reject\|supersede\|withdraw, value?, accepted_from?, reason?}` | **required** | `422 confirmation_required`; `422 unknown_proposal_action`; `422 not_an_allowed_value` (enum target); `409 human_actor_required` (§5); `422 no_write_path_for_field` (§6); `409 target_run_removed` (new — see below); **`409 target_scope_mismatch`** (added 2026-08-30, see below); `412 stale_write`; `409 proposal_stale` (new — ~~`base_rev` moved~~ **the TARGET DIGEST moved; `base_rev` is not the staleness key and never was — see §10 DEC-1, which supersedes this parenthetical and was written after it**; the accept re-reads and refuses rather than overwriting) |
| — | **There is no DELETE, and there will not be one.** `routes.py:10254-10259` | | |

**Every operation takes `scope: TutorialScopeDep` as its first parameter**, exactly as `post_note`
and `post_note_review` do, and every write holds `ws.record_lock(experiment_id, session_id=scope)`
(`routes.py:10023`, `:10233`). This is not optional plumbing — see invariant **I7**.

**`409 target_run_removed`.** A proposal may name a `run_id`, and `Experiment.remove_run`
(`workspace.py:3089`) is reachable through `POST .../runs/{run_id}/remove` (`routes.py:9529`). Its
docstring is explicit that **survivors' ordinals are NOT renumbered** (`workspace.py:3096-3118`),
so a removed run's id is never reissued and a proposal that named it goes **permanently dangling**
rather than silently shifting onto a neighbour. On review, a proposal whose `run_id` no longer
resolves is refused with `409 target_run_removed`, naming the run id, and **must never be silently
re-targeted** — §2 already forbids inferring a run from "the only run that happens to exist"
(`notes.py:349-352`, `conflict_resolution.py:390-392`), and re-targeting after a removal would be
that inference in its most damaging form. The proposal stays readable, its note is untouched, and a
person may `withdraw` it. Creation-time `422 unknown_run` covers only the run that never existed;
these are different failures and must not share a code.

**`409 target_scope_mismatch` (added 2026-08-30).** `_proposal_writer_for` is re-evaluated at
REVIEW time over a `run_id` that was fixed at CREATE time, so the create route's scope check cannot
bind a later read. Two ways they come apart, and the first was **measured as a reachable HTTP 500**:
a stored proposal naming a run-scoped `target_field_path` with `run_id: null` reached
`run.draft.get("fields")` with `run` at `None` (`AttributeError: 'NoneType' object has no attribute
'draft'`); and a schema refresh, or a change to any of the three sets the dispatch reads, can move a
path between writer classes — or out of all of them — after proposals for it are already stored.
`IngestionProposal.from_state` accepts such a document because this model performs no schema lookup
and deliberately does not learn to, so the shape is reachable through a hand edit or a legacy
document. It is now a typed **409** naming the path, the proposal's scope and the writer's, modelled
on `target_run_removed`: the body was fine and the record's own stored state is what refuses. Like
`target_run_removed` it gates **`accept` alone** — rejecting, superseding and withdrawing write
nothing, and gating them would leave a proposal no operation could ever clear.

**`422 proposals_too_large` (added 2026-08-30).** DEC-4 bounds ONE proposal and DEC-5 bounds the ROW
COUNT, and **the two do not compose**: their product is a **262 MB** experiment document that every
individual refusal admits. `load_experiment` parses the whole document on every read and
`_authoritative_signature` hashes the whole of it on every save, so a bound on rows that a client can
defeat by making each row large is not a bound. A total-bytes ceiling over `state["proposals"]` now
refuses at create — **never trims**, because the oldest proposal is a recorded judgement. **The
number is a JUDGEMENT and not a measurement, and the code says so**: nothing here has measured a
parse or a hash cost at any document size. It gates **create only**; refusing an *acceptance* because
the audit trail would not fit would leave a proposal permanently un-acceptable, which is DEC-9's
unclearable-queue defect one feature over.

**`order`, and `422 cursor_order_mismatch` (added 2026-09-02).** DEC-5's window is read from the
**oldest** end: `_sorted_proposals` (`workspace.py:1738`) orders `(proposed_utc, proposal_id)` and
the list route walks that order forward from the cursor. A newly created proposal carries the
LATEST `proposed_utc` on the record and therefore sorts **last**, so on a record already holding
`_PROPOSAL_WINDOW_DEFAULT` (50) proposals it is **not in the default window at all** and is
reachable only by paging to the end. That was measured as a real dead end on the website: the
panel's arrival announcement reads `by_state.open` — the whole record, deliberately — so it could
truthfully say a proposal had arrived while the window in front of the reader could never contain
it.

`GET .../proposals` therefore takes an optional **`order`**, with `oldest_first` (**the default,
and unchanged** — a review queue reads chronologically, and every existing client omits the
parameter) and `newest_first`, which is the **exact reverse of the same total order**. Both return
the same rows and the same `total`, `returned`, `by_state`, `unreadable_entries` and `has_more`;
only the direction differs, and there is no second sort — the reverse of a total order is total,
which is what keeps the cursor walk as well defined as the forward one.

**The RESPONSE states its own `order`**, beside `window_default` and `window_max` and for the same
reason they are there. A caller that has to remember what it ASKED for in order to describe what it
GOT will eventually describe one while holding the other, and that was measured rather than
imagined: the panel's count line was built from request state and so claimed "newest first" over
the oldest-first rows still on screen while a read was in flight, and went on claiming it over an
empty list after a read that failed — in a live region, so the single utterance a screen reader
received was the one made while the claim was false. It also answers the question for an MCP
caller, which never sees the query string at all. **A refusal carries no `order`**: there is no
window, so there is nothing whose direction could be stated.

**A CURSOR BELONGS TO THE ORDER IT WAS ISSUED UNDER, and a cross-order cursor is refused rather
than answered.** This is not caution: both orders hold the same proposals, so the id inside such a
cursor is always **found**, and the walk would simply continue from the wrong side and hand back
rows the client had already read as though they were the next page. Measured with the check
removed, over six proposals with `canonical` the stored oldest-first order: the crossed
newest-first request answered **200** with `[canonical[0]]` and the crossed oldest-first request
answered **200** with `[canonical[5]]` — two wrong answers, no error, nothing in either body
saying so. It is the same wrong-answer-instead-of-an-error failure `unknown_cursor` exists to
prevent, and it is invisible to that check, which is why it is a separate refusal:
**`422 cursor_order_mismatch`**, naming the cursor's order and the requested one.

It is checked **before** the lookup, and that is a **preference rather than a necessity** — a
review measured the stronger claim and found it false: on a cross-order cursor whose id the record
HOLDS, the two orderings are indistinguishable. Exactly one input separates them, and it is pinned
by test rather than argued here: a cross-order cursor naming an id the record does **not** hold.
Checked first it is `cursor_order_mismatch`, which names the mistake the client actually made;
checked second it is `unknown_cursor`, which sends a client that crossed the orders looking for a
proposal that was never the problem.

**The `oldest_first` cursor is still the bare proposal id.** The asymmetry is deliberate and is why
the order travels as a prefix rather than as an encoding: every `next_cursor` this server has ever
issued was a bare id meaning "continue oldest-first", so those keep meaning exactly that, and only
the new direction — which had issued none, because it did not exist — carries a
`newest_first:` tag. `:` is safe as the separator because a proposal id is 26 characters of
`[0-9A-Z]` from `new_record_id()` — **an invariant about API-MINTED ids, and the qualification is
part of it**: `IngestionProposal` validates no id shape on hydration, so a hand-edited or legacy
document could persist a `proposal_id` containing a `:`. **The consequence is a refusal and never a
wrong answer**, which is why it is stated rather than fixed here: such a value can only arrive as a
client's `after`, and every path through it ends in `422 unknown_cursor` or `422
cursor_order_mismatch` — none returns a window from the wrong side. Re-encoding both directions was mutation-tested and turns two
pre-existing DEC-5 tests red; that is the breaking change this shape avoids, and a future slice
that wants symmetry is proposing a contract break rather than a tidy-up.

`order` is published through `policy.proposal_list_query_parameters()`, so the OpenAPI parameter
and `isaac_list_proposals`' tool schema are **derived from the route signature** and neither was
edited by hand. Adding it to `PROPOSAL_LIST_QUERY_ALLOWLIST` is what exposes it, and that gate was
satisfied on the same ground as `state`: `order` names no field, selects on no scientific content,
and widens no response.

**Concurrent acceptance of the same field.** Two accepts naming one target serialise on the record
lock and on the record's `If-Match`: the first wins and moves `rev`; the second finds its
`base_rev` behind and is refused **`409 proposal_stale`** with nothing written — never `412`, which
would blame the caller's validator when what actually changed is the target. The loser is not
auto-superseded; a person re-reads the now-written value and either withdraws the proposal or
records `supersede` explicitly. If both accepts nonetheless land as two confirmed answers,
`evidence_classify` flags the address as conflicting and the existing conflict-resolution path
(`conflict_resolution.py:8-17`) is the remedy — this contract adds no second one.

Ordering, copied from `post_note` and `post_conflict_resolution` and non-negotiable: **every input
is resolved before the precondition is checked** (`routes.py:10036-10038`,
`routes.py:15995-15999`), so a malformed body is a 422 regardless of validator freshness and a
refused request can never leave a partial act behind. The whole review runs inside
`ws.record_lock` (`routes.py:10233`; the capture route takes it at `routes.py:10023`).

**THE FIRST IMPLEMENTATION BROKE THAT RULE IN TWO PLACES ON THE CREATE ROUTE, AND IS FIXED
(2026-08-30).** The `client_request_key` deduplication branch and the per-record ceiling both ran
*before* `_check_if_match`, so a create with **no `If-Match` at all** could be answered `200` (an
existing proposal, `deduplicated: true`) or `422 too_many_proposals` — while the operation's own
published description said an omitted header is `428`. Nothing was written by either, so this was a
false CLAIM rather than corruption; it is corrected by moving both checks after the precondition,
which is what this paragraph's rule required. A retrying client that presents the `ETag` it held
*before* its first attempt now meets `412` and re-reads, and the deduplication branch answers its
second attempt — **the exactly-once guarantee of DEC-13 is unchanged and is now delivered by two
mechanisms rather than one.** The BODY is still resolved first: that is this paragraph's rule and it
is a different rule from the state checks, which are questions about the record and may only be
answered for a caller holding the record's current version.

**The create operation declares ONE success code, `200`, and it is the only creating `POST` in this
API that does not answer `201`.** It has two outcomes and only one of them creates, so an
operation-level `201` would be an operation-wide claim that it creates; the repository's own contract
test refuses two success codes for exactly that ambiguity. The status says the request succeeded and
the body's `deduplicated` says which of the two happened.

~~**MCP: no new tool.**~~ — **AMENDED 2026-08-30, AND ONLY ONE OF THIS PARAGRAPH'S TWO HALVES IS
SUPERSEDED. It is struck in place rather than rewritten, because "no new tool" is a claim a future
session acts on.** `PERMITTED_TOOL_NAMES` is closed at 10 (`mcp/policy.py:683-699`) and
`forbidden_tool_reason` turns "we decided not to" into an `ImportError` (`mcp/policy.py:31-37`).

**THE HALF THAT SURVIVES, AND IS STRENGTHENED:** adding `isaac_accept_proposal` would give an
external agent a path to scientific content; `ai-integration-decision-packet.md` §6's "external
agents cannot submit" points the same way. **No accept, review, supersede, withdraw, finalize,
export or Submit tool may exist at any scope**, and `POST .../proposals/{id}/review` must never
appear in an MCP `OPERATIONS` entry. Measured while amending this: `FORBIDDEN_TOOL_TOKENS`
(`mcp/policy.py:116`) contains `approve` but **NOT `accept`**, so `isaac_accept_proposal` would
pass the token guard today and be caught only by the closed name set — one reviewer's attention
away from shipping. `accept` is added to that set, so the refusal is an `ImportError`.

**THE HALF THAT IS SUPERSEDED:** the decline of a *creation* tool, and the "not recommended"
verdict on a read-only `isaac_list_proposals`. The 2026-08-29 authorization covers the remote MCP
architecture, and the Claude voice-to-proposal workflow it authorizes is **unbuildable** if MCP
cannot create a proposal — that is the whole point of minting a proposal type rather than letting
an agent write a field. **The safety argument runs the other way from how §4 first read it:** §5
**I1** and **I2** make a proposal inert to the draft, to `export.transform` and to
`submissions.content_signature`, so CREATING one mutates no authoritative metadata. That inertness
is precisely what makes it the safe channel for model-derived output.

**The amended surface — ~~three~~ **FOUR** tools, least privilege:**

*(Heading corrected 2026-09-01. It said "three" while the cells below name **four**; the cells are
the spec and the count was wrong. The implementing slice found it, and — worth recording because it
is the same class of error — the slice's own note reporting the defect was filed against §10.2,
which is "The thirteen decisions" and says nothing about MCP tools. Both the defect and the
misfiled complaint came from the same conflation. Re-derive with
`grep -n '^## \|^### ' docs/ingestion-proposal-contract.md`: §4 Operations spans **210–343**, this
table sits at **342–350**, and §10.2 begins at **681**.)*

| Tool | Scope | Why this scope |
|---|---|---|
| `isaac_propose_field_value` | **new** `isaac:proposals.write` | Creating a proposal is NOT a draft write and must not require `DRAFT_WRITE`, which can change draft content directly. The model-derived channel gets the weakest scope that works. |
| `isaac_list_proposals`, `isaac_get_proposal` | `Scope.READ` | Reading proposal status is a read. §4 called it "arguable"; the workflow requires it. |
| `isaac_get_changes` | `Scope.READ` | The bounded cursor feed. |

Scopes still do not nest (`policy.py`, "WHY THE SCOPES DO NOT NEST"), so a deployment granting only
~~`isaac:proposals.write` can create a proposal and read nothing else.~~

**MEASURED FALSE 2026-09-01, AND STRUCK RATHER THAN REWORDED, because this sentence is what a slice
cites when it decides what a tool may cost — and one did.** An implementation gave
`isaac_propose_field_value` the `PROPOSALS_WRITE` scope ALONE to satisfy it. The safety case was
that the handler returns a BUILT projection rather than the route body, and that was true of the
SUCCESS branch. An independent review measured the other one — the refusal branch forwards the
route's body whole, and the route's refusals were written for a caller holding `READ`:

```
if_match='"0.0"'   -> 412 {"current_rev": 1, "current_version": "...1"}
if_match='"...1"'  -> 200, proposal STORED, envelope etag "...2"
bad span           -> 422 {"note_text_length": 55}
```

So a propose-only principal reached a validator in **one extra request**, then kept one forever
from each success envelope; bogus ids gave existence oracles besides.

**The correct reading is that the create route's precondition is the RECORD's ETag, so a principal
that may not read the record cannot use it.** Withholding `current_version` from the refusal does
not rescue the shape — it makes it INERT, because such a caller could then never obtain an ETag and
never create anything, and a capability that cannot work is not least privilege. The implementation
therefore requires `{READ, PROPOSALS_WRITE}`, and a `PROPOSALS_WRITE`-only principal is served an
**empty tool list**.

**What this sentence was reaching for survives intact, and is the reason the scope still exists:**
`isaac:proposals.write` separates *may propose* from `DRAFT_WRITE`'s *may change draft content
directly*. That separation is real, is enforced, and is unaffected by the correction above.

**Three consequences to state rather than discover.** §5 **I4** still binds unchanged: acceptance
requires a trusted human identity and answers `409 human_actor_required` in every
default-configured deployment, and MCP creating a proposal does not move that one inch. The
`trust_basis` of an MCP-created proposal is the OAuth **service principal's**, never a human's, and
the accepting scientist's identity is a separate field on a separate transition — the two must
never collapse. And `client_request_key` (§2, DEC-13) becomes load-bearing rather than optional,
because a retrying MCP client is exactly the case its reversal was argued for.

---

## 5. Hard safety rules, as testable invariants

**I1 — Creating a proposal never mutates authoritative metadata.**
Test: capture `export_draft(exp)` and every run's `resolved_run_draft` byte-for-byte before and
after `POST .../proposals`; assert equality. This is the shape
`test_conflict_resolution.py` already uses for evidence (`conflict_resolution.py:31-34`).

**I2 — A proposal is inert to export.** Test: `state["proposals"]` populated ⇒ the exported official
record is byte-identical and `export.transform` reads only its named keys
(`conflict_resolution.py:62-66`). Storing outside `draft` (§7) makes this structural, not asserted.

**I3 — Applying goes through the same service as manual entry.** Per target class, by name:

| Target class | Manual route | The function that must be reused |
|---|---|---|
| 5 run-level paths (`RUN_WRITABLE_FIELD_PATHS`) | `PATCH /experiments/{id}/runs/{run_id}` | **`routes._apply_run_field`** (`routes.py:7313`) |
| 13 `field:` addresses (of `EXPERIMENT_OVERRIDABLE_ADDRESSES`, `routes.py:7147`, which has **15** members — 13 `field:` plus `block:tags` and `block:attribution`) | `POST .../runs/{run_id}/overrides` (`routes.py:8613`) | **`workspace.Experiment.set_run_override`** (`workspace.py:3213`) |
| `system.technique` (record-level closed enum) | `POST /experiments/{id}/answers`, `.../edit` | **`routes._apply_record_fields`** (`routes.py:4190`), which itself reuses `_apply_run_field` (`routes.py:7320-7324`) |
| open blocking questions | `POST .../answers` | **`isaac_records.complete.apply_answers`** (`src/isaac_records/complete.py:153`) / `apply_corrections` (`:490`) |

Test: monkeypatch each of the four and assert the accept path calls it. Negative control:
`rg` the proposals module for `"status": "verified"` and for `user_confirmation(` and assert **zero
hits** — a second envelope builder is a second definition of "what a confirmed field looks like"
(`routes.py:4197-4200`).

**I4 — Acceptance requires a trusted human identity, and by default no deployment establishes one.**
`identity.require_human_actor` exists (`identity.py:1018`) and its dependency admits only
`TrustTier.EDGE_HUMAN` with a human (`identity.py:1070`); `HumanActorRequired` renders a typed
**409** (`identity.py:989-1000`) through `human_actor_required_handler` (`identity.py:1007`),
registered in `create_app` at `app.py:261`.

**No trusted authentication boundary exists in this build.** Dean reconfirmed the Service is a
plain ClusterIP with no NetworkPolicy, so any in-cluster pod can forge forwarded identity headers
(`CLAUDE.md` §15, 2026-08-12), and `identity.py:1024-1030` records the half that matters and is
unconditional: **no shipped verifier reads a request at all**, so a forged `X-authentik-*` header is
worth exactly nothing here.

~~**What that means for this contract, stated plainly:** if `POST .../proposals/{id}/review`
consumes `require_human_actor`, then **in every shipped deployment acceptance returns 409 and writes
nothing.**~~ — **STRUCK AND CORRECTED 2026-08-28, and kept in place rather than deleted because it
is exactly the form `identity.py` had already withdrawn, and I restated it anyway.**
`require_human_actor`'s own docstring records the withdrawal: *"THIS USED TO SAY 'in this build it
refuses EVERY request' … the default-refusal claim is a claim about **configuration**, not about the
build, and stating it the stronger way is the kind of comfortable falsehood this project has been
corrected for before"* (`identity.py:1024-1038`). The correction was available in the file I was
citing, one paragraph from the line I quoted, and I did not carry it.

**The accurate form.** A deployment that sets `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` and
`ISAAC_FIXTURE_ACTOR_SUBJECT` selects `FixtureEdgeVerifier`, which mints an actor **from the process
environment**; the dependency then admits the request, and everything it attributes carries
`trust_basis="test_fixture"` permanently. **No shipped deploy artifact sets either variable** —
pinned by `apps/api/tests/test_deploy_config.py:256`, which asserts the two names appear in no
deploy artifact. So: acceptance is refused in every **default-configured** deployment, and that is a
statement about configuration, not a property of the build. A slice must write the refusal path as
the one that runs everywhere, and must not write code, copy, or a test that assumes acceptance is
unreachable — it is reachable under a configuration nothing ships.

That refusal is the honest outcome and it is the recommended one — it is exactly what
`POST .../submit` already does. Three consequences a slice must not soften:

- The **frontend must not render an Accept control** whose only outcome is a 409. Precedent:
  `_UNACCEPTABLE_READER_PATHS` (`routes.py:10376-10384`) raises **`RuntimeError` while the module
  loads** — so the application fails to start — rather than let a control exist whose only possible
  outcome is a refusal. (The exception type is `RuntimeError`, not `ImportError`; the MCP name guard
  at `mcp/policy.py:31-37` is the one that fails the import itself, and the two are different
  mechanisms with the same purpose.)
- The proposal's `subject` stays `None` and `trust_basis` stays `unattributed`
  (`conflict_resolution.py:498-503`). No placeholder. `stamp_actor` returns `None` and the caller
  writes no actor rather than a placeholder (`identity.py:1122-1150`).
- **Reject / withdraw do not require an actor.** They record that nobody wants the proposal, which
  attributes nothing to anybody, and gating them would leave the queue permanently unclearable —
  the exact defect `conflict_resolution.py:8-17` was built to fix.

**I7 — Worked-example isolation. A proposal never escapes a tutorial session, and a tutorial
session never persists one as normal content.** `CLAUDE.md` §15 calls this "the invariant this
feature must not break", and it is enforced three times over on the persistence path. This contract
inherits it rather than restating it: every operation takes `scope: TutorialScopeDep` and every
write holds `ws.record_lock(experiment_id, session_id=scope)` (`routes.py:10023`, `:10233`), so a
proposal is read and written **only** within the scope that owns the record, and
`experiment_repository.refuse_if_not_persistable` (`experiment_repository.py:1956`) sits behind the
durable write. Two further consequences a slice must not drop:

- **`stamp_actor` returns `None` inside a tutorial session unconditionally and first** — *"a
  perfectly verified actor in a tutorial session still stamps nothing"* (`identity.py:1122-1140`).
  So a proposal accepted inside a worked example is `unattributed` even under the fixture verifier
  of I4.
- Tests must assert the negative: a proposal created under `X-Isaac-Tutorial-Session` is invisible
  to the ordinary-scope list, and a canonical example id is refused in any scope.

**I5 — A proposal can never present as a confirmed value.** Frozen + slotted, four constants as
read-only properties, serialised on the wire (`notes.py:31-50`, `:467-473`).

**I6 — Nothing captured is discarded.** Every proposal carries a `note_id` whose note holds the
verbatim words; the note survives every proposal outcome including `rejected`. Test: reject a
proposal, assert the note is unchanged and still listed.

---

## 6. The 7 paths writable by no route — confronted, not papered over

Re-derived at HEAD, not quoted: of `NOTE_MAPPABLE_FIELD_PATHS` (25, `routes.py:9613`), exactly **18**
are in `NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT` (`routes.py:9690`) — 5 run-writable and 13 reachable
as a `field:` override, with no overlap between the two. `system.technique` is one of the 13 **and**
is separately reachable through the record-level enum path; it is not a nineteenth path. The **7** that no route accepts are the
six `system.configuration.*` paths and `timestamps.created_utc`.

Why they have no route is **not** an oversight and must not be "fixed" in passing:
`system.configuration` is a **designated open namespace** in the vendored schema (it declares no
`properties`), `field_level` leaves it unclassified, and `CLAUDE.md` §15 records the six as
`unclassified, verified` pending an external answer (`routes.py:9635-9644`). Classifying them here
would be deciding an open question, not reporting a fact.

**The contract's answer: the permitted target set is derived at import from
`NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT`, not from `NOTE_MAPPABLE_FIELD_PATHS`.**

```
PROPOSAL_TARGET_PATHS = NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT   # 18 today, derived
```

with a construction-time guard in the same shape as `routes.py:10376-10384` — a module-level
`RuntimeError`, so the application refuses to start — so a future widening of
the reader that outran the writers fails at import rather than at a scientist's click.

Consequences, each deliberate:

- A candidate at one of the 7 **is still captured in full** — as a `Note`, exactly as today, with
  `candidate_field_path` set. Nothing is lost. `map_note` remains permitted for all 25, for its own
  stated reason: *"refusing the mapping would throw away a scientist's own judgement about where
  their prose belongs in order to avoid saying one honest sentence"* (`notes.py:624-629`).
- `POST .../proposals` at one of the 7 returns **`422 no_write_path_for_field`**, naming the path,
  saying the note *was* stored, and saying **this is a limitation of this build, not a statement
  about the official schema** — the refusal wording `routes.py:10077-10090` already models, and
  `CLAUDE.md` §1 requires (the schema is not ours to speak for).
- The response carries the served set under its own key so a surface can be true about the path in
  front of the reader (`routes.py:9647-9652`), and no Accept control is rendered for a path outside
  it.

**This makes "created and accepted but never applied" unconstructible**, which is why §3 folds
`applied` into `accepted`. The alternative — allow the proposal, refuse the apply — reproduces this
repository's most-repeated defect: a surface returning success for work it had not done.

**Named rather than implied:** the *better* fix is to give those 7 a write route. That is a product
decision gated on an external answer, it is explicitly not made at `routes.py:9635-9644`, and it is
not this contract's to make. When it lands, `PROPOSAL_TARGET_PATHS` widens automatically, because it
is derived from the routes that enforce it and never listed by hand.

**A known pre-existing divergence this contract must not inherit:** `field:system.technique` **is**
in `EXPERIMENT_OVERRIDABLE_ADDRESSES` and its run override returns 200 while accepting off-enum
values (`CLAUDE.md` §11, 2026-08-27). A proposal accepted at that path must route through
`_apply_record_fields`, which checks the enum — not through the override.

---

## 7. No `0006` migration. The state document suffices.

**Recommendation: store proposals in the experiment state document at `state["proposals"]`, beside
`state["notes"]`, and add no migration.**

The argument is mechanical, not preferential:

1. **Notes established the precedent and it holds today.** `Experiment.to_state` writes
   `"notes"` (`workspace.py:2817`); `from_state` reads it with `.get` and an empty default, and the
   comment says in terms: *"No migration is required for notes either... an absent key hydrates to
   an empty pair"* (`workspace.py:3678-3681`). The same `.get`-with-default tolerance gives
   `"proposals"` the same property: a document written before proposals existed hydrates to zero
   proposals rather than raising.
2. **The durable column already holds the whole document.** The state document is upserted into
   `isaac_experiments.state`; a new key inside it needs no DDL.
3. **A new table would be a recorded scope extension that has been botched four times.**
   `db_write.OWNED_TABLES` (`db_write.py:166-200`) documents `isaac_runs`, the five
   submission-lifecycle tables, and `isaac_run_projection` each being added before any committed
   `CLAUDE.md` §15 sentence named them — and `db_write.py:176-186` records that even the *correction*
   was false by one commit. A fifth instance is avoidable by not needing a table.
4. **The highest migration is `0005_run_projection`, which is NOT approved and NOT applied
   anywhere** (`CLAUDE.md` §15). A `0006` would queue behind an unapproved `0005`, and applying any
   migration to the hosted environment is the operator's act, not an agent's — a hard stop.
5. **Signature and CAS come for free.** `_experiment_signature` hashes `notes` (`workspace.py:1607`)
   with the reasoning that capture, mapping, editing and dismissal each change what the record holds,
   so `rev` and the `ETag` must move and a stale second writer must be refused
   (`workspace.py:1584-1606`). Adding `"proposals"` to that payload gives proposals the identical
   guarantee, and legacy documents hash with `"proposals": []` so no spurious `rev` bump occurs —
   the property runs and notes both relied on.

**Why `state["proposals"]` and not `draft["ingestion_proposals"]`,** i.e. why not follow
`conflict_resolution.DRAFT_KEY`: the draft is what export reads. `conflict_resolution.py:70-79` has
to disclose that for a zero-run experiment its key travels into `submissions.content_signature`.
Notes' location has no such disclosure to make, because `export_draft` reads `Experiment.draft` and
notes are not in it (`routes.py:9576-9577`). Choosing the location with no leak to disclose is
strictly better, and it makes invariant **I2** structural rather than asserted.

**Consequence to state rather than discover:** a proposal is therefore *not* visible to
`export.transform`, *not* in the submission content signature, and *not* in any run's
`resolved_run_draft`. If a future slice wants proposals to influence a submission, that is a new
decision requiring its own argument — it is not implied here.

**CORRECTION, 2026-08-30 — THAT LIST READS AS COMPLETE AND OMITS THE ONE ENTRY THAT POINTS THE OTHER
WAY.** All three statements above were re-verified and all three are true. What the enumeration does
not say is that `submission_store.record_submission` does
`json.dumps(exp.to_state(), sort_keys=True)` (`submission_store.py:504`) and writes the result into
`isaac_experiment_revisions.state`. `Experiment.to_state()` includes `proposals.STATE_KEY`, so
**every proposal — its proposed value, its `rule`, its `client_request_key` and its full audit
history — is copied verbatim into an owner-approved-but-unapplied lifecycle table at every submit.**

Three qualifications travel with that, so it is neither over- nor under-stated:

* **It is not new behaviour and it is not a defect.** `state["notes"]` has done exactly the same
  since notes were added, and a whole-document snapshot is what a revision row is *for* — a revision
  that stored only the export units could not answer "what did this record look like when it was
  submitted".
* **It does not move the content signature**, so it changes no submission identity; see §10 DEC-10
  as corrected.
* **No deployed system writes it today.** `0003_revisions` and `0004_submissions` are approved by
  the project owner and **applied to the hosted database nowhere** (`CLAUDE.md` §15).

It is recorded because an enumeration presented as complete is itself a checkable claim, and this
one was incomplete in the single direction a reader would rely on it for: it lists three places a
proposal does not reach, in a section arguing that the storage location has no leak to disclose.

---

## 8. WHAT THIS CONTRACT DOES NOT COVER

1. **Authorization.** ~~This is a design document. No committed sentence authorizes building it. A
   slice that implements it must establish and cite its own authorization basis.~~ **SUPERSEDED
   2026-08-29 — see §10. That sentence was TRUE when it was written and is struck in place rather
   than deleted, so a reader can see this is a recorded change of scope and not a drift.** The
   second half still binds: an implementing slice cites §10 and the `CLAUDE.md` §15 entry of the
   same date, not this paragraph. **One half was also OVER-strong and is corrected here:** storing
   at `state["proposals"]` writes `isaac_experiments.state`, which the 2026-08-07 §15 lift already
   covers ("app-owned tables for experiments and their normal application state"). The FEATURE
   needed authorizing; the persistence LOCATION was already covered, and a slice should cite that
   sentence rather than re-argue it.
2. **Any database migration, table, or hosted application.** §7 argues none is needed; if a future
   slice disagrees, it needs a packet, owner approval, and an operator action, and must name the
   table in `CLAUDE.md` §15 **in the same change**.
3. **Making acceptance actually possible.** §5 I4 concludes acceptance returns 409 in every
   **default-configured** deployment — a claim about configuration, not about the build, since
   `FixtureEdgeVerifier` reaches an actor from the process environment and no shipped deploy
   artifact sets its two variables (`test_deploy_config.py:256`). Building a trusted authentication
   boundary is out of scope, is gated on infrastructure ISAAC does not own, and is not fixed by
   anything here.
4. **Giving the 7 unwritable paths a write route.** §6 declines it and says why.
5. **An automatic producer.** `notes.py:10-21` is explicit that no pipeline was rewired and that the
   vocabulary exists ahead of its producers. This contract adds a *destination* for valued
   proposals; wiring `extraction.py`'s `unrecognised_labels`, ~~or CSV ingest, or the transcript
   reader's currently-unstored `candidates`, is~~ or CSV ingest, is separate work.
   **SUPERSEDED IN PART, 2026-09-03 — the transcript clause is struck IN PLACE rather than
   deleted, because it was true when it was written and a reader must be able to see that this
   is a recorded change and not a drift.** The transcript reader's candidates are **no longer
   unstored**: `POST /api/experiments/{experiment_id}/transcript` mints one durable
   `IngestionProposal` per candidate, server-side, inside the same `record_lock` and the same
   save as the notes it stores. See **§11**. The other two producers are unwired exactly as this
   item says, and "an automatic producer" is still not covered by anything — a capture is a
   scientist pressing Finalize, not a pipeline (§11.6).
6. **An apply route for `POST /ingestion/csv/preview`.** That is a **committed human decision**
   (reconciliation-only, "a deliberate authority boundary, NOT a defect"), not residual work.
7. **Any LLM or external model provider.** A proposal's `rule` is a deterministic sentence from a
   committed table. No production provider is authorized; every seam answers `501`.
8. **MCP surface, frontend design, and copy.** ~~§4 declines a new tool~~ — **AMENDED 2026-08-30:
   §4 now permits exactly three, all read-or-create, none able to accept, review or Submit.** The
   UI remains unspecified beyond the two negative constraints in §5 and §6 (no Accept control that
   can only be refused).
9. **Expiry, scheduling, background sweeps, change feeds, cursors, event logs, and Undo.** ~~None
   exists in this repository and none is designed here.~~ **The FIRST HALF was independently
   re-measured on 2026-08-29 and is TRUE — ~~`rg` for `get_changes_since|change_feed|changes_since|
   next_cursor|watermark|event_log` over `apps/api/isaac_api/**/*.py` returns nothing but DB-API
   cursor objects.~~ The SECOND half is superseded: a bounded cursor change feed IS authorized as of
   2026-08-29 (§10) and is designed in its own contract.** Expiry, background sweeps and Undo remain
   out of scope, and expiry for the reason this document already gives: nothing in this build runs
   on a timer, so a stored `expires_utc` no process enforces is a promise the system cannot keep.

   **THE `rg` CLAIM IS FALSE AT HEAD, AND IT WAS THIS CONTRACT'S OWN IMPLEMENTATION THAT FALSIFIED
   IT — corrected 2026-08-30, struck rather than deleted, because it was TRUE when it was measured
   and a reader must be able to see that it expired rather than that it drifted.**
   `GET .../proposals` serves **`next_cursor`** (contract §10 DEC-5's bounded window), so that
   alternation now matches `apps/api/isaac_api/routes.py`. Re-measured at this branch's HEAD:
   `next_cursor` is the **only** one of the six that matches — `get_changes_since`, `change_feed`,
   `changes_since`, `watermark` and `event_log` still return nothing but DB-API cursor objects. The
   substantive claim the sentence was making is therefore ~~**unchanged**: this repository still has
   no change feed, no watermark and no event log. What it has gained is one paginated list's cursor,
   which is the foundation DEC-5 named and is not the feed.~~

   **HALF OF THAT IS NOW FALSE, corrected 2026-09-01 and struck rather than deleted, because it was
   TRUE when it was measured on 2026-08-30 and a reader must be able to see that it EXPIRED rather
   than that it drifted.** The change feed shipped in PR #210 (merged `31ca1d2`), one day after the
   sentence above was written. Re-measured at `7ff8194` in the MAIN CHECKOUT:

   ```
   for t in get_changes_since change_feed changes_since watermark event_log; do
     grep -rla "$t" apps/api/isaac_api/ --include='*.py' | wc -l
   done
   ```

   `change_feed` -> **3** files (`change_feed.py`, `routes.py`, `workspace.py`); the other four ->
   **0**. So: **a change feed EXISTS** — `apps/api/isaac_api/change_feed.py`, served at
   `GET /api/experiments/{experiment_id}/changes` (`routes.py:3850`), with a `proposal` kind whose
   entry carries no content. **`watermark` and `event_log` remain at 0, and that half of the claim
   still holds** — the feed is a cursor-paged read over stored positions, not an event log, and
   `change_feed.py:548-556` says so itself: it reports current STATE and does not report lifecycle
   transitions.

   *A note on the measurement, because this document's own standard demands it: a first run of that
   loop returned `change_feed -> 4`. The fourth was an uncommitted in-flight edit in the working
   tree, not a committed fact. The figure above is from the committed tree and was cross-checked
   with `git grep -la 'change_feed' 7ff8194 -- 'apps/api/isaac_api/**/*.py'`.*
10. **Measurement.** No count, size, or timing in this document was measured against a running
    deployment. The path counts in §6 and the 15-member reading of
    `EXPERIMENT_OVERRIDABLE_ADDRESSES` in §5 were derived at HEAD by importing the constants;
    everything else is a reading of source.

---

## 9. Revision note — 2026-08-28

Amended after independent review. The review verified §5 **I3** (apply reuses the manual writers)
and §7 (no `0006` migration) against source, and reproduced the 25 / 18 / 7 path split exactly.
Four amendments were applied:

1. **§5 I4 and §8.3 reframed** from a claim about the *build* to a claim about *configuration*,
   adopting the wording `identity.py:1024-1038` had already withdrawn once. The original sentence is
   struck in place rather than deleted.
2. **Eleven citations corrected**, four of them load-bearing:
   `identity.py:1114-1119` → **`:1070`**; the handler registration → **`app.py:261`**;
   `NOTE_MAPPABLE_PATHS_A_VALUE_CAN_BE_WRITTEN_AT` → **`routes.py:9690`**; and the
   `_UNACCEPTABLE_READER_PATHS` guard → **`routes.py:10376-10384`**, which raises `RuntimeError` at
   module load, **not** `ImportError`. Each was re-derived, not transcribed.
3. **Four cases added**: `409 target_run_removed` (§4), worked-example isolation (**I7**, §5),
   the discard interaction (§3), and the outcome of a concurrent accept (§4).
4. **`EXPERIMENT_OVERRIDABLE_ADDRESSES` has 15 members, not 13** — 13 `field:` plus `block:tags`
   and `block:attribution` (§5, §6).

**One reviewer statement narrowed rather than adopted:** the guard mechanism at
`routes.py:10376-10384` does not fail the *import*, it raises `RuntimeError` while the module loads,
so the application fails to **start**. The separate `mcp/policy.py:31-37` guard is the one that
fails an import. §4's claim about the MCP guard is unchanged and was not among the errors.

---

## 10. Revision — 2026-08-29. Authorization, and thirteen decisions from a second review.

### 10.0 Authorization

**The project owner authorized application-side implementation of persistent ingestion proposals on
2026-08-29.** §8.1 previously said no committed sentence authorized building this. **That was TRUE
when written**; it is struck in place, not deleted, so this reads as a recorded change of scope
rather than a drift — the discipline `CLAUDE.md` §15 applies to its own four table-naming
corrections. The committed basis is the §15 entry of the same date. **Nothing here authorizes
applying a hosted migration, and §10 DEC-12 makes that moot by needing none.**

**PROVENANCE, and it is a limitation rather than a caveat.** This grant reaches the repository as an
**owner instruction relayed in-session**, in the same evidentiary class as the operator testimony
`CLAUDE.md` §15 records for Dean. No evidence file backs it and none can: every commit here is
authored by the owner with Claude co-authored, so authorship distinguishes nothing. An independent
forensic audit of the implementing branch raised precisely this — the sentence being cited was
written one commit earlier, by the same work that cites it — and **that objection is correct and is
not answered by this document.** What is checkable is the BOUNDARY (dated, scoped, no table, no
earlier slice may cite it); what is not checkable from inside the repository is that the instruction
was given. Only Krish can confirm it. An implementing slice must cite this as a recorded owner
decision, never as something the repository verified.

### 10.1 What a second independent review found

The review verified all ~110 `file:line` citations in this document and could not find one pointing
at the wrong code; every numeric derivation reproduced exactly. Its findings were about DESIGN, and
two factual failures, both the same failure — the document transcribed two `notes.py` docstrings
that have gone stale at HEAD (`:98-111` and `:10-21`), and in both cases this document's OWN other
sections state the correct fact. **Those docstrings are repository defects and are fixed
separately, not only here.**

### 10.2 The thirteen decisions

| # | Decision | Supersedes |
|---|---|---|
| **DEC-1** | **`base_rev` is NOT the staleness key.** It is the RECORD's rev and moves on any act — a note capture, a rename, an unrelated run edit — so it is wrong in BOTH directions: every proposal on an active record becomes permanently un-acceptable, AND the target itself goes unchecked. The precondition is a new **`target_digest`** over the current value and evidence envelope at `target_field_path`, on `competing_digest`'s shape, which this document already cited for a different purpose and then did not use. | §2 `base revision`, §2 `expiry` |
| **DEC-2** | **Acceptance follows the SUBMISSION precedent, not the record-attribution one.** `record_attribution.py:166-174` requires `verified_edge_assertion` because an official record has NO field to qualify an attribution, so a fixture name there is permanent and indistinguishable. A proposal row is not that — like a submission row it carries its own `trust_basis` and says what it is worth. Accept requires `identity.require_human_actor` and stamps `subject` + `trust_basis`. **The VALUE still goes through the unchanged manual writers, which stamp no actor, so no fixture name can reach an official record.** Both halves asserted by test. | §5 I4 |
| **DEC-3** | **Do not store `quote`.** Store `note_id` + offsets; derive the excerpt on read. Keeps `_retention_disclosure` exhaustive **structurally** rather than by assertion, and an edited note cannot leave a stale copy. | §2 excerpt row |
| **DEC-4** | **Bounded payload.** `_MAX_PROPOSAL_BYTES` at the `_MAX_NOTE_BYTES` scale over `proposed_value` + `rule`, typed `422 value_too_large`; offsets validated. This document specified no cap at all. | §4 refusals |
| **DEC-5** | **Bounded list, and it is the change-feed foundation.** `CLAUDE.md` §11 records the repository paying **1,772,692 B** for exactly the unpaginated shape this document inherited from `list_notes`. `GET .../proposals` takes a server-capped window and returns `next_cursor` + `has_more`; a per-record proposal count is bounded at create. | §4 |
| **DEC-6** | **Hydration returns the PAIR shape.** `_hydrate_notes` returns `(readable, unreadable_raw)` precisely so one malformed row cannot 500 the list screen — the `pending: 7` finding. Unreadable proposals are preserved VERBATIM, counted, surfaced as unreadable, and never coerced, parsed, walked, or dropped. | §7 |
| **DEC-7** | **Proposals are excluded from the MCP-reachable detail payload, by test.** `mcp/client.py` is bound to the OPERATION allowlist, not to a response shape, so a new `proposals` key would widen external-agent reads with no reviewed decision. | §4 "no new tool" |
| **DEC-8** | **`accepted` is terminal, and a DERIVED `still_current` is published beside it.** The target can be corrected afterwards through `/edit`, `/overrides` or `PATCH .../runs/{id}`; without this an accepted proposal reads as a standing claim about the record's present content. Derived at read by re-digesting the target — never stored. | §3 |
| **DEC-9** | **Reject/withdraw require no actor, and the asymmetry is DISCLOSED rather than discovered.** In a default deployment no verifier reads a request, so any caller past `ApiKeyAuthMiddleware` can withdraw any proposal, recorded `unattributed`. Gating them would leave the queue permanently unclearable — the exact defect `conflict_resolution.py:8-17` exists to fix. | §5 I4 |
| **DEC-10** | **Adding `"proposals"` to the experiment's authoritative signature (`workspace._authoritative_signature`, which §7.5 calls `_experiment_signature`) moves `rev` and the ETag. That is INTENDED** — a proposal act changes what the record holds and a stale second writer must be refused. ~~**so a proposal act DOES create a revision at the next submit**~~ — **MEASURED FALSE 2026-08-30, and struck in place rather than reworded, because that clause is the kind of claim a future slice acts on.** The sentence joined two different mechanisms and only the first is true. `rev` moves; **the revision does not.** A submission's identity is `submissions.content_signature`, computed over the EXPORT UNITS, and no export unit contains a proposal — proposals live at `state["proposals"]`, outside `draft`, which is the property §7 chose the location FOR. So proposing, rejecting, superseding or withdrawing leaves the content signature exactly where it was, and the next `POST .../submit` answers **`409 already_submitted`** rather than recording a revision. The claim holds for **`accept` alone**, and even there the revision comes from the VALUE WRITE the acceptance performs through the manual writer — not from the proposal act. This document asserted the safe half (proposals stay out of `submissions.content_signature`) and then contradicted it one decision later; **the safe half is the one that holds.** | §7.5 |
| **DEC-11** | **Drop `unit`** — the one no-guessing breach the review found. | §2 `unit` |
| **DEC-12** | **No new table and no `0006`.** §7's argument is mechanically sound and is adopted. **Decisive additional reason:** a feature needing `0006` would not work until an operator acts, and applying a hosted migration is a hard stop no authorization lifts. `db_write.OWNED_TABLES` is UNCHANGED — the first scope extension in §15 that adds no table, deliberately, because §15 records four occasions on which a table reached that list before any committed sentence named it. | — (confirms §7) |
| **DEC-13** | **An idempotency key IS required, and the decline was answering a different question.** §2 argued every write is idempotent by content — true of APPLYING, false of CREATING: two identical `POST`s mint two `proposal_id`s, so a retrying MCP client duplicates. Create accepts an optional `client_request_key`; inside `record_lock` a key already present returns the EXISTING proposal. Exactly-once within a scope with no uniqueness constraint, because every write to one experiment holds that lock. | §2 `idempotency key` |

### 10.3 The critical section, stated because the review found it unspecified

The `target_digest` re-read, its comparison, and the mutation happen **inside one
`ws.record_lock(experiment_id, session_id=scope)` block**, in that order, before any write. A digest
read before the lock would let two accepts both pass. This is the discipline `CLAUDE.md` §11
records for the reset `plan_digest`, whose match "is verified *inside the same critical section as
the mutation*", and for the malformed-record preflight, whose two rows are built from ONE read
because reading twice lets a concurrent write masquerade as a permanent condition.

### 10.4 What is still NOT covered

Everything in §8 except items 1 and 9, unchanged. Plus: no automatic producer is wired here; no
production model provider exists or is authorized; and the **acceptance route answers `409
human_actor_required` in every default-configured deployment**, because no trusted authentication
boundary exists in this build — a configuration fact, not a build defect, and one no application
change can close. It is exercised in CI through the deterministic fixture verifier.

---

## 11. Revision — 2026-09-03. The first producer is wired, and §8.5 is superseded.

**Authorization basis.** The committed sentence permitting this work is `CLAUDE.md` §15's 2026-08-29 application-side
scope extension, which authorizes *"persistent ingestion proposals and the durable contract they
need"* — a producer that mints them is inside that grant, and §10.0's basis for this contract is the
same entry. **The storage LOCATION needs no new authorization and this slice claims none:** proposals
stay at `state["proposals"]` inside the experiment state document, covered by the 2026-08-07 lift's
*"app-owned tables for experiments and their normal application state"*. `db_write.OWNED_TABLES` is
unchanged, no migration exists, and DEC-12 holds — so this slice adds no table and needs no operator
action, which is the property §7 chose the location for.

**What this entry does NOT claim.** The 2026-08-29 grant reaches the repository as an owner
instruction relayed in-session and, as §15 itself says, the repository records the decision and not
its delivery. Nothing here is authorized by this document's own prose.

### 11.0 What changed

**§8.5 said this contract adds "a *destination* for valued proposals" and that "wiring
`extraction.py`'s `unrecognised_labels`, or CSV ingest, or the transcript reader's currently-unstored
`candidates`, is separate work."** That separate work has now been done for **one** of the three:
**the transcript reader**. The sentence is superseded for that producer and is otherwise unchanged —
`extraction.py`'s residue and CSV ingest are still unwired, and the CSV apply route is still a
committed human decision (§8.6) rather than residual work. **§8.5 itself now carries the
correction, struck IN PLACE and dated, so a reader who arrives there rather than here is not told
the candidates are still unstored.**

`POST /api/experiments/{experiment_id}/transcript` now mints one `IngestionProposal` per candidate
it reads, **server-side, inside the same `ws.record_lock` block and the same `save_versioned` call
as the notes it stores**.

### 11.1 Why the mint is server-side, and in that critical section

The contract's own rule for the review route (§10.3) is that the read, the comparison and the
mutation happen inside one `record_lock` block. The same reasoning applies to a capture, for two
reasons that are specific to it rather than borrowed:

1. **The scientist performed ONE act.** A client-side mint would be N+1 requests, each with its own
   `If-Match`, each able to fail on its own — so a closed tab, a slept laptop or a `412` partway
   through would leave a record whose notes were stored and whose proposals were not, with no
   surface able to say which candidates were missing. Minting here makes the proposals **atomic with
   the notes they cite**: one lock, one save, one revision, and either the record holds both or it
   holds neither.
2. **The citation is not constructible client-side.** A proposal REQUIRES a `note_id` naming a note
   the record already holds, and the ids of the notes a capture stores do not exist until that
   request mints them — so a client minting proposals would have to read them back out of the
   capture's own response, which is exactly the round trip atomicity removes.

### 11.2 The idempotency key, and the guarantee it does NOT give

Each minted proposal carries a deterministic `client_request_key`:
`transcript-capture:{note_id}:{candidate_index}`. **`note_id` AND the index**, because two candidates
can come from one segment — and therefore from one note — when a sentence gives two values for one
field, and the reader deliberately keeps both.

**It does not make two finalizations of the same text idempotent, and reading it that way is the
error worth naming.** A note id is a fresh ULID minted by the same request, so two deliberate
finalizations produce different notes, different keys, and two sets of proposals — which is correct
and is what `capture_note` already does with the words themselves: two finalizations are two acts.
What protects a **retry** is the record's own precondition: a capture that reached disk advanced the
`ETag`, so the retry meets `412` and nothing is stored twice.

The key's actual job is the one DEC-13 added it for, and it is a job about **two producers rather
than one**: the capture publishes the key, so a client that mints a proposal cannot mint a second
one for a candidate this route already minted.

~~**AND THAT IS A CAPABILITY TODAY, NOT A LIVE CONCERN — corrected 2026-09-03, because the first
version of this paragraph overstated it.** It said `api.ts` gaining `createProposal` "is what makes
that a live concern rather than a hypothetical". It does not. `createProposal` exists in
`apps/web/src/lib/api.ts` and NO SURFACE CALLS IT at this HEAD: the transcript route is the only
producer in this build, so no second producer is racing it and none can until a surface performs the
create. The method is kept rather than deleted because its caller is named and next — the "Propose a
value from this note" act in Unmapped Notes, the note-mapping path — and because it is the client
half of the guarantee this key exists to give, which is exactly what that surface will need. Its own
comment block in `api.ts` records the same ruling, including the condition under which it should be
deleted instead (the standard this repository applied to `getProposal`, which shipped with no caller
and was removed), and quotes rather than deletes the paragraph that had declined to add it "until a
producer lands". The collision becomes live when that surface lands, and not before.**~~ —
**SUPERSEDED, SAME DAY (PR-D).** The named surface landed: `UnmappedNotesPanel.tsx`'s "Propose a
value from this note" act calls `api.createProposal` — `note_id`, `target_field_path`, `rule` and
`proposed_value` are all supplied by the form, never defaulted, exactly as this contract requires. **A
second producer now exists, and the collision this key was added for is live, not merely capable.** A
transcript capture and a person mapping the same note by hand can now race to mint a proposal for the
same candidate; `client_request_key` (§2 DEC-13) is what keeps that to one proposal. The transcript
route's key is unchanged: `transcript-capture:{note_id}:{candidate_index}`. The note-mapping surface's
own key is a different shape, deliberately: `note-propose:{note_id}:{target_field_path}:{a
non-cryptographic digest of the proposed value, taken over its JSON serialisation}` — it keys on the
path and the VALUE rather than a candidate index, because a person choosing a field and typing a value
has no candidate index to key on at all. The two shapes never need to match each other for the
guarantee to hold: exactly-once dedup is per producer's own retry of its own request, inside one
`record_lock`, and the two producers are never asked to agree on one key format.

### 11.3 A candidate with no proposal is DISCLOSED, never dropped (§5 I6)

The response carries two new keys. `proposals` is one entry per candidate that now has a stored
proposal — `candidate_index`, `client_request_key`, `deduplicated`, and the proposal view. `deduplicated`
is **per item**, because a capture is many creates and one flag for the batch would answer a question
nobody asked. `unproposable` is one entry per candidate that got none, carrying the path, the note id
and the server's own typed `error` and `message`; **a client renders that message and composes none
of its own.**

Both ceilings are DISCLOSED rather than enforced by refusing the capture, because refusing a
transcript for a reason that has nothing to do with it would destroy it:

* the **row** ceiling (`_MAX_PROPOSALS_PER_RECORD`) is checked per candidate as the batch grows;
* the **per-record byte** ceiling (`_MAX_PROPOSAL_STATE_BYTES`) is measured once over the whole
  projected document, and over it **no proposal from that capture is stored** and every candidate is
  disclosed. All-or-nothing rather than "as many as fit": a partial batch chosen by byte arithmetic
  would be the route deciding which of a scientist's values are worth keeping.

Every segment still becomes a Note, unconditionally, so the words survive every outcome.

### 11.4 `accept_contract` names the review route now

It named `PATCH /api/experiments/{experiment_id}/runs/{run_id}`, which was correct while a candidate
lived only in a response body: accepting one WAS a direct run edit made by the tab holding it. It now
names `POST /api/experiments/{experiment_id}/proposals/{proposal_id}/review`, and lists the record's
`ETag` and **a trusted human identity that no default-configured deployment establishes** among its
requirements (§5 **I4** is unchanged in every respect). The value still lands through the same
writer; what changed is who a client asks. `test_transcript_capture.py`'s assertion was **inverted
rather than deleted**.

### 11.5 What this does NOT change

**I1** and **I2** hold and are asserted over the capture itself: every export unit's draft and every
run's resolved draft are byte-identical across a capture that mints proposals, and the exported
record is byte-identical. **I4** is untouched — acceptance still answers `409 human_actor_required`
in every default-configured deployment. **I7** is untouched and asserted: a capture inside a
worked-example session is invisible to the ordinary scope. **DEC-12 holds: `db_write.OWNED_TABLES`
is unchanged and no migration exists** — proposals still live at `state["proposals"]`.

Change-feed emission needed **no new code and that is the point**: `save_versioned` maintains
`Experiment.proposal_change_revs`, so minting inside the capture's existing save emits exactly what
`POST .../proposals` emits, by the same mechanism rather than by a second one this route would have
to keep in step. Asserted by test rather than argued.

### 11.6 Still not covered

The other two producers §8.5 names. An automatic producer of any kind — this is a scientist pressing
Finalize, not a pipeline. And the record-scoped case is **unconstructible from a transcript rather
than merely unbuilt**: all five paths the reader can propose are run-scoped
(`_PROPOSAL_WRITER_SCOPE` over `tc.READABLE_FIELD_PATHS` is `{"run"}`, derived by test), and
`read_transcript` withholds every candidate while the run is unsettled — so a capture with no run
selected stores its notes and no proposal at all, and says so.
