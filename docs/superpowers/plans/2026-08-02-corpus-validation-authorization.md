> ## VERDICT SUPERSEDED — 2026-08-05
>
> This audit's verdict was **`Ambiguous — Dean Confirmation Required`**. That confirmation has since
> arrived: **Q19 is APPROVED**, relayed by the project owner; no direct agent-to-owner communication
> occurred. The record is
> [`docs/evidence/2026-08-05-q19-q20-authorization.md`](../../evidence/2026-08-05-q19-q20-authorization.md);
> the machine-readable form is
> [`apps/api/isaac_api/authorization.py`](../../../apps/api/isaac_api/authorization.py).
>
> **The audit's analysis is NOT superseded — only its verdict is.** Three findings from it are now
> load-bearing in shipped code and must not be treated as historical:
>
> - **§3's finding that there was no minimum-cell-size suppression anywhere in the aggregation
>   path.** That gap is closed by `apps/api/isaac_api/disclosure.py`, and floor suppression now runs
>   on both distributions in **both** verification modes, unconditionally.
> - **The applicability-disclosure argument** (a per-operator breakdown is a field-presence map over
>   the corpus). It still holds. Mutation counts remain global scalars; no per-operator,
>   per-category or per-record breakdown is served in either mode.
> - **`:221-223` — "a disabled runner is a runner someone enables."** This is why withdrawal of the
>   approval is implemented as *absence*: `verification.VERIFICATION_MODES` is derived from the
>   approval flag, so clearing the flag deletes the mode rather than disabling it.
>
> **Q20 (`format` enforcement) remains unanswered**, and per-record display remains closed by
> default. Nothing in this note widens either.

# Corpus-Validation Authorization Audit — 30 Production-Derived Records

**Date:** 2026-08-02 · **HEAD at audit:** `d521dd7` · **Method:** static reading of Dean's committed
guide, the readiness plan, `CLAUDE.md` §15, the baseline matrix, and the shipped Slice 2A
implementation. **No database connection was opened during this session.**

---

## The proposal under audit

Have the **deployed** ISAAC backend read each of the 30 production-derived records through the existing
read-only reconnaissance path, deep-clone each **in process memory**, apply controlled deterministic
mutations to the clone (remove a required field, inject an invalid enum token, remove evidence, remove
confirmation), run ISAAC's deterministic validator and workflow engine, discard every clone, and return
**aggregate-only** conclusions. Zero writes, zero DDL, zero temporary tables, no new access path.

---

## VERDICT: `Ambiguous — Dean Confirmation Required`

**The database *read* is already authorized. The *output category* is not.** In its natural form the
proposal would re-derive an aggregate this project deliberately withdrew six days ago.

---

## 1. What is already authorized — the precedent, established by citation

The shipped, reviewed, deployed Slice 2A recon **already does almost all of this**:

| Fact | Citation |
|---|---|
| Full record `data` JSONB is SELECTed | `db_recon.py:1079-1082` — `SELECT record_id, record_type, record_domain, data FROM records …` |
| Deliberately held in memory | `:1076-1078` — "needed in memory to validate and to derive structural paths; it NEVER reaches the report" |
| Each payload parsed per-record | `:1835-1859` |
| **The authoritative validator runs on each real record** | `_official_findings` → `validate_official(dict(record), Path(root))` (re-derive: `rg -n 'validate_official' apps/api/isaac_api/db_recon.py`) |
| A second engine also runs | `:1862-1867` → `:1368`, `diagnose(dict(record), Path(root))` |
| Output projected onto frozen allowlists | `_DB_RECON_DATASET_KEYS`, with an unlisted key raising |

**So "read real records → hold in pod memory → run ISAAC's deterministic validator → emit aggregates →
discard" is already-shipped precedent.** Steps 1, 2, 4-validator, 5 and 7 of the proposal introduce
nothing new. Exactly three things are new:

1. **Mutating the in-memory clone** before validating.
2. Running the **workflow engine**, a code path with no precedent over real records.
3. An **output category** — "expected-vs-actual outcome counts" — that is not on Dean's list.

## 2. Why it is nevertheless not covered

Dean's authorization of aggregate output is an **enumerated list**, not a general grant
(`postgres-test-db-guide.md:154-158`): *"Aggregate output -- record counts, counts by type and domain,
validation totals, schema version, database reachability -- is fine to build and show now."*

"Counts of expected-vs-actual outcomes under controlled mutation" is not a member of that list, and it
is not "validation totals" — validation totals answer *do the stored records validate*, which Slice 2A
already answers.

The project has already ruled on exceeding the list. Baseline matrix §4.4: *"Any field whose content
originates from the record rather than from the schema"* requires Dean's explicit approval, and *"If
drift cannot be classified within this boundary, that is a **hard stop** for Dean, not a licence to
widen the allowlist."* §4.2 gives the test: **the schema may describe the data; the data may not
describe itself.**

