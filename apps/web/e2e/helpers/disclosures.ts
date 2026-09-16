/**
 * Open EVERY disclosure on a surface that NO `SURFACES` entry can reach, so
 * their contents are scanned rather than silently exempt.
 *
 * ── Why this is a HELPER and not a private function in one spec ─────────────
 *
 * It lived inside `specs/a11y-axe.spec.ts` until `specs/a11y-narrow.spec.ts` was
 * added. The narrow sweep called `app.open(surface)` and scanned — without this
 * step — so the two sweeps were scanning DIFFERENT DOM on `statistics` and
 * `statistics-example`: five disclosures open at the five Playwright viewports,
 * five disclosures CLOSED at 320 and 390. Two axe baselines whose numbers are
 * compared to each other must come from the same page state, and a spec cannot
 * import a helper out of another spec without re-registering that spec's tests.
 * Hence this file.
 *
 * ── Why it exists at all ────────────────────────────────────────────────────
 *
 * A `<details>` has no URL state, so a surface's `path` cannot open one; and axe
 * does not scan a closed disclosure. When the Statistics slice moved the two
 * `/api/about` cards into a collapsed `Technical Details` region, their two
 * `.stat-card-note` `color-contrast` failures stopped being counted — and the
 * baseline recorded the drop as a coverage gap, with a note claiming the
 * unmeasured instances were only those two and that "not one is a chart".
 *
 * Both halves of that claim were false. Measured by an independent reviewer,
 * opening the region on `statistics-example` raised the failing node count from
 * 9 to 12: the third node was a CHART AXIS TICK, at `--text-tertiary` #78838f /
 * 10.5px — a new WCAG 1.4.3 failure shipping invisibly behind a note asserting
 * it did not exist. (The token has since been darkened to `--text-muted`, which
 * is why the tick no longer appears in the counts; the coverage this restores is
 * what made it visible.)
 *
 * ── AND FOUR MORE, ADDED BY THE VISUAL-FIRST REORGANISATION ─────────────────
 *
 * That slice moved Record Verification to the top of the Statistics General tab
 * and moved its supporting PROSE into four new closed disclosures beside
 * Technical Details. Every one of them is unreachable by URL for exactly the
 * reason above, so they are opened here too.
 *
 * THE RULE THIS ENFORCES IS THE ONE THE HISTORY ABOVE ESTABLISHED: a baseline
 * number that drops because content is now hidden is a COVERAGE LOSS, not an
 * accessibility win. Four disclosures' worth of copy going unscanned while the
 * counts stayed flat would be that same defect at four times the size — and it
 * would look like nothing had happened, which is what makes it worth a helper
 * rather than a comment.
 *
 * ── AND THE RECORD SCREEN'S FOUR DRAFT BLOCKS, ADDED 2026-08-30 ─────────────
 *
 * A measured coverage hole of the same shape, and a larger one. `FieldGroup` collapses
 * every draft block on arrival — the four sections that hold every field row on the
 * record screen — and it is a `button[aria-expanded]` over conditionally rendered
 * children, so the body is not merely hidden, it is NOT IN THE DOM. axe has therefore
 * never seen a single `.field-row`, at any viewport, on any surface, since those
 * sections were written. Everything the group-skeleton slice put inside them (the
 * per-path capture sentence, and the value control on the two paths a record-level route
 * accepts) would have landed in exactly that blind spot.
 *
 * THE SELECTOR IS `section[data-draft-block]`, NOT `.fg-header`, and the distinction is
 * the whole reason that attribute exists. `RenameExperimentPanel`, `RecordInfoPanel` and
 * `RecordLinksPanel` deliberately reuse `FieldGroup`'s shell down to the class names
 * (each says so in its own header), so a `.fg-header` sweep would also open three
 * sections this addition is not about and move their counts for an unrelated reason.
 * Same argument as `details.stats-disclosure` carrying its own class rather than
 * borrowing `details.stats-technical`.
 *
 * THE COUNT IS ASSERTED AS "AT LEAST ONE", NOT AS AN EXACT NUMBER, and that is a
 * deliberate departure from `PROSE_DISCLOSURES` above. The number of draft blocks is a
 * property of the RECORD under test — `serialize.draft_to_groups` emits a section only
 * for a group that has rows — so pinning it here would make an unrelated change to a
 * record's field set fail inside a helper whose job is coverage. What the assertion has
 * to catch is the failure mode that matters: the blocks becoming unreachable, or
 * silently ceasing to exist, while the baselines quietly drop. `FIELD_GROUP_SURFACES`
 * names the surfaces that must mount at least one, so a surface losing them entirely
 * names itself.
 *
 * ── What it deliberately does NOT open ──────────────────────────────────────
 *
 * Each chart's own data-table `<details class="stats-chart-table-wrap">` stays
 * closed. Those are a per-figure text equivalent whose default state is closed
 * for every reader, and opening four tables at seven widths would move counts
 * for a reason unrelated to this gap. They remain unscanned, which is a real and
 * still-open limitation and is stated here rather than left to be discovered.
 *
 * The record screen's OTHER collapsed `.field-group` cards (Experiment Name, Record
 * Information, Record Links) also stay closed, for the same reason and with the same
 * status: a real, still-open coverage gap, named here rather than left to be found.
 *
 * ── AND ASSET REFERENCES, ADDED WITH THE RECORD WORKSPACES ──────────────────
 *
 * `AssetReferencesPanel` is mounted `collapsedByDefault` on the Record Fields
 * workspace, which would otherwise have taken a whole browser — its create form,
 * its per-asset cards, its run-association controls — out of every scan at every
 * viewport, and the counts would have DROPPED. This helper's own history is that
 * exactly such a drop was once recorded as an accessibility win; it is a coverage
 * loss. So the disclosure is opened here, and the panel keeps the same scanned DOM
 * it had when it was an always-open section.
 */

