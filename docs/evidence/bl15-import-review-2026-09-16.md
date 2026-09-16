# BL15R-012 — the large-corpus Historical Import review surface (2026-09-16)

Branch `feat/bl15-import-review`, based on **`1a4ca90a`** (`origin/feat/bl15-foundation`).

---

## 0. A correction to the setup instruction, made before any code was written

I was told to branch off `origin/main` because *"several BL15 contracts have landed"*. **They have
not landed on `main`.** Measured:

```
git ls-tree origin/main --name-only apps/api/isaac_api/bl15/     -> (empty)
git ls-tree origin/main --name-only docs/ | grep -i bl15         -> only bl15-2-data-request-2026-09-12.md
git log --oneline -1 origin/feat/bl15-foundation                 -> 1a4ca90a
git rev-list --count d315fca0..origin/feat/bl15-foundation       -> 6
```

Every artifact I was told to read first — `relate.py`, `mapping.py`, the integration design and the
corpus characterization — exists **only** on `origin/feat/bl15-foundation`, which is **6 commits
ahead of `d315fca0`** (the Settings base). Branching off `main` would have left me with no data
contract at all, and the brief forbids inventing a field.

So this branch is based on `1a4ca90a`. The instruction's *real* constraint — **"do not build on top
of the Settings commit"** — is satisfied and checked mechanically:
`git merge-base --is-ancestor 2a813c6a HEAD` **exits non-zero**, so `2a813c6a` is not in this
history.

---

## 1. The finding that shaped the whole surface

**`MeasurementUnit` carries no scientific value, and a committed test forbids adding one.**

`apps/api/tests/test_bl15_relate.py::test_nothing_in_the_output_carries_a_scientific_value` pins the
exact 17-key set of `MeasurementUnit.to_state()`, and its docstring says why:

> *"the tempting next step is to hang a parsed potential off a unit, and that would put an unmapped
> value one step from a record with no registry between."*

The requested table is `Legacy # | Sample | Medium | State | Filter | Potential | Scans | Sources |
Status`. **Five of those nine columns are not on a unit and cannot be put there.** They live in
`SourceEvidence`, keyed by `measurement_stem` + `concept`, so the surface joins them
(`readingsByStem` / `cellFor`). The join yields **zero, one, or many** readings per concept and all
three are real states the table tells apart — *many* is what a disagreement looks like before
anything adjudicates it. `§1` of the test suite asserts both halves: the unit key set, and that the
evidence really does carry the values, so the join is not vacuous.

---

## 2. Contract fields I found insufficient — named, not invented

| # | What a surface needs | What the contract has | What I did |
|---|---|---|---|
| **G-1** | A per-file manifest under disclosure | **`ArchiveInventory.to_state()` omits `entries` entirely** — it serialises `entry_count` and nothing else per file | Rendered **no** manifest, and **stated the absence** in copy rather than implying a list is one click away. What *is* disclosed in full is the complete `unattached` and `refused` lists — the "what was left out" half that `Relationships`' own docstring calls *"as load-bearing as `units`"*. |
| **G-2** | Counts **by source type** for the digest ("scan exports, macros, text sources, processed spectra, documentation") | `SourceRecord` has **no `source_type`** (classification is `bl15.classify`, which does not exist yet), and `ArchiveInventory.to_state()` carries no breakdown | Derived every count from what the payload *does* expose — `units[].scan_count`, distinct `declared_by[].macro_path`, `processed_products`, `note_rows`, and `unattached[].source_type` (a real field). The digest is 15 rows, each carrying the expression it came from. Two categories the brief named — "text sources" and "documentation" as archive-wide counts — are **not derivable** and are therefore **not shown**; they appear only where `unattached` names them. |
| **G-3** | Group per-measurement **candidates** by the registry's five statuses | **`SemanticCandidate.to_state()` carries no `concept` and no `status`** — only `target_field_path`, which is `null` for every one of the 24 `not_expressible` concepts and so cannot distinguish them. **Re-checked against `reconstruct.py`, which landed mid-slice: still true** — `_candidate_state` (`:487`) emits the same 12 keys and adds neither | The mapping review groups **the registry** (corpus-level), which is exactly what the 6/14/24/1-of-45 breakdown describes and needs no per-candidate join. **But see §11: two indirect routes now exist and G-3 is narrower than this row says.** |
| **G-4** | A container grouping the five payloads | None exists — no route emits one | `Bl15CorpusReview` is declared as **the one shape in this slice that is a proposal rather than a mirror**, and it is nothing but the union of committed `to_state()` outputs, so a route can satisfy it by serialising objects it already builds. Said plainly in the module header. |

