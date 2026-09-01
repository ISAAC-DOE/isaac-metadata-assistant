# Session handoff — 2026-08-31: four branches integrated, and what merging found

**For:** Krish. **Written by:** the session that did the work.
**Read §1 before acting on anything here.** Every claim below is a claim you can check,
and the commands to check it are given rather than implied.

---

## 1. Verify before you trust this page

```bash
git -C ~/Documents/ISAAC fetch origin --prune
git -C ~/Documents/ISAAC log --oneline -8 origin/main
gh pr list --state merged --limit 8 --json number,mergeCommit,headRefName
.venv/bin/pytest -q                      # backend
cd apps/web && npx vitest run && npx tsc -b
```

This document records what the session did and measured. It is **not** an
authorization, and nothing in it grants scope.

---

## 2. What merged

| PR | Branch | Merge | What it closes |
|---|---|---|---|
| **#199** | `feat/campaign-sheet-record-writes` | `3cd40d2` | A 500 the merge itself created; six false sentences in the served API reference; a 320px overflow that CLIPPED the record screen's section headers |
| **#200** | `test/security-attack-and-concurrency` | `ecbf8f4` | Nine unhandled 500s an enumeration kept missing; two tests that raced writers which could never win |

`#198` (bounded change feed) and `#201` (experiment data workspace) were open with
green local suites at the time of writing; check their state with `gh pr view`.

---

## 3. The one thing worth remembering from this session

**Every branch was green on its own, and merging them found defects none of them
could see.** That is not a coincidence and it is not about test quality — each of
these was invisible *by construction* to the branch that introduced it:

- **A live HTTP 500.** `7822b13` renamed `_apply_record_enum_fields`; PR #195 arrived
  on `main` with a proposal-acceptance path calling the old name. `main` alone
  resolves the old name, the branch alone defines the new one, and the merge was
  **textually clean**. Accepting a record-level enum proposal returned
  `500 Internal Server Error` on the merged tree only.
- **A capture surface that lied about twelve fields.** After the campaign-sheet
  widening reached the workspace branch, `capture_facts` still derived
  `record_writable` from the pre-widening set, so the screen would have told a
  scientist that twelve sample and facility values cannot be entered on the record —
  one screen away from an operation that accepts them.
- **A screen blaming an impossible cause.** Fixing that made twelve paths
  `record_writable: true` with no `choices`, and the copy said *"the set of values the
  official schema allows here did not load."* Measured: an unreadable schema makes
  `record_writable` **false at every path** (0 of 26, against 14 normally), so that
  cause cannot occur — and "right now" invited a retry that can never succeed.
- **A test that predicted its own inversion, correctly.** The security branch asserted
  `GET .../changes` was ABSENT and wrote: *"the day it ships this test goes red and the
  substitute below is replaced by the real thing."* It shipped; it went red; it was
  inverted rather than deleted.
- **A disclosure test that assumed every section starts open.** The run card grew a
  third `RunSection`; the loop read `[0, 1]` with a hard `aria-expanded === 'false'`.
  The new section starts CLOSED, so a correct toggle read as a failure. It now asserts
  the state **flips**, which holds however a section is seeded.
- **A duplicate object key `tsc` cannot see.** The merge kept both branches'
  `darwin:` lines in one literal; JavaScript silently took the later. Only the
  baseline invariant suite caught it, as a stale total.

**Only the Docker job could see a seventh.** `record-description.test.tsx` imports the
vendored schema from outside `apps/web`; `npm run build` is `tsc -b && vite build` and
the web stage copies `apps/web/` alone — so the branch **could never build a production
image**, while `npx tsc -b` locally and CI's `frontend` job (both full checkouts) stayed
green.

---

## 4. The recurring shape, stated once

Three separate tests in this session were **mechanically requiring a false or stale
sentence to stay**. Each was re-pinned to the invariant it was actually for:

1. a served OpenAPI description had to keep `~~struck~~` prose, in a surface rendered
   as **plain text** (`apps/web` declares no markdown dependency), so scientists saw
   literal tildes wrapping a claim the same paragraph contradicted;
2. the `422` refusal descriptions had to keep the same strike typography;
3. the change feed's gap guarantee had to keep a proviso that was measured false —
   **twice**, in two different wordings.

That last one is the lesson: two wrong provisos in a row meant the sentence was being
written about the wrong thing. It is now a property of the **sort key** rather than of
the clock, which subsumes all three failure modes at once.

---

## 5. Campaign-sheet capture: all 25 paths, measured over HTTP