import { expect, type Page } from '@playwright/test';

/**
 * How many `details.stats-disclosure` each surface mounts.
 *
 * DECLARED PER SURFACE, not counted and accepted, so that a disclosure appearing
 * or disappearing names itself here instead of moving a scan count that nobody
 * can then explain. Anything absent from this map must mount none.
 *
 * The four are the Statistics General tab's supporting-copy disclosures — How
 * Verification Works, How to Interpret Results, Mutation Methodology, Known
 * Limitations. `statistics-mine` is the My Stats tab, which renders none of them
 * and no `details.stats-technical` either.
 */
export const PROSE_DISCLOSURES: Readonly<Record<string, number>> = Object.freeze({
  /*
   * *** THE FOUR MOVED, 2026-09-15, AND THIS MAP IS WHAT CAUGHT IT. ***
   *
   * ~~statistics: 4, 'statistics-example': 4~~ — the Statistics redesign moved
   * every prose disclosure off the Overview tab and onto the new
   * `Build & Verification` tab. Measured in Chrome: Overview mounts **0**, My
   * Stats **0**, `?tab=build` **4**.
   *
   * SETTING THE OLD ENTRIES TO 0 WOULD HAVE MADE THIS GREEN AND DELETED THE
   * COVERAGE — the four blocks would then be opened, and scanned, at no
   * viewport at all. So the declaration MOVES with the disclosures, and
   * `statistics-build` is added to `e2e/surfaces.ts` in the same change so
   * there is a surface for this entry to apply to. An absent surface reads `?? 0`
   * here, which is exactly how a silent loss would have looked.
   */
  /*
   * `statistics-example` IS **2**, NOT 0, AND REMOVING IT WAS MY OWN
   * REGRESSION — corrected here rather than quietly.
   *
   * I set both Statistics entries to absent (`?? 0`) on the strength of
   * measuring the ORDINARY scope, where Overview genuinely mounts 0. The
   * WORKED-EXAMPLE scope holds five seeded records, so Overview renders
   * sections the empty workspace has nothing to render — and two of them carry
   * a prose disclosure. Measured twice, on both platforms: CI reported
   * `surface "statistics-example" mounts 2` on linux and a local run reproduced
   * it on darwin.
   *
   * The lesson is the map's own: a per-surface count is a property of the
   * SURFACE AND ITS SCOPE, and measuring one scope does not measure the other.
   */
  'statistics-example': 2,
  'statistics-build': 4,
});

