# The run-scoped ingestion proposal, proven end to end — 2026-09-02

**Status:** measured. Backend and browser evidence below was produced on this machine
at the commits named; the real-PostgreSQL half is **unverified locally and must be
judged from exact-head CI** — there is no PostgreSQL, no `psql` and no container
runtime in this environment, which is the same limitation
`apps/api/tests/test_proposal_durability.py` already records for itself.

**Data boundary:** none. Every record, run, note, proposal and value named here was
created by a test, in a `tmp_path` or `/tmp` workspace, seconds before it was read. No
database connection was opened from this machine, no migration was applied anywhere, no
hosted environment was contacted, and nothing under `examples/` was read or staged.

**Authorization basis:** `CLAUDE.md` §15, *"APPLICATION-SIDE SCOPE EXTENSION — PROJECT
OWNER, 2026-08-29"*, which authorizes *"persistent ingestion proposals and the durable
contract they need … and the associated tests, documentation, migration artifacts, PRs
and safe integration."* This work adds tests and one CI step over an already-shipped
feature; it adds no table, no route, no migration and no dependency.

---

## 1. The claim this overturns

`apps/web/e2e/mutation/proposals.spec.ts` states, in its own header:

> ONE CONSEQUENCE OF THAT CHOICE, STATED RATHER THAN DISCOVERED: an exported record
> refuses `POST .../runs` (`409 already_exported_without_runs`, measured), so no
> run-scoped proposal is exercised here. Every target below is the one record-scoped
> path this build has — `system.technique`, the sole member of
> `record_scoped_target_field_paths`. Run-scoped acceptance, the `target_run_removed`
> refusal and the run's own current-value read are NOT covered by this file.

**Every word of that is true, and the conclusion drawn from it — that run-scoped
proposals are structurally untestable in a browser — is not.** The refusal is a property
of the two records that spec chose (`SEED.exported` and `SEED.exportedAlt`, the only two
canonical examples no other mutation spec touches, and both exported). It is not a
property of the product.

`POST /api/experiments` is the product's own creation path, it works in the ordinary
scope, and a record created through it takes runs. Both halves are now asserted:

* `apps/api/tests/test_run_scoped_proposal_lifecycle.py::test_the_exported_seed_records_really_do_refuse_a_run`
  keeps the original measurement honest — the canonical exported record still answers
  `409 already_exported_without_runs`;
* `::test_the_product_s_own_creation_path_reaches_a_run_scoped_proposal` walks
  create → two runs → note → run-scoped proposal → accept entirely over HTTP with
  nothing borrowed from a seed;
* `apps/web/e2e/trusted/proposals-run-scoped.spec.ts` does the same **through the
  screen** — Create Experiment, then **Add Run** twice — and reviews the proposal by
  clicking.

## 2. The second structural claim, and why it needed a third backend

The same spec also says:

> THE SUCCESSFUL-ACCEPTANCE LEG IS NOT PROVEN HERE, AND THE REASON IS STRUCTURAL … The
> verifier is chosen from the BACKEND PROCESS's environment, and this suite starts
> exactly one backend … One process has one configuration, so the refusal leg and the
> success leg cannot both be measured in one run of one suite.

**That reasoning is correct and is the reason a THIRD Playwright config exists** rather
than the mutation config being altered. `apps/web/playwright.trusted.config.ts` starts
its own backend (port 8101), its own workspace and its own Vite server (5275), with
`ISAAC_EDGE_TRUST_VERIFIER=test_fixture` and `ISAAC_FIXTURE_ACTOR_SUBJECT`. **The
mutation suite is byte-unchanged** and still measures the refusal every shipped
deployment produces — re-run and green:

```
npx playwright test -c playwright.mutation.config.ts e2e/mutation/proposals.spec.ts
  12 passed (37.0s)
```

Nothing about this makes acceptance reachable in a deployment.
`apps/api/tests/test_deploy_config.py::test_no_committed_deploy_artifact_arms_the_edge_trust_verifier`
scans the `Dockerfile`, `build-push.yaml` and `pr-docker-smoke.yml`; the new config is
none of those, and — measured rather than assumed, because the file **does** contain the
literal — the `Dockerfile` copies `apps/web/` only into the web BUILD stage (`COPY
apps/web/ ./`, line 19) while the final stage takes `--from=web /web/dist` alone (line
63). The file reaches no runtime image, and Vite bundles nothing outside `src/`.

## 3. The target is derived, never guessed