**Nothing else was missing.** Every other field the surface renders is a verbatim member of a
committed `to_state()`.

---

## 3. What was built

| File | |
|---|---|
| `apps/web/src/lib/bl15Review.ts` | **new** — wire types mirroring each `to_state()` by name, plus every derivation (`corpusDigest`, `readingsByStem`, `cellFor`, `unitState`, `conflictsByKind`, `unattachedByType`) |
| `apps/web/src/lib/bl15ReviewContent.ts` | **new** — only the copy this surface authors: column headings, category names, screen furniture |
| `apps/web/src/components/ImportCorpusReview.tsx` | **new** — the surface |
| `apps/web/src/screens/bl15-review.css` | **new** |
| `apps/web/src/__tests__/bl15-import-review.test.tsx` | **new** — 43 tests in 12 sections |
| `apps/web/src/__tests__/fixtures/bl15-corpus-review.json` | **new** — generated by the real Python contract |
| `apps/web/src/screens/HistoricalImport.tsx` | mounted, conditional on the payload |
| `apps/web/src/lib/types.ts` | optional `corpus_review` on `ApiImportSession` |
| `apps/web/e2e/helpers/disclosures.ts` | `BL15_REVIEW_DISCLOSURES` registered |

**The fixture is generated, not hand-written**, and that is the load-bearing choice. It was produced
by calling `relate()`, `ArchiveInventory.to_state()`, `SourceEvidence.to_state()` and
`coverage()`/`MAPPINGS` in Python. A hand-authored payload shares its typos with the component that
reads it; a generated one cannot. It reproduces the real archive's anomalies at 1/30 scale: a
**three-reading** `internal_declaration_vs_filename` conflict, a duplicated legacy number, a macro
target never acquired, a **zero-scan** measurement, two units that are **not** run candidates, a
`group_token: null` bucket, and beamtime documentation attached to nothing. Every name is
unmistakably fake (`ZZ1`, `ZZ2`, `ZZOxide`) per `CLAUDE.md` §6.

### The digest, not a manifest

`HIST-004` bans `Upload → Spinner → Mysterious JSON`; a 1,192-row table is its sibling. The archive
opens as **15 collapsed derived counts** in a 4-column grid, each disclosing the expression it came
from — because `CLAUDE.md` §11 records four surfaces that shipped a number they had not derived from
what they claimed to describe.

### `source_count`, never `scans + 1`

Measured on the fixture: the unit `03_01_ZZ1_…` has **3 scans and `source_count` 7** (acquisition + 3
scans + 1 macro + 1 processed product + 1 note row), where `scans.length + 1` gives **4**. Summed
over the fixture the two expressions give **14 against 22**. The table renders `source_count`, and
the mutation below proves the test can tell.

### No "Ready", and no progress bar — either would be a promise the build cannot keep

The integration design §5 establishes that a candidate Run from this corpus **cannot** be
export-ready. So the four unit states name what was **observed** — `Values read`, `Sources
disagree`, `No values read`, `Alignment or standard` — and there is no `ready`. `§8` asserts the
string `Ready` appears nowhere in the rendered output, and that `unitState` can only return those
four.

Likewise no bar over "fields mapped": 6 of 45 proposable would read as **87% failure** when 24 of
those are a correct description of the official schema's coverage and 14 are a question for a domain
owner. `§7` asserts there is no `<progress>`, no `role="progressbar"`, and no `%` anywhere.

### Registry coverage, measured rather than quoted