/**
 * Surfaces that MUST mount at least one collapsed draft block.
 *
 * `record-detail` is the record workbench, which renders one `FieldGroup` per draft
 * section. Declared rather than measured-and-accepted, for the reason
 * `PROSE_DISCLOSURES` is: a surface that quietly stopped mounting them would otherwise
 * take every field row out of every scan while the baselines merely drifted down, which
 * this helper's own history shows reads as an accessibility win.
 *
 * The COUNT is deliberately not declared — see the header. A surface absent from this set
 * may mount zero, and any it does mount are still opened.
 */
export const FIELD_GROUP_SURFACES: ReadonlySet<string> = new Set(['record-detail']);

/**
 * How many `details.bl15-digest-row` / `.bl15-disclosure` / `.bl15-unit-disclosure`
 * each surface mounts — the BL15-2 large-corpus review (`BL15R-012`).
 *
 * ── DECLARED AT ZERO, AND THE REASON CHANGED 2026-09-16 ───────────────────
 *
 * ~~The review renders only when the session payload carries `corpus_review`, and
 * **no route emits one today** — the archive source kind is a separate slice's step 1
 * and `historical_import.SOURCE_KINDS` holds only `reference` and `synthetic_fixture`.~~
 * **Every clause of that was false by the time it was written or shortly after**: the
 * kind shipped in `6cdb2279` on the same branch, and `historical_import._corpus_review`
 * now serves the member. Independent review found the stale reason.
 *
 * **THE NUMBER IS STILL 0, AND NOW IT IS A MEASUREMENT RATHER THAN AN ABSENCE.** The
 * sweep reaches `/imports` at its INDEX — the empty-list state, no session open — so no
 * archive reading exists there and `corpus_review` is absent, which is why the surface
 * mounts none of these. Verified after the route landed: `a11y-axe` 150 passed and
 * `a11y-narrow` 63 passed with no baseline movement and no edit to `a11y-baseline.ts`.
 *
 * IT IS WRITTEN DOWN REGARDLESS, because the Settings slice on 2026-09-16 proved what
 * the silence costs. Twelve Data & Privacy definitions went behind `<details>` and would
 * have left every axe scan at every viewport while `settings-privacy`'s baseline — which
 * records no cell at all — could not move to reveal it. A disclosure that is not opened
 * here is not scanned, and a surface with zero recorded violations cannot signal the
 * loss by a number changing.
 *
 * So a slice that makes THIS sweep reach a loaded session changes this number, and the
 * assertion below names the file to edit — an `imports` surface that suddenly mounts
 * disclosures against a declared 0 fails loudly instead of quietly exempting a
 * nine-column table, every conflict explanation and the whole mapping registry.
 *
 * ~~That is the only remaining precondition — a seeded session in `SURFACES`.~~ —
 * **WRONG, AND CORRECTED 2026-09-16 the same day it was written.** It repeated this
 * registry's framing without checking `surfaces.ts`, which records the opposite:
 * adding `imports-session` to `SURFACES` was DECLINED, because it would enrol the
 * surface in thirteen sweeps across seven viewport projects, **every one of which
 * needs a POST this config forbids**.
 *
 * The loaded state is covered, in the suite that IS allowed to POST:
 * `e2e/mutation/imports-session-a11y.spec.ts`, which now drives SIX states — four
 * from an example source and two from an ARCHIVE, including the corpus review — and
 * requires each axe-clean. So the honest statement is not "unmeasured", it is
 * "measured elsewhere, by design, and not by this registry".
 */
export const BL15_REVIEW_DISCLOSURES: Readonly<Record<string, number>> = Object.freeze({});

