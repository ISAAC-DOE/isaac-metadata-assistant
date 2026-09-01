# Session closure — 2026-08-31 / 2026-09-01

**Org `main` at `31ca1d2`.** Seven PRs merged, each green on its **exact pushed head**, each
independently reviewed by an agent that did not implement it, with every Critical and
Important finding fixed before merge.

> **Verify before you trust this page.** Every number here quotes the command that produced
> it, because this session's recurring finding was that *a measurement can return a plausible
> non-answer*. Re-run them rather than citing them.

---

## 1. What merged

| PR | Merge | Slice |
|---|---|---|
| #203 | `ddec2b5` | Backend skip measurement; two driver-gate error paths no environment executed |
| #204 | `f201e78` | A skip that killed its own test; the `preserve/*` correction |
| #206 | `700cca2` | Five documentation claims a future session would have acted on |
| #207 | `f1fe5d1` | Record-field inventory derived from the server; the NUL-byte finding |
| #208 | `1339636` | ISAAC Assistant artifact feasibility; the deep-link decision |
| #209 | `c6422af` | **A3 contrast debt closed** — browser-measured on both platforms |
| #210 | `31ca1d2` | Change feed: durable sequence ordering, proposal kind, consumer mounted |

**Final verification at `31ca1d2`, measured in the main checkout, not projected:**

```
.venv/bin/pytest -q -rs        6973 passed, 39 skipped, 0 failed      exit 0
npx vitest run                 189 files, 4956 passed                 exit 0
npx tsc -b                                                            exit 0
build_memory_snapshot --check   no drift, BOTH artifacts               exit 0
worktrees                       1 (primary)          stranded work: none
```

Skip families sum to exactly 39: real-engine parity **29**, opt-in benchmarks **4**,
psycopg2-installed **2**, strict-reader tolerated **4**, MCP `q` **0** (closed this session).

