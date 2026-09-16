# Settings density — progressive disclosure on Data & Privacy (2026-09-16)

Branch `fix/settings-progressive-disclosure`, based on `d315fca0` (`feat/bl15-foundation`).

**The report that authorized this**, from the project owner, about the hosted app:

> "as of right now at least from what i checked in settings, its still js a wall of text, i
> thought we discussed these fixes as well as the previous ones"

**Why this is authorized now, when it was previously declined.**
[`ISAAC_EXECUTION_LEDGER.md`](../superpowers/plans/ISAAC_EXECUTION_LEDGER.md) (~line 405) records a
deliberate decline of exactly this work, ending *"A future session should not retry this as a layout
task"* and *"If the page is to get shorter it is by the owner deciding which caveats may be
weakened, which is not an engineering call."*

**That decline was correct and is superseded rather than refuted, and its constraint still binds.**
The owner has made the call. But the decline's reasoning is why this change does not shorten
anything: **not one word of copy is edited, merged, shortened or deleted.** The lever used is the one
the decline did not consider — progressive disclosure, which reduces what is *visible by default*
while keeping every sentence present in the DOM and reachable. In-repo precedent and shape:
`UX-021b` (Help, 7 sections → 4 *"by disclosure, not deletion"*, `CLAUDE.md` §11).

---

## 1. Environment, and the two caveats on it

| | |
|---|---|
| Backend | `PYTHONPATH=apps/api ISAAC_UI_WORKSPACE=<fresh tmp> ISAAC_UI_CORS_ORIGINS=http://127.0.0.1:5193,http://localhost:5193 .venv/bin/python -m uvicorn isaac_api.app:create_app --factory --port 8931` |
| Frontend | `VITE_API_BASE=http://127.0.0.1:8931/api node_modules/.bin/vite --port 5193 --strictPort` |
| `/api/about` | `data_regime: synthetic-only`, `persistence: ephemeral`, `record_schema_version: 1.05`, `build_commit: null` |
| Browser | real Chromium via the Chrome automation tooling; every viewport exercised through a **same-origin iframe** |

**CAVEAT 1 — the brief said to leave `VITE_API_BASE` at its default, and I could not.** The default
is `http://127.0.0.1:8000/api` (`src/lib/api.ts:115`) and the dev-server default is port 5173
(`e2e/env.ts`); **both were already held by other live slices' servers**, which I must not disturb.
So the bundle under measurement classifies itself as a *hosted* build (`isHostedBuild =
RAW_BASE !== LOCAL_API_BASE`, `api.ts:139`).

That trap is real and is recorded in the ledger, so here is why it cannot reach these numbers rather
than an assurance that it does not. `isHostedBuild` has exactly five non-test consumers
(`grep -rn isHostedBuild src | grep -v __tests__`): `BackendDown` copy and its `RUN_COMMAND` line,
`SearchDialog`'s copy of the same, the `Build Mode` row inside `DiagnosticsPanel`, and
`ENVIRONMENT_LABEL` in `lib/runtimeContext.ts`. **`grep -rn ENVIRONMENT_LABEL src/screens/SettingsPage.tsx
src/screens/settings/` returns nothing**, and the backend was up throughout, so no `BackendDown`
branch rendered. `PrivacyBody` renders *only* `settingsConcepts(settingsFactsFrom(data))` — strings
from `/api/about` facts — and my backend reports facts identical to the one on port 8000
(both `synthetic-only` / `ephemeral`, checked by `curl`).

**CAVEAT 2 — the two measurement traps the ledger warns about, and which one bit.**
`resize_window` reports success while the rendered viewport does not follow, so **every** figure
below comes from a same-origin iframe sized exactly; that trap affected nothing because it was
avoided from the start. The hidden-tab trap (`document.visibilityState === "hidden"` in every driven
tab, so CSS transitions do not advance) **did** apply, and it is why no number here is a transition
end-state: the only animated property involved is the summary's hover colour, which is not measured.
Change-feed-driven updates never fire in a driven tab either; no measurement here depends on one.

**CAVEAT 3 — a divergence from the figures in my brief, resolved.** The brief quoted
`settingsConcepts()` "total `detail` prose: 6,712 characters" and "3 of the 12 have a `more`
disclosure". Measured by evaluating the real module through esbuild and by the browser, both
independently: **detail total 8,577 chars and 4 `more` disclosures**. The per-card figures agree with
the browser exactly (794 / 936 / 734 / 614 / 981 / 1469 / 513 / 667 / 272 / 366 / 223 / 1008), so the
higher number is the right one. The likely cause of the brief's figure is a different `persistence`
value: `what-resets` and `how-long-it-is-kept` branch on it.