/**
 * How many `details.settings-concept` each surface mounts.
 *
 * ── ADDED 2026-09-16, AND IT IS THIS HELPER'S OWN RULE APPLIED TO A NEW SITE ──
 *
 * Data & Privacy rendered its twelve concept definitions always-expanded, which
 * measured 2.5 viewports of prose at 1280x900 and 7.4 at 375x812. Each `detail`
 * now sits behind its own `<details class="settings-concept">` — nothing deleted,
 * every sentence still in the DOM.
 *
 * WITHOUT THIS ENTRY THAT CHANGE WOULD HAVE BEEN INVISIBLE AND WRONG. axe does
 * not scan a closed disclosure, so twelve paragraphs would have left every scan
 * at every viewport — and `settings-privacy` records NO baseline cell, i.e. zero
 * violating nodes, so the loss could not even show up as a number moving. It
 * would have looked exactly like nothing had happened, which is the failure mode
 * the Statistics `Technical Details` history in this file's header describes.
 *
 * Opening them restores precisely the DOM the surface was scanned with before,
 * so the correct outcome is that NO baseline cell moves. That is a checkable
 * claim and it is the one this entry exists to keep true.
 *
 * EXACT COUNT, following `PROSE_DISCLOSURES` rather than `FIELD_GROUP_SURFACES`,
 * because this number is a property of the APP's own content module
 * (`settingsConcepts()` in `src/lib/settingsContent.ts`) and not of any record
 * under test. A thirteenth concept therefore names itself here instead of
 * quietly going unscanned.
 *
 * The nested `details.settings-more` drawers stay CLOSED, unchanged: they were
 * closed before this change too, so leaving them shut is what keeps the scanned
 * DOM identical. Their contents remain unscanned — a real, pre-existing
 * limitation, named here rather than introduced here.
 */
export const SETTINGS_CONCEPT_DISCLOSURES: Readonly<Record<string, number>> = Object.freeze({
  'settings-privacy': 12,
});

/**
 * Surfaces that MUST mount the COLLAPSED Asset References disclosure.
 *
 * Declared for exactly the reason `FIELD_GROUP_SURFACES` is, and the reason is
 * sharper here because the first version of `openAssetReferences` had no such
 * declaration and FAILED OPEN. It guarded on `count() === 0 → return` and then
 * asserted `toHaveCount(0)` on the SAME selector, so a broken selector satisfied
 * both: nothing was found, nothing was opened, nothing was asserted, and the a11y
 * gate stayed green while a whole browser — the create form, the per-asset cards,
 * the run-association controls — went unscanned at every viewport. Measured: the
 * only visible effect was axe `passes` dropping 46 → 44, which no gate reads.
 *
 * `record-detail` is the bare `/record/<id>`, i.e. the Record Fields workspace,
 * which is the one workspace that mounts the collapsed variant. The other record
 * surfaces (`record-runs`, `record-capture`) mount no Asset References at all.
 */
export const ASSET_DISCLOSURE_SURFACES: ReadonlySet<string> = new Set(['record-detail']);