| Authority | Paths | record `answers`/`edit` | run `PATCH` | run `overrides` |
|---|---:|---|---|---|
| experiment-level | **13** | `200` | `422` | `200` |
| run-level | **5** | `422` | `200` | `422` |
| unclassified | **7** | `422` | `422` | `422` |
| | **25** | | | |

`system.domain` is a 26th record-writable path, absent from this table because the
extractor's field map never emits it — so 13 and 14 are both correct about different
questions. All 14 have a website input surface.

Validation observed at the boundary: enum member `200`; off-enum
`422 not_an_allowed_value` carrying the schema's own list; wrong JSON type
`422 invalid_field_value`; a run-level path at the record arm `422 unrecognized_field`
(**authority is not conflated**); `attribution.uploaded_by` `422`; `block:attribution`
carrying `uploaded_by` `422 invalid_block_payload`. A run override with
`status: "verified"` and empty evidence is refused `invalid_envelope` — the
no-guessing rule enforced at a **write** boundary, not only at export.

---

## 6. What needs YOU, and what needs nobody

**Yours:**
- **Hosted QA** of every image from this session. `/krish` sits behind an Authentik
  edge this environment cannot authenticate to; no rollout is claimed as verified.
- **The 200%-zoom / responsive human sign-off**, still open. No CDP method drives it.
- **Personal-deploy retirement** (Vercel + Railway), still open.
- **A decision on sub-second timestamps** — see §7.

**Angel's**, unchanged and blocking nothing: the six `system.configuration.*` fields
(`docs/angel-scope-questions-2026-08-25.md`). `timestamps.created_utc` sits in the same
bucket for a different reason and must not be folded in with them — it needs no
scientific answer.

**Dean's / the operator's**, unchanged: applying any migration. `0005` remains
unapproved and the backfill has never run anywhere.

~~**Nobody's — it is just work:** a text input for the twelve free-text record-writable
paths; a `proposal` kind in the change feed; mounting `useChangeFeed` on a screen.~~

**CORRECTED 2026-08-31 — THE FIRST OF THE THREE WAS ALREADY DONE, AND THE REASON NOBODY
COULD SEE IT IS THE FINDING.** Struck rather than edited, because "it is just work" sends
a future session to build something that exists.

**The twelve free-text record-writable paths HAVE had a website input since `7822b13`** —
all 14 record-writable paths do. Three separate sessions measured otherwise because
`apps/web/src/components/RecordDescriptionPanel.tsx`, *the file that implements record
capture*, holds **2 raw NUL bytes**, and `grep`/`rg` classify such a file as binary and
skip it **silently, exiting 0**:

```bash
grep -rl  RecordDescriptionPanel apps/web/src   # 2 files  <- the panel is MISSING
grep -ral RecordDescriptionPanel apps/web/src   # 3 files  <- -a finds it
```

Measured at `bebf4e2` and again at `f201e78`: **379 files under `apps/web/src`, exactly
one holds a NUL**, and it is that one. `CLAUDE.md` §11 had declared this trap dead on
2026-08-30 and told future sessions not to cite it as live; that was true of
`lib/experimentGraph.ts` and false as a general claim. Both entries are corrected.

**A real defect did exist there, and it was a different one:** the UI's field inventory
was a hardcoded `RECORD_FIELDS` list whose only guard was a *Python* test that
regex-parses the TypeScript — so `vitest` alone stayed green over a stale list. The
inventory is now derived at runtime from the server's own `capture.record_writable`.

~~**The other two remain accurate as written:** the change feed still has no `proposal`
kind, and `useChangeFeed` is still mounted on no screen — re-measured with `grep -a`
after the NUL finding, precisely because the first item on this list had just proved
that a NUL-free measurement was not safe to assume.~~

**BOTH CLOSED 2026-09-01, in PR #210 (`31ca1d2`).** The sentence above was true when
written and is struck rather than edited so the sequence stays legible. Measured at
`main`:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0,'apps/api')
from isaac_api import change_feed as cf; print(sorted(cf.feed_kinds()))"
# ['experiment', 'proposal', 'run']