**The most load-bearing evidence is in git history.** Dean's one and only revision to the guide
(`b746b1a`) *deleted* the sentence *"Everything here is disposable test data: write, mutate, and drop
freely"*, replacing it with *"the seeded rows are real production-derived records, so what the hosted
app **displays** is a separate decision"*. That sentence concerned mutating **database rows**, not
in-memory clones, so it is not a direct prohibition here — but it is the clearest evidence of his
posture, and reading a *new* mutation permission into the guide runs against the direction of the only
edit he has ever made to it.

## 3. THE FINDING THAT MATTERS — mutation applicability *is* a field-presence map

This is the part that would have been easy to miss, and it is the reason the honest verdict is not
"covered".

**Whether a mutation is applicable to a record is a fact about that record's structure.** "Removing
field X was applicable to 12 of 30 records" discloses that **12 records populate X**. A mutation catalog
iterated across the corpus therefore produces, as a by-product, a **field-presence map over the
corpus** — which is in substance `aggregate_structure`'s `path_presence` (`db_recon.py:1565-1568`):
"removing X applied to 12 of 30" ≡ `{path: X, records_with_path: 12}`.

**Correction, 2026-08-02, after review — an earlier draft of this paragraph misstated the code, and
the method of this document is citation, so the error matters more than usual.** It claimed
`path_presence` and `by_instance_path` were "both named in `_DB_RECON_WITHHELD_AGGREGATES`". They are
not. That tuple (`routes.py:3194-3200`) contains exactly `by_instance_path`,
`distinct_structural_signatures`, `total_link_count`, `dangling_link_count`, `vocabulary_term_count`.
**`path_presence` is not in it — because it was never served at all**: it is computed in `db_recon.py`
and excluded by the `_DB_RECON_DATASET_KEYS` projection, with `test_db_recon_endpoint.py` asserting
`"path_presence" not in dumped`.

**The finding is unchanged and in fact strengthened.** `by_instance_path` shipped once and was
withdrawn; `path_presence` was **never published even once**. Reconstructing it through a mutation
harness would therefore expose something the project has never disclosed, rather than re-disclosing
something it briefly did.

It is arguably **worse** than `by_instance_path`, which only illuminated paths where validation already
failed — the drifting minority. A mutation harness sweeps *every* record against *every* catalog entry,
producing a presence map over the whole corpus. And it would ship while **every existing contract test
passed**, because those tests freeze key *names*, not semantics — precisely the structural root cause
recorded in the matrix.

Two further rules bite directly:

- **§4.3.1 minimum cell size.** Over ~30 rows, "applicable to 1 record" is a single-record fact wearing
  aggregate clothing. **There is no minimum-cell-size suppression anywhere in the aggregation path** —
  `rg -n 'MIN_CELL|suppress' apps/api/isaac_api/db_recon.py apps/api/isaac_api/routes.py` returns
  nothing. *(An earlier draft quoted a tree-wide `rg 'MIN_CELL|suppress'` as "0 matches". It returns
  three — a `--quiet` help string in `scripts/db_recon.py` and two unrelated Assistant follow-up
  suppressions. The substantive claim was right and the quoted command was wrong; `CLAUDE.md` requires
  the command to reproduce, so it is narrowed to the files that matter.)*
- **§4.3.2 cross-tabulation limit.** Mutation-category × outcome-class is a 2-D breakdown; *"adding a
  dimension to an existing breakdown is not a free extension of it."*

## 4. The one safe line — and why it makes the real corpus nearly worthless here

There is a principled boundary, and it maps exactly onto §4.2:

**SAFE — mutations targeting UNCONDITIONALLY required fields, computed over the PASSING subset only.**
If a record validates, the schema *entails* the field is present. Applicability is therefore derived
from the **public vendored schema**, not from reading the record, and the count is already implied by
`records_passing_full_schema`, which Dean explicitly authorized. *"Removing `isaac_record_version`
produced a validation failure in 30/30 trials"* is predictable from the schema alone.

**Both qualifiers are load-bearing and were missing from an earlier draft.** Without them the "safe"
line leaks:

1. **Over the passing subset only.** The entailment holds only for records that validate.
   `records_failing_full_schema` is **not known to be zero by measurement** — Dean's guide calls full
   schema conformance *"expected but unverified"*, and 30/30 is operator testimony, not a captured
   artifact. If any record fails, an applicability count of N < 30 discloses *which failing records
   lack that field* — exactly the `path_presence` leak §3 forbids. State it as: applicability computed
   over the passing subset, where it is **identically** `records_passing_full_schema`.
2. **Unconditionally required.** "Schema-required" is not a flat set. A field required only under
   `if`/`then`, `oneOf`, or `dependentRequired` has **record-derived** applicability — whether the
   condition fires depends on the record's own content. Conditional blocks are already in the NOT SAFE
   list below; the safe line must say *unconditionally* required so the two do not contradict.

**SAFE — global scalars with no breakdown:** total trials run; one global `outcomes_matched` boolean;
`determinism_failures: 0` — *provided* a nonzero value triggers refusal-to-elaborate rather than a
breakdown, since a localized determinism failure is a per-record structural fact.

**NOT SAFE without Dean:** any applicability or outcome count for an **optional** field (evidence,
descriptors, links, conditional blocks) — that is `path_presence` renamed; **evidence-removal and
confirmation-removal specifically**, since those structures are optional and applicability *is* the
disclosure; enum-injection results keyed by target field; any mutation × outcome cross-tab; any count
able to reach 1 without a stated floor; anything keyed by instance path.