PR #205 was **closed, not force-pushed**: its head had been rebased after publishing, and
rewriting a published ref was prohibited. The work moved to `fix/a3-accessible-palette-v2`
(#209) with nothing lost.

---

## 2. The through-line: four tools that returned a wrong answer without erroring

Each was caught **only because a second method disagreed** — never because the first
complained. This is why every count in this document quotes its command.

| Tool | What it reported | Truth |
|---|---|---|
| `tr -dc '\000' < f \| wc -c` | **7** NUL bytes | **918**. macOS `tr` aborts on binary input (`Illegal byte sequence` → stderr) and the pipeline still exits 0 |
| `ugrep` regression scan | nothing, read as "no regressions" | hit a **complexity limit** and never ran |
| `grep IMPROVED` over an a11y CI log | **66** changed cells | **157**. A rule that stops firing *entirely* yields no axe result and is reported as **`FIXED?`** by a separate loop (`e2e/helpers/axe.ts:214`) |
| the `foregrounds` exact-set guard | **0** failures | **vacuously true**. `auditScan` reaches that check only when a count already MATCHES — a `continue` sits right after the `IMPROVED` push — and none of 161 matched. Transcribing the counts exposed **14** failures |

Use a reader that cannot fail silently:

```bash
python3 -c "import sys;print(open(sys.argv[1],'rb').read().count(b'\x00'))" FILE
```

---

## 3. A3 is closed, and it is the first a11y figure here measured on both platforms with
nothing carried forward

```
A11Y_BASELINE_TOTAL_NODES   darwin 2464 -> 871      linux 2466 -> 871
161 cells -> 70   ·   91 reach zero (13 whole surfaces)   ·   66 lowered   ·   4 unmoved
DARWIN_CARRIED_FORWARD = []          all 7 platform splits collapsed
```

`--text-tertiary` `#78838f` → `#626c77`: 5.34:1 on white, **4.54:1** on the worst ground
`--assist-tint`, which paints the 342px `.record-right` / `.memory-right` panels and
`.assistant` — not just chips. An independent reviewer re-implemented WCAG 2.x from the W3C
text **without** the repo helper and reproduced all **47** published ratios exactly, then
brute-forced the ramp to confirm `#626c77` is the lightest compliant value in its own
hue/saturation band.

**Measured, and it inverts the old design intent:** *zero* declarations qualify for the 3:1
large-text exemption (max font-size 13px), so 4.5:1 is the bar everywhere. The palette had
encoded "smaller text → lighter grey", which is backwards — and meaningful scientific content
(experiment id, schema field path, record filename, evidence provenance keys, a 10.5px/600
subsection heading) sat at **2.53:1**.

**Still open, asserted so by test:** three ancestor-`opacity` composites that darkening
cannot reach *without destroying the ramp* — the opacity itself has to go.

---

## 4. Both preserved WIPs were broken, and were audited rather than trusted

A prior session left work uncommitted in two worktrees. It was **committed first** (nothing
lost), then judged:

- **A3 WIP** had *deleted* the `--text-quaternary` declaration while leaving **74 live
  `var()` references across 17 files** resolving to an invalid value, and its chosen
  `#646e79` still failed at **4.41:1** on the assistant panel.
- **Change-feed WIP** had **five** defects including three false published claims, left the
  suite red in **9** places having never run it, and cited a test file twice in committed
  prose **that did not exist**.

The two worst change-feed defects, both independently pinned: `Experiment.rev` was never
floored, so a persisted `"rev": -5` keyed the record's own entry *below* `ZERO_KEY` and was
returned by **no** read — not even the cursorless resync the contract offers as the universal
remedy; and a skipped entity could move **backwards**, which is the very defect being fixed.

---

## 5. The change feed lost events silently, and now cannot

Its own docstring admitted it: a change *"moved forward only into the second your cursor
already sits in"* was **not reported**. The sort key is now `(changed_at_rev, kind,
entity_id)` — a durable per-record sequence position, floored ≥0 on read and ≥1 on write.
`CURSOR_VERSION` 1→2; a v1 cursor is **refused (422)**, never misread. `updated_utc` remains
for display and is load-bearing for nothing. A third kind, `proposal`, is served carrying
**no content** (key set exactly `{kind, entity_id, changed_at_rev, updated_utc, state}`).

An independent reviewer **could not break the ordering property**: 4 mutations, 23 malformed
persisted shapes across 3 routes, 15 cursor-forgery variants, 4 page-boundary regimes, a
served-body leak scan, an AST-guard mutation, and an independent re-derivation of every
published aggregate.

**`useChangeFeed` is mounted in `lib/useRecordSession.ts` — not a screen**, because that hook
already owns record-scoped polling for all four record screens.

**What was NOT built, and was not faked to satisfy a proof step:** there is **no proposal
inbox in the frontend**. `lib/api.ts` carries zero proposal references. So a proposal entry
can honestly only *announce*, and no read surface was invented for it to refresh.

---

## 6. Claims that were false and are now scoped, not deleted

- **A correct caveat was deleted and replaced with a stronger claim, in text served to
  clients.** `SEQUENCE_PROOF` published an unqualified three-step proof while all three steps
  read `self.state_path` — the local filesystem, not the durable row. The description it
  replaced said the right thing: *"it is small because this application runs as a single pod
  reading one clock — that is the REASON it is small, not a proof that it is zero."*
  Re-scoped; a test now pins the scope so it cannot vanish again.
- **A docstring's two chosen examples were exactly what happens.** `_position` claimed `bool`
  is refused and `int("7")` never coerced; measured, `"7"`→7, `true`→1, `3.9`→3. **The claim
  was corrected, not the code**, and for a concurrency reason: `rev` is also the served
  `version` token and the basis of every `If-Match`, so refusing a coerced `"7"` to `0` would
  move a record's version **backwards** and could let a stale token match.
- **The NUL-byte trap was declared dead and was live.** `components/RecordDescriptionPanel.tsx`
  — *the file implementing record capture* — holds 2 NULs, which is why three sessions believed
  the twelve free-text record paths had no website input. They have had one since `7822b13`.
- **A plan document describing the NUL defect was itself invisible because of it**, in the
  directory §16's resume protocol sends every session to read.

---

## 7. Two honesty guards passed while being wrong

Found by review, not CI. Both are the same shape: *a test asserting more than it established.*

| Probe | Before | After |
|---|---|---|
| visible **lowercase** "Status: connected to your ISAAC workspace" | 25 passed | **RED** |
| a **fabricating seam** returning `{ok: true, record: {status: "complete", …}}` | 25 passed | **RED (4 tests)** |
| change-feed poller set `enabled: false` (feature wholly inert) | 3 mount tests passed, incl. the **anti-loop guarantee** | **1** (the one legitimate negative) |

---

## 8. The engine-parity skips earned their keep

`test_run_row_parity.py` pins the run document's exact key set and is gated on
`ISAAC_RUN_REAL_ENGINE_PARITY`, so all **24** of its tests skip on a developer machine. The
slice adding `changed_at_rev` ran the full `apps/api` suite locally (6,086 passed, 41 skipped)
**and** an independent reviewer ran it — it skipped for both. **Only CI, against a real
PostgreSQL, caught it.**

That is the skip measurement **vindicated**: it called those 29 skips *"not a coverage hole"*
precisely because `ci.yml` sets the flag at four sites and also sets
`ISAAC_REQUIRE_REAL_ENGINE_PARITY`, so an absent engine **fails** rather than skips.

**And a skip count without its checkout is not a measurement:** any backend skip total from a
git **worktree** is `+2` against the main checkout, because `graphify-out/graph.json` is
gitignored and exactly two tests gate on it. This already produced one false "regression".

---

## 9. A cross-slice collision, predicted, sequenced around — and then absent

A3 and the change feed both move `settings-explorer` a11y cells: the Endpoint Explorer renders
from the **live** `/api/openapi`, and the feed's description grew 7 → 9 paragraphs. A3 was
merged first on review evidence.

**The predicted failure never fired** — 0 `IMPROVED` / `FIXED?` / `GREW` / `NEW COLOUR` lines.
The prediction reasoned about **rendered** nodes; the baseline counts **violating** nodes, and
after A3 that token is compliant, so more prose on it adds **zero** failures. Merging A3 first
did not merely avoid stale numbers — it *eliminated* the collision.

---

## 10. Hygiene

Worktrees **23 → 1**. Each of the 22 removals was re-proven immediately beforehand (zero
unique commits, HEAD reachable from a remote ref), not on the strength of an earlier audit.
`server.py.bak` was proven byte-identical to `origin/main` before removal.

**Zero stranded work**, proven by content rather than ancestry: every branch with unique
commits is either on a remote or byte-identical to `main`. The pre-rebase A3 branch was
**renamed** `preserve/a3-pre-rebase-superseded` rather than deleted, after all five of its
files were shown identical to `main`.

The three `preserve/*` branches hold 19 commits (4+13+2), **all present on the remote** — the
`-superseded` suffix is why a *name*-based lookup misses them, and for preservation only the
*commit* question matters.

---

## 11. External gates — the only things left

Nothing below is an agent's act.

**Dean / operator / SLAC** — `0005` approval and any hosted migration application; **G2**
per-record hosted display; **G3** the five withheld aggregates; production remote-MCP routing
and OAuth/IdP configuration; the infrastructure half of trusted identity (the ClusterIP bypass
means edge headers still cannot prove authentication); any production LLM or transcription
endpoint, credential, governance and billing.

**Angel** — Experiment-versus-Run classification and inheritance for `detector_model`,
`monochromator_crystal`, `spectrometer_geometry`, `n_scans`, `proposal_id`, `session_id`.
These block nothing and **must not be guessed**; all six remain `unclassified, verified`.

**Krish or another authenticated human** —
1. **Hosted QA of every image from this session.** `/krish` sits behind an Authentik edge this
   environment cannot authenticate to, and an agent must not enter credentials. Sequence:
   `docs/krish-manual-verification-checklist.md`. Expect `/krish/api/health` `commit` to read
   `31ca1d2` once Flux rolls.
2. **The genuine browser 200%-zoom sign-off.** No CDP method, flag or API can drive it — it is
   not automatable, and the automated proxy is a proxy.
3. **Team Owner review and internal sharing of the ISAAC Assistant artifact**, plus a real
   Team-artifact + remote-MCP authentication test and a real voice+MCP smoke test.
   `docs/isaac-assistant-artifact-operator-checklist.md` opens with **"Do not start"** and
   names the Dean-deferred hard stops.
4. **Personal-deploy retirement** (Vercel `isaac-demo-web` + Railway), preserving the Railway
   volume — pausing preserves data that deleting destroys.

---

## 12. Named rather than implied — still not done

- An apply route for `POST /ingestion/csv/preview` is a **committed human decision, not
  residual work** (reconciliation-only authority boundary).
- `isaac_runs` Stage 2b — gated on the operator's two completeness queries.
- The three ancestor-`opacity` contrast composites (asserted still-open by test).
- The **five** undeclared custom properties in `components/transcriptCapture.css`, a shipped
  ungated panel — pre-existing, two-way ratchet added; repointing them is a visual decision.
- The **client API** for AI-powered / MCP-calling artifacts is undocumented by the vendor, and
  is now the load-bearing gap for the artifact programme.
- No hosted figure of any kind is measured anywhere in this repository.