grep -ral useChangeFeed apps/web/src | grep -v __tests__
# apps/web/src/components/RecordActivityNote.tsx
# apps/web/src/lib/useRecordSession.ts
# apps/web/src/lib/useChangeFeed.ts
# apps/web/src/lib/recordChanges.ts
```

`useChangeFeed` is mounted in **`lib/useRecordSession.ts`, not a screen** — that hook is
already the single owner of record-scoped polling and all four record screens go through
it, so mounting per-screen would have meant four screens agreeing to run one poller each
with nothing enforcing it.

**One thing that was NOT built, and was not faked to satisfy a proof step:** there is no
proposal inbox in the frontend. `lib/api.ts` carries **zero** proposal references — no
client, no list, no detail — so a proposal entry can honestly only *announce*, and no read
surface was invented for it to refresh. A proposal entry carries no content either: its
key set is exactly `{kind, entity_id, changed_at_rev, updated_utc, state}`, and a
full-body scan of the served page for proposal values, notes, rules, digests and evidence
returns zero hits.

---

## 7. Two open decisions this session deliberately did NOT take

**Sub-second timestamps.** `workspace._now_iso()` formats whole seconds, so a change
that leaves an entity's key at or behind your cursor is not reported by that cursor.
The claim is now truthful and the exposure is pinned by a test that freezes the clock.
The recommended remedy is sub-second stamps in `_now_iso`, as its own reviewed slice
before any screen mounts the feed. Recorded so it is not re-derived: the schema declares
these timestamps `format: date-time` with **no `pattern`**, so RFC 3339 fractional
seconds are schema-legal, and `format` enforcement is shadow-mode-only per Q20 — the
blast radius is presentation, not validation. **A lagging watermark should be rejected**,
and on stronger grounds than "it buys duplicates": one `save_versioned` stamps every
changed run with one instant, so a cursor rewound to the start of its own second could
re-read the same page forever without advancing.

**A3, the app-wide palette debt.** Opening the record screen's draft blocks made axe
scan `.field-row` for the first time. Three tokens were this slice's own and were fixed
(`.field-path`, `.ev-row`, `.ev-locator` → `--text-muted`, 5.93:1), taking
`record-detail @ desktop` from 71 to 46 nodes. The remaining **+25 per cell across all
seven cells** is `--text-tertiary` (3.86:1) and `--text-quaternary` (2.53:1) elsewhere —
pre-existing failures becoming **measurable**, not new ones. Settling it is a palette
decision.

---

## 8. One risk that is nobody's fault and should not be left

> **CORRECTED 2026-08-31 — THE RISK THIS SECTION RAISED DOES NOT EXIST, AND THE
> COMMAND IT OFFERED AS PROOF RETURNS THE OPPOSITE OF WHAT IT SAYS.** The original
> text is struck in place rather than deleted, because "19 commits are one disk
> failure from gone" is exactly the kind of claim a future session acts on — by
> re-pushing refs that are already pushed, or by refusing to clean a worktree it
> could safely clean.

~~Three `preserve/*` branches hold **19 commits that exist on this machine only** —
`git ls-remote --heads origin 'preserve/*'` returns nothing. A previous session renamed
rather than deleted them precisely because they carry unique work. They are one disk
failure from gone. Either push them or decide out loud that they are disposable.~~

**What is actually true, measured at `ddec2b5`:** that `ls-remote` returns **10 refs**,
not nothing. All **19 commits are preserved on the remote** — 4 + 13 + 2, which is where
the original 19 came from — and each local branch's tip is **byte-identical** to a remote
ref's tip:

| Local branch | Tip | Unique commits | Remote ref holding the same tip |
|---|---|---:|---|
| `preserve/feat-run-page-api-superseded` | `4dac6b3` | 4 | `origin/preserve/feat-run-page-api` |
| `preserve/local-integration-qa-superseded` | `76622d4` | 13 | `origin/preserve/local-integration-qa` |
| `preserve/test-visual-responsive-sweep-superseded` | `85ef50b` | 2 | `origin/preserve/test-visual-responsive-sweep` |

**WHY THE ORIGINAL CLAIM LOOKED TRUE, because the mechanism is the reusable lesson and
not the arithmetic.** The three *local* branches carry a **`-superseded` suffix that the
remote refs do not**. So a lookup **by name** — `git ls-remote origin
"refs/heads/$b"` for each local `$b` — correctly returns nothing for all three, and a
session that checked that way would conclude, reasonably and wrongly, that the commits
were unpushed. The commits are on the remote; only the *names* differ. **A name-based
existence check is not a commit-based one, and for preservation only the second
question matters.**

Re-derive rather than trusting this table — the suffix mismatch is precisely why the
name-based form is the wrong instrument:

```bash
# The glob form. Returns 10 refs, not nothing.
git ls-remote --heads origin 'preserve/*'

# The question that actually matters: is each local tip present on the remote?
for b in $(git for-each-ref --format='%(refname:short)' refs/heads/preserve/); do
  tip=$(git rev-parse "$b")
  hit=$(git ls-remote origin 'refs/heads/preserve/*' | grep -c "^$tip")
  echo "$b $(git rev-list --count origin/main..$b) commits  remote_copies=$hit"
done
```

**Consequence for cleanup:** these three local branches hold **no unique state**, so
removing them destroys nothing. This section no longer asks anyone for a disposition
decision, because there is no longer a decision to take.