Both the backend and the browser proof choose their target from the **server's own**
derivation, never from a literal.

Backend — the three expressions the create and review routes dispatch on:

```
$ python -c "from isaac_api import routes as r; ..."
record-scoped: ['system.technique']
run-scoped:    ['context.environment', 'context.temperature_K',
                'context.thermodynamics.atmosphere',
                'sample.composition.CuO2_mass_fraction',
                'sample.composition.sucrose_mass_fraction',
                'sample.geometry.pellet_diameter_mm',
                'sample.material.formula', 'sample.material.name',
                'sample.material.provenance', 'sample.sample_form',
                'system.facility.beamline', 'system.facility.endstation',
                'system.facility.facility_name', 'system.facility.organization',
                'system.facility.site', 'timestamps.acquired_end_utc',
                'timestamps.acquired_start_utc']
  context.environment        -> run_field
  sample.material.formula    -> run_override
  system.technique           -> record_enum_fields
```

`test_the_derivation_is_not_vacuous_and_agrees_with_the_wire` then asserts that this
derived run-scoped set is exactly `target_field_paths` minus
`record_scoped_target_field_paths` as the list operation serves them, so the file cannot
be aiming at a path the routes classify differently from the way it believes they do.

The two targets are chosen by a stated **property**, not by name:

* `RUN_FIELD_TARGET` — the lowest-sorting `run_field` target that the vendored schema
  closes with an enum of **four or more** members which the seed run draft already holds
  a value at. Four, because the proof needs three distinct values at once (run A's, run
  B's and the proposed one) plus one for the edited acceptance. Today this resolves to
  `context.environment`, enum `["operando", "in_situ", "ex_situ", "in_silico"]`.
* `OVERRIDE_TARGET` — the lowest-sorting `run_override` target that is an unconstrained
  schema `string` the seed experiment draft holds a value at. Today `sample.material.formula`.

The **values** come from the vendored schema too, not from the author. A schema refresh
that closed or reopened an enum moves the choice automatically.

The browser spec derives the same thing from **two wire reads and no literals**: the
run-scoped set from the list operation, and a three-member string enum from
`GET /api/schema`.

## 4. The fourteen points, and what each one's status actually is

**Thirteen are established; point 6 is UNMET BY DESIGN and is labelled as such in its
own row rather than in a footnote.** The distinction matters: "the API offers no
pre-acceptance edit primitive" is a finding about the contract, not a test result, and a
row that read as though it had been demonstrated would be the exact defect this proof
keeps catching elsewhere.

| # | Claim | Where |
|---|---|---|
| 1 | a run-scoped proposal can be created with no export side effect | `test_1_creating_a_run_scoped_proposal_has_no_export_side_effect` — the whole authoritative snapshot (every export unit's draft + every run's `resolved_run_draft` + the record draft) is **byte-identical**, as `json.dumps(..., sort_keys=True)`, and both run bodies are **document-identical** (every key of the served document equal); `exported` false; `record_id` null; `/artifacts` reports nothing; no `*.evidence.json` anywhere in the workspace. Positive control: `test_1_the_no_side_effect_comparison_is_not_vacuous` |
| 2 | it survives a new request and a store reload | `test_2_the_proposal_survives_a_new_request_and_a_store_reload` (a fresh `create_app()`; every key of the create response compared except the three derived-on-read ones). **PostgreSQL: CI only** — `test_REAL_ENGINE_a_run_scoped_acceptance_survives_the_round_trip_with_its_run` and `test_REAL_ENGINE_the_run_scoped_acceptances_survive_a_pod_restart` |
| 3 | listed and readable with `run_id` set | `test_3_the_proposal_is_listed_and_readable_with_its_run_id` (both the list and the detail operation) |
| 4 | it appears in the website review surface | `proposals-run-scoped.spec.ts` › *the scientist sees it, and sees which RUN it is about* — the card's `.proposal-scope` reads exactly `On run <run id>` |
| 5 | current run value and proposed value are distinguishable there | *the CURRENT value it shows is the targeted run's* — see §5 below |
| 6 | *"editing (before acceptance) changes only the proposal, not the run"* — **UNMET BY DESIGN, not established.** No pre-acceptance edit primitive exists: a proposal is immutable (contract §3), and `PATCH`/`PUT`/`DELETE` on one all answer **405**, asserted by `test_6_no_operation_edits_a_stored_proposal_in_place`. The edit primitive this build has is the `accepted_from: "edited"` acceptance, and it is covered — `test_6_an_edited_acceptance_writes_the_CORRECTED_value_to_one_run_only` (the corrected value is written, `proposed_value` is not rewritten, the other run is untouched). The "change my mind before accepting" path is `supersede` + a new proposal, and it writes nothing: `test_6_superseding_writes_nothing_to_either_run` | 
| 7 | authorized acceptance changes ONLY the targeted run | `test_7_and_8_acceptance_writes_the_named_run_and_the_other_is_document_identical[run_field]` and `[run_override]`, plus the browser's *accepting it through the screen writes ONE run* |
| 8 | the other run is **document-identical** (every key of the served document equal) | same tests — the untargeted run's **whole** `GET .../runs/{id}` body, `version`, `rev` and `updated_utc` included. **Not byte-identical, and the word was corrected**: the comparison is `==` over the parsed JSON, so a key reordering or a whitespace change would pass it. Content is the right claim here; the stronger word was not the one being measured. Negative control: `test_the_isolation_comparison_is_not_vacuous` |
| 9 | 412 / 428 / `409 proposal_stale` | `test_9_a_stale_if_match_is_412_and_carries_the_current_token`, `test_9_a_missing_if_match_is_428_when_an_actor_EXISTS`, `test_9_a_moved_target_is_409_proposal_stale_and_the_other_run_is_untouched`, paired with `test_9_an_unrelated_write_does_NOT_make_the_proposal_stale` |
| 10 | attribution on the history; `user_confirmation` on the value | `test_10_the_acceptance_history_carries_the_fixture_subject_and_trust_basis`, `test_10_the_written_run_field_records_a_user_confirmation`, `test_10_the_override_acceptance_records_what_it_displaced`, and the browser's *the acceptance is attributed to the subject this deployment vouches for* |
| 11 | change-feed entries above the pre-accept cursor, no duplicate, no loss | `test_11_the_feed_reports_the_proposal_and_the_targeted_run_above_the_cursor`, `test_11_paging_one_entry_at_a_time_loses_and_duplicates_nothing` |
| 12 | rejection leaves both runs unchanged | `test_12_rejecting_leaves_both_runs_unchanged` and the browser's *rejecting it through the screen leaves BOTH runs exactly as they were* |
| 13 | a retried create with the same `client_request_key` returns the existing proposal | `test_13_a_retried_create_with_the_same_client_request_key_returns_the_existing` — asserts the **scoped** claim DEC-13 actually makes and no more, in both directions: the retry on the same record deduplicates (and a retry naming a *different run* under that key still returns the FIRST proposal — the key is the identity, not the body), and **a second record given the same key mints its own**. Mutation-checked: making the route's lookup search every experiment in the scope drove the second-record leg RED while every same-record assertion still passed |
| 14 | record-scoped proposals still behave | `test_14_a_record_scoped_proposal_is_refused_a_run_and_still_works`, plus the unchanged `test_ingestion_proposals.py` and `test_mcp_proposals.py` |
| + | validation and the export dry run read the accepted canonical run value | `test_validation_and_the_export_dry_run_read_the_ACCEPTED_run_value` |

Additionally: `test_a_removed_target_run_refuses_acceptance_and_writes_nothing`
(`409 target_run_removed`, reachable only where the record has a surviving second run to
show untouched), and `test_the_default_configuration_still_refuses_acceptance`
(`409 human_actor_required` — the leg every shipped deployment produces) are asserted in
the same file, so neither leg of I4 can be quietly lost.

## 5. The browser finding on run scope — the panel is CORRECT, and it is measured

`IngestionProposalsPanel`'s `CurrentValue` branches on `proposal.run_id`: for a
run-scoped proposal it calls `GET .../runs/{run_id}` and reads that run's
resolved-then-own value; for a record-scoped one it reads the record's draft. **There is
no defect here to report, and nothing was patched.**

It is measured rather than read. The spec puts **three distinct values** in play — run
one's, run two's, and the proposed one — and the panel must render the second run's:

```
await expect(body).toContainText(target.runTwo);
await expect(body).not.toContainText(target.runOne);
await expect(body).not.toContainText(target.proposed);
await expect(label).toHaveText(/run/i);
```

**Negative controls, run by hand and reverted** (recorded in the spec header too):

| control | applied to | result |
|---|---|---|
| A | expect the OTHER run's value in the panel | **FAILED** — `Received string: "in_situ"`, which is the second run's value |
| B | delete the `Accept as Proposed` click | **FAILED** — the "— Accepted" card never appeared, so nothing in the setup accepts on its own |
| C | write the untargeted run out of band after the baseline is captured | **FAILED** — *"the run this proposal did not name was modified by accepting it"* |

## 6. The durability gap that was found, and closed

Before this change, over `apps/api/tests/test_proposal_durability.py`:

```
$ grep -an applied_run_id apps/api/tests/test_proposal_durability.py
185:    ``applied_via``, ``applied_run_id``, ``applied_rev`` and
```

**One line, and it is a docstring.** No assertion touched the field, and none could:
`build_the_scenario` accepts exactly one proposal and that one is RECORD-scoped, so
`applied_run_id` was `None` in every document the file had ever compared. A
serialisation change that dropped it, or wrote it back as `null`, passed all fourteen
scenarios. `None == None` is the durability equivalent of `[] == []` — the vacuousness
that file's own §2 exists to refuse.

§6 of that file now builds a record with **two runs and an accepted run-scoped proposal
on each**, so `applied_run_id` is non-null, differs between them, and cannot be
reconstructed from "the first run". Its premise test additionally asserts that the
ORIGINAL builder still produces `applied_run_id == [None]`, so a future change that made
the original cover the field would make this section's justification **fail** rather than
quietly become false.

Its second target is DERIVED too, and this needed a correction: `SECOND_RUN_FIELD_PATH`
and `SECOND_RUN_FIELD_VALUE` were two literals under a comment claiming they were *"read
from the application's own derived set"*. They now are — `_second_run_field()` takes the
lowest-sorting member of `routes.RUN_WRITABLE_FIELD_PATHS` other than `RUN_FIELD_PATH`
that the vendored schema closes with a string enum, and its first member as the value
(today `context.environment` / `operando`). `RUN_FIELD_PATH` beside it stays a literal
and its comment says so, which is what made the false claim next to it visible.

`.github/workflows/ci.yml`'s `expected_scenarios` moves **14 → 20** in the same commit
(+4 local: one premise/rehearsal and three damage controls — dropped, nulled, and
**swapped to the wrong run**, the last being the one a picked-key comparison would miss;
+2 `@real_engine`).

## 7. Mutation checks — every `MUTATION:` line was earned

Each was applied to `apps/api/isaac_api/routes.py`, the named test run, and the file
restored from a pristine copy (`git diff --stat` empty afterwards).

| # | mutation | test | result |
|---|---|---|---|
| 1 | `_apply_run_field(...)` added after `exp.add_proposal(proposal)` in the create route | `test_1_creating_a_run_scoped_proposal_has_no_export_side_effect` | **RED** |
| 2 | `accepted_value = body["value"]` → `= proposal.proposed_value` | `test_6_an_edited_acceptance_writes_the_CORRECTED_value_to_one_run_only` | **RED** |
| 3 | `run = exp.sorted_runs()[0]` at the top of the run-field branch | `test_7_and_8_acceptance_writes_the_named_run_and_the_other_is_document_identical[run_field]` | **RED** |
| 4 | `current != proposal.target_digest` → `proposal.base_rev != exp.rev` | `test_9_a_moved_target_...` **PASSED** (it cannot tell the two apart alone) and its pair `test_9_an_unrelated_write_does_NOT_make_the_proposal_stale` | **RED** |
| 5 | `actor_subject = identity_module.stamp_actor(...)` → `= None` | `test_10_the_acceptance_history_carries_the_fixture_subject_and_trust_basis` | **RED** |
| 6 | the run-field branch loops over `exp.sorted_runs()` and writes every one | `test_11_the_feed_reports_the_proposal_and_the_targeted_run_above_the_cursor` | **RED** |
| 7 | the accept branch widened to `action in (ACTION_ACCEPT, ACTION_REJECT)` | `test_12_rejecting_leaves_both_runs_unchanged` | **RED** |
| 8 | the create route's `client_request_key` lookup searched `[q for other in ws.list_experiments(session_id=scope) for q in other.sorted_proposals()]` instead of `exp.sorted_proposals()` | `test_13_...`'s second-record leg | **RED**, on exactly its own message, while every same-record assertion still passed |

## 8. Two measured facts a future session should not re-derive

**The ordinary scope is required for this proof, not merely convenient.**
`identity.stamp_actor` returns `None` **unconditionally and first** inside a
worked-example session, so an acceptance there is recorded UNATTRIBUTED *even under the
fixture verifier* — which `test_ingestion_proposals.py::test_I7_an_acceptance_inside_a_tutorial_session_is_unattributed`
already pins. Attribution is one of the things this proof establishes, so a session-scoped
suite could not have established it. That is why the trusted browser suite opens no
session at all.

**Under the fixture verifier, `428` and `412` on `accept` become observable for the first
time.** `post_proposal_review` runs the attributability gate **before** `_check_if_match`,
which is deliberate and documented — a permanent refusal must not be reported as a
transient one. The consequence is that in every default deployment an `accept` with no
`If-Match` answers `409 human_actor_required` and never the `428` the operation's own
`If-Match` sentence promises. `test_9_a_missing_if_match_is_428_when_an_actor_EXISTS`
measures the other side of that ordering, so both halves of the published contract are
now asserted somewhere instead of one being taken on trust.

## 9. Verification actually run

All commands from the worktree at branch `test/run-scoped-proposal-proof`, with
`PYTHONPATH=<worktree>/apps/api:<worktree>/src` and the repo venv's interpreter.

```
pytest apps/api/tests/test_ingestion_proposals.py apps/api/tests/test_mcp_proposals.py \
       apps/api/tests/test_proposal_durability.py \
       apps/api/tests/test_run_scoped_proposal_lifecycle.py -q -rs
  247 passed, 6 skipped

pytest -q -rs                     # FULL backend suite, in a WORKTREE
  7117 passed, 47 skipped in 559.03s

pytest apps/api/tests/test_committed_snapshot.py apps/api/tests/test_memory_graph_detail.py -q
  154 passed, 1 skipped

npx tsc -b                                        exit 0
npx vitest run                                    191 files, 5074 passed
npm run typecheck:e2e                             exit 0

npx playwright test -c playwright.trusted.config.ts
  5 passed (14.6s)
npx playwright test -c playwright.mutation.config.ts e2e/mutation/proposals.spec.ts
  12 passed (37.0s)
npx playwright test --list          # the READ-ONLY suite
  0 lines matching "trusted/"; Total: 1508 tests in 20 files

python scripts/build_memory_snapshot.py --graph-dir <main>/graphify-out \
  --out apps/api/isaac_api/data/memory-snapshot.json \
  --detail-out apps/api/isaac_api/data/memory-graph-detail.json --check
  ok: no drift (both artifacts), exit 0
```

**THE SKIP COUNT IS QUOTED WITH ITS CHECKOUT, because a skip total without one is not a
measurement.** `47` is the **worktree** figure. `graphify-out/graph.json` is gitignored
and therefore absent from every worktree and every clone, and exactly two tests gate on
its presence, so the same commit measured in the **main checkout** reads `45`. The
6 skips inside `test_proposal_durability.py` are the `@real_engine` gate
(`ISAAC_RUN_REAL_ENGINE_PARITY`), which CI's `postgres-migration` job sets — and where
`ISAAC_REQUIRE_REAL_ENGINE_PARITY` makes an absent engine a **failure** rather than a
skip.

**Delta arithmetic, labelled as arithmetic rather than a second measured run:** the new
file collects **30** tests and `test_proposal_durability.py` moves **14 → 20** collected
(`pytest --collect-only -q`, and 9 → 13 top-level test functions), so the baseline this
branch started from is `7083 passed / 45 skipped` in a worktree. That figure was not
re-measured by running the suite at `origin/main`.

## 10. What is NOT established here

* **The real-PostgreSQL half is unverified locally.** There is no PostgreSQL, no `psql`
  and no container runtime in this environment. `test_REAL_ENGINE_a_run_scoped_acceptance_survives_the_round_trip_with_its_run`
  and `test_REAL_ENGINE_the_run_scoped_acceptances_survive_a_pod_restart` **skipped
  here** and must be judged from exact-head CI. This is the same limitation
  `test_proposal_durability.py`'s own header records, and CI is the first execution of
  every `@real_engine` case in this repository.
* **Nothing about the hosted deployment.** `/krish` sits behind an Authentik edge this
  environment cannot authenticate to. `HOSTED QA PENDING (Krish)`.
* **Acceptance remains impossible in any real deployment**, and that is unchanged by
  this work. It requires a trusted authentication boundary ISAAC has not built and
  cannot build: Dean reconfirmed on 2026-08-12 that the Service is a plain ClusterIP
  with no NetworkPolicy, so an in-cluster caller can forge forwarded identity headers,
  and the presence of `X-authentik-username` proves nothing. The fixture verifier is a
  **test-only** configuration that no shipped artifact sets. Everything proven here
  about the success leg is proven about the code path, not about a deployment that can
  reach it.
* **No production code was changed.** No defect in `apps/api/isaac_api/**` was found by
  this proof. Measured rather than asserted:

  ```
  $ git diff --stat origin/main -- apps/api/isaac_api/ src/
   apps/api/isaac_api/data/memory-snapshot.json | 6 +++---
   1 file changed, 3 insertions(+), 3 deletions(-)
  ```

  One regenerated memory artifact and nothing else — `memory-graph-detail.json` did not
  move, and `src/isaac_records/**` (the truth core) is untouched. The mutations in §7
  were applied to a working copy and reverted from a pristine backup; `git diff` over
  `routes.py` was empty afterwards, which is why it does not appear above.

---

## 11. Corrections made after independent review

The review of PR #223 at head `75f7350` returned **FIX FIRST** on text-only claim
defects — no assertion was wrong, and every one of these was a sentence claiming more
than the code beside it did. They are recorded rather than silently swapped, because
that is what this repository's §11 discipline asks for and because four of the five are
the same shape as the defects this proof was written to catch.

| id | defect | fix |
|---|---|---|
| **I1** | `test_13`'s docstring said the test *"shows the same key on a DIFFERENT record minting its own"*. **The body created no second experiment** — its last assertion was `listed["total"] == 1` on the one record. DEC-13's *"within a scope"* half was therefore unasserted while the docstring claimed it. | The leg was **added**, not the clause deleted: a second record is created through `POST /api/experiments`, given the same key, and asserted to mint its own `proposal_id`, with neither record seeing the other's. Mutation-checked (§7 row 8). |
| **I2** | `test_proposal_durability.py`'s `SECOND_RUN_FIELD_PATH`/`SECOND_RUN_FIELD_VALUE` were **literals** under a comment saying they were derived *"for the reason `RECORD_VALUE` is"*. | Derived, via `_second_run_field()` — see §6. The comment is now true rather than removed, because it was the right claim to make. |
| **I3** | the `@real_engine` count is **six** since §6 was added, and **three sites still said four**: `.github/workflows/ci.yml` (the skip guard and the deleted-scenario converse) and `test_proposal_durability.py`'s local-rehearsal docstring. | All three corrected. `ci.yml`'s other "four real-engine scenarios" line belongs to the **discard** step and is still right — it was deliberately left alone. |
| **M1** | *"byte-identical"* described a `==` over `response.json()`, which is equality of every key and value and **not** of the response bytes. | Reworded to **document-identical (every key of the served document equal)** at every site, including the test's own **name**, with the reason stated in place. `_authoritative_snapshot`'s comparison keeps the word, because it really is a byte comparison over `json.dumps(..., sort_keys=True)`. |
| **M2** | §4 row 6 read as though *"editing changes only the proposal"* had been demonstrated. | Relabelled **UNMET BY DESIGN** in the row itself, with the contract reference and what IS covered. §4's heading now says thirteen of fourteen are established. |

Re-verified after these changes:

```
pytest apps/api/tests/test_ingestion_proposals.py apps/api/tests/test_mcp_proposals.py \
       apps/api/tests/test_proposal_durability.py \
       apps/api/tests/test_run_scoped_proposal_lifecycle.py -q -rs
  247 passed, 6 skipped

npx tsc -p e2e/tsconfig.json --noEmit                            exit 0
pytest apps/api/tests/test_committed_snapshot.py \
       apps/api/tests/test_memory_graph_detail.py -q              154 passed, 1 skipped
snapshot regeneration + --check                                   no drift, exit 0
```

**`247`, UNCHANGED — and the first draft of this line said `248`, which had not been
measured when it was written.** It is recorded rather than quietly replaced because it
is the same defect class as I1 through M2 above, committed by the same hand inside the
paragraph correcting them, and because the number was *reasoned* ("the leg must add
one") when the arithmetic is the opposite: **none of these five fixes adds a test.** I1
adds an assertion leg *inside* `test_13`; I2 replaces two literals with a derivation;
I3, M1 and M2 are comment, name and prose. The collected counts are therefore identical
to §9's — 30 for the lifecycle file, 20 for the durability file. Re-derive rather than
trusting this sentence: `pytest <the four files> --collect-only -q`.