```
PYTHONPATH=apps/api .venv/bin/python -c "from isaac_api.bl15 import mapping as m; print(m.coverage())"
-> deterministic 2, normalized 4, needs_domain_review 14, not_expressible 24, blocked_by_build 1,
   examined 45, not_examined 0, concepts_total 45
```

2+4 = **6** proposable, and 2+4+14+24+1 = 45 exactly. The brief's figures are confirmed.
`registry_paths_exist()` returns `()` — every registry path exists in the vendored schema.

### Conflicts: three readings, the server's words, no winner

`ConflictView` maps over `readings` with no assumption of two. Every `Conflict.explanation` is
rendered **verbatim** — `§6` asserts it for all seven conflicts in the fixture — and the surface
neither paraphrases it nor writes its own. `unresolved_reason` (`sources_disagree`) is surfaced, and
`§6` bans "most likely", "best match", "recommended value" and "we chose".

---

## 4. Rendered measurements — a real Chromium, both widths

No before/after: this is a new surface. Measured through a **same-origin iframe** sized exactly
(the `resize_window` trap), against a throwaway probe entry serving the generated fixture, which was
**deleted after measuring** (`apps/web/bl15-probe.html`, `src/bl15-probe-entry.tsx` — both gone; the
tree shows 3 modified + 6 new files and neither probe file).

| | 1280×900 | 375×812 |
|---|---:|---:|
| `scrollHeight` | **3,316** (3.7 viewports) | **5,508** (6.8 viewports) |
| visible prose chars | 6,358 | 6,358 |
| prose nodes | 153 | 153 |
| **paragraphs > 400 chars** | **0** | **0** |
| longest single block | **251** | **251** |
| `<details>` total / open | 30 / **0** | 30 / **0** |
| table rows | 8 | 8 |
| conflict blocks | 7 | 7 |
| table scrolls inside its own box | no (fits) | **yes (by design)** |
| **page overflows horizontally** | **no** | **no** |

**Zero paragraphs over 400 characters and a longest block of 251** is the number that matters
against the owner's Settings complaint: this surface has no wall of text at any width, and nine
columns at 375px scroll **inside the table's own box** rather than pushing the page sideways.
Dropping columns at a breakpoint was rejected: it would hide a scientific value at exactly the width
a scientist is most likely to be holding a phone at a beamline.

### Per-section heights at 1280 (measured)

| block | height |
|---|---:|
| What This Archive Contains (15 collapsed rows, 4 columns) | 292 |
| What Cannot Be Finished Here (collapsed) | **38** |
| Measurements by Sample (8 units, 4 groups, search + 5 filters) | 1,093 |
| **Where Sources Disagree (7 conflicts, always visible)** | **1,501** |
| What the Official Schema Can Take (5 collapsed statuses) | 217 |
| What This Import Left Out (collapsed) | **38** |

Per-item costs, so the real-corpus scale can be derived rather than guessed: **table row 44px**,
per-unit evidence disclosure row **22px**, **conflict block 178px**, group chrome **≈87px**.

### Extrapolated to the real corpus — stated because it is the point of the slice

94 units · 10 groups · 21 conflicts, using the measured per-item costs:

```
94 × (44 + 22)  = 6,204   measurement rows + their evidence disclosures
10 × 87         =   870   group chrome
21 × 178        = 3,738   conflicts (always visible)
292+38+217+38   =   585   digest, ceiling, mapping, left-out (all collapsed)
                  ------
                 11,397 px  ≈ 12.7 viewports at 1280×900
```

This is an **extrapolation from measured per-item costs, not a measurement** — no 94-unit payload
exists to render. It is reported because it names the one place the design will strain: **the
conflicts block reaches ~3,738px (4.2 viewports) of always-visible content.** That is deliberate —
the brief requires conflicts to be unmissable, and 21 real disagreements each carrying a scientist
explanation plus every reading is the honest size of that content. It is named as residue below
rather than pre-emptively collapsed, because collapsing the *one* thing the brief calls unmissable
is a decision that needs its own argument.

### Computed-style checks (the capture-surface lesson)