---

## 2. Before / after — rendered, per tab, at both widths

Method, identically before and after: `document.documentElement.scrollHeight`; prose = `innerText`
of every `<p>`/`<li>` that contains no nested `<p>`/`<li>` and is non-empty; `details` = total
`<details>` on the surface / how many were `open`. **Every `<details>` was CLOSED in both readings**,
so "prose" is visible characters in both columns.

### The surface the owner was describing — `settings?tab=privacy`

| | before | after | change |
|---|---:|---:|---:|
| `scrollHeight` @ 1280×900 | **2252** | **900** | **−60.0%** — fits the viewport, no scroll |
| `scrollHeight` @ 375×812 | **6003** | **1453** | **−75.8%** — 7.4 viewports → 1.8 |
| visible prose chars | **8746** | **169** | −98.1% |
| visible prose nodes | 14 | 2 | |
| paragraphs > 400 chars | **9** | **0** | |
| longest paragraph | **1469** | 91 | |
| `<details>` (total / open) | 4 / 0 | 16 / 0 | +12, one per concept |

The 169 remaining characters are the card's own subtitle and the Governance link — not a definition.

**Independent agreement with the orchestrator's hosted reading** (1510×828, commit `108ba4e4`,
i.e. current `main`): it measured privacy `scrollHeight` 2066, longest 1469, 9 of 14 paragraphs over
400. My 1280×900 pre-change reading gives 2252 / 1469 / 9 of 14. The `longest` and the
over-400 count match exactly; `scrollHeight` differs by viewport width as expected. Its prose total
was 9681 against my 8746 — consistent with hosted reporting `persistence: durable` where mine
reports `ephemeral`, which changes two `detail` strings.

### Every other tab, measured at 1280×900 (before == after; none was changed)

| surface | `scrollHeight` | prose | nodes | >400 | longest | `<details>` |
|---|---:|---:|---:|---:|---:|---:|
| `settings?tab=overview` | 1401 | 427 | 3 | 0 | 184 | 0 |
| `settings?tab=about` | 900 | 903 | 6 | 0 | 286 | 1 |
| `settings?tab=help` | 900 | 1647 | 5 | 1 | 876 | 0 |
| `settings?tab=api` | 1348 | 610 | 6 | 0 | 261 | 3 |
| `settings?tab=explorer` | 1949 | 10040 | 101 | 2 | 1295 | 2 |
| `settings?tab=mcp` | 1409 | 3065 | 13 | 0 | 360 | 4 |
| `governance?tab=policy` | 900 | 1426 | 4 | 1 | 542 | 0 |

### Per-concept detail lengths (unchanged — this is the proof nothing was shortened)

`synthetic-data-only` 794 · `no-real-experiment-data` 936 · `what-is-stored` 734 ·
`what-resets` 614 · `how-long-it-is-kept` 981 · `reset-and-deletion` **1469** ·
`export-handling` 513 · `no-telemetry` 667 · `no-external-model-calls` 272 ·
`project-memory-boundary` 366 · `record-truth-boundary` 223 · `authentication-boundary` 1008.
**Total 8,577.** Opening `Reset and Deletion` in the browser after the change returned exactly
**1469** characters beginning *"Deliberate removal is narrow in this build. Reset Worked Exa…"*.

---

## 3. What was done

**Each concept is a native `<details class="settings-concept">` inside its existing `<li>`, whose
`<summary>` carries the concept's `heading` and nothing else.** The full `detail` is inside,
verbatim; the existing `more` drawer stays nested inside, unchanged.

**The `<summary>`-is-a-topic rule is the entire safety argument, and it is enforced mechanically.**
`PrivacyBody`'s doc comment previously stated *"Secondary edge cases sit behind a native `<details>`
— never an honesty caveat, which would let the visible copy overstate what the code checks."* That
rule is right, is unchanged, and this change does not meet it: a heading is a **topic**, not an
assertion, so shutting a row leaves no claim standing unqualified. The doc comment now records the
distinction explicitly so a future session does not read this as a reversal.

