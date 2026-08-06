# Authorization record — Q19 approved, Q20 unanswered

**Date recorded:** 2026-08-05
**Source:** relayed by the project owner; no direct agent-to-owner communication occurred.
**Machine-readable form:** [`apps/api/isaac_api/authorization.py`](../../apps/api/isaac_api/authorization.py)
**Question as put:** [`docs/dean-authorization-packet.md`](../dean-authorization-packet.md) — Q19

---

## What this file is, and what it is not

This is a record of an approval, written down so that code can be derived from it and so that a
future session does not have to reconstruct it from prose scattered across four documents.

It is **testimony, not a captured artifact.** The approval was relayed by the project owner. No
agent spoke to the database owner, no transcript exists in this repository, and none is reproduced
here. That distinction is the same one `CLAUDE.md` §15 draws about the single observed
reconnaissance scan and about the Authentik header probe: an operator's report of an event is
weaker evidence than an inspected artifact, and the difference must never be smoothed over by
confident phrasing.

Deliberately absent, and not an oversight: no third-party contact details, no message text, no
infrastructure detail (no hostname, namespace, service name, secret name, credential, or
connection parameter), and no record content of any kind.

---

## Q19 — APPROVED

**The capability approved.** The record-verification engine may draw its records from the
application's own datastore instead of from committed test fixtures, and report **aggregates only**.

Concretely, that is: read the stored records, clone each one in process memory, run the existing
official validator, the advisory format shadow and the deterministic mutation harness over the
clone, discard every clone, and publish global counters and floor-suppressed histograms.

**Zero writes. Zero DDL. No new access path. No per-record output.**

### The constraints that came with it

Transcribed as data in `authorization.DATASTORE_CONSTRAINTS`, implemented in
`apps/api/isaac_api/db_provider.py`:

1. One short-lived connection per aggregate run. The connection limit is 5; a run must never
   approach it. **"Short-lived" is measured against the fetch, not the sweep**: the rows are drained
   and the connection closed before any record is validated or mutated, so a multi-minute sweep never
   holds an open transaction. (An earlier implementation yielded from inside the open transaction and
   would have held it for roughly 21 minutes at the row ceiling; that is corrected.)
2. An explicit transaction, with read-only declared twice — through the driver
   (`set_session(readonly=True)`) and through `SET TRANSACTION READ ONLY`.
3. Read-only **verified server-side**: read back `SHOW transaction_read_only` and refuse to proceed
   unless it is `on`.
4. Conservative `statement_timeout` and `lock_timeout`, set with `SET LOCAL` so they expire with the
   transaction.
5. Deterministic rollback and close in a `finally` block. No autocommit path.
6. Every statement a module-level frozen constant; every value parameterized.
7. A query-policy guard rejecting `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `ALTER`, `DROP`,
   `TRUNCATE`, `COPY`, `CALL`, temporary tables, sequence functions, `;`-chaining, and any statement
   not in the frozen set.
8. A caller can never supply SQL, an identifier, a pointer, a path, a mode, or a schema location.
9. The identifier column is `CHAR(26)` and blank-padded: strip the padding, then drop the identifier
   before yielding, so no caller ever receives it.
10. Exactly one parsed record yielded at a time; the whole parsed corpus is never retained, and
    neither is any structure derived from it — the consumer aggregates each record's result and
    discards it.
11. Cross-references pointing outside the sample are **expected**. Tolerate a missing referenced
    row; never repair it, never follow it, never report it.
12. The driver is imported lazily, so the module imports cleanly when the driver is absent and the
    run then reports a safe `unavailable` state.

### How the approval binds the code

`verification.VERIFICATION_MODES` is **computed** from `authorization.verification_modes()`, which
returns the datastore mode only while `Q19_AGGREGATE_DATASTORE_VERIFICATION_APPROVED` is `True`.

Withdrawal is therefore **absence, not a disabled switch** — the audit at
`docs/superpowers/plans/2026-08-02-corpus-validation-authorization.md:221-223` is explicit that a
disabled runner is a runner someone enables. `apps/api/tests/test_authorization_state.py` fails if
the engine's mode tuple ever stops tracking the flag, and includes a negative control that clears
the flag and asserts the guard **fails**.

---

## Q20 — NOT ANSWERED

Arming JSON Schema `format` enforcement in the official validator is a **separate decision**. The
packet states the two questions are independent and should not be bundled
(`docs/dean-authorization-packet.md:6`). No answer to Q20 has been relayed.

`authorization.Q20_FORMAT_ENFORCEMENT_APPROVED` is therefore `False`, the official validator remains
format-blind, and the format shadow remains advisory: it never decides validity, never gates export,
and never overrides the official result.

`tests/test_truthpath_characterization.py` is the permanent record of that behaviour and was **not
modified** by the work this file authorizes.

---

## No broader authorization is inferred

This approval extends to nothing beyond what is written above. In particular it does **not**
authorize, and must not be cited as authorizing:

- **Per-record display** of datastore content — record ids, titles, field values, evidence entries,
  exports, or any per-record outcome. Hosted per-record display remains **closed by default**
  pending an explicit visibility decision by the database owner
  (`docs/postgres-test-db-guide.md`, "Displaying record content"; gate **G2** in the baseline
  completion matrix). Reachability is not display authorization.
- **Any write of any kind** — insert, update, delete, DDL, temporary table, or a durable record
  repository.
- **Any connection originating from a laptop or from CI**, and any local kubeconfig, port-forward,
  or secret retrieval. That prohibition is a project rule
  (`docs/superpowers/plans/2026-07-24-phase-37-readiness-plan.md:48-52`) and stands on its own
  authority; it never depended on the datastore being unreachable.
- **Restoring the five aggregates withdrawn in `v0.0.32`** — `by_instance_path`,
  `distinct_structural_signatures`, `total_link_count`, `dangling_link_count`,
  `vocabulary_term_count`. Gate **G3** remains open.
- **Caller-parameterized aggregation, cross-tabulation**, or any histogram cell below the
  disclosure floor.
- **Arming `format` enforcement** (Q20, above).
- **Phase 37 as a feature phase** — portal integration, persistence, API keys, identity/role
  enforcement, or an external model provider.

The exclusion list is not decoration. An approval to *compute* aggregates over a corpus is routinely
misread as an approval to *show* it, and this project shipped exactly that mistake once already:
five aggregates went beyond the owner's enumerated list in `v0.0.32` and had to be withdrawn.

---

## What was executed against a real datastore for this record

**Nothing.** No database connection was opened during the session that produced this file or the
code it authorizes. The provider was developed and tested entirely against in-process fake
connection and cursor doubles, and the driver is not installed in the development interpreter, so
the absent-driver path is exercised for real rather than simulated.

The honest form, per `CLAUDE.md` §15: *no connection was opened here* — never *the database has
never been contacted*, which is false of the deployment as a whole.
