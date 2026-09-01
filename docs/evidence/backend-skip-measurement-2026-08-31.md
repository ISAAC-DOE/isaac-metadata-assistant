# Every backend skip, measured — 2026-08-31

**Command, quoted rather than described:**

```bash
.venv/bin/pytest -q -rs
```

**Result:** `6870 passed, 40 skipped, 1 warning in 552.65s (0:09:12)`, exit `0`.
Measured at `main` @ `bebf4e2523a1cec8bf2ec6b58bdf18ded9f4cdc1` (= tag `v0.0.192`).

This is the **complete** backend suite, not a partial collection. The 40 skips below
sum to exactly 40; the arithmetic is shown so a reader can check it rather than trust it.
**One family has since been closed** — see §3.5 — so a run today measures **39**, and both
totals are carried in the §2 table with their vantage points rather than one overwriting
the other.

---

## 1. Why this document exists

A previous session attributed these skips to **shallow git history**, then corrected
itself because this checkout is a full clone. A later static analysis guessed the
families were *"missing database migrations (0003/0004) — 3 instances"*, driver
presence, absent Graphify artifacts, and build variants.

**Both explanations were wrong, and the measurement says so plainly.** There is not one
migration-gated skip, not one Graphify-gated skip, and not one `git show`-gated skip in
this run. **29 of the 40 — 72.5% — are one family nobody had named.** That is the whole
reason a guess about a skip set is not a substitute for `-rs`.

---

## 2. The measured table

| # | Skip reason | Tests | Files / markers | Expected locally? | Expected in CI? | Externally gated? | Hides an untested path? | Deterministic local substitute? |
|---|---|---:|---|---|---|---|---|---|
| 1 | `ISAAC_RUN_REAL_ENGINE_PARITY is not '1'` — *"this suite WRITES, so it never connects by accident"* | **29** | `test_run_row_parity.py` (24), `test_discard_an_unsubmitted_experiment.py` (5) | **Yes** — by design | **No** | Yes — needs a throwaway PostgreSQL | **No** | Not wanted (see §3.1) |
| 2 | `ISAAC_PERF_BENCH is not 1` — opt-in wall-clock benchmark | **4** | `test_pending_count_is_not_materialised.py:349` (2), `test_pending_reads_are_boundable.py:686` (1), `test_change_feed.py:1056` (1) | Yes | Yes | No — opt-in flag | No | Deliberately not (see §3.2) |
| 3 | `psycopg2 is installed`; the **absent**-driver path is untestable | **2** | `tests/test_db_recon.py:1294`, `apps/api/tests/test_db_provider.py:703` | Yes | **Yes** | No | **YES — it did** | **Yes — now built (§3.3)** |
| 4 | *"tolerated by the strict reader; covered by the route tests"* | **4** | `test_one_malformed_document_does_not_take_down_the_list.py:283` (`source`, `draft`, `created_utc`, `answer_log`) | Yes | Yes | No | No — covered elsewhere | Not needed (§3.4) |
| 5 | ~~*"the run-list route implements `q` in this checkout"*~~ — **CLOSED 2026-08-31, §3.5** | ~~1~~ **0** | `test_mcp_server.py:342` | — | — | No | **it did** | **Built** |
| | **Total, as measured at `bebf4e2`** | **40** | | | | | | |
| | **Total, after family 5 was closed (§3.5)** | **39** | | | | | | |

`29 + 4 + 2 + 4 + 1 = 40.` ✔ — the run this document reports, at `bebf4e2`.

`29 + 4 + 2 + 4 + 0 = 39.` ✔ — after §3.5 closed family 5 on 2026-08-31. **Both sums are
kept, each with its vantage point**, because a reader who runs `-rs` today and counts 39
must be able to see that this is the *same* measurement advanced by one closure, not a
second measurement that disagrees with the first.

---

## 3. Family-by-family verdict

### 3.1 Real-engine parity (29) — LEGITIMATE, and **not** skipped where it counts

The largest family, and the one a reader is most likely to mis-read as a coverage hole.
It is not one. **CI sets the flag and these tests run there**, against a real
PostgreSQL service container:

```bash
rg -n "ISAAC_RUN_REAL_ENGINE_PARITY|ISAAC_REQUIRE_REAL_ENGINE_PARITY" .github/workflows/ci.yml
#  1014:  ISAAC_RUN_REAL_ENGINE_PARITY: "1"
#  1015:  ISAAC_REQUIRE_REAL_ENGINE_PARITY: "1"
#  1127:  ISAAC_RUN_REAL_ENGINE_PARITY: "1"
#  1128:  ISAAC_REQUIRE_REAL_ENGINE_PARITY: "1"
```

`ISAAC_REQUIRE_REAL_ENGINE_PARITY=1` additionally makes the *absence* of an engine a
failure rather than a skip in CI, so the suite cannot go green there by skipping. The
local skip is **consent-to-connect**: the suite writes, and a developer's laptop must
never connect to a database by accident. Keep exactly as is.

### 3.2 Opt-in benchmarks (4) — LEGITIMATE, and correctly excluded

Wall-clock benchmarks. `CLAUDE.md` records this project being bitten twice by
timing-sensitive assertions that were green locally and red under CI contention; a
correctness suite that silently included wall-clock measurement would reintroduce that.
Opt in with `ISAAC_PERF_BENCH=1`. Keep.