**The concrete reason it must be the heading and never `concept.summary`** — stated in the code and
in the tests, because it is one edit away: `no-telemetry.summary` reads *"This application measures
and transmits nothing about your session"*, while its `detail` carries the server-log, access-log and
identity-gateway scope that stops exactly that sentence from overstating the code. Promoting the
summary into the `<summary>` would restore that retracted overstatement behind a shut drawer.

Two new tests in `src/__tests__/settings-page.test.tsx`:

1. `gives every concept a disclosure whose summary is the heading and nothing else` — one row per
   concept in order, all collapsed, `summary.textContent` **exactly equal** to `concept.heading`
   (not `toContain`, which a summary carrying a trailing claim would satisfy), the `<h3>` preserved,
   and `row > p`'s text exactly equal to `concept.detail`.
2. `never promotes a concept summary line into a disclosure summary` — over **every** `<summary>` on
   the tab (both layers), asserted as a set difference so an entirely new summary also fails, plus an
   explicit ban on each `concept.summary` string.

**Mutation check, as required.** Promoting `concept.summary` into the `<summary>`:

```
× gives every concept a disclosure whose summary is the heading and nothing else
  → expected 'Synthetic-Only Mode Synthetic-only mo…' to be 'Synthetic-Only Mode'
× never promotes a concept summary line into a disclosure summary
  → expected [ …(12) ] to deeply equal []
```

plus **12 pre-existing** `… — summary is rendered exactly once` guards fired (`rendered 2x — per
surface [Overview:1, Data & Privacy:1, …]`). Reverted; `settings-page.test.tsx` → 142 passed.

---

## 4. The finding that changed the plan: the a11y sweep has a mechanism for this, and my brief was wrong about it

My brief said: *"The a11y sweep does not scan inside a closed `<details>` … So a cell count that
drops because content is now hidden is **not** an accessibility improvement; say so plainly in your
report rather than claiming a win."*

**The first clause is true. The conclusion is not the right one, because the repository already has a
mechanism built for exactly this and the honest fix is to use it rather than to disclaim it.**
`e2e/helpers/openUnreachableDisclosures` exists to open every disclosure no `SURFACES` entry can
reach, and its own header states the rule:

> "a baseline number that drops because content is now hidden is a COVERAGE LOSS, not an
> accessibility win"

**`details.settings-concept` was not in its selector list**, so shipping without touching it would
have taken twelve paragraphs out of every axe scan at every viewport. And it would have been
*invisible*: `settings-privacy` has **no `A11Y_BASELINE` cell at all** (`grep -nE
"^\s+'settings-privacy@" e2e/a11y-baseline.ts` → no output; the only live settings cells are the
seven `settings-explorer@*`), i.e. zero violating nodes, so the loss could not even show up as a
number moving. That is precisely the Statistics `Technical Details` defect the helper's header
describes, at twelve times the size.

So `SETTINGS_CONCEPT_DISCLOSURES = { 'settings-privacy': 12 }` was added and the rows are opened and
asserted open, following `PROSE_DISCLOSURES`' exact-count pattern (the count is a property of the
app's own content module, not of a record under test, so a thirteenth concept names itself here).

**Consequence, which is the strongest available outcome: the scanned DOM is identical to before, so
NO baseline cell moves and `e2e/a11y-baseline.ts` is not edited at all.** Measured:

```
playwright test e2e/specs/a11y-axe.spec.ts --grep "a11y scan: Settings — Data & Privacy"
  → 5 passed  (desktop-1280x800, laptop-1024x768, tablet-768x1024, mobile-375x812, zoom-200)
playwright test e2e/specs/a11y-narrow.spec.ts --grep "Data & Privacy"
  → 2 passed (320px, 390px), 8 skipped by design (the narrow sweep runs on the desktop project only)
```

**There is therefore no darwin/linux transcription and nothing is carried forward.** The brief asked
me to mark the linux half `DARWIN_CARRIED_FORWARD` rather than invent it; that instruction does not
apply, because **no cell was added, deleted or changed** — `A11Y_BASELINE_TOTAL_NODES` and
`DARWIN_CARRIED_FORWARD` (`[]`) are untouched. The honest limit remains: **this was a darwin run and
CI (linux) is the authority.** What a linux run has to reproduce is "still zero violations on this
surface", not a transcribed number.

Also run, because the change touches CSS and DOM structure on a scanned surface:

```
playwright test layout-widths.spec.ts wide-prose.spec.ts pill-shape.spec.ts keyboard.spec.ts
  → 131 passed, 332 skipped, exit 0
playwright test visual-sweep.spec.ts self-check.spec.ts
  → 34 passed, 56 skipped, exit 0   (captured 30/30 distinct images at 320px and at 375px)
```

---

## 5. A guard caught a real defect in my own CSS

The first version added `padding: 1px 0` to the summary. `src/__tests__/type-scale-and-spacing.test.ts`
(`UX-001 · spacing literals do not grow`) failed:

```
spacing: 2401 raw literals, recorded ceiling 2400.
```

The axis counts every hand-authored length in `padding|margin|gap|row-gap|column-gap`
(`scanSpacing`, `:157`), and `1px` was the +1. Following the guard's own remedy, the literal was
**removed** rather than the ceiling raised: the row is already a full-card-width target (measured
**453 × 22** at 1280) inside `.settings-points > li`'s own 11px/13px padding, so it bought nothing
the card had not already paid for. The reason is recorded at the site. Re-run: 205 passed across the
four style guards.

That removal is also why the narrow `scrollHeight` reads 1453 rather than the 1477 measured with the
padding — 12 rows × 2px = 24px, and 1477 − 24 = 1453 exactly.

---

## 6. Decisions taken, and decisions declined