| property | computed | why checked |
|---|---|---|
| `.bl15-chip input` `accent-color` | **`rgb(44, 106, 176)`** = `--action` | `auto` would paint the radios **crimson** in default Chromium |
| `.bl15-input` `border-style` | **`solid`** | the capture textarea shipped `border-style: none` from undeclared properties |
| `.bl15-digest-row > summary` `cursor` | **`pointer`** | "controls must look interactive" |

---

## 5. Repository guards caught four real defects in my own work

Every one of these was found by a guard I did not know existed, and each was a genuine defect rather
than a false positive.

1. **Three phantom custom properties.** My first CSS used `--space-3xs`, `--warn-border` and
   `--warn-surface`. **None is declared anywhere** (`--space-*` has exactly six rungs and no `3xs`;
   there is no warning-colour token at all). The fallbacks I wrote would not have rescued them —
   `palette-contrast.test.ts` keys on the **name**. Fixed by using the repository's actual token for
   "read this", the `--advisory-*` family, which `historical-import.css`'s own `.hi-warn` already
   uses.
2. **Four ratcheted axes, not one.** `type-scale-and-spacing.test.ts` ratchets `font-size` (1043),
   `font-weight` (282), `line-height` (421) **and** spacing (2400). My first CSS was full of raw
   `12px` / `1.55` / `700`. The file now uses **only tokens in all four axes**, so it moves no
   ceiling: re-run gives **63 passed** across the three style guards with no ceiling edited.
3. **`native-control-accent.test.ts` — and its reason bites hardest here.** My filter radios had no
   explicit `accent-color`, so they would paint in the viewer's OS accent — **crimson in default
   Chromium**, in a colour `tokens.css` reserves for the validation verdict. On a surface whose
   entire argument is that **nothing here is a pass or a failure**, a red `Sources disagree` radio
   would say the opposite, differently on every machine. Fixed with `accent-color: var(--action)`,
   following `.conflict-candidate input[type='radio']`.
4. **`casing-registers.test.tsx` §3 — two hardcoded label-slot literals.** Every other title on the
   surface already came from `BL15_COPY`; exactly two did not. That was an inconsistency, not a
   register choice, so both moved into the content module rather than the ceiling being raised.

---

## 6. Accessibility

**No baseline cell moves, and no cell could have moved.** The review renders only when the session
payload carries `corpus_review`, and **no route emits one** — so on `imports`, the one scanned
surface that could mount it, nothing renders today. `e2e/a11y-baseline.ts` is **not edited**;
`A11Y_BASELINE_TOTAL_NODES` and `DARWIN_CARRIED_FORWARD` (`[]`) are untouched, and there is no
darwin/linux half to carry forward because there is no cell.

**The disclosures are registered anyway, and that is the Settings lesson applied.**
`BL15_REVIEW_DISCLOSURES` is declared (at `{}` — i.e. 0 for every surface) and
`openUnreachableDisclosures` now opens and asserts `details.bl15-digest-row`,
`.bl15-disclosure` and `.bl15-unit-disclosure`. `?? 0` would have given the same behaviour today;
writing it down is what makes the **next** slice fail loudly instead of quietly exempting a
nine-column table, every conflict explanation and the whole mapping registry from every axe scan at
every viewport — on a surface that records no cell and therefore cannot signal the loss by a number
changing. **The slice that gives `corpus_review` a route must change that number in the same
change**, and the assertion message names the file to edit.

Accessibility choices inside the component: native `<details>`/`<summary>` throughout (no
hand-rolled `aria-expanded`); `<h4>`/`<h5>` inside a first `<summary>`, which is the spec's own
allowance, so headings keep their level; a real `<fieldset>`/`<legend>` for the filter radios;
`scope="col"` / `scope="row"` on the table; `aria-labelledby` on the section.

---

## 7. Impeccable — DEGRADED, with the negative control run first

> ⚠️ **DEGRADED: single-context** (no second isolated assessor), and the **deterministic scan is
> unavailable**, not clean.

**Negative control, run before anything else**, on a fixture containing an unlabelled `<img>`, a
clickable `<div>` with no role, 8px text, a nested interactive element and a bare radio:

```
node .../impeccable/scripts/detect.mjs bad.tsx   -> EXIT=0, stdout EMPTY, stderr EMPTY
node .../impeccable/scripts/detect.mjs bad.html  -> EXIT=0, stdout EMPTY, stderr:
   "impeccable detect: DEGRADED - HTML parser modules unavailable
    (htmlparser2, css-select, css-tree, domutils). ... findings are an undercount,
    not a clean bill of health."
```

Same bad markup, two extensions, two behaviours — which localises the defect precisely. On `.tsx`
the detector is **silent on both streams**, so a caller reading only stdout or the exit code sees a
clean page; it does not even emit the DEGRADED banner, because the `.tsx` path routes to a regex
engine that never imports those parsers and **has no accessibility ruleset at all**. This reproduces
`CLAUDE.md` §11 exactly. **I report "deterministic scan unavailable" and never "0 findings."**

Design evidence therefore comes from live-browser measurement (§4) plus the `critique.md` playbook
applied by hand. **Not run: the in-browser overlay** — it is a different code path and does work, but
it needs a served page, and the probe harness was deleted as soon as the geometry was measured;
re-standing it up would mean re-adding files I removed. That is a real gap in this run and is stated
rather than papered over.

### Nielsen heuristics, scored against the measured surface

| # | Heuristic | Score | Key issue |
|---|---|---:|---|
| 1 | Visibility of system status | 4 | 15 derived counts up front; a truncated walk warns *before* the digest so every number reads as a floor |
| 2 | Match system / real world | 4 | "Sample 01", "Legacy #", "Scans" — scientist words; `group_token: null` becomes "No sample token" rather than an empty heading |
| 3 | User control and freedom | 3 | Search + 5 filters, everything collapsible. No way to *sort* the table, and no deep link to a measurement (the session is deliberately not in the URL) |
| 4 | Consistency and standards | 4 | Same disclosure shape, tokens and prose measure (68ch) as Data & Privacy and `.gov-policy-section` |
| 5 | Error prevention | n/a | The surface is read-only; it mutates nothing and submits nothing |
| 6 | Recognition rather than recall | 4 | Every number carries its own expression; every conflict carries its explanation; nothing requires remembering a prior screen |
| 7 | Flexibility and efficiency | 3 | Filters and search are there; at 94 units the groups are the only navigation — no jump-to-group index |
| 8 | Aesthetic and minimalist design | 3 | 0 paragraphs over 400 chars and 30 collapsed disclosures, **but** the conflicts block is 1,501px at 7 conflicts and extrapolates to ~3,738px at 21 |
| 9 | Error recovery | n/a | No operation can fail here; the component takes a prop and renders |
| 10 | Help and documentation | 4 | Every category states its own meaning, and the ceiling explains what cannot be finished and why |
| **Total** | | **29/32** | two `n/a` (read-only surface), renormalized |

**Design specificity:** grounded. The nine-column table, the four unit states, the three-reading
conflict block and the five mapping outcomes are all shaped by *this* corpus's measured anomalies; no
unrelated product could use them unchanged.

**Priority issues, in order:**

1. **Conflicts do not scale visually.** 1,501px at 7; ~3,738px extrapolated at 21. The kind headings
   already carry counts, so per-kind collapsing is available — but collapsing what the brief calls
   unmissable needs the owner's call.
2. **No jump-to-group index.** At 10 groups and 94 units the only navigation is scrolling.
3. **Every unit gets its own disclosure row**, which doubles table row count (44px + 22px). At 94
   units that is 2,068px of disclosure triggers. A single detail panel would be cheaper but adds
   state and correlation-by-eye.

**Cognitive load:** the filter row is the only decision point and it has 5 options — one over the
>4 threshold. Kept, because `All` is a reset rather than a fifth category and the four real states
are the four the payload can produce.

---

## 8. Verification