### 3.3 Absent-driver path (2) — **WAS A REAL HOLE. NOW CLOSED.**

These two assert the error an operator sees when `psycopg2` is missing. They are gated
on the driver being genuinely absent — and it is absent in **neither** environment this
project runs in: a developer checkout and CI both install the `api` extra
(`.github/workflows/ci.yml`: `pip install -e ".[dev,api]"`, four sites).

**So `MissingDependency` and `ProviderUnavailable(gate="driver")` were executed by no
test anywhere.** A skip that fires in every environment is not an environment gate; it
is an untested path wearing one.

Closed by a deterministic sibling in each file that poisons `sys.modules["psycopg2"]`
with `None` — the one value the import machinery turns into an `ImportError` — so the
module's own `except ImportError:` runs, rather than a double being substituted for the
function under test. `monkeypatch.setitem` restores the real entry at teardown.

The environment-gated originals are **kept, not replaced**: witnessing a *genuinely*
absent driver is a different fact from a poisoned import, and they cost nothing while
they skip. Their skip messages now name the sibling, so the skip no longer reads as an
untested path.

*Negative control, run:* deleting the `monkeypatch.setitem` line makes
`test_an_unimportable_driver_reports_the_driver_gate` **FAIL**. The test measures the
substitution rather than passing by coincidence.

### 3.4 Strict-reader tolerance (4) — LEGITIMATE

A table-driven test over eight malformed-document rows; only the rows the strict reader
actually *raises* on are asserted here, and the tolerated ones are covered by the
list/detail route tests. The skip message names each case, so nothing is hidden.

One honest caveat rather than a silent pass: the test's docstring says *"three of the
eight rows"* are tolerated while **four** skip. The docstring's count is stale; the
skips themselves are individually truthful and each names its row. Not a correctness
defect, and deliberately not "fixed" by widening the assertion — `CLAUDE.md` §11 records
that making every row reachable is exactly how a table-driven test stops being able to
show which rows were reachable before.

### 3.5 The MCP `q` skip (1) — **OBSOLETE. The condition inverted under it.**

`test_list_runs_refuses_a_filter_the_route_does_not_have` exists to distinguish
**refused** from **ignored**: a query parameter the route does not have must be refused
by the tool layer, because passing it through would reach FastAPI, be dropped, and
return every run *under a claim of a filtered search*.

Its docstring still reads *"`q` is not on this route at this commit"*. Measured:

```bash
cd apps/api && ../../.venv/bin/python -c "
from isaac_api.mcp.policy import OPERATIONS
print(sorted(OPERATIONS['list_runs'].query_parameters))"
# ['exported', 'limit', 'offset', 'overrides', 'q']
```

`q` **is** on the route now. So the guard fires, the test skips, and the invariant it
protects is asserted nowhere — the skip silently converted a live test into a dead one
the day the route gained the parameter.

The invariant is still worth having; only the example expired. The fix is to assert it
with a parameter the route genuinely lacks, **and to assert that the chosen parameter is
still absent**, so the next widening fails loudly instead of skipping quietly.

~~*Deferred by one slice, deliberately:* `apps/api/isaac_api/mcp/**` and
`test_mcp_server.py` are owned by a concurrent slice adding MCP proposal tools, which
will move this operation table. Fixing it here would conflict with that work and be
re-measured immediately afterwards. It is carried in this document so it cannot be
lost, and is closed in the follow-up slice.~~

**CLOSED 2026-08-31, in the follow-up slice this paragraph promised.** The fix is the
one prescribed two paragraphs above, implemented literally: the probe is now **derived**
rather than named —

```python
declared = OPERATIONS["list_runs"].query_parameters
absent_filter = "no_such_filter_" + "".join(sorted(declared))[:24]
assert absent_filter not in declared, ...
```

so the test **cannot go dead again** when the route grows a filter, and the derivation
is *asserted* rather than assumed: a collision fails loudly instead of skipping quietly.

**A SELECTIVITY CONTROL WAS ADDED IN THE SAME CHANGE, AND IT IS THE HALF THE ORIGINAL
PRESCRIPTION DID NOT NAME.** A refusal test alone stays green under a *different* bug —
a tool that refuses **every** extra argument, rejecting a caller's legitimate filter as
unknown. `test_list_runs_accepts_a_filter_the_route_does_have` asserts the other half
using `q` itself, which is what makes removing `q` from the refusal probe correct rather
than merely convenient.

**Measured, before → after:** `test_mcp_server.py` `63 passed, 1 skipped` → **`65 passed,
0 skipped`** (`.venv/bin/pytest apps/api/tests/test_mcp_server.py -q -rs`). The +2 is the
revived test plus the new control. **The suite-wide skip count therefore moves 40 → 39**,
and family 5 in the §2 table is now empty rather than deferred.

---

## 4. What did **not** appear, stated because it was predicted

- **No** shallow-git-history skip. This checkout is a full clone
  (`git rev-parse --is-shallow-repository` → `false`), so the `git show`-guarded
  assertions in `test_the_two_constraint_numbers_are_each_still_the_measured_ones`
  **executed**. `CLAUDE.md` §11 is right that they degrade to skips *in CI* at
  `fetch-depth: 1`; they do not degrade here, and this run confirms the direction.
- **No** migration-gated skip. `0003`/`0004` gate nothing in this suite.
- **No** Graphify-artifact skip.
- **No** build-variant skip.
