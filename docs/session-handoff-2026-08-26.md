# Session handoff — 2026-08-26, **CLOSED OUT 2026-08-27**

> ## READ THIS BOX FIRST — the document below is a SNAPSHOT OF A SESSION THAT HAS SINCE FINISHED
>
> This file was written when a session stopped on a usage limit with one unreviewed PR and four
> unverified `wip/*` branches. **All of that is now resolved.** Everything the box below records is
> what a reader needs; the rest of the document is kept for its evidence and its reasoning, not as
> a description of current state.
>
> **`main` is `1dd28ad`. Zero open PRs. Zero `wip/` branches. Working tree clean, 0 ahead / 0
> behind.** Image `v0.0.177`. Backend **5,784 passed / 34 skipped**; frontend **4,469 passed / 173
> files**; `tsc -b` clean; snapshot `--check` clean on both artifacts. All measured on `1dd28ad`.
>
> **Every PR §3 and §4 were waiting on has merged**, each with an independent review and green CI
> on its exact head SHA: **#179** (the unreviewed one — its review returned DO NOT SHIP on four
> Critical findings, all closed), **#182** capture surfaces, **#183** five reachable 500s + the
> `record_id` path escape + a Critical reset fix, **#184** rename, **#185** the
> `official_validator_ran` wire discriminator, **#186** three a11y items + 119 transcribed Linux
> baseline cells, **#187** the committed `.venv` symlink, **#188** the session record.
>
> **The four `wip/*` branches §4 told you not to merge were not merged.** Each slice was re-run
> from its brief and re-measured from scratch; the snapshots are kept as
> `preserve/*-wip-superseded` for their history. **§4's warning was right and is worth keeping**:
> two of them looked finished and were not — the rename snapshot called `exp.save()` instead of
> `_save_versioned`, so **a rename never bumped `rev`** and a concurrent client's stale precondition
> would have passed; the discriminator snapshot had **9 real frontend assertion failures** and a
> false claim in its own comment.
>
> **Everything in §6 — what is Dean's, Krish's or Angel's — is UNCHANGED and still theirs.**
> Nothing in this session touched a database, a credential, the hosted deployment, or any external
> authorization.
>
> **What §5 listed as implementable and is now DONE:** §5.1 all five reachable 500s and the
> `record_id` path escape · §5.2 D1 and D3 (D2 declined with a measured basis — see below) · §5.3
> rename (**discard declined, and that is the finding**) · §5.4 the wire discriminator · §5.5's
> undocumented items · the automatable half of the accessibility work.
>
> **What is still open, and it is a short list:**
> - ~~**`system.domain` has no write path anywhere** (§5.2 D2). Declined deliberately: the fix
>   belongs in `Experiment.resolved_run_draft`, and **the repository holds two stored expressions
>   of the same derivation with opposite confirmation postures** — `draft_builder` stores it
>   directly, `inferability.system_domain` requires user confirmation and has no production caller.
>   Which posture governs is a decision, not a mechanical step. Deriving `domain` from `technique`
>   would mean authoring a **37-entry scientific classification that exists nowhere here**, which
>   §5 forbids.~~ **CLOSED 2026-08-27 — and the decline is struck rather than deleted because it
>   was RIGHT about the question it answered.** Deriving `domain` from `technique` is still
>   declined, for exactly this reason; the 37-entry figure was re-measured and is correct. What
>   changed is that the derivation turned out never to be required: **both** `system.domain` and
>   `system.technique` are closed enums declared by the official schema itself, so a scientist
>   CHOOSING from the schema's own enum is a user confirmation over a bounded set, not an
>   inference. Both now have a record-level write path. The two stored expressions of the
>   derivation rule are untouched and choosing between their postures is still an open decision.
>   See `CLAUDE.md` §11 for the measurement.
> - **Discard an experiment.** §15 enumerates only `INSERT`s and `UPSERT`s, so no committed
>   sentence permits a `DELETE` — while `db_write.WriteStatementPolicy` **does not refuse one**
>   (`delete` is absent from `_FORBIDDEN_KEYWORDS`; verified). **Mechanical permission is not
>   authorization.** A hard delete needs eight statements across seven referencing tables, six of
>   them append-only history, none carrying `ON DELETE`. **Owner's call.**
> - **A11Y-06's residue**: `/settings?tab=explorer` renders two `region` landmarks both named
>   "Endpoint Explorer". Baselined at the measured 1×7 with the one-line fix named; taking it costs
>   another CI round-trip.
> - **The a11y darwin column is REASONED, not measured**, and CI runs no macOS at all
>   (`grep -rn 'macos\|darwin' .github/workflows/` returns nothing). If anyone runs the suite on a
>   Mac, that reading wins.
> - `isaac_runs` Stage 2b · the Evidence Graph / Compare Runs cross-feature work · the residues each
>   merged PR names in its own body.
>
> **One correction to §5 itself:** it lists an apply route for `POST /ingestion/csv/preview` as
> outstanding. **It is not.** It is a committed human decision — *"Option 1 —
> reconciliation-only … a deliberate authority boundary, NOT a defect"*. Do not build it.
>
> **Three operational traps this session paid for, all now guarded or recorded:**
> 1. **A `.venv` symlink reached `main` and destroyed the reader's virtualenv.** `.gitignore` had
>    `.venv/` — trailing slash, which matches a directory and **not a symlink of the same name**.
>    Guarded in #187 by asserting no tracked entry has git mode `120000`. Rebuild on **Python
>    3.12**, not 3.14: 3.14 fails collection with a `UnicodeEncodeError`.
> 2. **Every merge to `main` conflicts every other open PR on the memory snapshot.** Resolve by
>    taking a side **and then regenerating** — doing only the first leaves CI red on indexed-source
>    drift, which happened here once.
> 3. **The OpenAPI aggregates in `settings-api.test.tsx` must be RE-MEASURED at every merge, never
>    added.** They moved four times in one session (93,478 → 98,335). Re-transcribe `apiFixtures.ts`
>    **by script** with `ensure_ascii=False`; hand-editing has broken it three separate ways.
>
> The durable record of all of this is `CLAUDE.md` §11, *"Session of 2026-08-26/27"*.