export async function openUnreachableDisclosures(page: Page, surfaceId: string): Promise<void> {
  const technical = page.locator('details.stats-technical');
  const mounted = await technical.count();
  /*
   * ONE, ASSERTED. `technical.locator('> summary').click()` resolves through a
   * strict-mode locator, so a second `details.stats-technical` on any surface
   * would throw "resolved to 2 elements" from inside a helper whose job is
   * coverage — an opaque failure in every a11y scan at every viewport, naming
   * neither the surface nor the cause. Asserted here so the second mount names
   * itself.
   *
   * IT IS STILL ONE, and that is why the four prose disclosures carry their own
   * class (`details.stats-disclosure`, see `StatsCharts.tsx` →
   * `TechnicalDetailsProps.variant`): giving them this class would have turned
   * this locator — and the `toHaveCount(1)` in `statistics-states.spec.ts`, and
   * `openTechnicalDetails` in `charts.spec.ts` — into that same opaque failure.
   */
  if (mounted > 0) {
    expect(mounted, 'a surface must mount exactly one details.stats-technical').toBe(1);
    await technical.locator('> summary').click();
    await expect(technical).toHaveAttribute('open', '');
  }

  /*
   * The prose disclosures, opened one at a time by index — `.nth(i)` rather than
   * a bare locator, because there are legitimately several and a strict-mode
   * click would throw on the second.
   *
   * The count is DECLARED (`PROSE_DISCLOSURES`) and asserted, not measured and
   * accepted: an unopened fifth disclosure would silently exempt its contents
   * from every scan at every viewport, which is precisely the coverage gap this
   * helper exists to close.
   */
  const prose = page.locator('details.stats-disclosure');
  const expectedProse = PROSE_DISCLOSURES[surfaceId] ?? 0;
  const proseCount = await prose.count();
  expect(
    proseCount,
    `surface "${surfaceId}" mounts ${proseCount} details.stats-disclosure; ` +
      `PROSE_DISCLOSURES in e2e/helpers/disclosures.ts declares ${expectedProse}. A disclosure ` +
      'that is not opened here is not scanned by axe at any viewport — update the map in the ' +
      'same change that adds or removes one.'
  ).toBe(expectedProse);
  for (let i = 0; i < proseCount; i++) {
    const one = prose.nth(i);
    await one.locator('> summary').click();
    await expect(one).toHaveAttribute('open', '');
  }

  /*
   * The BL15-2 corpus review's disclosures — digest rows, the four explanatory
   * blocks, and one per measurement. Same mechanism and same reasoning as the
   * prose disclosures above; see `BL15_REVIEW_DISCLOSURES` for why the declared
   * count is 0 today and why it is written down anyway.
   */
  const bl15 = page.locator(
    'details.bl15-digest-row, details.bl15-disclosure, details.bl15-unit-disclosure'
  );
  const expectedBl15 = BL15_REVIEW_DISCLOSURES[surfaceId] ?? 0;
  const bl15Count = await bl15.count();
  expect(
    bl15Count,
    `surface "${surfaceId}" mounts ${bl15Count} BL15 corpus-review disclosure(s); ` +
      `BL15_REVIEW_DISCLOSURES in e2e/helpers/disclosures.ts declares ${expectedBl15}. ` +
      'A disclosure that is not opened here is exempt from every axe scan at every ' +
      'viewport, and because this surface records no baseline cell the loss would move ' +
      'no number at all — update the map in the same change that adds or removes one.'
  ).toBe(expectedBl15);
  for (let i = 0; i < bl15Count; i++) {
    const one = bl15.nth(i);
    await one.locator('> summary').click();
    await expect(one).toHaveAttribute('open', '');
  }

  /*
   * The Data & Privacy concept rows. Same mechanism and same reasoning as the
   * prose disclosures above — declared count, opened by index, asserted open —
   * and see `SETTINGS_CONCEPT_DISCLOSURES` for why an unopened row here would be
   * a coverage loss that no baseline number could reveal.
   */
  const concepts = page.locator('details.settings-concept');
  const expectedConcepts = SETTINGS_CONCEPT_DISCLOSURES[surfaceId] ?? 0;
  const conceptCount = await concepts.count();
  expect(
    conceptCount,
    `surface "${surfaceId}" mounts ${conceptCount} details.settings-concept; ` +
      `SETTINGS_CONCEPT_DISCLOSURES in e2e/helpers/disclosures.ts declares ${expectedConcepts}. ` +
      'A concept row that is not opened here has its whole definition exempt from every axe ' +
      'scan at every viewport, and because settings-privacy records no baseline cell the loss ' +
      'would move no number at all — update the map in the same change that adds or removes one.'
  ).toBe(expectedConcepts);
  for (let i = 0; i < conceptCount; i++) {
    const one = concepts.nth(i);
    await one.locator('> summary').click();
    await expect(one).toHaveAttribute('open', '');
  }

  await openDraftBlocks(page, surfaceId);
  await openAssetReferences(page, surfaceId);
}

/**
 * Open the Asset References disclosure on the surfaces that mount it.
 *
 * ── IT ASSERTS THAT IT OPENED SOMETHING, WHICH THE FIRST VERSION DID NOT ─────
 *
 * That version guarded on `count() === 0 → return` and then asserted
 * `toHaveCount(0)` on the same selector, so BOTH steps were satisfied by finding
 * nothing — a broken selector read exactly like a surface with no disclosure.
 * `ASSET_DISCLOSURE_SURFACES` is what makes the difference checkable: on a surface
 * that must mount one, finding none is a FAILURE rather than a quiet return.
 *
 * DESCENDANT SELECTORS, NOT CHILD COMBINATORS, for the reason `openDraftBlocks`
 * records: the toggle is wrapped in an `<h2 class="fg-heading">` so the section is
 * a heading landmark, and a `>` chain encodes that wrapper's exact depth. If a
 * later change moves the button one element, a child chain stops matching and —
 * without the positive assertion below — would fail open all over again.
 */