> **The asymmetry is the finding.** The interesting mutations are precisely the unsafe ones. A safe
> contract exists, but it is so constrained — required-field mutations plus global booleans — that it
> answers almost nothing that could not be derived from the schema plus a synthetic corpus.

## 5. What this means for the phase

**A mutation harness tests the validator and the workflow engine**, whose behaviour is fully determined
by `schema/isaac_record_v1.json` plus `src/isaac_records/` — **not** by which real records happen to
have been seeded. Real records add a **coverage** argument ("do real-world shapes exercise paths our
fixtures miss?"), not a **correctness** argument.

So the entire harness — catalog, expectation model, oracles, determinism checks, reporting shape — can
be built, reviewed and merged with **no database dependency whatsoever**, and is genuinely useful on its
own. Only the final connection to the 30 rows stops.

That also produces the strongest possible position for the Dean conversation: a working harness and a
concrete sample output, rather than an abstract request.

## 6. What Dean HAS blessed, quoted exactly

Worth recording, because he is generous on the *processing* axis and restrictive only on *output*:

- `:3-6` — *"The app owns it: its schema, its rows, its reads and writes … seeded with a sample of real
  record data **so the app can work against the real thing**."*
- `:151` — *"**Writing to this database is unrestricted.** Rendering its rows in the hosted app is
  not."*
- `:136-140` — the role *"can freely create and alter tables, indexes, sequences … adding app-specific
  tables next to the mirrored schema is fine."*
- `:119-123` — *"**Finding drift is a useful result, not a problem with the database.**"*

He would very likely be relaxed about the in-memory mechanics — he permits far more (writes, DDL, new
tables) than this project's own rules allow. **What he has never addressed is whether an aggregate that
is a function of real record structure may be published.** That question is live, unanswered, and is the
same question already sitting in G3.

## 7. The question to put to Dean — and why the obvious version is wrong

The obvious phrasing ("may we clone in memory, mutate, validate, and return only aggregate pass/fail
conclusions with no per-record output?") **would get a yes to a question he did not understand**: a
per-mutation count over 30 rows *is* per-record output, it does not distinguish required from optional
fields, it leaves "aggregate" granularity undefined, and asked cold he cannot connect it to G3.

**Ask it attached to G3 instead — this is Q19:**

> Following on from G3: `GET /api/runtime/database/recon` already reads all 30 records' full `data` JSON
> into pod memory and runs our v1.05 validator over them, emitting only the aggregates you enumerated.
> We would like to extend that to a **validator test harness**: clone each record in memory, apply a
> fixed catalog of deterministic mutations (remove a required field, inject an invalid enum token,
> remove evidence), run our workflow engine, discard every clone. Zero writes, zero DDL, no new access
> path, no per-record output.
>
> **The disclosure question we cannot answer ourselves.** Whether a mutation is *applicable* to a record
> is a fact about that record's structure. So "removing field X was applicable to 12 of 30 records"
> discloses that 12 records populate X — a field-presence map over the corpus, close to the
> `by_instance_path` aggregate we withdrew and are already asking you about. Over 30 rows an
> applicability count of 1 is a single-record fact, and we have **no minimum-cell-size suppression
> anywhere** in the code.
>
> We see one clean line and want your ruling on it: **mutations targeting UNCONDITIONALLY required
> fields, counted over the passing subset only, are safe** — if a record validates, the schema entails
> the field is present, so the count is identically `records_passing_full_schema`, which you already
> authorized. Both qualifiers matter: a field required only under `if`/`then` or `oneOf` has
> record-derived applicability, and if any record *fails* full-schema validation then a count below the
> corpus size discloses which failing records lack that field. **Mutations targeting optional fields
> (evidence, descriptors, links, conditional blocks) are not safe** — there, applicability *is* the
> disclosure.
>
> Three questions: **(a)** Is that line right? **(b)** May we publish per-mutation-category counts for
> required-field mutations only, with everything else reduced to a single global pass/fail boolean?
> **(c)** If any optional-field breakdown is acceptable, what minimum cell size should apply?

## 8. Consequences, recorded so they are not quietly reversed

- **Slice T4 (real-corpus runner) is BLOCKED** pending Q19. Do not implement it. Do not implement a
  "temporarily disabled" version either — a disabled runner is a runner someone enables.
- **Slices T2, T3, T5 proceed in full on synthetic fixtures**, with no database access.
- If a defect is ever found via a real-corpus case, the rule stands: build a **synthetic minimal
  reproducer**, commit only that, fix against it.
- **`workflow.py` has never run against a real record.** Even if Q19 is answered yes, it needs its own
  code-safety review first — it is a different code path from `validate_official`, with no precedent.

## Caveats on this audit

Static code reading, not runtime observation. Two `db_recon.py` ranges (connection setup, final report
assembly) were not read in full; neither bears on authorization. `src/isaac_records/workflow.py` was not
audited — that is a code-safety question, deliberately separate.
