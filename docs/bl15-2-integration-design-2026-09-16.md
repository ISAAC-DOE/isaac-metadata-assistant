# Wiring the BL15 readers into the existing import session

**Audience: the slice that implements `BL15R-011` (candidate assembly) and the routes.**
This document exists so that slice does not rediscover a hard ceiling, invent a second
evidence shape, or build a parallel Runs model. Everything here was measured against
`apps/api/isaac_api/historical_import.py` and the real corpus on 2026-09-16.

The layers below `historical_import` are already built and tested:
`bl15/evidence.py` · `bl15/inventory.py` · `bl15/mapping.py` · `bl15/relate.py`, plus the
readers and the archive walk from their own slices.

---

## 1. THE BLOCKER: one source per file does not fit, and should not

`historical_import.MAX_SOURCES_PER_SESSION` is **500**. The real corpus is **1,192
files** — over by **692**.

**Raising the ceiling is the wrong fix, and the reason is not performance.** `HIST-004`'s
banned pattern is *"Upload → Spinner → Mysterious JSON"*, and the authorizing brief adds
*"do not display ~1,192 flat source rows by default"* and *"do not require manual source
entry for 1,192 files"*. A 1,192-row manifest satisfies the letter of the manifest
requirement and defeats its purpose: a scientist cannot audit 1,192 rows, so a complete
manifest they cannot read is the same as no manifest.

### The fix: a third source kind — the archive

`SOURCE_KINDS` is currently `{reference, synthetic_fixture}`. Add **one** more, for a
folder or ZIP the scientist selected. **One `SourceReference` for the whole archive**, so:

- the manifest has **1 row**, not 1,192, and the 500 ceiling is untouched;
- the inventory (1,192 entries, its refusals, its duplicate groups) is the *parse result*
  of that one source, not 1,192 manifest rows;
- what a scientist first sees is the **corpus digest** the brief asks for, with the full
  inventory under progressive disclosure.

**Three properties of the existing model that this must preserve, because each was
argued for and is asserted by a test:**

- **`"NO BYTES, EVER"` for a pointer.** An archive source is a *third* kind precisely so
  it does not weaken that rule for the existing two. The archive kind is read — that is
  its whole point — so it must be honest about being read, exactly as the
  `synthetic_fixture` kind already is.
- **No digest is ever computed**, *"not even for a file it does read"*. **This conflicts
  with the inventory**, whose `SourceRecord.content_sha256` is load-bearing: content
  hashing is the only thing that stops the corpus doubling (measured: 94 measurements
  became 181 without it) and the only correct way to recognise the 96 duplicate groups.
  **Resolve it explicitly, do not paper over it.** The narrow, defensible position:
  digests of archive members are computed **inside the parse, for structural
  deduplication, and are never published as a manifest `sha256` for any source** — that
  field stays *"what the scientist said"*. Whoever implements this must state the
  decision in `historical_import.py` beside the existing claim and **correct the existing
  absolute wording**, which will otherwise be false. `CLAUDE.md` §11 records several
  claims that went false because a later slice widened behaviour without revisiting the
  sentence; this is that situation, seen in advance.
- **A session is not durable** and says so on eight of nine responses. An archive import
  does not change that. Do **not** reach for migration `0006`: a working area that says
  it is a working area does not need one, and that route was deliberately not taken.

---

## 2. The evidence bridge — one adapter, not a second shape

Two evidence shapes now exist and they are **deliberately different**:

| | `bl15.evidence.SourceEvidence` | `historical_import.EvidenceStatement` |
|---|---|---|
| fields | 16 — concept, locator, raw literal, normalized value, unit, rule, profile, scope, timestamp, stem… | **3** — `key`, `value`, `locator` |
| purpose | audit a reading of a real instrument file | carry a statement into the existing review pipeline |

**Do not widen `EvidenceStatement`.** Its three fields are what `session_view`, the review
surface and the note/proposal mint already consume, and its docstring records why it has
no `determinism` field: *"A parser reads; it does not normalise… the
deterministic-versus-inferred distinction belongs one stage later."* That is exactly the
split `bl15` implements, so the shapes agree on the principle and differ on detail.

Write **one adapter**, in one place:

```
SourceEvidence  ->  EvidenceStatement(
    key      = concept,
    value    = raw_literal,                      # VERBATIM, never the normalized value
    locator  = f"{source_path} · {locator}",     # the archive path is the scientist's handle
)
```

`value` must be the **raw literal**. Handing the normalized value across would put
`filter 35` into the pipeline where the file says `ffilter35`, and the normalization would
become invisible at precisely the point a scientist reviews it. The normalized value and
its rule belong on the **candidate**, where `SemanticCandidate.rule` already exists to
carry them.

---

## 3. Candidate assembly — what a `MeasurementUnit` becomes

`relate` produces `MeasurementUnit`s. `SemanticCandidate` is what the review pipeline
consumes. The mapping between them:

| unit property | candidate |
|---|---|
| the unit itself | **one `kind="run"` structural candidate.** `CANDIDATE_KIND_RUN` already exists and is already refused as unproposable with a named reason — `HIST-005` records that *"a proposal is about one value at one official field path, so 'an experiment exists here' has no proposal shape"*. The same is true of a run, so this candidate is **shown, never sent**. |
| each mapped concept | one `kind="field"` candidate, `target_field_path` from `mapping.mapping_for(concept).official_path` |
| a concept whose mapping is **not** in `PROPOSABLE_STATUSES` | a candidate with `not_proposable_reason` = the registry's `reason`. **Do not drop it** — `HIST-005` requires unproposable candidates to be *"reported with the server's own reason, never dropped"*, and **39 of 45 concepts land here**, so dropping them would discard most of the corpus. |
| a `Conflict` | a candidate with `unresolved_reason = UNRESOLVED_SOURCES_DISAGREE` and `disagreement` carrying **every** reading. `SemanticCandidate` already enforces that `proposed_value` is `None` exactly when `unresolved_reason` is set — so a conflicted candidate *cannot* carry a chosen value. That invariant is the whole design; do not work around it. |

**Use `mapping.mapping_for` for every field candidate and never a path literal.** The
registry's own guard (`registry_paths_exist()`) checks each path against the schema at
runtime, so a schema refresh breaks the registry loudly instead of the candidate quietly.

**The `proposable` property already covers the `no_write_path_for_field` case** — its
docstring records that an earlier version overclaimed and offered a `Send to Review`
control for a candidate the server was always going to refuse. Set
`not_proposable_reason` and let `proposable` derive.

---

## 4. Add to Experiment — and why no new Run field is needed

A run's authoritative content is exactly
`{id, experiment_id, label, ordinal, draft, record_id, overrides}`
(`workspace._run_signature_payload`). **Adding an `origin` field would touch the run
signature, the `isaac_run_projection` write and `test_run_row_parity.py`'s exact key set
— which is CI-only against a real PostgreSQL and cannot be verified locally.** It is not
needed:

- **Provenance is already durable and per-value.** `_mint_import_candidate` writes a
  **note** carrying the source filename and statement alongside every proposal. That is a
  better provenance record than a run-level flag, because it says *which file supports
  which value* rather than *this run came from somewhere*.
- **The scientist-readable condition goes in `label`**, which already exists. The brief's
  §47 asks the Runs screen to show *"Legacy Run/File 44 · Sample 04 · JK2 · Base · After
  1500 mV cycling · Filter 35 · Potential 1.2 V · New spot"* instead of a raw stem — and
  the legacy number is the right label because the registry marks it `not_expressible`
  and records that it is *"the handle they already use"*.
- **`workspace.new_run` already accepts a `draft`**, and its docstring says the parameter
  was added for exactly this slice: *"NO caller passes `draft` today… the next slice is
  the one that seeds runs from a template or from the experiment."* It deep-copies, so a
  seeded run owns its draft.

**Seed the draft EMPTY.** A historical import writes no value — `HIST-005` proves both
target paths absent after a batch add, with proposals and notes present — and seeding a
draft with reader output would bypass review entirely.

---

## 5. What cannot be completed, and must be said rather than discovered

A candidate Run from this corpus **cannot be export-ready**, for three measured reasons.
The surface must say so plainly; it must not show a progress bar that can never fill.

1. **`context.temperature_K` is required whenever `context` is present, and the corpus
   states no temperature anywhere.** `mapping.TEMPERATURE_ABSENT_REASON` is the sentence.
   ~~298 must not be defaulted in.~~ **NARROWED 2026-09-17 by `DEC-43`, and struck rather
   than deleted because "must not be defaulted in" is exactly the kind of clause a future
   session enforces.** It is still true of the PARSER and of every profile but one: for
   the **BL15-2 Angel-style historical profile only**, the project owner has adopted
   298 K as a nominal room-temperature assumption, recorded as nominal, domain-supplied
   and **NOT measured** (`apps/api/isaac_api/bl15/nominal.py`). The corpus measurement is
   unchanged — no source states a temperature — so the value comes from the scientist's
   authority rather than from anything read. Any other profile leaves the field absent and
   the record blocked.
2. **`record_type: "evidence"` requires `descriptors`** (`schema allOf[0]`), and no
   historical source provides one.
3. **`assets[]` requires `sha256`** — `mapping.ASSETS_BLOCKED_REASON`. So the acquisition
   files, the 908 scans and the 34 processed products cannot be recorded as official
   assets in this build, however well the `content_role` enum fits them.

This is the correct outcome and it is already the architecture: the import mints
**proposals**, and acceptance answers `409 human_actor_required` in every
default-configured deployment because no trusted authentication boundary exists. The
chain stops at an open proposal, by design.

---

## 6. Order of work

1. The archive source kind + the digest, with the `sha256` claim corrected in place.
2. The evidence adapter (one function, one test proving `value` is the raw literal).
3. Candidate assembly over `relate` + `mapping`, including the 39 unproposable concepts
   and the conflicts.
4. Runs via `new_run(draft={})` + the existing batch mint; label from the legacy number.
5. The end-to-end walk: archive → digest → classify → read → relate → candidates →
   review → add → ordinary Runs → `draft_validator.validate_draft`.

**Step 5 must be a real walk over sanitized fixtures**, not a seeded one.
`test_scientist_can_finish_a_record.py` is the precedent and its lesson is recorded: all
five canonical scenarios are built from a fixture sheet that *already carries* the values,
so every completion test in the suite began past the part that did not work. Write the
values out; do not harvest them.