export async function openAssetReferences(page: Page, surfaceId: string): Promise<void> {
  const COLLAPSED = '.assets-collapsible .fg-header[aria-expanded="false"]';
  const toggle = page.locator(COLLAPSED);
  const mounted = await toggle.count();
  if (ASSET_DISCLOSURE_SURFACES.has(surfaceId)) {
    expect(
      mounted,
      `surface "${surfaceId}" is declared in ASSET_DISCLOSURE_SURFACES ` +
        '(e2e/helpers/disclosures.ts) but mounts no collapsed Asset References ' +
        `disclosure matching "${COLLAPSED}". Either the panel stopped being mounted ` +
        'collapsed there — in which case remove it from the set — or this selector ' +
        'is broken, in which case a whole asset browser is silently exempt from every ' +
        'axe scan at every viewport while the counts merely drift down.'
    ).toBeGreaterThan(0);
  }
  if (mounted === 0) return;
  await toggle.first().click();
  await expect(page.locator(COLLAPSED)).toHaveCount(0);
  /* AND THE BODY IS REALLY OPEN. `aria-expanded` moving is the button's claim
     about itself; this is the thing axe will actually scan. */
  await expect(page.locator('.assets-collapsible .fg-body').first()).toBeVisible();
}

/**
 * Open every collapsed draft block on the record screen.
 *
 * A separate function from the one above — though called from it, so no spec has to
 * remember a second step — because the two open different things by different mechanisms:
 * a `<details>` toggled through its `<summary>`, and a `button[aria-expanded]` whose
 * panel does not exist in the DOM until it is pressed. Keeping them apart means a failure
 * names which kind failed.
 *
 * IDEMPOTENT AND ORDER-INSENSITIVE: it re-reads the collapsed set on each pass rather
 * than iterating a snapshot, because pressing one header re-renders the list. It presses
 * only headers reporting `aria-expanded="false"`, so a block an earlier step already
 * opened is never toggled shut again.
 */
export async function openDraftBlocks(page: Page, surfaceId: string): Promise<void> {
  const blocks = page.locator('section[data-draft-block]');
  const mounted = await blocks.count();
  if (FIELD_GROUP_SURFACES.has(surfaceId)) {
    expect(
      mounted,
      `surface "${surfaceId}" is declared in FIELD_GROUP_SURFACES (e2e/helpers/disclosures.ts) ` +
        'but mounts no section[data-draft-block]. A draft block that is not opened here is not ' +
        'scanned by axe at any viewport, and its disappearance would read as a baseline ' +
        'improvement rather than as the coverage loss it is.'
    ).toBeGreaterThan(0);
  }

  /* Bounded rather than `while (true)`: each pass can only shrink the collapsed set, and
     the bound turns "a header that will not stay open" into a named failure instead of a
     hung scan at every viewport. One press each is `mounted` passes. */
  for (let pass = 0; pass < mounted; pass++) {
    /* A DESCENDANT SELECTOR, NOT A CHILD ONE, and the change is load-bearing.
       `FieldGroup`'s toggle is now wrapped in an `<h2 class="fg-heading">` so the
       section is a heading landmark (it was measured invisible to heading
       navigation). `>` stopped matching at that point — and it would have failed
       OPEN rather than loudly: `count() === 0` reads as "nothing left to open",
       so the loop would break immediately and every draft block would go
       unscanned while this helper reported success. */
    const collapsed = page.locator(
      'section[data-draft-block] .fg-header[aria-expanded="false"]'
    );
    if ((await collapsed.count()) === 0) break;
    await collapsed.first().click();
  }

  await expect(
    page.locator('section[data-draft-block] .fg-header[aria-expanded="false"]')
  ).toHaveCount(0);
}
