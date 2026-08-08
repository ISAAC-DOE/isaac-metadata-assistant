# Poster-ready evidence — two results

Numbers below were recomputed from committed artifacts in this session, not quoted from prose.

---

## A. Authorized private verification

**Not "privacy mode."** The correct name is **authorized private verification mode**: a bounded
diagnostic path that reads the authorized 30-record production-derived corpus and returns only
sanitized aggregate results. It is not a user-facing toggle and must never be described as one.

### Poster paragraph (~70 words)

> ISAAC's validation and mutation-oracle engine was run against 30 authorized production-derived
> records. All 30 passed official schema validation and all 30 passed shadow validation. 755
> mutation operators produced 22,650 trials; 9,136 were applicable, of which 7,021 behaved as
> expected, 2,115 were observation-only, and **0 were unexpected**. All seven oracle categories
> returned zero. The database transaction was server-confirmed read-only with zero DML and zero
> DDL. A second, independent run differed in 0 of 50 deterministic fields.

### Figures suitable for display

| Quantity | Value |
|---|---|
| Records | 30 |
| Official validation | 30 pass / 0 fail |
| Shadow validation | 30 pass / 0 fail |
| Mutation operators | 755 |
| Trials attempted | 22,650 |
| Applicable | 9,136 |
| Skipped | 13,514 |
| Expected | 7,021 |
| **Unexpected** | **0** |
| Observation-only | 2,115 |
| Oracle categories firing | 0 of 7 |
| DML / DDL statements | 0 / 0 |
| Deterministic rerun | 0 differences across 50 fields |

Accounting closes exactly: `9,136 + 13,514 = 22,650` · `7,021 + 0 + 2,115 = 9,136` · `755 × 30 = 22,650`.

### Caption

> 30 authorized production-derived records, 22,650 mutation trials, zero unexpected outcomes, on a
> server-confirmed read-only connection emitting aggregate results only.

### What the poster must NOT say

- **Do not claim an independent source-row re-read.** None happened. The honest form: *no source
  writes were possible or observed — the transaction was server-confirmed read-only, DML and DDL
  counts were zero, and mutation operators acted on in-memory deep copies. Source-row equality was
  not independently re-read after execution.*
- **Do not imply `_leak_scan` ran.** It did not; a different check did (see below).
- **Do not present the figures as captured artifacts.** They are operator-relayed from an
  authenticated session. That is testimony, not an inspected response body.

---

## B. The Graphify experiment — hypothesis → benchmark → decision

This is the more interesting poster result *because* the outcome was not the one expected.

### Poster paragraph (~75 words)

> ISAAC initially adopted a repository knowledge graph as a semantic navigation aid, on the
> hypothesis that it would reduce repository-navigation overhead. A controlled benchmark — 8 frozen
> tasks, 2 arms, 32 runs — measured the opposite of a clean win: graph assistance reduced files
> opened (−15.8%) and dead ends (−33.3%), but increased tool calls (+5.7%) and total tokens (+4.2%)
> with no consistent correctness gain. On that evidence the graph was demoted from a default
> reasoning tool to an optional semantic discovery layer; deterministic source inspection remained
> the truth path.

### Three-stage mini-figure

```
┌── 1. HYPOTHESIS ─────────┐   ┌── 2. MEASURED ───────────┐   ┌── 3. DECISION ───────────┐
│                          │   │  files opened    −15.8%  │   │  Demoted to OPTIONAL      │
│  A semantic repository   │   │  dead ends       −33.3%  │   │  semantic exploration.    │
│  graph should reduce     │──▶│  ─────────────────────── │──▶│                           │
│  navigation overhead.    │   │  tool calls      +5.7%   │   │  Deterministic tools stay │
│                          │   │  total tokens    +4.2%   │   │  the truth path.          │
│                          │   │  correctness   no gain   │   │                           │
└──────────────────────────┘   └──────────────────────────┘   └──────────────────────────┘
        expected                    8 tasks · 2 arms · 32 runs         evidence-driven
```

Keep the eight per-category verdicts OFF the poster. They belong in supporting documentation.

### Caption

> A negative result, kept. The graph made navigation *narrower* but not *cheaper*, so it stopped
> being the default and became an option.

### Honest framing rules

- Not "Graphify failed." Two metrics moved in its favour.
- Not "Graphify made everything more efficient." Total effort rose.
- **Do not overstate significance.** Two repeats per task per arm. No confidence interval or
  significance test was computed and none is claimed. Percentage deltas on small-integer medians
  (dead ends 1.5 → 1.0) are shown for comparability only.
- Self-rating across 16 graph-arm runs: 13 "partly", 3 "no", **0 "yes"**.
- Wall-clock was excluded as contaminated (16 concurrent agents, CPU contention). The excluded
  figure was **unfavourable** to the graph (median 154.9 s → 218.4 s, +41%), so the exclusion is
  conservative, not selective — say so if the number is mentioned at all.

### The routing rule this produced

| Use deterministic tools first | Graph is optional for |
|---|---|
| exact strings · completeness audits · stale-phrase audits · exact callers/symbols · test truth · runtime truth · schema truth · security completeness · configuration truth | semantic orientation · conceptual neighbourhoods · cross-document discovery · early exploration in an unfamiliar subsystem |

> The graph returns **leads**. Files and tests remain the source of truth.

---

## C. The distinction the poster must keep separate

**Graphify (developer/agent repository-analysis tooling)** and **the visual graph an ISAAC
scientist sees** are two different products. The benchmark says nothing about the second.

Worth stating on the poster or in the talk track, because it is a genuine finding in its own
right: the graph that was being shown to scientists was a graph of **the repository** — its 220
nodes were 201 source-file paths plus 19 documentation concepts, the first of them
`.claude/skills/isaac-complete/SKILL.md`, `.github/workflows/ci.yml`, `CLAUDE.md` — wired by
`imports` and `calls`. 121 of the file nodes were code. Zero were scientific records. The
replacement is scoped to one experiment and built only from record, schema, evidence and
provenance relationships.