| Check | Command | Result |
|---|---|---|
| New suite | `cd apps/web && node_modules/.bin/vitest run src/__tests__/bl15-import-review.test.tsx` | **43 passed**, exit 0 |
| Full frontend | `cd apps/web && node_modules/.bin/vitest run` | **236 files / 6,147 tests passed**, exit 0 |
| Typecheck (**after** adding files) | `cd apps/web && node_modules/.bin/tsc -b` | exit **0** |
| Style guards | `vitest run type-scale-and-spacing palette-contrast interaction-states` | **63 passed**, no ceiling edited |
| Guards that had caught me | `vitest run casing-registers native-control-accent bl15-import-review type-scale-and-spacing palette-contrast` | **124 passed** |
| Registry coverage | `PYTHONPATH=apps/api .venv/bin/python -c "…coverage()"` | 2/4/14/24/1 of 45 |

**Frontend test count 6,104 → 6,147** (235 → 236 files). Derived mechanically, not asserted: this
slice adds **one** test file containing 43 tests and **modifies no existing test file**
(`git status --short` shows `e2e/helpers/disclosures.ts`, `lib/types.ts` and
`screens/HistoricalImport.tsx` as the only modifications).

**Backend: not run, and not touched.** No file under `apps/api/`, `src/isaac_records/`, `schema/` or
`apps/api/isaac_api/bl15/` was modified. Truth / export / validation paths: **untouched**.
`HistoricalImport.tsx` was in scope for this slice (the brief names it as the shell being extended);
`SettingsPage.tsx` was not touched.

`vitest` and Playwright were **never run concurrently**.

### Mutation checks — both actually run, both RED

| Mutation | Result |
|---|---|
| `corpusDigest`'s `scans` row → `u.scans.length + 1` | **RED**: `expected 22 to be 14` |
| `ConflictView` → `conflict.readings.slice(0, 2)` | **RED**: `expected 2 to be 3` |

Both reverted and re-verified green (43/43; `grep -c "readings.slice"` → 0).

**A false figure in my own committed prose, corrected.** The first draft of the §2 `MUTATION:`
comment said *"fixture: 15 real scans against 23"* — guessed from reasoning rather than taken from
the run. The measured pair is **14 against 22**, and the comment now records both the real numbers
and the fact that the guessed ones were wrong.

### Five test failures on the first run — four were my tests, one was my selector

Worth recording because none was a component defect:

1. My expected key set omitted `group_token` (the contract has 17 keys, not 16).
2. My three-readings selector matched by `subject`, and the fixture's three-way conflict **shares its
   stem** with a two-reading `acquired_never_declared` — so `.find()` returned the wrong block and
   read 2 against 3, looking exactly like a component defect. Now selected by **kind**.
3. A regex whose `.*` spanned the **entire document**, so "complete" anywhere plus any later "N of
   45" matched. Bounded.
4. `expect(text).not.toContain('298')` — **298 is present and must be**, inside
   `TEMPERATURE_ABSENT_REASON` itself (*"298 must not be defaulted into `context.temperature_K`"*).
   A blanket ban on the digits contradicted the requirement to render that sentence. Now asserts 298
   appears in no table cell and no evidence row.
5. A verb blacklist in the summary guard flagged my own `What Cannot Be Finished Here`. **The test
   was wrong, not the heading** — a verb blacklist is a crude proxy. Replaced with the two checks
   that name the real hazard: every summary is drawn from a **closed set** (stated as a set
   difference, so a new summary also fails), and **no scope-carrying server sentence** —
   `ConceptMapping.reason`, `Conflict.explanation`, `unattached[].reason`, either ceiling reason —
   appears in any summary. That is the `PrivacyBody` hazard stated precisely.

---

## 9. Snapshot preflight

**`apps/web/src/lib/types.ts` is in the served-content manifest and has DRIFTED.** Proven by
re-hashing rather than by running the generator. The other eight files are **not** manifest-listed.
Manifest total: 200. Regeneration (with `--detail-out`, per §17) is the orchestrator's step.

---

## 10. Deliberately not built

- **Any `apps/api` change**, including the route that would emit `corpus_review`, the archive source
  kind, and a `concept` field on `SemanticCandidate` that would close **G-3**. Out of scope by
  constraint.
- **A per-file manifest**, at any depth — not available on the wire (**G-1**) and banned by
  `HIST-004` in spirit.