| Decision | Outcome | The measurement behind it |
|---|---|---|
| Each concept behind a native `<details>`, summary = heading only | **TAKEN** | 2252→900 px at 1280×900; 6003→1453 at 375×812; 9→0 paragraphs over 400 |
| Open some rows by default | **DECLINED** | The tab already fits one viewport (900 px = exactly the 900 px viewport) with every row shut, so no row needs opening for the page to read as populated. Opening a subset would rank twelve privacy facts against one another — a judgement no measurement here supports — and the two likeliest candidates are carried elsewhere anyway (the mode chip's accessible name; `ASSISTANT_NO_MODEL_CLAIM` in the Assistant dock, `CLAUDE.md` §11). The marker, the pointer cursor and the hover tint are what signal that a row opens; screenshot confirms all twelve triangles render. |
| Group the 12 into 3–4 headings | **DECLINED** | Density does not need it: twelve collapsed rows render as **six** grid rows (`grid-template-columns` measured `453px 453px`) inside one viewport. And it costs something real — a group tier would push each concept heading `h3`→`h4`, moving twelve accessible names and the surface's heading order, on a surface currently recording **zero** axe violations. Structure for no measured gain, against a measured risk. |
| Restructure `GovernancePage` → Policy | **DECLINED — and I re-measured it myself rather than taking either number on faith** | My brief said Policy is "4 `<p>` tags holding 6,104 characters with zero disclosures" and that "it should" get this treatment; the orchestrator then retracted that as a *source-file* count that had swept in other tabs' copy. **My own rendered measurement agrees with the retraction:** `governance?tab=policy` is **1,426 chars in 4 nodes, `scrollHeight` 900 at 1280×900 — exactly the viewport, no scroll — and 1,325 at 375×812**, longest paragraph 542. It is not a wall of text. Declining is also the safer outcome: `CLAUDE.md` §11 records three separate occasions where a Governance claim was false because it was stated without its scope, so splitting a sentence there is honesty-critical work that needs its own slice and its own reason. |
| `ApiDocs.tsx` (the densest file by source chars) | **DECLINED, and the premise was wrong** | The brief's 22,224 figure is source characters, not rendered prose. Rendered: `?tab=api` is **610** chars; `?tab=explorer` is 10,040 chars across **101** nodes, and its only two paragraphs over 400 are `p.api-docs-description` — **server-supplied OpenAPI operation descriptions rendered verbatim** (544 and 1,295 chars, on `persistence` / `unavailable`). They live in `apps/api`, which this slice must not touch, and the explorer is master-detail so at most one shows at a time. |
| `ConnectYourAgent` / `AssistantCompanion` / `ApiKeys` | **DECLINED** | `?tab=mcp` = 3,065 chars in 13 nodes, **0** over 400, already 4 disclosures. `?tab=api` = 610 chars, 3 disclosures. Neither is dense. |

---

## 7. No sentence of copy changed — how that was verified mechanically

Three independent checks:

1. **`git diff --exit-code -- apps/web/src/lib/settingsContent.ts` exits 0.** Every Data & Privacy
   string lives in that module and it is **byte-identical**.
2. **The whole non-comment diff of `SettingsPage.tsx` contains no string literal** — added or
   removed. It is one `<details>`/`<summary>` wrapper plus re-indentation of the same four
   expressions (`concept.heading`, `concept.detail`, `concept.more.label`, `concept.more.text`):
   ```
   git diff -U0 -- apps/web/src/screens/SettingsPage.tsx | grep -E '^[+-]' \
     | grep -vE '^(\+\+\+|---)' | grep -vE '^[+-]\s*(\*|//|/\*|\{/\*)' | grep -vE '^[+-]\s*$'
   ```
   There is no literal privacy copy in the component at all; it is entirely interpolation.
3. **A committed test now asserts it per concept**: `row > p`'s `textContent` must equal
   `concept.detail` exactly, and each `<summary>` must equal `concept.heading` exactly.

**A false claim found and left alone, as instructed:** none. I read all twelve `detail` strings and
the four `more` strings while measuring them and found nothing I could show to be false; every
scope-limiting clause the ledger describes (the `no-telemetry` server-log/access-log/identity-gateway
scope, `no-real-experiment-data`'s "nothing in the app inspects that text to judge whether it is
real", `authentication-boundary`'s "no way to report whether either restriction is active") is
present and intact, and all three are still in the always-visible `detail` rather than behind the
inner `more` drawer — the existing guard that pins that passed unchanged.

---

## 8. Verification

| Check | Command | Result |
|---|---|---|
| Frontend suite | `cd apps/web && node_modules/.bin/vitest run` | **235 files / 6106 tests passed**, exit 0 |
| Typecheck (**after** adding tests) | `cd apps/web && node_modules/.bin/tsc -b` | exit **0** |
| Targeted claim-parity | `vitest run settings-page upload-claim-parity db-recon-truthfulness help-claim-parity assistant-model-claim-parity governance-tabs settings-api` | **7 files / 760 tests passed** |
| Style guards | `vitest run type-scale-and-spacing palette-contrast interaction-states settings-page` | **4 files / 205 passed**, exit 0 |
| a11y, 5 viewports | `playwright test a11y-axe --grep "Settings — Data & Privacy"` | **5 passed** |
| a11y, 320/390 | `playwright test a11y-narrow --grep "Data & Privacy"` | **2 passed**, 8 skipped by design |
| Layout / prose / pill / keyboard | `playwright test layout-widths wide-prose pill-shape keyboard` | **131 passed**, exit 0 |
| Visual sweep | `playwright test visual-sweep self-check` | **34 passed**, exit 0 |

**Frontend test count: 6,104 → 6,106** (235 files, unchanged). Derived mechanically rather than
asserted — the diff adds exactly 2 `it(` blocks and removes 0
(`git diff -- …/settings-page.test.tsx | grep -cE '^\+  it\('` → 2; the `-` form → 0), and
`settings-page.test.tsx` went 140 → 142.

**Backend: not run, and not affected.** No file under `apps/api/`, `src/isaac_records/` or `schema/`
was touched. Truth / export / validation paths: **untouched**.

**`vitest` and Playwright were never run concurrently** — the ledger records a concurrent run
producing 26 failures of which 15 were pure contention.

---

## 9. Snapshot preflight

**`apps/web/src/screens/SettingsPage.tsx` IS in the served-content manifest, so the snapshot needs
regenerating.** Drift proven without invoking the generator, by re-hashing the one file:

```
recorded: c26c4b5aea67302a8d83edf3c3021f48064c07980043d2ddb4830a6554cd4aa2
live    : 4934783a8016aa4d1dc729da408e3ced025fb6f8c6d086f7810d8ceb1d34f0c0   → DRIFT
```

The other four changed files are **not** manifest-listed (`screens.css`, `settings-page.test.tsx`,
`e2e/helpers/disclosures.ts`; and `settingsContent.ts` is unchanged anyway). Manifest total: 200.
Regeneration is the orchestrator's step, with `--detail-out` as §17 requires.

---

## 10. Step 4 residue — the "previous ones"

The owner said *"as well as the previous ones"*, so every primary screen and every Settings tab was
swept for the same pattern. **Fixed in this slice: Settings → Data & Privacy only.** Ranked by
`scrollHeight` at 1280×900, after this change:

| # | surface | `scrollHeight` 1280×900 | prose | nodes | >400 | longest | `<details>` | verdict |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | `statistics?tab=build` | **5129** (**9260** @375) | **6048** | 55 | 2 | 436 | 9 | **THE REAL RESIDUE.** 5.7 viewports at desktop, **11.4 at 375px** — now the densest surface in the app. It already carries 9 disclosures, so it is partially disclosed and still this tall. Note it is the ONE surface where this fix interacts with a11y coverage: `PROSE_DISCLOSURES` declares `statistics-build: 4`, so four of those nine are already force-opened by the axe sweep, and any new disclosure there must be declared in the same change. |
| 2 | `settings?tab=explorer` | 1949 | 10040 | 101 | 2 | **1295** | 2 | **Leave.** Generated: 101 short nodes from the live `/api/openapi`, and both >400 paragraphs are server-supplied `p.api-docs-description`. Shortening means editing backend docstrings in `apps/api` — a different slice, different owner. |
| 3 | `statistics` (Overview) | 1752 | 1956 | 22 | 0 | 270 | 0 | Cards and figures, not prose. No action. |
| 4 | `settings?tab=mcp` | 1409 | 3065 | 13 | 0 | 360 | 4 | Already disclosed; no paragraph over 400. No action. |
| 5 | `settings?tab=overview` | 1401 | **427** | 3 | 0 | 184 | 0 | **MEASURED AND NOT NEEDED.** Tall because of cards and controls; 427 characters of prose is not a wall of text. |
| 6 | `statistics?tab=mine` | 1362 | 2826 | 25 | 0 | 339 | 0 | 25 short nodes. No action. |
| 7 | `settings?tab=api` | 1348 | 610 | 6 | 0 | 261 | 3 | No action. |
| 8 | `governance?tab=schema` | 1061 | 8028 | **279** | **0** | 343 | 0 | Generated schema reference — 279 nodes, none over 400. No action. |
| 9 | `memory` | 926 | 1326 | 9 | 0 | 343 | 0 | No action. |
| 10 | `experiments` | 917 | 947 | 8 | 0 | 207 | 0 | No action. |
| 11 | **`settings?tab=privacy`** | **900** | **169** | 2 | 0 | 91 | 16 | **FIXED HERE.** Was 2252 / 8746 / 9 over 400. |
| 12 | `settings?tab=help` | 900 | 1647 | 5 | **1** | **876** | 0 | **Candidate, small.** One 876-char paragraph. Note `UX-021b` already restructured the Help *popover* by disclosure; this is the *tab*, a different surface. **And it is scanned by no axe surface at all** — `grep -nE "id: 'settings" e2e/surfaces.ts` yields `settings`, `settings-privacy`, `settings-about`, `settings-api`, `settings-explorer`, `settings-connect`, and `grep -n "tab=help" e2e/surfaces.ts` returns nothing. (An earlier draft of this doc asserted the opposite; corrected here by measurement.) So a disclosure here would move no a11y number — which is a reason to add the surface, not a reason to skip the declaration. |
| 13 | `governance?tab=policy` | 900 | 1426 | 4 | 1 | 542 | 0 | **MEASURED AND DECLINED** — see §6. Fits one viewport; my brief's 6,104 was a source count. |
| 14 | `settings?tab=about` | 900 | 903 | 6 | 0 | 286 | 1 | **MEASURED AND NOT NEEDED.** |
| 15 | `load` | 900 | 1280 | 3 | **2** | **649** | 0 | **Candidate, small.** Two paragraphs over 400 in only 3 nodes — the highest >400 *density* on any surface, but it fits one viewport. |
| 16 | `governance?tab=validator` | 900 | 369 | 4 | 0 | 180 | 1 | No action. |
| 17 | `imports` | 900 | 407 | 3 | 0 | 263 | 1 | No action. |

**Not measured, and named rather than implied:** the four record workspaces
(`?view=fields|runs|capture|graph`), `record/:id/complete`, `/evidence` and `/export`. They need a
record, which this iframe harness does not create, and the ledger's own rule is that a count I did
not measure is not a count I may report. A record-screen sweep needs the worked-example fixture and
is its own slice.

**Recommended next target: `statistics?tab=build`** — it is now the app's densest surface by a wide
margin (9,260 px at 375px), it is the only one over two viewports, and it has an existing disclosure
pattern (`details.stats-disclosure`) and an existing declared-count entry to extend, so the shape is
already established. `load` and `settings?tab=help` are one-paragraph fixes after that.