**Written at the end of a session that stopped on a usage limit, not at a natural boundary.**
Read this before doing anything else, then verify every fact in it with the commands in §1.
Nothing here is authorization; it is a description of where the work stopped.

---

## 0. The one-paragraph version

Org `main` is **`844b4ff`**, clean, 0 ahead / 0 behind, with **one open PR (#179)** waiting on
its last CI job and on an independent review that was still running when the session ended.
**Four implementation slices were in flight and are preserved as `wip/*` branches — they are
UNVERIFIED SNAPSHOTS committed by the orchestrator, not by their agents, and none of them may be
merged as-is.** Nine PRs merged this session (#171–#179 minus #179 itself, which is open). The
highest-value remaining work is enumerated in §5 with evidence, and the things that are genuinely
someone else's are in §6.

---

## 1. Verify this before trusting any of it

```bash
cd ~/Documents/ISAAC
git status -sb                       # expect: ## main...origin/main, clean
git log --oneline -3                 # expect 844b4ff at HEAD
gh pr list --state open              # expect exactly #179
git ls-remote --heads origin | grep wip/     # expect the four wip branches below
.venv/bin/pytest -q                  # expect 5368 passed, 30 skipped ON main
cd apps/web && npx vitest run        # expect 4390 passed, 167 files
cd apps/web && npx tsc -b            # expect exit 0
.venv/bin/python scripts/build_memory_snapshot.py --graph-dir graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json \
  --detail-out apps/api/isaac_api/data/memory-graph-detail.json --check   # expect no drift
```

If any of these disagrees with what is written here, **the commands win** and this document is
stale. Say so rather than working around it.

---

## 2. What was merged this session

| PR | merge | title |
|---|---|---|
| #171 | `c153ec9` | a scientist can finish a record they created, and the server stamps who |
| #172 | `6baadc8` | the write path returned the whole record's question set on every answer |
| #173 | `383ae2a` | an answer the record could not store returned 200 and said it was identical |
| #174 | `b7008b8` | a conflict decision could never be recorded, and Compare Runs scrolled sideways |
| #175 | `625e4d1` | the Assistant panel said nothing about whether a model is involved |
| #176 | `721238a` | the write path is now 98% smaller, and the graph stopped showing a deleted run |
| #177 | `1ad1f8f` | one malformed run draft took My Experiments down for the whole workspace |
| #178 | `844b4ff` | four of the six "STILL OPEN" items were already closed |

Latest published image: **`v0.0.167`** (from the #177 merge). #178 will have published a
successor; check `git ls-remote --tags origin | grep -oE 'v0\.0\.[0-9]+$' | sort -t. -k3 -n | tail -1`.

`CLAUDE.md` §11 carries the durable record of #171–#177 under **"Session of 2026-08-25/26"**. Do
not re-derive it; extend it.

---

## 3. THE OPEN PR — #179 — and exactly what it needs

**Branch** `fix/malformed-pending-entry-is-served-not-500`, head `724ce58`, base `1ad1f8f`.

**Status:** four of five CI checks **pass**; the a11y job was still pending. **The independent
review LANDED after this document was first written, and its verdict is DO NOT SHIP — 4 Critical,
9 Important.** The full findings are posted as a comment on #179; the four Critical ones are
summarised in §3.1 below. **Do not merge this PR.** The three gap fixes are sound and worth
keeping; the work is to close the four false user-facing claims first.

**What it does.** Closes the three residual gaps PR #177 named in its own tests: `GET /pending`
returned **500** on a malformed *entry* (`pending: [7]`); a wrong-typed *item* in a top-level
draft list raised out of `validate_draft`; and two `complete.py` write-path 500s. It adds a new
wire shape to the pending route — `unavailable: true` + `unavailable_reason` naming the JSON
*shape*, never the value — and widens `ApiPendingItem.id/kind/question` to `| null` so every
frontend consumer must decide rather than render `"Null"`.

### 3.1 The review's four Critical findings — this is the work

**C1 — the client tells the scientist a question "could not be read" that the server read and
served, and discards the prose.** `serialize.py:236` returns `kind or "blocker"`, so
`{"question": "q?"}` is served as `{id: "blocker", kind: null, question: "q?"}` with **no**
`unavailable` flag — but `adapt.ts:470-471` requires `typeof kind === 'string'`, so the screen
reports it unreadable. Pre-PR the same entry rendered the scientist's own question. It is the
**exact inverse** of the defect `adapt.ts:461-465` claims to have avoided: that docstring protects
`question` and leaves `kind` exposed.

**C2 — one consumer still renders the literal `"null"`, which falsifies the PR's headline claim**
that widening the three fields *"forced every consumer to handle it"*.
`assistantComposer.ts:537-543` interpolates `question` under a comment asserting it is
non-optional — **a premise the same commit deleted** at `types.ts:800`. `tsc -b` passes because
template literals accept `null`, so the type widening could not have forced anything there.

**C3 — "Every question reviewed this visit" is newly reachable over an unresolved blocker.**
`GuidedCompletion.tsx:1358` gates on `!blocker && …`, and `blocker` now derives from `answerable`,
so `!blocker` no longer means "every question". The comment at `:1351-1357` calls `notShown === 0`
*"LOAD-BEARING"* **precisely because** `!blocker` accounts for every question; the filter
invalidated that premise and the guard was not extended with `unreadable.length === 0`.

**C4 — a published MCP contract is now false, not merely incomplete.** `mcp/tools.py:965` says
*"The answer key is always `id`"* and there is now a class where `id` is `null`. `grep -c
unavailable tools.py` → 0, four tools forward the raw body, and there is no `outputSchema`
anywhere, so nothing rejects it. `tools.py:332-349` states the rule that makes this §1's business:
the MCP description is *"a SEPARATE PUBLISHED CONTRACT, read by external agents that never see the
OpenAPI document."*

**Two Important findings I re-verified myself at `724ce58`**, so they are not relayed on trust:

```
block_evidence = {"series:s": 7}   ->  TypeError: 'int' object is not iterable   (GET /{id} = 500)
series = [7]                       ->  findings: ['series[0]', 'qc']
```

**I5** puts a false claim inside a §13-protected file, and the falsity is a live 500:
`draft_validator.py:306-310` justifies the guard's boundary by saying `block_evidence` values are
type-checked by `_claim_covered` — which is `any(isinstance(e, dict) for e in (entries or []))`
and raises on `7`. **I6** is #177's own defect returning one level down: `_container` returns `[7]`
unchanged, so `if series:` is true and the qc gate produces *"a claim this module is in no position
to make, derived from the very value it just refused"* — which is verbatim what #177's comment says
it prevents. The new test uses `any(where == ...)`, so nothing pins the finding set.

**Also named by the review and NOT in the PR's own residue list: six more read-path 500s** —
`assets[0].sha256 = 7`, `assets[0].evidence = 7`, `implicit[0].evidence = 7`,
`series[0].series_id = {}`, `descriptors_outputs[0].descriptors = [7]`, and the `block_evidence`
value case above. Only two of the eight are covered by the "nested items still raise, by design"
rationale; that argument is about the override probe and does not reach the other six.

**And one that is worse than a 500: `{"kind":"qc","question":{"a":1}}` is *answerable*,** so the
object reaches `<h2>{blocker.question}</h2>`. There is **no ErrorBoundary anywhere** in the
codebase, so React blanks the whole page — and it falsifies `types.ts:826-832`'s claim that an
unreadable entry *"cannot reach any of them by accident — it is a compile error"*.

**Before merging, you must:**

1. Close C1–C4, I5 and I6. Then re-review with a **fresh** agent — the one that produced these
   findings has seen the code and is no longer independent of the fix.
2. Confirm the a11y job passed. `gh pr checks 179`.
3. Regenerate the snapshot: #179 touches six manifest-listed files (`serialize.py`,
   `draft_validator.py`, `complete.py`, `adapt.ts`, `types.ts`, `GuidedCompletion.tsx`).
4. **One non-issue, named so nobody chases it:** a parallel auditor reported
   `test_the_entry_is_served_and_names_the_shape_that_was_found` failing. That was its own
   mutation, applied in a shared worktree and reverted immediately after; the file passes 32/32
   clean. Two agents sharing one checkout is the mistake, and it is the second time this session
   that it produced a phantom result.

**What #179 itself names as NOT fixed** — carry these forward, do not lose them:

- `routes._answer_asset_uris` iterates `draft.get("pending") or []` directly instead of via
  `workspace._blocker_entries`, so a non-iterable `pending` still **500s a WRITE** while every
  read of the same record is 200. One line. Pinned in-tree with "invert when closed".
- The **typed** refusal for a wrong-typed stored `block_evidence` (the write still returns a bare
  500; the refusal is already atomic, it is just untyped, and typing it is a `routes.py` change).
- A dict pending entry whose `about` is an object is passed through as-is: no 500, but React
  would refuse to render an object child.
- The `list_questions` OpenAPI description and the MCP `isaac_list_questions` tool description do
  **not** mention the `unavailable` discriminator, so two published contracts are now incomplete.

---

## 4. THE FOUR IN-FLIGHT SLICES — preserved, unverified, do not merge

Each was an implementation agent still working when the session ended. I committed and pushed
whatever was on disk **so nothing would be lost**. The commit message on each says the same thing
and it is the truth:

> Committed by the orchestrator to preserve work in progress, NOT by the implementing agent, and
> NOT reviewed, tested, or verified by anyone. Treat every file here as a partial draft: it may
> not compile, may not pass its own tests, and may contain scaffolding the agent intended to
> remove.

**How to resume one:** re-dispatch the slice from its brief (§7), pointing the new agent at the
`wip/` branch as a starting point, and instruct it to **re-measure every claim from scratch**. Do
not ask it to "finish" the branch — ask it to reach the brief's acceptance criteria, using the
branch only if the branch helps.

| branch | head | files | scope |
|---|---|---|---|
| `wip/reachable-500s-and-record-id-containment` | `cf4e66d` | `routes.py`, `workspace.py` (+399/−13) | five reachable 500s **and a path-escape read** — see §5.1 |
| `wip/capture-surfaces-that-promise-what-they-refuse` | `0abb6bd` | `notes.py`, `routes.py`, `workspace.py`, `UnmappedNotesPanel.tsx`, `types.ts`, `apiFixtures.ts`, `extract/draft_builder.py` (+420/−26) | three capture surfaces that accept or promise what the system then refuses — §5.2 |
| `wip/rename-and-discard-an-experiment` | `fda8723` | 14 files, +2157/−47, incl. new `RecordNamePanel.tsx`, `CharacterCount.tsx`, `record-name.css`, and 1,134 lines of new tests | a scientist cannot rename or discard anything they create — §5.3 |
| `wip/official-validator-ran-discriminator` | `2c0b35c` | 13 files, +1857/−339, incl. new `lib/officialAttribution.ts` | the durable fix for a defect that has recurred four times — §5.4 |

**Two of these look substantially complete** (`rename` and `discriminator` both carry large new
test files), which makes them *more* dangerous, not less: a branch that looks finished invites
merging without the review it never had. Neither has been run by anyone.

**Note on `wip/rename-and-discard-an-experiment`**: it changes
`apps/api/tests/test_about_and_openapi.py` and `apps/web/src/test/apiFixtures.ts`, which means it
moves the **published OpenAPI operation count away from 69**. `apiFixtures.ts` descriptions must
be **re-transcribed from `create_app().openapi()` with `ensure_ascii=False`, never hand-edited** —
hand-transcription has broken this twice (escaped em-dashes; a doubled brace).

---

## 5. The remaining work, with evidence

This comes from a read-only audit run at `1ad1f8f`. Every claim carries a citation; several were
independently re-measured. **Two things it found are new and recorded nowhere else** — §5.1 and
§5.5.

### 5.1 Reachable HTTP 500s, and one path escape — HIGHEST URGENCY

`wip/reachable-500s-and-record-id-containment` was mid-flight on all five.

| id | defect | evidence |
|---|---|---|
| **F1** | **`Experiment.record_id` is unguarded — a 500 AND an arbitrary JSON file read that escapes the workspace.** `record_id = "../planted_secret"` → **200**, body contains a file outside `records_dir`; `"../../../far_away_secret"` → **200**, outside the whole workspace. `{}`/`[]`/`0`/`""`/`False` → **500** on `/evidence` and `/artifacts` | `workspace.py:3559` raw vs `Run.from_state`'s `_as_record_id` at `:1323`; `record_path` has no containment check; `routes._read_artifact_json` swallows `OSError` |
| **F2** | **One malformed document → 500 on `GET /api/experiments`**, hiding every record, while each healthy record's own detail route still returns 200 — a silent whole-list outage | `workspace.py:3553-3560`; `_load_all_experiments` catches only `FileNotFoundError`. `Run.from_state`'s docstring says this exact defect was measured and fixed **for runs** — it is the design precedent |
| **F3** | `answers` that is not an object → **500** on four write routes. `(body.get("answers") or {}).items()` — `or {}` is not a type guard | `routes.py:3719`, `:4510`, `:7041`. Verified with `"str"`, `5`, `1.5`, `True`, `[1]`, `[{"a":1}]` |
| **F4** | An unhashable `source`/`action` tested against a `frozenset` → **500** two lines before a correct typed refusal that already exists | `routes.py:7948`, `:8139`; sets at `notes.py:167`, `:179` |
| **F5** | `experiment_id` ≥ 256 bytes → **500 on ~40 operations** (`Path.exists()` raises `OSError`). 255 → 404, 256 → 500. MCP bounds the same identifier at 128; HTTP does not | `workspace.py:4663-4664`; `routes.py:630-638` |

**Reachability, stated honestly:** F1 and F2 need malformed *persisted* state — no route lets a
client set `record_id`, and export mints it. So F1 is **defence-in-depth, not a live breach**, and
must not be reported as one. F3, F4, F5 are reachable by any HTTP client with one wrong JSON type
or a long URL.

**The governing rule, from #177 and worth restating because it decides every fix here:** *a
malformed value in a REQUEST can be refused, because the caller sent it and a typed 422 names what
to fix; a malformed value already PERSISTED cannot be refused to the reader, who did nothing wrong
and whose record would simply vanish.* F3/F4/F5 → typed 4xx. F1/F2 → degrade truthfully, never
repair, never invent, keep the record BLOCKED.

**A methodological warning the audit surfaced about itself, and it is the most transferable thing
in this document:** its own independent fuzz sweep — 728 requests, every GET route × 11 malformed
path ids × 11 malformed query params, 26 write targets × 28 wrong-typed nested bodies — returned
**zero 500s**, and nearly shipped as a clean bill of health. It was wrong about F3: the bodies
omitted `confirmed_by_user: true`, so every write was refused at the confirmation gate *before*
reaching the crash line. **A fuzz corpus that does not satisfy a route's preconditions never
reaches its body.** Two independent sweeps disagreed and the disagreement was the finding.

What *did* survive both sweeps: no accepted write leaves state a later read cannot survive; the
structured-answer values are well guarded; and the **MCP tool layer had zero hits** across all 10
tools × every property × 19 wrong types plus 20 malformed JSON-RPC envelopes — its JSON Schema
closes F3 and F5, which the HTTP routes leave open.

### 5.2 Three capture surfaces that promise or accept what the system refuses

`wip/capture-surfaces-that-promise-what-they-refuse` was mid-flight on all three. **All three are
currently untested**, so any fix must end with a test that fails on `main`.

- **D1.** After mapping a note, `UnmappedNotesPanel.tsx:827-829` says *"a value still has to be
  entered and confirmed on the field itself"*, and the API says the same in three places including
  the published OpenAPI. `mappable_field_paths` is **25 paths**. **Both write paths refuse every
  one:** `edit` and `answers` on `system.technique` → `422 unrecognized_field`. No test pins the
  copy. Same class as the three claims `CLAUDE.md` §12 records as *scoped, not deleted*: a
  true-sounding sentence pointing at a locked door.
- **D2.** Setting `technique` or `facility` makes the record **un-exportable** through a field the
  scientist cannot reach. Measured against a controlled baseline: `field:system.technique` adds
  `system: 'domain' is a required property`; `field:system.facility.beamline` adds `'domain'` AND
  `'technique'`. And `field:system.domain` → **422 `not_overridable`**. The derivation exists and
  is used on the fixture path (`extract/draft_builder.py:100-120`, which even says *"omitting it
  would make the draft un-exportable"*) but no write path applies it. Recoverable via
  `overrides/clear`, so un-exportable-*until-cleared*, not permanent.
- **D3.** A contributor set through the only available write path can **never export**.
  `block:attribution` → 200 accepted; export then fails at the *draft* validator with
  `official_report: null` and `attribution.contributors[0]: contributor has no evidence`. The
  override route writes no `block_evidence`; `draft_validator.py:433-434` requires an
  `attribution:<name>|<role>` entry.

**§5 is the crux of D2 and D3.** Do not invent a domain or fabricate evidence. Legitimate answers
include: apply the *stored, documented* derivation (§5 permits inference by a documented rule, and
refusing the techniques it cannot decide); make `system.domain` overridable so the scientist
states it; or **refuse the write** with a message naming what else is needed — turning a silent
un-exportable state into an immediate, actionable refusal. What is not acceptable is a 200 that
silently breaks export, or weakening an evidence requirement to make a write pass.

### 5.3 A scientist cannot rename or discard anything they create

`wip/rename-and-discard-an-experiment` was mid-flight. Verified: no `PATCH /api/experiments/{id}`
and no `DELETE` among the 69 published operations; `title` is written only at creation;
`workspace.remove_experiment` has exactly one caller (the demo reset path); the repository layer
has **no delete statement at all**. **With `0001_experiments` applied to the hosted database, every
mistakenly created experiment is permanent, with its typo.**

Rename is the easy half and needs **no migration** — `title`/`description` live in the `state`
jsonb. Discard is the half that may correctly end in *"not this slice"*: check whether §15's lift
authorises a delete at all (quote the sentence, and §15's own rule that a slice which cannot cite
one has not established its basis), check `db_write.WriteStatementPolicy`'s treatment of `DELETE`,
and note that **`0005`'s foreign key has no `ON DELETE`** so a projection row must go first. A
soft discard in the existing jsonb may be right — weigh it honestly rather than defaulting to it.
Whatever ships must not reuse the demo-reset typed-gate phrase (`CLAUDE.md` §11 records at length
that `RESET` and `RESET EXAMPLE WORKSPACE` are different strings and conflating them disables the
confirm button); do not create a third confusable phrase.

### 5.4 The wire discriminator — the durable fix for a four-time recurrence

`wip/official-validator-ran-discriminator` was mid-flight. `POST .../check` stamps its `official`
block `schema: "ISAAC v1.05"` **unconditionally**, and `dry_run: true` does **not** discriminate: a
dry-run *pass* requires `validate_official`, but a dry-run *failure* may never have reached it
(`export.py` returns `official_report=None` on the no-guessing and exactness paths). **There is
nothing on the wire to branch on**, so every consumer must independently remember an ordering rule
— which is why "fix the surfaces" is unbounded.

Measured on #171: a slice fixed the conflation in **three renderers** and left it standing in
**both machine-readable contracts** (OpenAPI for two routes, the MCP `isaac_check_run`
description), in a fourth screen, and — on a different discriminator, `unavailable` — inside two
of the files it had just rewritten. `routes.py:12388-12400` and `:916` call this *"THE DURABLE
FIX"* and defer it; two independent reviewers converged on it.

Follow the precedent `POST /api/validate/record` already set, whose three properties `CLAUDE.md`
§12 says must not be collapsed back together: `schema_ok` beside `ok`; findings in a **separate**
list never merged into `errors`; and **no surface may report an ISAAC-local refusal as an
official-schema error** (§1 — the vendored schema is not ours to speak for). Do **not** as a side
effect "fix" the deliberate, documented divergence §12 records between the two validate routes.

**The second half is what makes it durable:** a guard that fails when a *new* consumer renders a
schema verdict without consulting the discriminator. Pinning today's five surfaces will not stop
the sixth.

### 5.5 Not recorded anywhere else — found by audit, unaddressed

- **A screen tells the scientist to enter a value on 25 fields, all of which 422.** §5.2 D1. No
  test pins the copy: `rg "No value was written"` returns one hit, the string itself.
- **`system.domain` is unreachable and its absence breaks export.** §5.2 D2. Untested.
- **A contributor set the only available way can never export.** §5.2 D3. Untested.
- **No delete, no rename.** §5.3. No document in the repository named either absence before now.
- **`ExportUnit.record_path`'s docstring calls itself *"the only place this slice could have turned
  document content into a filesystem path"*** — measurably false of the experiment-level twin
  (§5.1 F1). Fix the code and the docstring together.

### 5.6 Smaller category-A items, with citations

`Evidence Graph draws one page of runs with no page control` (`screens/EvidenceExplorer.tsx`,
`limit: RUNS_PAGE_SIZE` = 50 from `lib/runPaging.ts:35`; disclosed at `lib/evidenceGraph.ts:1280`.
The audit cited this as `EvidenceExplorer.tsx:575` — the file is under `screens/`, not
`components/`, and the line was not re-verified here) · `Compare Runs "Open"
opens Focus Run, not the field` (`RunCompare.tsx:752`, link `:791` — its own comment names the
needed change) · no link between Evidence Graph and Compare Runs, which is the literal
"cross-feature" residue · **Compare Runs has zero browser/axe/layout/visual coverage** (absent
from `e2e/surfaces.ts`; no seeded record has runs so the table never mounts read-only — pinned at
`e2e/specs/layout-widths.spec.ts:803-829`; closable as a *mutation-suite* spec) · actor
negative-control suite, two of four cases unpinned (`docs/actor-attribution-seam-survey.md:88-96`)
· `runtime_records.py` still calls `status()`/`export_ready()` unshared (2× dry run per record) ·
**persist exported artifact files** — `records/<id>.json` + sidecar live only in the workspace dir,
so a pod restart leaves a record saying *exported* with no artifact
(`docs/create-experiment-persistence.md:471-482`) · detail-route latency still linear (78.2 →
31.4 ms at 1,000 runs after #176; residual is repeated `resolved_run_draft`, 53% in `deepcopy`).

**Accessibility, and which half is automatable:** A4 `scrollable-region-focusable` (3 pairs), A5
`/load` has no `<h1>`, A6 two unnamed `role="search"` landmarks, and the `.section-tab` contrast
(**3.86:1**, `--text-tertiary #78838f` at 12.5px/500; in-repo precedent `--text-muted #5b6570` at
5.93:1) are all doable here — the contrast one needs a **Linux-CI round-trip** to re-transcribe
~35 baseline cells. The record-chrome reflow slice (LAYOUT-01…04) is prescribed as one slice by
the baseline matrix. **A3's systemic 1,610-node contrast failure is NOT ours** — five failures are
`opacity` composites of tokens that pass at full strength, `tokens.css:3-5` forbids editing values
there, and the matrix says it *"needs a palette decision, not a patch"*.

---

## 6. What is genuinely someone else's

**Nothing in §5 is blocked on any of this.** Do not wait on it, and do not do any of it.

**Dean (infrastructure / operator):** apply `0003_revisions` + `0004_submissions` — owner-approved
and digest-pinned; the sequence is `--plan --through 0004_submissions` then `--apply --through
0004_submissions`, and **`--through` is why it is now possible at all** (before this session
`--apply` globbed every migration, so `0003`+`0004` could not be applied without the unapproved
`0005`). Also **E1, a trusted authentication boundary** — `POST /api/experiments/{id}/submit`
answers **409 `human_actor_required` / `no_verifier_configured`** in *every* deployment, so Submit
is fully built and unreachable; gates **G2** (per-record display), **G3** (the five withdrawn
aggregates), **G6** (personal data in the seed's `attribution`); the Stage 2b environment; and
**D1–D9**, which he deferred (`POST /api/mcp` → 404; `/api/assistant/ask` → 501;
`/api/transcription` → 501 — all measured).

**Krish (owner):** hosted QA of every image since `v0.0.13` (`/krish` is behind an Authentik edge
this environment cannot authenticate to, and an agent must not); **G4**, the real `Cmd`/`Ctrl`-`+`
200% zoom sign-off, which **no CDP method, flag or API can drive** and is therefore not
automatable at all; **G5**, personal-deploy retirement (disable, not delete — Railway has a
persistent volume); `0005` approval; the run-override actor storage decision; A3's palette
decision; whether ISAAC should surface Authentik's logout path; and **whether the 2026-08-25
operator addendum and the Angel question list have been forwarded — only Krish can say, and the
repository records preparation, not delivery.**

**Angel (scientific scope):** the six `system.configuration.*` fields — one question asked six
times, *"may two runs legitimately hold different values?"* — and which keys
`sample.composition`/`sample.geometry` should offer (the three current ones are hardcoded to the
synthetic demo material).

**Deliberately out of scope, with a committed sentence behind each — do not "fix" these:** a CSV
apply/commit route (*"Option 1 — reconciliation-only … a deliberate authority boundary, NOT a
defect"*); a product screen advertising the assistant seam (§3/§9 of the AI packet — PR #175
refused exactly this brief and was right to); any production provider; `POST /api/uploads`
accepting a file; a real-record adapter; collaboration in any form; audio `source_type`; n-way
Compare Runs (`RUN_COMPARE_MAX = 2` is a decision, not a deferral).

---

## 7. Operational notes that cost time to learn

**7.1 Reviews.** Every PR this session got an independent Opus review from an agent that
implemented none of it, **and every single review found something CI could not see** — #179's
found four false user-facing claims and stopped it from merging. #177's found
that its own §13 disclosure was false. Run reviews in **isolated worktrees** — a read-only
reviewer sharing a checkout with an implementer detected drift and briefly retracted its own
arithmetic. Give the reviewer: the branch, the branch point, what the change claims, a
priority-ordered check list, the explicit instruction *"do not fix anything, report"*, and a
required verdict line. Tell it not to run the full suites.

**7.2 The snapshot.** `apps/web/src/**` and `src/**` are manifest-listed, so an ordinary component
or truth-core edit **drifts the snapshot**. Always pass `--detail-out` — without it, `--check`
prints "ok: no drift" over a stale deep artifact. Regenerate **once** after all in-flight work in
one working tree settles. In a worktree, pass an **absolute path** to `graphify-out`. Every merge
to `main` puts every other open PR in CONFLICTING on the snapshot; resolve by **regenerating**,
never by hand.

**7.3 Shell traps that produced false results this session.** `pytest ... 2>&1 | tail` reports
exit 0 while pytest errored — use `set -o pipefail`. `--timeout` is not installed. When
re-transcribing OpenAPI descriptions, `json.dumps` must use `ensure_ascii=False` or em-dashes
become `—` and the parity test's `_unescape` cannot handle them. And a doubled `}}` in an
f-string-plus-concatenation snippet broke the same transcription **twice**, the second time
because the buggy snippet was reused.

**7.4 Two flaky frontend tests were fixed, and both had the same shape as the honesty defects.**
One sampled a counter of two independent effects after awaiting only one (`expected 1 to be 2` in
CI, green locally — reproduced on demand with a 120 ms probe). The other had raised
testing-library's `asyncUtilTimeout` to 5,000 ms while vitest's own per-test deadline was **also**
5,000 ms, so the raised budget was unreachable and the failure named neither the query nor the
DOM. If a test fails in CI and passes locally, suspect an ordering assumption dressed up as an
assertion before suspecting the product.

**7.5 Mutation-test everything, and expect one to survive.** #177's list-aliasing mutation
initially survived because the test exercised only one branch. #179's report describes the same
pattern. A guard nobody has tried to break is a guard nobody has tested.

**7.6 The pattern that has now recurred five times, stated as plainly as possible.** A surface
returns 200, or a green check, or a passing test, for work it did not do — and the *proof artifact*
is what conceals it. A table-driven test whose fixture makes every row reachable cannot see which
rows were reachable before, and it reads as one more confirmation. A correction sweep that claims
"all N artifacts are fixed" is itself a checkable claim, and one such sweep was published
unchecked. When you write "every", "only", "no route can", or a number — measure it in that
sitting, or do not write it.

---

## 8. Repository hygiene

`main` clean and synced. Local branches: `main` plus three intentional `preserve/*`. The four
`wip/*` branches are **remote-only by design** — they exist so the work survives, not so it gets
merged. Agent worktrees under `.claude/worktrees/` are disposable now that everything is pushed;
`git worktree remove --force <path>` then `git worktree prune`.

Do not delete a `wip/*` branch until its slice has been redone and merged. When one is superseded,
rename it `preserve/*` rather than deleting it, and precede any deletion with a mechanical
`git rev-list --count origin/main..<branch>` = 0 proof — that is this repository's established
practice.