- **A "Ready" state or any progress indicator** — integration design §5.
- **Sorting, a jump-to-group index, and deep-linking a measurement.** The last is a standing
  decision: `HistoricalImport`'s header records that a session is deliberately not in the URL
  because it is not durable.
- **Per-kind collapsing of the conflicts block** — the measurement arguing for it is in §4, and the
  decision is the owner's because it trades against "conflicts must be unmissable".
- **Add to Experiment / run seeding.** Integration design §4 specifies `new_run(draft={})` with the
  label from the legacy number; it needs the route and is a separate slice.
- **The in-browser Impeccable overlay** — see §7.

---

## 11. EIGHT COMMITS LANDED ON MY BASE BRANCH WHILE I WORKED, AND ONE NARROWS G-3

Measured at the end of the slice, not assumed: `git status -sb` reported **`[behind 8]`**, and
`origin/feat/bl15-foundation` is now **`7afc7d1d`**, not the `1a4ca90a` I based on. What arrived:

```
7afc7d1d fix(bl15): my own characterization doc broke its own governance rule
97e4d3f7 fix(bl15): the evidence ceiling's justification was false and the ceiling was reached
f951a614 merge: the BL15 readers, the profile registry, and content-led classification
0d495e64 feat(bl15): the readers — a versioned profile, content-led classification, and four formats
58345206 docs(ledger): five BL15R rows move from PLANNED/IN PROGRESS to DONE
b69d0724 merge: the safe archive walk, evaluation harness, and domain packet
e06b4476 docs(bl15): three facts I published were wrong; the archive slice measured them
a8f52ffe feat(bl15): the safe archive walk, the evaluation harness, and the packet for Angel
e5df9e8b feat(bl15): candidate assembly — the only module that interprets, and what it may not do
```

**This surface is built against `1a4ca90a` and every contract it reads is unchanged by those eight
commits** (`relate.py`, `mapping.py`, `evidence.py`, `inventory.py`). But `e5df9e8b` added
`bl15/reconstruct.py`, and reporting G-3 without re-checking it would have been exactly the stale
claim this repository punishes. Re-checked, three findings:

1. **G-3's core is intact.** `_candidate_state` (`reconstruct.py:487`) emits the same twelve keys as
   `SemanticCandidate.to_state()` — no `concept`, no `status`. A candidate still cannot be joined to
   its registry status by a field of its own.
2. **But two indirect routes now exist, so G-3 is NARROWER than §2 states.**
   `statement_for` sets **`EvidenceStatement.key = item.concept`**, so a candidate's
   `supporting_statements[].key` *is* the concept — which makes candidate→concept→status derivable
   today without a new field. And `ReconstructionReport.to_state()` serves **`by_mapping_status`**
   (status → count) and **`by_concept`** (concept → count) directly. Those are counts over the
   candidates actually PRODUCED, which is a different and more useful number than the registry
   coverage this surface renders. **A follow-up slice should read `by_mapping_status` rather than
   recompute anything**, and it does not need the field I said was missing.
3. **`reconstruct.py` independently reached this surface's own conclusion about the progress bar**,
   which is worth recording as corroboration rather than coincidence. Its docstring:
   *"The per-status breakdown is what makes it legible — and it is deliberately NOT a ratio: 39 of
   45 concepts have no proposable mapping, so a 'percentage mapped' would report the schema's
   coverage as this feature's failure."* Two slices, no contact, same refusal.

It also corroborates the scale argument in §4 with a figure I did not have: *"Over the real corpus
this produces roughly **a thousand candidates** across 94 measurements, and a surface that rendered
them flat would be `HIST-004`'s banned pattern."*

**Consequence for integration:** this branch needs rebasing onto `7afc7d1d` before merge. Nothing in
the eight commits touches the four contracts this surface reads, and no file I changed is touched by
them — but that is a claim to re-verify on the merge result, not to trust from here. `CLAUDE.md` §11's
rule is explicit and was written after this exact failure cost two red `main` builds:
**exact-head-green protects the HEAD, not the MERGE** — re-run `tsc -b` and the suite on the merge
result before landing.
