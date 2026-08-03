# Product-hardening phase — closure record (2026-08-03)

Six merged PRs. This file records what changed, what was **deliberately not** changed, and the
mistakes worth not repeating. It is written for the session that picks this up cold.

---

## 1. Merged

| PR | Slice | Merge |
|---|---|---|
| #47 | Critical false upload claim + 4 dishonest/dead controls | `3263e1e` |
| #48 | Reset safety — plan digest, symmetric locking, measured outcome | `0c13629` |
| #49 | Validation truthfulness + Validator advisory UI + QA package + manual checklist | `a3c0fb3` |
| #52 | Correction of a false coverage claim about 390/320 px | `74299b3` |
| #50 | Browser mutation coverage + an HTTP 500 fix in the truth core | `91dc09c` |
| #51 | Guided tutorial + truthful workspace language | see git log |

---

## 2. Defects fixed

**Critical — Governance denied a capability it ships one tab away.** `GovernancePage` asserted
*"every file upload is refused outright, whatever it contains, and no file is read, parsed, or
inspected."* Its own `validator` tab mounts `RecordValidator`, which reads the chosen file
(`file.text()` / `FileReader`) and POSTs it; `CsvReconcilePanel` does the same for a campaign sheet;
`LoadMaterials` repeated the sentence. The refusal is true of `POST /api/uploads` **only**, so it is
kept and **scoped**, and the two readers are disclosed. `settingsContent.ts` already had the correct
formulation — the drift existed because nothing pinned the three sites together.

**Reset could silently destroy confirmed work.** Three separate defects:

- no precondition — a dialog left open executed a classification that no longer held;
- managed-legacy removal took **no lock** while canonical re-materialisation took `record_lock`;
- `final_count` was **asserted** as `len(CANONICAL_IDS)`, so a record created mid-reset made the
  response state a false number.

Fixed with an opaque `plan_digest` over the classified workspace (id, bucket, version token,
answer-log length, authoritative signature — so a delete-then-recreate of the same id changes it,
defeating the ABA), `428` for an omitted digest, `412` for a stale one, symmetric locking, and a
measured `final_count`. The digest is verified **inside the same critical section as the mutation**.
`preview` also returns a *derived* `at_risk` summary, so the dialog states real numbers.

**A fabricated CLI transcript.** `VerdictCard` rendered `isaac validate --official · exit N` in a
monospace command block. No CLI runs; `exitCode` was a client-side `ok ? 0 : 1` in three places. On
the surface that gates export.

**Export silently deleted an evidenced scientific judgment.** `export.transform` guarded the
measurement block on truthiness, so `series: []` skipped the whole block and an evidenced
`qc: {status: "compromised", evidence: …}` vanished — with official validation passing. It
**compounded**: with the qc block gone, `_qc_nonvalid_without_evidence` had nothing to inspect, so
the deletion suppressed the one advisory that would have flagged it.

**The standalone validator never ran the advisory tier.** `POST /api/validate/record` called
`validate_official` and nothing else, so a record with no measured data arrived as an unqualified
PASS. It now returns `warnings` with `advisory: true, gating: false`.

**A wrong-typed answer returned HTTP 500.** `POST /answers` with a string for a `series` or
`descriptor` blocker raised out of `complete.py`. `qc` was already `isinstance`-guarded; the fix
follows that convention. No traceback ever reached the client.

Plus: `Re-Validate` could silently do nothing; a dead `Answer 5 Fields →` with a hard-coded count;
session-only state presented as a durable review outcome.

---

## 3. Deliberately NOT done, with reasons

| Item | Why not |
|---|---|
| Backend-sourced jargon on product screens | `MANAGED_SOURCE_DESCRIPTION` is a live input to `classify_experiment`, which decides what reset may delete. Renaming it is a **behaviour change to the destructive path**, not a copy edit. |
| A typed **422** for wrong-typed answers | Needs the route to distinguish "dropped because wrong type" from "dropped because unrecognised". The crash was the defect; the 422 is an improvement. |
| axe scans at 390/320 px | `a11y-baseline.ts` keys by project and refuses an unlisted one — correctly, since that is what stops a new viewport passing vacuously. Satisfying it needs **measured** counts on darwin *and* linux. Attempted, abandoned rather than commit numbers CI would reject. |
| `.section-tab` contrast | Pre-existing: inactive tabs are already below threshold, which is why the baselines read 7/14/17/46 and not 0. Fixing it *lowers* many baselines and touches a class shared by Governance, Project Memory and Settings. |
| Real-record display, `POST /api/uploads` | Withheld by the database owner / governance. Not gaps to close. |
| Evidence, confirmation, validation mutation specs; tutorial browser specs; screenshot sweep | Not written. Answers and export are covered. |

---

## 4. Mistakes worth not repeating

**A guard test can be vacuous for the exact defect it was written for.** The upload-claim guard
passed an inverted disclosure (*"No review tool reads a file you paste or pick"*) on all 35
assertions, because checking that the validator is *mentioned* cannot distinguish "does read" from
"does not read". Two fixes were tried and rejected first: a greedy negator window false-positives on
correct copy, and requiring an un-negated affirmative sentence fails on good copy that pairs both
polarities in one sentence. The landed fix is a clause-local pattern **plus the inverted sentence
kept verbatim as a fixture**.

**"Obviously platform-independent" was false.** A removed DOM node was assumed to change both a11y
columns equally. darwin measured 13, linux 12 — the removal changes how remaining fragments wrap.
Later, four `settings-*@zoom-200` entries went the other way: darwin rose by **2** where linux rose
by **1**, because the added tab changed the wrap and closed a pre-existing split. **Never derive a
baseline number; measure it on the platform you are writing.**

**A green local suite proves nothing about the branch.** Three tutorial modules were untracked
because an explicit-path `git add` list predated their creation. Local runs passed from disk; CI
would have failed on missing modules. A `node_modules` symlink pointing at a local absolute path was
also committed and had to be amended out. Read `git status`; do not trust the suite.

**Absence from a project list is not absence of coverage.** 390/320 px were reported as "unverified
by anything." `layout-widths.spec.ts` sweeps them inside one project by moving the viewport itself.
The checklist was corrected in #52.

**A test can be wrong about the API rather than the API being wrong.** `answer_log` is never
serialised; `res.ok()` does not mean an answer was applied (unrecognised answers are *dropped*);
`If-Match` needs a strong **quoted** validator. All three cost a debugging cycle.

---

## 5. The mutation suite

`apps/web/playwright.mutation.config.ts` — its own backend, its own `ISAAC_UI_WORKSPACE`, its own
dev server, `workers: 1`, `retries: 0`, one viewport. **Do not fold it into the read-only suite**:
that suite seeds once via a GET and five viewport projects assert canonical seed *content* in
parallel, so any spec that answers or exports would break it by scheduling.

`e2e/mutation/global-setup.ts` wipes the workspace and asserts all five records are at `rev 0`,
because a fixed workspace plus `reuseExistingServer` made an early run inherit the previous run's
mutations.

It found the HTTP 500 on its first real run.

One property it could **not** establish: a stale-write 412 through the browser. `useRecordSync`
adopts the fresh token before a human could finish typing — the safer outcome — and the poll shares
the endpoint the screen needs, so blocking it blocks the page. Rather than mock a mutation, the spec
asserts that **neither concurrent write is lost**.

---

## 6. Hosted status

**HOSTED QA PENDING (Krish)** for every image from this phase. `/krish/api/health` returns `302`
here (Authentik edge) and an agent must not enter credentials. No rollout in this phase is claimed
as verified.

Manual sequence: [`docs/krish-manual-verification-checklist.md`](../../krish-manual-verification-checklist.md).
QA files: `qa/validator-upload-package/`, ZIP sha256
`71c2303450487f0ae418e869844d336c2d7be53d01e87956901386f0292bc6f3`.

**Check `/krish/api/health`'s `commit` against `origin/main` first.** If Flux has not rolled, every
subsequent observation describes the previous image.
