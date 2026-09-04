/**
 * TWO SCIENTISTS, TWO REAL BROWSERS, ONE RECORD.
 *
 * ── WHAT IS DIFFERENT FROM `two-actor-workflow.spec.ts`, AND WHY IT COULD NOT
 * ── HAVE BEEN WRITTEN BEFORE THIS BRANCH ────────────────────────────────────
 *
 * That file's own header states its central limitation as a fact about the build:
 *
 *   > `lib/api.ts` deliberately ships no `createProposal`, and `routes.py` records
 *   > that *"NOTHING WAS REWIRED TO FEED THEM. There is no automatic producer"* —
 *   > so **no surface in this build can create a proposal**, and a second browser
 *   > would have nothing to click.
 *
 * **That is no longer true, and this file is the consequence.** PR #228 made
 * `TranscriptCapturePanel`'s *Finalize and Read* mint durable proposals server-side,
 * and PR #231 added `UnmappedNotesPanel`'s *Propose a value from this note*. There
 * are now TWO surfaces a person can click to produce a proposal, so Scientist B can
 * be a **second browser context driving the real UI** rather than an HTTP client.
 *
 * The older spec is deliberately left untouched. It measures a producer-less
 * arrival over HTTP, which is still exactly what an MCP producer would do, and
 * deleting it would trade one proof for another rather than adding one.
 *
 * ── WHO THE TWO ACTORS ARE, PRECISELY ───────────────────────────────────────
 *
 *   · **Scientist A** — the Playwright `page` fixture (browser context 1). A creates
 *     the record, fills it in, and reviews. A's page is opened once in step 1 and
 *     **is not reloaded at all** until step 9; a same-document sentinel planted on
 *     `window` and re-read later proves that mechanically rather than by promise
 *     (`assertSameDocument`), because "no reload happened" is the premise every
 *     live-arrival assertion in this file rests on.
 *   · **Scientist B** — a SECOND browser context (`browser.newContext()`), with its
 *     own cookie jar, its own `localStorage`, its own page and its own pollers. B
 *     types, selects and clicks. **B issues no HTTP call of its own**; every act
 *     attributed to B below is a DOM interaction.
 *
 * `request` (the Playwright API context) appears throughout and is NEVER the act
 * under test. It establishes starting state that no surface may create — one seeded
 * proposal, for the hydration negative control in step 4 — and it reads server state
 * back as an INDEPENDENT check. This is `fixtures.ts`'s one rule, unweakened.
 *
 * ── SAME-TAB SUPPRESSION IS NOT EXERCISED HERE, AND THAT IS THE POINT ───────
 *
 * `lib/selfMintedProposals.ts` is a MODULE-LEVEL map, so it is per page load. B's
 * context is a different page load, so B's proposals are invisible to A's copy of it
 * and A's arrival note fires normally — which is the behaviour a colleague's change
 * is supposed to produce. Stated so nobody reads this file as evidence that the
 * same-tab courtesy works: it is evidence that it does not reach across contexts,
 * which is a different (and weaker) claim, and the only one made here.
 *
 * ── WHAT IS PROVEN HERE, WHAT ONLY IN CI, AND WHAT NOWHERE ──────────────────
 *
 *   · PROVEN HERE, against a real FastAPI process and two real browsers: every step
 *     below, at the config's `trusted-1280x800` viewport, plus the four narrower
 *     viewports the second test walks.
 *   · PROVEN ONLY IN CI, against a real PostgreSQL: durability across a process
 *     restart. This backend is FILESYSTEM-BACKED — asserted from `/api/health` in
 *     step 9 rather than assumed — so the reload there proves the values are re-read
 *     FROM THE SERVER and proves nothing about PostgreSQL. That leg is
 *     `apps/api/tests/test_proposal_durability.py`'s real-engine scenarios, CITED
 *     here and never claimed.
 *   · PROVEN NOWHERE by this file: anything hosted, and anything about a real
 *     Claude/MCP client. `/krish` sits behind an Authentik edge this environment
 *     cannot authenticate to, and `ISAAC_EDGE_TRUST_VERIFIER=test_fixture` is set by
 *     NO shipped deploy artifact (`apps/api/tests/test_deploy_config.py` pins that),
 *     so a hosted acceptance would answer `409 human_actor_required`.
 *
 * ── DETERMINISM ─────────────────────────────────────────────────────────────
 *
 * No `waitForTimeout`, no sleep, no timing assertion. Every wait is `expect`
 * polling on a condition that is either true or false. `DISCOVERY_DEADLINE` is a
 * BOUND on how long a background poller may take before this file calls it broken —
 * a deadline, not a measurement; nothing here passes BECAUSE of a delay.
 *
 * ── NO STEP MAY PASS BY CONSTRUCTION ────────────────────────────────────────
 *
 * Every count is compared against a value captured BEFORE the act that is supposed
 * to move it; every "unchanged" claim is a comparison against a snapshot taken
 * beside it; and every loop that asserts a property of each element is preceded by a
 * non-vacuity assertion that the collection is non-empty. `CLAUDE.md` §11 records
 * both defects (a rev compared against zero, a loop that could iterate zero times)
 * being found by review in this exact area of the codebase.
 *
 * ── SYNTHETIC ONLY ──────────────────────────────────────────────────────────
 *
 * Every record, run, transcript, note, proposal and value here is created by this
 * file seconds earlier, in a workspace `global-setup` wiped. Nothing
 * production-derived is read, and nothing leaves the process.
 */

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import type { APIRequestContext, Browser, BrowserContext, Page } from '@playwright/test';

import {
  addRunThroughTheUi,
  backToAllRuns,
  createExperimentThroughTheUi,
  expect,
  openRun,
  openWorkspace,
  proposalCard,
  switchWorkspace,
  test,
  type ServerApi,
  type ServerProposal,
} from './fixtures';
import { FIXTURE_ACTOR_SUBJECT, FIXTURE_TRUST_BASIS, TRUSTED_API_BASE, TRUSTED_BASE_URL } from './env';
import { RECORD_FIELDS } from '../../src/lib/recordFields';

/**
 * How long a background poller may take to notice a colleague's write.
 *
 * The same deadline `two-actor-workflow.spec.ts` uses, for the same stated reason:
 * `useRecordSync` and `useChangeFeed` poll on a jittered interval with a drain
 * ladder between continuation pages, so 45 s is several cycles. It makes "the page
 * never noticed" FAIL rather than hang, and asserts nothing about how fast the
 * poller is.
 */
const DISCOVERY_DEADLINE = 45_000;

/**
 * The transcript B types. Every clause is chosen against
 * `apps/api/isaac_api/transcript_capture.py`'s CLOSED rule table, read rather than
 * guessed:
 *
 *   · `_TEMPERATURE_K` needs the word "temperature", a number, and the unit K or
 *     kelvin in one clause — so `context.temperature_K` gets `300`.
 *   · `_ATMOSPHERE` needs the word "atmosphere", a copula/colon separator, and a
 *     short phrase that ENDS the sentence — so `context.thermodynamics.atmosphere`
 *     gets `dry nitrogen`, quoted exactly and matched against no vocabulary.
 *   · The third sentence names no field at all and is stored as a note, which is
 *     what makes step 3's note-propose act have a note to act on.
 *
 * IT NAMES NO RUN. `_RUN_REFERENCE` would produce a run clarification, and the run
 * this transcript is about is chosen in the panel's own selector — which is the
 * behaviour under test ("checked against the run you selected, never used to pick
 * one"). A run named in the words would make the selector's contribution invisible.
 */
const TRANSCRIPT_TEXT =
  'Temperature was 300 K. Atmosphere was: dry nitrogen. ' +
  'The cryostat rattled about halfway through, worth checking.';

/** What the reader's transcript is expected to produce, derived above, not invented. */
const TRANSCRIPT_TARGETS = {
  temperature: { path: 'context.temperature_K', value: 300 },
  atmosphere: { path: 'context.thermodynamics.atmosphere', value: 'dry nitrogen' },
} as const;

/** The RECORD-level free-text value A types. Unmistakably synthetic. */
const MATERIAL_NAME = 'SYNTHETIC two-actor sample — not a real material';

/** The corrected atmosphere A types into the "Correct the Value" editor (step 6). */
const CORRECTED_ATMOSPHERE = 'SYNTHETIC corrected — dry argon, not nitrogen';

/** The reason A types when rejecting (step 6). Stored verbatim, asserted verbatim. */
const REJECT_REASON = 'SYNTHETIC — this one names a sample this record never held';

/** The temperature B types straight into run two, to make a filed proposal stale. */
const B_MOVED_TEMPERATURE = 77;

/** The label the record-fields panel gives a path — read from the app, not retyped. */
function recordFieldLabel(path: string): string {
  const spec = RECORD_FIELDS.find((f) => f.path === path);
  if (spec === undefined) {
    throw new Error(
      `RECORD_FIELDS declares no spec for ${path}, so this spec cannot address its ` +
        'control by the label the panel actually renders.',
    );
  }
  return spec.label;
}

/** Every option the vendored official schema closes a path with. */
async function schemaEnum(api: APIRequestContext, path: string): Promise<string[]> {
  const res = await api.get(`${TRUSTED_API_BASE}/schema`);
  expect(res.ok(), `GET /schema -> ${res.status()}`).toBeTruthy();
  const { schema } = (await res.json()) as { schema: Record<string, unknown> };
  let node: unknown = schema;
  for (const segment of path.split('.')) {
    const properties = (node as { properties?: Record<string, unknown> } | null)?.properties;
    if (!properties) throw new Error(`no schema node at ${path}`);
    node = properties[segment];
    if (node === undefined || node === null) throw new Error(`no schema node at ${path}`);
  }
  const values = (node as { enum?: unknown }).enum;
  if (!Array.isArray(values) || !values.every((v) => typeof v === 'string')) {
    throw new Error(`${path} is not a closed string enum in the vendored schema`);
  }
  return values as string[];
}

/** One note stored on the record, as the notes operation reports it. */
interface ServerNote {
  id: string;
  run_id: string | null;
  text: string;
  source: string;
  state: string;
}

/**
 * The record's notes, over HTTP.
 *
 * A LOCAL HELPER RATHER THAN A `fixtures.ts` ADDITION. `ServerApi` is shared with
 * two other specs; a read only this file performs belongs here, where its single
 * caller can see it.
 */
async function serverNotes(api: APIRequestContext, id: string): Promise<ServerNote[]> {
  const res = await api.get(`${TRUSTED_API_BASE}/experiments/${id}/notes`);
  expect(res.ok(), `GET /notes -> ${res.status()} ${await res.text()}`).toBeTruthy();
  return ((await res.json()) as { notes: ServerNote[] }).notes;
}

/** One run's field value, off the run's own served document. */
async function runFieldValue(
  server: ServerApi,
  id: string,
  runId: string,
  path: string,
): Promise<unknown> {
  const body = (await server.runBody(id, runId)) as {
    run: { fields: Record<string, { value: unknown }> };
  };
  return body.run.fields[path]?.value;
}

/** A proposal by id, off the list operation. Throws rather than returning undefined. */
async function proposalById(
  server: ServerApi,
  id: string,
  proposalId: string,
): Promise<ServerProposal> {
  const found = (await server.proposals(id)).proposals.find((p) => p.proposal_id === proposalId);
  if (found === undefined) {
    throw new Error(`the record no longer lists proposal ${proposalId}`);
  }
  return found;
}

/** A proposal card addressed by path AND state — the card's own accessible name. */
function cardInState(page: Page, path: string, stateLabel: string) {
  return page.getByRole('article', {
    name: new RegExp(`^Proposal for ${path.replace(/\./g, '\\.')} — ${stateLabel}`),
  });
}

/** The mark planted on A's `window` in step 1. */
const SAME_DOCUMENT_MARK = 'isaac-two-actor-real-browser';

/**
 * Plant a value on `window` that a full page load destroys.
 *
 * A CLIENT-SIDE NAVIGATION KEEPS IT; A RELOAD DOES NOT. That is what makes every
 * "without a reload" claim in this file a MEASUREMENT rather than a description of
 * what the spec intended to do — a stray `page.goto` or `page.reload` added by a
 * later edit turns the claim false and fails the assertion instead of silently
 * weakening it.
 */
async function plantSameDocumentMark(page: Page): Promise<void> {
  await page.evaluate((mark) => {
    (window as unknown as Record<string, unknown>).__isaacDocumentMark = mark;
  }, SAME_DOCUMENT_MARK);
}

async function assertSameDocument(page: Page, message: string): Promise<void> {
  const held = await page.evaluate(
    () => (window as unknown as Record<string, unknown>).__isaacDocumentMark ?? null,
  );
  expect(held, message).toBe(SAME_DOCUMENT_MARK);
}

/**
 * Press Tab until the focused element satisfies `matches`, and return how many
 * presses it took.
 *
 * BOUNDED, AND A MISS THROWS. A helper that gave up silently would let a control
 * that is unreachable by keyboard read as a pass. The bound is generous rather than
 * tuned: this asserts REACHABILITY, and a specific tab count would be a brittle
 * claim about DOM order that no accessibility requirement makes.
 */
async function tabUntil(
  page: Page,
  what: string,
  matches: (active: ActiveElement) => boolean,
  max = 150,
): Promise<number> {
  for (let presses = 1; presses <= max; presses += 1) {
    await page.keyboard.press('Tab');
    if (matches(await activeElement(page))) return presses;
  }
  throw new Error(
    `${what} was not reached by ${max} Tab presses from where this walk started. ` +
      'Either it is not in the keyboard order, or the walk started somewhere unexpected.',
  );
}

interface ActiveElement {
  tag: string;
  text: string;
  id: string | null;
  ariaCurrent: string | null;
  ariaLabel: string | null;
  className: string;
  /** True when the focused element is inside the screen's `<main id="main">`. */
  inMain: boolean;
  /** The id of the nearest ancestor `.record-view-panel`, or null. */
  workspacePanel: string | null;
}

async function activeElement(page: Page): Promise<ActiveElement> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (el === null) {
      return {
        tag: '',
        text: '',
        id: null,
        ariaCurrent: null,
        ariaLabel: null,
        className: '',
        inMain: false,
        workspacePanel: null,
      };
    }
    const panel = el.closest('.record-view-panel');
    return {
      tag: el.tagName,
      text: (el.textContent ?? '').replace(/\s+/g, ' ').trim(),
      id: el.id === '' ? null : el.id,
      ariaCurrent: el.getAttribute('aria-current'),
      ariaLabel: el.getAttribute('aria-label'),
      className: typeof el.className === 'string' ? el.className : '',
      inMain: document.getElementById('main')?.contains(el) ?? false,
      workspacePanel: panel === null ? null : panel.id,
    };
  });
}

/** The page has no HORIZONTAL overflow: nothing sticks out past the viewport. */
async function horizontalOverflow(page: Page): Promise<{ scrollWidth: number; clientWidth: number }> {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

/** Open a SECOND browser context wired to this suite's app, and its first page. */
async function openSecondScientist(
  browser: Browser,
): Promise<{ context: BrowserContext; page: Page }> {
  /*
   * THE OPTIONS ARE PASSED EXPLICITLY, AND THAT IS NOT BOILERPLATE. Playwright
   * applies `use` (baseURL, viewport, reducedMotion) to the `context`/`page`
   * FIXTURES; a context created by hand from the `browser` fixture gets the
   * browser's defaults instead. Without `baseURL` every relative `page.goto` in B's
   * half would fail, and without the viewport B would run at a size this suite never
   * chose — which is exactly the kind of silent divergence between two actors that
   * would make a difference between them look like a product behaviour.
   */
  const context = await browser.newContext({
    baseURL: TRUSTED_BASE_URL,
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'reduce',
  });
  return { context, page: await context.newPage() };
}

/**
 * B types a transcript into the capture panel and finalizes it, through the UI.
 *
 * Returns the number of proposals the panel says it stored — read off the panel's
 * own "Review N Proposals" control, so the number asserted afterwards is the number
 * the READER was shown, not one this file computed.
 */
async function bFinalizesATranscript(
  bPage: Page,
  runId: string,
  text: string,
): Promise<number> {
  const capture = bPage.getByRole('region', { name: 'Transcript Capture' });
  await capture.getByRole('button', { name: 'Capture Experiment Notes' }).click();
  await capture.getByLabel('Run These Notes Describe').selectOption(runId);
  await capture.getByLabel('Transcript', { exact: true }).fill(text);
  await capture.getByRole('button', { name: 'Finalize and Read' }).click();

  const review = capture.getByRole('button', { name: /^Review \d+ Proposals?$/ });
  await expect(review, 'B: the reading reports what it stored').toBeVisible({
    timeout: DISCOVERY_DEADLINE,
  });
  const label = (await review.textContent()) ?? '';
  const parsed = Number(/^Review (\d+) Proposals?$/.exec(label.trim())?.[1]);
  expect(
    Number.isInteger(parsed),
    `B: the review control's label did not carry a count — ${JSON.stringify(label)}`,
  ).toBe(true);
  return parsed;
}

test.describe('two scientists, two real browsers, one record', () => {
  /*
   * ONE TEST FOR THE WALK, ONE FOR THE VIEWPORTS. The eleven steps below are a
   * SEQUENCE — step 8 is a statement about what step 7 left behind — so splitting
   * them would mean either eleven rebuilds of the same record or eleven tests
   * sharing mutable state through a module variable, which is the thing
   * `workers: 1` exists to avoid rather than to enable. Each step announces itself
   * in its assertion messages, so a failure names its step.
   */
  test('a colleague’s browser mints proposals, and A judges them without ever reloading', async ({
    page,
    browser,
    request,
    server,
  }) => {
    /*
     * THE PER-TEST DEADLINE, RAISED DELIBERATELY. The config's 60 s is sized for the
     * single-browser specs beside this one; this test drives TWO browser contexts
     * through eleven steps and waits on a jittered background poller several times,
     * each bounded by `DISCOVERY_DEADLINE`. A budget is not a timing assertion:
     * nothing below passes because of elapsed time, and a poller that has stopped
     * still fails at its own deadline rather than at this one.
     */
    test.setTimeout(420_000);

    const second = await openSecondScientist(browser);
    const bPage = second.page;
    try {
      // ══ STEP 1 — A builds the record through the website ════════════════════
      const id = await test.step('1 · A creates a record, describes it, and gives two runs different values', async () => {
        const created = await createExperimentThroughTheUi(page, 'Two-actor, two browsers');

        // ---- 1a. two RECORD-level values, through the real capture controls ----
        await switchWorkspace(page, 'fields');
        const techniqueOptions = await schemaEnum(request, 'system.technique');
        expect(
          techniqueOptions.length,
          'step 1: system.technique must be a closed enum for the panel to render a picker',
        ).toBeGreaterThan(1);
        const technique = techniqueOptions[0];

        const recordPanel = page.getByRole('region', {
          name: 'Record Description (record-level values)',
        });
        await recordPanel.getByRole('button', { name: /^Record Description/ }).click();

        /*
         * BEFORE, so the assertion after the save is a CHANGE rather than a state.
         *
         * `?? null` NORMALISES, AND THE REASON IS MEASURED RATHER THAN DEFENSIVE: the
         * served draft carries the path with an explicit `null` for a field the record
         * does not hold, not by omitting it, so a `toBeUndefined()` here fails with
         * `Received: null` on a record that is in fact empty. Both spellings mean "the
         * record holds nothing here", and this asserts that rather than which of the
         * two the serializer chose.
         */
        expect(
          (await server.recordFieldValue(created, 'system.technique')) ?? null,
          'step 1: the record holds no technique before A types one',
        ).toBeNull();
        expect(
          (await server.recordFieldValue(created, 'sample.material.name')) ?? null,
          'step 1: nor a material name',
        ).toBeNull();

        await recordPanel
          .getByLabel(recordFieldLabel('system.technique'), { exact: true })
          .selectOption(technique);
        await recordPanel
          .getByLabel(recordFieldLabel('sample.material.name'), { exact: true })
          .fill(MATERIAL_NAME);
        await recordPanel.getByRole('button', { name: 'Save record description' }).click();

        await expect
          .poll(
            () => server.recordFieldValue(created, 'system.technique'),
            'step 1: the website write of system.technique reached the server',
          )
          .toEqual(technique);
        expect(
          await server.recordFieldValue(created, 'sample.material.name'),
          'step 1: and so did the free-text one, in the same save',
        ).toEqual(MATERIAL_NAME);

        // ---- 1b. and they SURVIVE a reload -------------------------------------
        /*
         * THE ONLY RELOAD BEFORE STEP 9, AND IT HAPPENS BEFORE THE SENTINEL IS
         * PLANTED. Everything from step 2 onward depends on A's document surviving,
         * so this durability check is done first and the mark is planted after it.
         */
        await page.reload();
        await switchWorkspace(page, 'fields');
        await recordPanel.getByRole('button', { name: /^Record Description/ }).click();
        await expect(
          recordPanel.getByLabel(recordFieldLabel('sample.material.name'), { exact: true }),
          'step 1: the free-text record value is re-read from the server after a reload',
        ).toHaveValue(MATERIAL_NAME);
        await expect(
          recordPanel.getByLabel(recordFieldLabel('system.technique'), { exact: true }),
          'step 1: and so is the enum one',
        ).toHaveValue(technique);

        await plantSameDocumentMark(page);

        // ---- 1c. to Runs BY KEYBOARD ------------------------------------------
        /*
         * TAB TO THE SIDEBAR LINK AND PRESS ENTER — not a click and not a URL. The
         * workspace switcher is the record's primary wayfinding, and a destination
         * that can only be reached with a mouse is not a destination for everyone.
         */
        await page.locator('body').click({ position: { x: 2, y: 2 } });
        await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
        /*
         * NO ASSERTION ON THE RETURNED COUNT — CORRECTED AFTER INDEPENDENT REVIEW
         * (m-2). `tabUntil` returns a 1-based press count and THROWS on a miss, so
         * `expect(presses).toBeGreaterThan(0)` could not fail for any behaviour of the
         * page. **The guarantee is the throw**: reaching this line at all means the
         * link was focused by Tab within the bound.
         */
        await tabUntil(
          page,
          'step 1: the Runs workspace link',
          (active) => active.tag === 'A' && active.text === 'Runs',
        );
        await page.keyboard.press('Enter');
        await expect(
          page.getByRole('link', { name: 'Runs' }),
          'step 1: Enter on the focused link opened the Runs workspace',
        ).toHaveAttribute('aria-current', 'page');
        await assertSameDocument(page, 'step 1: the keyboard switch was a client-side navigation');

        // ---- 1d. two runs, two DIFFERENT values, via Next run ------------------
        await addRunThroughTheUi(page, 1);
        await addRunThroughTheUi(page, 2);
        const runs = await server.runs(created);
        expect(runs, 'step 1: two Add Run clicks produced two runs on the server').toHaveLength(2);
        return created;
      });

      const runs = await server.runs(id);
      const [runOne, runTwo] = runs;
      const environments = await schemaEnum(request, 'context.environment');
      expect(
        environments.length,
        'context.environment must offer at least three options: run one, run two, and the ' +
          'value B proposes must all be distinguishable',
      ).toBeGreaterThanOrEqual(3);
      const [envOne, envTwo, envProposed] = environments;
      expect(
        new Set([envOne, envTwo, envProposed]).size,
        'the three environment values in play must be DISTINCT, or a wrong read passes',
      ).toBe(3);

      await test.step('1 (continued) · run one and run two hold different values, and stay isolated', async () => {
        const runOneCard = await openRun(page, 0);
        await runOneCard.getByLabel('Environment').selectOption(envOne);
        /*
         * POLLED ON THE SERVER, NOT READ BACK OFF THE CONTROL. `RunCard` has no
         * per-field Save: `runAutosaveStore` flushes after a debounce through
         * `PATCH .../runs/{id}`. Reading the box back would confirm only that typing
         * works. Waiting for the SERVER also flushes the pending write before the
         * Next-run click below, which is what keeps the leave guard from opening its
         * confirmation dialog on an edit that has already landed.
         */
        await expect
          .poll(
            () => runFieldValue(server, id, runOne.id, 'context.environment'),
            'step 1: run one’s environment autosaved to the server',
          )
          .toEqual(envOne);

        /*
         * THE INHERITED / OVERRIDDEN DISTINCTION, IN THE RUN'S OWN WORDS. This is the
         * only place the two are named together, and it is a COUNT of each rather
         * than a completion figure — `inheritedSummary` in `RunCard.tsx`. Asserted as
         * a shape rather than as an exact pair of numbers: the numbers depend on what
         * the record happens to carry, and pinning them here would make this step a
         * test of the record's content rather than of the disclosure.
         */
        await expect(
          runOneCard.locator('.run-section-summary').filter({ hasText: /inherited/ }).first(),
          'step 1: the open run names what it inherits and what it overrides',
        ).toHaveText(/\d+ inherited · \d+ overridden on this run/);

        // ---- Next run, through the toolbar control ----------------------------
        await page.getByRole('button', { name: 'Next run', exact: true }).click();
        const runTwoCard = page.locator('.run-card:not([data-compact])');
        await expect(
          runTwoCard.locator('.run-card-name'),
          'step 1: Next run opened the SECOND run',
        ).toHaveText(runTwo.label);
        await runTwoCard.getByLabel('Environment').selectOption(envTwo);
        await expect
          .poll(
            () => runFieldValue(server, id, runTwo.id, 'context.environment'),
            'step 1: run two’s environment autosaved to the server',
          )
          .toEqual(envTwo);

        // ---- isolation, on the server -----------------------------------------
        expect(
          await runFieldValue(server, id, runOne.id, 'context.environment'),
          'step 1: writing run two did not touch run one',
        ).toEqual(envOne);

        await backToAllRuns(page);
        // ---- and isolation on the SCREEN, in the compact rows ------------------
        const rows = page.locator('.run-card[data-compact="true"]');
        await expect(rows, 'step 1: both runs are compact rows').toHaveCount(2);
        await expect(
          rows.nth(0).locator('.run-card-conditions'),
          'step 1: the first row summarises run one’s own conditions',
        ).toContainText(envOne);
        await expect(
          rows.nth(1).locator('.run-card-conditions'),
          'step 1: and the second row summarises run two’s — a different value',
        ).toContainText(envTwo);
        await expect(
          rows.nth(0).locator('.run-card-conditions'),
          'step 1: the first row does NOT show the second run’s value',
        ).not.toContainText(envTwo);
        /*
         * AND NEITHER ROW CLAIMS AN OVERRIDE, because neither has one. Writing a RUN
         * FIELD is not an override — an override is a run's deliberate divergence
         * from a value the RECORD holds, written through `/overrides` — so the chip
         * `RunCard` renders when `tally.overridden > 0` must be absent here. Asserted
         * rather than left implicit: a chip that appeared on every row would be the
         * distinction collapsing, and nothing else on this screen would say so.
         */
        await expect(
          rows.locator('.status-chip', { hasText: /overridden/ }),
          'step 1: no run claims an override it does not have',
        ).toHaveCount(0);
      });

      // ══ STEP 2 — A opens the review surface; it makes no recording claim ═════
      let seeded: ServerProposal | null = null;
      await test.step('2 · A opens Capture & Proposals: one entry action, no recording claim', async () => {
        /*
         * SEEDED FIRST, OVER HTTP, AND ONLY THIS ONE. It exists to prove the negative
         * control in step 4: a proposal that was ALREADY on the record when A's panel
         * hydrated must never be announced as an arrival. B could not create it — B's
         * proposals are the thing under test and would defeat the control by being
         * indistinguishable from an arrival.
         *
         * ITS TARGET IS RUN ONE AND A DIFFERENT PATH, so nothing later in this file
         * can move it, make it stale, or be confused with it.
         */
        const noteId = await server.captureNote(
          id,
          'SYNTHETIC — seeded before A opened the review surface, to prove hydration is silent',
        );
        seeded = await server.propose(id, {
          note_id: noteId,
          run_id: runOne.id,
          target_field_path: 'sample.material.formula',
          proposed_value: 'SyN2Th',
          rule: 'SYNTHETIC — seeded, never announced',
          client_request_key: 'real-browser-seed-1',
        });
        expect(seeded.state, 'step 2: the seeded proposal is open when A arrives').toBe('open');

        await switchWorkspace(page, 'capture');
        await assertSameDocument(page, 'step 2: switching workspace did not reload the page');

        const capture = page.getByRole('region', { name: 'Transcript Capture' });
        await expect(
          capture.getByRole('button', { name: 'Capture Experiment Notes' }),
          'step 2: collapsed, the panel offers exactly ONE entry action',
        ).toBeVisible();
        /*
         * AND NOTHING ELSE. `CAPTURE_COPY.entryOpen` is the only control the collapsed
         * panel renders; a second one here would be the "one clear primary action per
         * state" property the panel's own header table claims, quietly broken.
         */
        expect(
          await capture.locator('button:visible').count(),
          'step 2: and no second control beside it while collapsed',
        ).toBe(1);
        /*
         * NO RECORDING CLAIM WHILE COLLAPSED. The collapsed header deliberately names
         * only the path that always works — typing or pasting — because finalize
         * posts TEXT and turning a recording into text needs a transcription provider
         * this build never ships configured. A collapsed panel mentioning recording
         * would present it as an equally finished path, which is the C1 correction
         * `transcriptCaptureContent.ts` records making.
         */
        const collapsedText = (await capture.locator('.capture-sub').textContent()) ?? '';
        expect(collapsedText.length, 'step 2: the collapsed panel says something').toBeGreaterThan(0);
        for (const word of ['record', 'Record', 'audio', 'Audio', 'microphone', 'voice', 'Voice']) {
          expect(
            collapsedText,
            `step 2: the collapsed panel makes no recording claim — found ${JSON.stringify(word)}`,
          ).not.toContain(word);
        }
      });

      // ══ STEP 3 — B, a SECOND BROWSER, mints proposals through the UI ═════════
      const proposalsBeforeB = (await server.proposals(id)).proposals.length;
      let mintedByTranscript = 0;
      await test.step('3 · B (a second browser) captures a transcript and proposes from a note', async () => {
        await bPage.goto(`/record/${id}?view=capture`);
        await expect(
          bPage.getByRole('heading', { name: 'Ingestion Proposals' }),
          'step 3: B is on the same record’s Capture & Proposals workspace',
        ).toBeVisible();

        mintedByTranscript = await bFinalizesATranscript(bPage, runTwo.id, TRANSCRIPT_TEXT);
        expect(
          mintedByTranscript,
          'step 3: the reading stored at least one proposal',
        ).toBeGreaterThanOrEqual(1);

        // ---- what the SERVER actually holds, independently --------------------
        const afterTranscript = (await server.proposals(id)).proposals;
        expect(
          afterTranscript.length - proposalsBeforeB,
          'step 3: the server gained exactly the number the panel reported',
        ).toBe(mintedByTranscript);
        const minted = afterTranscript.filter((p) => p.proposal_id !== seeded?.proposal_id);
        expect(minted.length, 'step 3: the minted set is non-empty').toBeGreaterThan(0);
        for (const proposal of minted) {
          expect(
            proposal.run_id,
            `step 3: every proposal from this reading names the run B selected — ${proposal.target_field_path}`,
          ).toBe(runTwo.id);
        }
        const paths = minted.map((p) => p.target_field_path).sort();
        expect(
          paths,
          'step 3: the closed rule table read the two clauses the transcript wrote for it',
        ).toEqual([TRANSCRIPT_TARGETS.atmosphere.path, TRANSCRIPT_TARGETS.temperature.path].sort());
        const atmosphere = minted.find(
          (p) => p.target_field_path === TRANSCRIPT_TARGETS.atmosphere.path,
        );
        expect(
          atmosphere?.proposed_value,
          'step 3: the phrase is proposed exactly as written, matched against no vocabulary',
        ).toBe(TRANSCRIPT_TARGETS.atmosphere.value);
        expect(
          minted.find((p) => p.target_field_path === TRANSCRIPT_TARGETS.temperature.path)
            ?.proposed_value,
          'step 3: and the number is read as written, with no unit conversion',
        ).toBe(TRANSCRIPT_TARGETS.temperature.value);

        // ---- "Review N Proposals" MOVES FOCUS ---------------------------------
        await bPage.getByRole('button', { name: `Review ${mintedByTranscript} Proposals` }).click();
        const focused = await activeElement(bPage);
        expect(
          focused.id,
          'step 3: the review control moved focus to the proposals heading rather than ' +
            'only scrolling — a scroll is invisible to a keyboard reader',
        ).toBe('ingestion-proposals-heading');

        // ---- and B proposes from a stored NOTE, at a different target ---------
        const notes = await serverNotes(request, id);
        expect(notes.length, 'step 3: the finalized transcript stored notes').toBeGreaterThan(0);
        /*
         * THE PROSE SENTENCE, DELIBERATELY. It produced no candidate, so proposing
         * from it is a person deciding what the words mean — which is the act this
         * surface exists for, and is distinguishable from re-proposing something the
         * reader already read.
         */
        const proseNote = notes.find((n) => n.text.includes('cryostat'));
        expect(
          proseNote,
          'step 3: the sentence that named no field was stored as a note',
        ).toBeTruthy();

        /*
         * ── B RELOADS ITS OWN PAGE HERE, AND THAT IS A MEASURED PRODUCT FINDING
         * ── RATHER THAN A CONVENIENCE ────────────────────────────────────────
         *
         * `UnmappedNotesPanel` fetches the record's notes ONCE per mount and takes no
         * live-refresh input at all: its props are `{ experimentId }` and nothing
         * else, so it has no equivalent of the `activity` summary
         * `IngestionProposalsPanel` receives. Finalizing a transcript stores notes and
         * proposals in the SAME save, and on this screen the proposals appear on their
         * own while the notes — sitting one panel above them — do not, until the page
         * is reloaded. Measured: without this reload the card for a note the server is
         * already serving is simply not in the DOM (`element(s) not found`).
         *
         * It is B's page, not A's. A's document is untouched, so every "without a
         * reload" claim about A in steps 4-8 is unaffected — and this reload is itself
         * an honest depiction of what a scientist has to do today to reach the second
         * proposal-producing surface after using the first.
         */
        await bPage.reload();
        const noteCard = bPage.locator(`.note-card[data-note-id="${proseNote!.id}"]`);
        await expect(
          noteCard,
          'step 3: its card is on B’s screen once B reloads — see the finding above',
        ).toBeVisible();
        await noteCard.getByRole('button', { name: /^Propose a value from this note$/i }).click();
        await noteCard.getByLabel('Field this value is for').selectOption('context.environment');
        await noteCard.getByLabel('Run this value is about').selectOption(runTwo.id);
        await noteCard.getByLabel('Environment', { exact: true }).selectOption(envProposed);
        await noteCard.getByRole('button', { name: 'Propose This Value' }).click();

        await expect
          .poll(
            async () => (await server.proposals(id)).proposals.length,
            'step 3: B’s note-propose act stored one further proposal',
          )
          .toBe(proposalsBeforeB + mintedByTranscript + 1);
      });

      const fromNote = (await server.proposals(id)).proposals.find(
        (p) => p.target_field_path === 'context.environment',
      );
      expect(fromNote, 'step 3: the note-proposal is on the record').toBeTruthy();
      expect(fromNote!.run_id, 'step 3: and it names run two').toBe(runTwo.id);
      expect(fromNote!.proposed_value, 'step 3: with the value B chose').toBe(envProposed);

      const temperatureProposal = (await server.proposals(id)).proposals.find(
        (p) => p.target_field_path === TRANSCRIPT_TARGETS.temperature.path,
      )!;
      const atmosphereProposal = (await server.proposals(id)).proposals.find(
        (p) => p.target_field_path === TRANSCRIPT_TARGETS.atmosphere.path,
      )!;

      // ══ STEP 4 — A's page discovers them, once, without a reload ═════════════
      await test.step('4 · A is told once, and was NOT told about what was already there', async () => {
        await assertSameDocument(
          page,
          'step 4: A’s page has not been reloaded since step 1 — the whole arrival claim rests on it',
        );

        const proposals = page.getByRole('region', { name: 'Ingestion Proposals' });
        const arrivalNote = proposals.locator('.proposals-arrival-note-text');

        /*
         * THE RUNNING TOTAL REACHES THE NUMBER B MINTED — AND NOT ONE MORE.
         *
         * `arrivalTotalRef` accumulates since the last dismiss, so this counts every
         * arrival A has been told about. The seeded proposal was on the record BEFORE
         * A's panel hydrated, and `lastOpenCountRef === null` on the first load is the
         * guard that suppresses it. If hydration announced, this total would be one
         * higher — which is exactly the negative control this step exists to be.
         */
        const expectedTotal = mintedByTranscript + 1;
        await expect(arrivalNote, 'step 4: an arrival note appears on its own').toBeVisible({
          timeout: DISCOVERY_DEADLINE,
        });
        await expect
          .poll(() => arrivalNote.textContent(), {
            message: 'step 4: the note counts B’s arrivals and NOT the seeded proposal',
            timeout: DISCOVERY_DEADLINE,
          })
          .toBe(
            `At least ${expectedTotal} proposed changes arrived and are ready to review.`,
          );

        // ---- and the spoken half said something too ---------------------------
        const spoken =
          (await proposals.locator('p.sr-only[role="status"]').textContent()) ?? '';
        expect(
          spoken,
          'step 4: a screen-reader user was told as well, not only shown',
        ).toContain('proposed change');
        /*
         * AND NEITHER HALF LEAKS CONTENT. Both sentences are built from a COUNT and
         * fixed words, so a live region can never read out a scientific value nobody
         * asked for.
         */
        const visible = (await arrivalNote.textContent()) ?? '';
        for (const [where, sentence] of [
          ['visible', visible],
          ['spoken', spoken],
        ] as const) {
          expect(sentence, `step 4: the ${where} sentence names no proposed value`).not.toContain(
            String(TRANSCRIPT_TARGETS.atmosphere.value),
          );
          expect(sentence, `step 4: nor a field path`).not.toContain('context.');
        }

        /*
         * ── THE TOTAL DID NOT GROW ACROSS TWO FURTHER FEED POLLS ──────────────
         *
         * WHAT THIS ESTABLISHES, AND — CORRECTED AFTER INDEPENDENT REVIEW (I-1) —
         * WHAT IT DOES NOT.
         *
         * IT ESTABLISHES: across at least two further `GET .../changes` from A's own
         * page, the running total stayed at the number B's acts produced. That is a
         * real observation and it is worth having: it is the assertion that would fail
         * if anything on this screen re-counted a standing arrival while the page sat
         * still.
         *
         * ~~IT DISCRIMINATES AGAINST "fires once per POLL rather than once per
         * EVENT".~~ — **WITHDRAWN. MEASURED FALSE.** Removing the count-rise guard,
         * and separately removing the signal-dedupe early return, both leave this
         * assertion GREEN. The reason is structural: the announce effect's dependency
         * array is `[proposalSignal, reload, activity, experimentId]`
         * (`IngestionProposalsPanel.tsx:907`), and `activity` is `null` once the
         * record read has caught up — so an EMPTY poll re-runs the effect at all, and
         * there is nothing for a per-poll bug to fire from. The events-not-polls
         * property is enforced by that dependency array, and it is verified by READING
         * that line, not by anything this assertion can distinguish. Stating it as a
         * discrimination here (and in the evidence document) was an assertion claiming
         * more than it establishes, which is the exact defect class this file exists
         * to catch — so it is struck rather than reworded.
         *
         * THE SETTLE IS THE CLIENT'S OWN POLLER, NOT A SLEEP. Feed reads FROM A'S PAGE
         * are counted at the wire, and two further ones are waited for, so the window
         * this holds over is a real number of real polls rather than an elapsed time.
         */
        const feedReads: string[] = [];
        const feedRe = new RegExp(`/experiments/${id}/changes(\\?|$)`);
        page.on('request', (req) => {
          if (req.method() === 'GET' && feedRe.test(req.url())) feedReads.push(req.url());
        });
        const feedBefore = feedReads.length;
        await expect
          .poll(() => feedReads.length - feedBefore, {
            message: 'step 4: settle — wait for two further feed polls from the page itself',
            timeout: DISCOVERY_DEADLINE,
          })
          .toBeGreaterThanOrEqual(2);
        expect(
          await arrivalNote.textContent(),
          'step 4: and the total is UNCHANGED across two further feed polls (see the note ' +
            'above for what this does and does not discriminate against)',
        ).toBe(`At least ${expectedTotal} proposed changes arrived and are ready to review.`);

        // ---- the cards are on screen, including the seeded one ----------------
        await expect(
          proposalCard(page, 'sample.material.formula'),
          'step 4: the seeded proposal is VISIBLE — it was never hidden, only never announced',
        ).toBeVisible();
        await expect(
          proposalCard(page, TRANSCRIPT_TARGETS.temperature.path),
          'step 4: and so is B’s temperature proposal',
        ).toBeVisible();
      });

      // ══ STEP 5 — current vs proposed, and whose run ══════════════════════════
      await test.step('5 · a card distinguishes what the record holds now from what is proposed', async () => {
        const card = proposalCard(page, TRANSCRIPT_TARGETS.temperature.path);
        await expect(
          card.locator('.proposal-scope'),
          'step 5: the card names the run it is about',
        ).toHaveText(`On run ${runTwo.label}`);
        await expect(card.locator('.proposal-value-label').first()).toHaveText('Proposed value');
        await expect(card.locator('.proposal-value-body').first()).toContainText(
          String(TRANSCRIPT_TARGETS.temperature.value),
        );

        /*
         * NOTHING IS READ UNTIL A PERSON ASKS. One current-value read per card on
         * mount would be N requests for a question nobody asked, so the current value
         * sits behind its own control.
         *
         * THE REGION IS PRESENT AND EMPTY, NOT ABSENT, and the distinction is the
         * component's rather than this file's: `.proposal-current-body` is the card's
         * `aria-live` region and has to stay MOUNTED to be announced at all — a region
         * inserted with its content is never read out. So "nothing has been read yet"
         * is an EMPTY region, and asserting its absence would have been asserting a
         * different (and wrong) design. Measured: `toHaveCount(0)` fails here with
         * `Received: 1`.
         */
        await expect(
          card.locator('.proposal-current-body'),
          'step 5: the live region is mounted from the start, so an answer can be announced',
        ).toHaveCount(1);
        await expect(
          card.locator('.proposal-current-body'),
          'step 5: and it is EMPTY — nothing was read before a person asked',
        ).toBeEmpty();

        /*
         * ── THE ABSENCE IS REPORTED AS AN ABSENCE ─────────────────────────────
         *
         * Run two carries no temperature: B's proposal is the first thing to name that
         * path. The honest read is therefore "nothing is stored here", and the card has
         * to say so rather than render an empty box that reads like a failed read.
         * Asserted against the server first, so this is a claim about AGREEMENT rather
         * than about wording alone.
         */
        expect(
          await runFieldValue(server, id, runTwo.id, TRANSCRIPT_TARGETS.temperature.path),
          'step 5: the server holds nothing at the temperature target yet',
        ).toBeUndefined();
        await card.getByRole('button', { name: 'Show What the Record Holds Now' }).click();
        await expect(
          card.locator('.proposal-current-absent'),
          'step 5: and the card says the record holds nothing there, in words',
        ).toHaveText('No value is stored at this field path.');
        await expect(
          card.locator('.proposal-current-body'),
          'step 5: an absence is never dressed up as the proposed value',
        ).not.toContainText(String(TRANSCRIPT_TARGETS.temperature.value));

        /*
         * ── AND ON A TARGET THAT DOES HOLD SOMETHING, IT IS THE RUN'S OWN ─────
         *
         * `context.environment` is the one target in play where run one, run two and
         * the proposal all carry DIFFERENT values, which is what makes "the card read
         * the run this proposal names" a distinguishable claim rather than a
         * tautology. A correct value under a label claiming it came from the record
         * would still be a false statement about provenance, so the label is asserted
         * too.
         */
        const envCard = proposalCard(page, 'context.environment');
        await expect(
          envCard.locator('.proposal-scope'),
          'step 5: the note-proposal names run two as well',
        ).toHaveText(`On run ${runTwo.label}`);
        await expect(envCard.locator('.proposal-value-body').first()).toContainText(envProposed);
        await envCard.getByRole('button', { name: 'Show What the Record Holds Now' }).click();
        const envCurrent = envCard.locator('.proposal-current-body .proposal-value-body');
        await expect(envCurrent, 'step 5: the current value is RUN TWO’s').toContainText(envTwo);
        await expect(envCurrent, 'step 5: not run one’s').not.toContainText(envOne);
        await expect(envCurrent, 'step 5: and not the proposal’s').not.toContainText(envProposed);
        await expect(
          envCard.locator('.proposal-current-label'),
          'step 5: and the label says whose value it is',
        ).toHaveText(/run/i);

        /*
         * THE ATMOSPHERE CARD CARRIES THE PHRASE EXACTLY AS B TYPED IT — quoted from
         * the transcript, matched against no vocabulary, and not normalised into one.
         */
        const atmoCard = proposalCard(page, TRANSCRIPT_TARGETS.atmosphere.path);
        await expect(atmoCard.locator('.proposal-scope')).toHaveText(`On run ${runTwo.label}`);
        await expect(
          atmoCard.locator('.proposal-value-body').first(),
          'step 5: with the phrase exactly as B typed it',
        ).toContainText(TRANSCRIPT_TARGETS.atmosphere.value);
      });

      // ══ STEP 6 — a corrected acceptance, and a rejection ═════════════════════
      await test.step('6 · A corrects one value before accepting it, and rejects another', async () => {
        /*
         * ── A CORRECTION TO THE SLICE BRIEF, RECORDED RATHER THAN QUIETLY FIXED ──
         *
         * The brief for this spec asked this step to assert that
         * "Correct the Value, Then Accept" SUPERSEDES the original, leaves a NEW open
         * proposal, and leaves canonical run two UNCHANGED.
         *
         * MEASURED OVER HTTP AGAINST THIS BACKEND, ALL THREE ARE FALSE. The control
         * is an ACCEPT with `accepted_from: "edited"`: the original proposal moves to
         * `accepted`, no new proposal is created, and the CORRECTED value is written
         * to the run. That is what `IngestionProposalsPanel`'s own hint says it does
         * — *"Accepting this way records that the proposed value was WRONG and that
         * this is the corrected one"* — and `Supersede…`, a different control behind
         * the same disclosure, is the one that does not write.
         *
         * The real semantics are asserted below, and the brief's premise is written
         * out here so a future reader can see this was checked rather than assumed.
         */
        const runOneBefore = await server.runBody(id, runOne.id);
        const atmosphereBefore = await runFieldValue(
          server,
          id,
          runTwo.id,
          TRANSCRIPT_TARGETS.atmosphere.path,
        );
        const proposalCountBefore = (await server.proposals(id)).proposals.length;

        const card = cardInState(page, TRANSCRIPT_TARGETS.atmosphere.path, 'Awaiting your judgement');
        await expect(card, 'step 6: the atmosphere card is open for judgement').toBeVisible();
        await card.getByRole('button', { name: 'More Actions' }).click();
        await card.getByRole('button', { name: 'Correct the Value, Then Accept' }).click();
        const editor = card.getByLabel('The corrected value, as JSON');
        await expect(
          editor,
          'step 6: the editor is PREFILLED with the proposed value, so a correction is an edit',
        ).toHaveValue(JSON.stringify(TRANSCRIPT_TARGETS.atmosphere.value));
        await editor.fill(JSON.stringify(CORRECTED_ATMOSPHERE));
        await card.getByRole('button', { name: 'Accept the Corrected Value' }).click();

        await expect(
          cardInState(page, TRANSCRIPT_TARGETS.atmosphere.path, 'Accepted'),
          'step 6: the screen shows it accepted',
        ).toBeVisible();

        const reviewed = await proposalById(server, id, atmosphereProposal.proposal_id);
        expect(reviewed.state, 'step 6: the SAME proposal is accepted').toBe('accepted');
        expect(
          reviewed.accepted_from,
          'step 6: and the record keeps "corrected" apart from "as proposed"',
        ).toBe('edited');
        expect(reviewed.accepted_value, 'step 6: with the value A typed').toBe(CORRECTED_ATMOSPHERE);
        expect(
          (await server.proposals(id)).proposals.length,
          'step 6: correcting-then-accepting creates NO new proposal — the brief’s premise, ' +
            'measured false',
        ).toBe(proposalCountBefore);
        expect(
          await runFieldValue(server, id, runTwo.id, TRANSCRIPT_TARGETS.atmosphere.path),
          'step 6: the CORRECTED value is what reached run two',
        ).toBe(CORRECTED_ATMOSPHERE);
        /*
         * CORRECTED AFTER INDEPENDENT REVIEW (I-2). This read
         * `expect(atmosphereBefore).not.toBe(CORRECTED_ATMOSPHERE)` under the message
         * "the run held something else a moment ago" — and `atmosphereBefore` is
         * `undefined`, because nothing in this file writes that path before step 6.
         * The assertion was therefore unfalsifiable and its message was false. What is
         * actually true, and is the stronger claim, is that the acceptance wrote into
         * an EMPTY path: the run held nothing there at all.
         */
        expect(
          atmosphereBefore,
          'step 6: the run held NOTHING at this path before — the acceptance is the ' +
            'first thing to write it',
        ).toBeUndefined();
        expect(
          await server.runBody(id, runOne.id),
          'step 6: the run this proposal did not name was not modified',
        ).toEqual(runOneBefore);

        // ---- and a rejection writes NOTHING -----------------------------------
        const runOneBeforeReject = await server.runBody(id, runOne.id);
        const runTwoBeforeReject = await server.runBody(id, runTwo.id);
        const seededCard = cardInState(page, 'sample.material.formula', 'Awaiting your judgement');
        await seededCard.getByRole('button', { name: 'Reject…' }).click();
        await seededCard.getByLabel('Reason (optional)').fill(REJECT_REASON);
        await seededCard.getByRole('button', { name: 'Confirm Reject' }).click();
        await expect(
          cardInState(page, 'sample.material.formula', 'Rejected'),
          'step 6: the card is rejected on screen',
        ).toBeVisible();

        const rejected = await proposalById(server, id, seeded!.proposal_id);
        expect(rejected.state, 'step 6: and rejected on the server').toBe('rejected');
        expect(
          rejected.history.find((h) => h.action === 'reject')?.reason,
          'step 6: the reason A typed was stored verbatim',
        ).toBe(REJECT_REASON);
        expect(rejected.accepted_value, 'step 6: nothing was written').toBeNull();
        expect(
          await server.runBody(id, runOne.id),
          'step 6: rejecting left run one exactly as it was',
        ).toEqual(runOneBeforeReject);
        expect(
          await server.runBody(id, runTwo.id),
          'step 6: and run two too',
        ).toEqual(runTwoBeforeReject);
      });

      // ══ STEP 7 — B moves the target; A's accept is refused as stale ══════════
      await test.step('7 · B edits the target in a second browser, and A’s accept is refused', async () => {
        expect(
          (await proposalById(server, id, temperatureProposal.proposal_id)).target_stale,
          'step 7: the temperature proposal is FRESH before B moves its target',
        ).toBe(false);

        // ---- B, through the UI, in its own browser ----------------------------
        await bPage.goto(`/record/${id}?view=runs&run=${runTwo.id}`);
        const bEditor = bPage.locator('.run-card:not([data-compact])');
        await expect(bEditor, 'step 7: B has run two open').toBeVisible();
        await bEditor.getByLabel(/^Temperature/).fill(String(B_MOVED_TEMPERATURE));
        await expect
          .poll(
            () => runFieldValue(server, id, runTwo.id, TRANSCRIPT_TARGETS.temperature.path),
            'step 7: B’s typed temperature autosaved to the server',
          )
          .toBe(B_MOVED_TEMPERATURE);

        await expect
          .poll(
            async () =>
              (await proposalById(server, id, temperatureProposal.proposal_id)).target_stale,
            'step 7: the proposal’s target is now reported stale',
          )
          .toBe(true);

        // ---- A, who has still not reloaded, tries to accept -------------------
        await assertSameDocument(page, 'step 7: A’s page is still the document from step 1');
        const card = cardInState(page, TRANSCRIPT_TARGETS.temperature.path, 'Awaiting your judgement');
        await expect(
          card.locator('.proposal-target-state'),
          'step 7: the card tells the reader the value moved',
        ).toContainText(/CHANGED since this proposal was made/, { timeout: DISCOVERY_DEADLINE });
        /*
         * ACCEPT IS STILL OFFERED, AND THAT IS DELIBERATE RATHER THAN A DEFECT.
         * `acceptUnavailableReason` fails OPEN — `target_stale` was read a moment ago
         * and the value at the target can move back — and the card's own copy says the
         * SERVER decides. So the guarantee under test here is the server's refusal
         * surfacing on the screen, which is what the click below measures.
         */
        await card.getByRole('button', { name: 'Accept as Proposed' }).click();
        await expect(
          page.locator('.proposals-error'),
          'step 7: the refusal is on A’s screen, in a scientist’s words',
        ).toContainText('has changed since this proposal was made');
        await expect(
          page.locator('.proposals-error'),
          'step 7: and it says plainly that nothing was written',
        ).toContainText('Nothing was written');

        expect(
          (await proposalById(server, id, temperatureProposal.proposal_id)).state,
          'step 7: the proposal is still open — a refusal is not a judgement',
        ).toBe('open');
        expect(
          await runFieldValue(server, id, runTwo.id, TRANSCRIPT_TARGETS.temperature.path),
          'step 7: and the canonical value is B’s edit alone, never the proposed one',
        ).toBe(B_MOVED_TEMPERATURE);
      });

      // ══ STEP 8 — A accepts a still-fresh proposal ════════════════════════════
      const runOneBeforeAccept = await server.runBody(id, runOne.id);
      const cursorBeforeAccept = (await server.changes(id, { limit: 200 })).next_cursor;
      const versionBeforeAccept = await server.version(id);
      const revBeforeAccept = Number(
        versionBeforeAccept.slice(versionBeforeAccept.lastIndexOf('.') + 1),
      );
      expect(
        Number.isFinite(revBeforeAccept),
        'step 8: the version token must carry a numeric rev, or the feed floor below is not a floor',
      ).toBe(true);

      await test.step('8 · the acceptance lands on exactly the run it named, and nowhere else', async () => {
        expect(
          (await proposalById(server, id, fromNote!.proposal_id)).target_stale,
          'step 8: staleness is scoped to the (run, path) pair — B moved a DIFFERENT path ' +
            'on the SAME run, and this proposal is still fresh',
        ).toBe(false);

        const card = cardInState(page, 'context.environment', 'Awaiting your judgement');
        await expect(card, 'step 8: the note-proposal is open for judgement').toBeVisible({
          timeout: DISCOVERY_DEADLINE,
        });
        /*
         * READ FROM THE SERVER IMMEDIATELY BEFORE THE CLICK — CORRECTED AFTER
         * INDEPENDENT REVIEW (m-1). The "it is a change" assertion below used to
         * compare `envTwo` with `envProposed`, which are two constants this file
         * derived from the schema and already asserted distinct: it could not fail for
         * any behaviour of the product. The comparison now has one side that is a
         * MEASUREMENT of what run two held a moment before the acceptance.
         */
        const environmentBeforeAccept = await runFieldValue(
          server,
          id,
          runTwo.id,
          'context.environment',
        );
        await card.getByRole('button', { name: 'Accept as Proposed' }).click();
        await expect(
          cardInState(page, 'context.environment', 'Accepted'),
          'step 8: the screen shows it accepted',
        ).toBeVisible();

        const accepted = await proposalById(server, id, fromNote!.proposal_id);
        expect(accepted.state, 'step 8: the server recorded the acceptance').toBe('accepted');
        expect(accepted.accepted_from, 'step 8: as proposed, not corrected').toBe('candidate');
        expect(accepted.accepted_value, 'step 8: with the value B chose').toBe(envProposed);
        expect(accepted.applied_run_id, 'step 8: applied to the run it named').toBe(runTwo.id);

        // ---- ONLY run two changed --------------------------------------------
        expect(
          await runFieldValue(server, id, runTwo.id, 'context.environment'),
          'step 8: run two carries the accepted value',
        ).toBe(envProposed);
        expect(
          environmentBeforeAccept,
          'step 8: and it is a change — this is what run two actually held immediately ' +
            'before the acceptance, read from the server',
        ).not.toBe(envProposed);
        expect(
          environmentBeforeAccept,
          'step 8: and what it held was the value A entered in step 1, so the acceptance ' +
            'overwrote a real value rather than filling a hole',
        ).toBe(envTwo);
        expect(
          await server.runBody(id, runOne.id),
          'step 8: run one’s WHOLE document is unchanged, rev and version included',
        ).toEqual(runOneBeforeAccept);

        // ---- attribution ------------------------------------------------------
        const acceptEntry = accepted.history.find((h) => h.action === 'accept');
        expect(acceptEntry, 'step 8: the acceptance is in the history').toBeTruthy();
        expect(
          acceptEntry?.actor_subject,
          'step 8: attributed to the subject this deployment vouches for',
        ).toBe(FIXTURE_ACTOR_SUBJECT);
        expect(
          acceptEntry?.actor_trust_basis,
          'step 8: on a basis that says what it is worth',
        ).toBe(FIXTURE_TRUST_BASIS);
        /*
         * AND PROPOSING STAYS UNATTRIBUTED — the boundary rather than a gap. B made
         * this proposal through the website, in a real browser, and the record still
         * names nobody for it: creating a proposal requires no actor in any
         * deployment, and inventing one would be the fabrication this programme
         * refuses. Only the JUDGEMENT is attributed.
         */
        const proposeEntry = accepted.history.find((h) => h.action === 'propose');
        expect(proposeEntry?.actor_subject, 'step 8: proposing named nobody').toBeNull();
        expect(proposeEntry?.actor_trust_basis).toBe('unattributed');
        expect(
          accepted.trust_basis,
          'step 8: and the proposal’s own trust basis is the proposer’s, not the reviewer’s',
        ).toBe('unattributed');

        // ---- the change feed reports it, above the cursor ---------------------
        const feed = await server.changes(id, { cursor: cursorBeforeAccept, limit: 200 });
        const entries = feed.changes.filter(
          (c) => c.kind === 'proposal' && c.entity_id === fromNote!.proposal_id,
        );
        expect(entries, 'step 8: the accepted proposal appears ONCE in the feed').toHaveLength(1);
        expect(entries[0].state, 'step 8: in its current state').toBe('accepted');
        expect(
          feed.changes.filter((c) => c.kind === 'run' && c.entity_id === runOne.id),
          'step 8: and run one is ABSENT from it — it did not move',
        ).toHaveLength(0);
        expect(
          feed.changes.length,
          'step 8: the page reports something, so the loop below is not vacuous',
        ).toBeGreaterThan(0);
        for (const entry of feed.changes) {
          expect(
            entry.changed_at_rev,
            `step 8: ${entry.kind} ${entry.entity_id} at rev ${entry.changed_at_rev} must be ` +
              `above the record’s rev when the cursor was taken (${revBeforeAccept})`,
          ).toBeGreaterThan(revBeforeAccept);
        }

        // ---- the Runs workspace has it, WITHOUT any navigation at all ---------
        /*
         * READ OUT OF THE HIDDEN, STILL-MOUNTED RUNS PANEL. `RecordWorkbench` keeps a
         * workspace mounted once visited and hides it with the `hidden` attribute, so
         * `RunsSection` has been live since step 1 and its own pollers are running
         * while A sits on Capture & Proposals. Asserting the value in its DOM — before
         * switching to it — is therefore a claim about the LIVE REFRESH rather than
         * about a fresh mount, which is what a switch-then-look assertion would
         * actually have measured.
         */
        await expect
          .poll(
            () => page.locator('#record-workspace-runs').innerText(),
            {
              message:
                'step 8: the mounted Runs workspace picked the accepted value up on its own, ' +
                'with no navigation and no reload',
              timeout: DISCOVERY_DEADLINE,
            },
          )
          .toContain(envProposed);
        await assertSameDocument(page, 'step 8: and still no reload');

        // ---- and it is VISIBLE once the reader goes there ---------------------
        await switchWorkspace(page, 'runs');
        const rows = page.locator('.run-card[data-compact="true"]');
        await expect(
          rows.nth(1).locator('.run-card-conditions'),
          'step 8: run two’s row shows the accepted value',
        ).toContainText(envProposed);
        await expect(
          rows.nth(0).locator('.run-card-conditions'),
          'step 8: run one’s row does not',
        ).not.toContainText(envProposed);

        // ---- validation reads it ---------------------------------------------
        const verdict = await server.validate(id);
        expect(verdict.official_validator_ran, 'step 8: the official validator ran').toBe(true);
        /*
         * THE RECORD DOES NOT EXPORT YET, AND THAT IS THE MEASUREMENT RATHER THAN A
         * DISAPPOINTMENT: a record created through the product's own path still owes
         * blocking questions nothing in this test answered. The honest two-part claim
         * is that the accepted value IS what the served draft holds, and that no
         * refusal names it.
         */
        expect(verdict.ok, 'step 8: it does not export yet, and says so').toBe(false);
        const messages = verdict.errors.map((e) => `${e.path} ${e.message}`);
        expect(
          messages.length,
          'step 8: the dry run enumerated its refusals, so the loop below is not vacuous',
        ).toBeGreaterThan(0);
        for (const message of messages) {
          expect(message, `step 8: no refusal names the accepted value — ${message}`).not.toContain(
            envProposed,
          );
        }
        expect(
          await runFieldValue(server, id, runTwo.id, 'context.environment'),
          'step 8: and what the validator read at the target is the accepted value',
        ).toBe(envProposed);
        expect(verdict.runs?.length, 'step 8: the dry run judged each run').toBe(2);
      });

      // ══ STEP 9 — durability across a reload ═════════════════════════════════
      await test.step('9 · everything survives a reload of A’s browser', async () => {
        const health = await (await request.get(`${TRUSTED_API_BASE}/health`)).json();
        expect(
          health.experiment_storage.backend,
          'step 9: this backend is FILESYSTEM-backed, so PostgreSQL durability is CI’s claim ' +
            '(apps/api/tests/test_proposal_durability.py, real-engine scenarios) and not this file’s',
        ).toBe('filesystem');

        await page.reload();
        await openWorkspace(page, id, 'runs');
        const rows = page.locator('.run-card');
        await expect(rows, 'step 9: both runs survive').toHaveCount(2);
        await expect(rows.nth(0)).toBeVisible();
        await expect(rows.nth(1)).toBeVisible();
        await expect(
          rows.nth(1).locator('.run-card-conditions'),
          'step 9: with run two’s accepted value',
        ).toContainText(envProposed);

        await switchWorkspace(page, 'capture');
        await expect(
          cardInState(page, 'context.environment', 'Accepted'),
          'step 9: the accepted proposal survives',
        ).toBeVisible();
        await expect(
          cardInState(page, 'sample.material.formula', 'Rejected'),
          'step 9: and so does the rejected one — a rejection is KEPT, not deleted',
        ).toBeVisible();
        await expect(
          cardInState(page, TRANSCRIPT_TARGETS.temperature.path, 'Awaiting your judgement'),
          'step 9: and the refused one is still open, exactly as the refusal said',
        ).toBeVisible();

        /*
         * AND THE SENTINEL IS GONE, which is what makes every earlier
         * `assertSameDocument` a real measurement rather than a ritual: this proves a
         * reload actually destroys the mark those assertions relied on surviving.
         */
        const held = await page.evaluate(
          () => (window as unknown as Record<string, unknown>).__isaacDocumentMark ?? null,
        );
        expect(
          held,
          'step 9: a reload destroys the same-document mark — the negative control for steps 2-8',
        ).toBeNull();
        await plantSameDocumentMark(page);
      });

      // ══ STEP 10 — nothing here can Submit, export or accept on its own ══════
      await test.step('10 · no proposal, agent or tool can finalize a record', async () => {
        /*
         * (a) THE FINALIZING CONTROL IS NOT ON THE PROPOSALS SURFACE AT ALL.
         *
         * A CORRECTION TO THE BRIEF, MEASURED: this build ships no control labelled
         * "Submit" anywhere — there is no portal submission in the product (Ready to
         * Export says so in its own words). The act that finalizes a record is
         * `Export Official Record + Sidecar`, on the Ready to Export screen. So the
         * assertion the brief asks for is made about the control that actually exists,
         * and the absence of a "Submit" one is asserted too rather than assumed.
         */
        await switchWorkspace(page, 'capture');
        const proposals = page.getByRole('region', { name: 'Ingestion Proposals' });
        /*
         * THE REGION IS ASSERTED PRESENT BEFORE ANYTHING IS COUNTED IN IT — ADDED
         * AFTER INDEPENDENT REVIEW (m-3). Four `toHaveCount(0)` checks scoped to a
         * locator that matched NOTHING would all pass, and would read as "the
         * proposals surface offers no submit control" while measuring "there is no
         * proposals surface". Non-vacuity first, then the counts.
         */
        await expect(
          proposals,
          'step 10: the proposals surface is on screen, so the counts below are about it',
        ).toBeVisible();
        for (const forbidden of [/submit/i, /export/i, /publish/i, /finali[sz]e/i]) {
          await expect(
            proposals.getByRole('button', { name: forbidden }),
            `step 10: no control on the proposals surface offers ${forbidden}`,
          ).toHaveCount(0);
        }
        await expect(
          page.getByRole('button', { name: /^Submit/i }),
          'step 10: and this build has no Submit control on the record screen at all',
        ).toHaveCount(0);

        /*
         * ---- THE FINALIZING ACT LIVES ON READY TO EXPORT, AND ON THIS RECORD IT
         * ---- IS NOT EVEN RENDERED --------------------------------------------
         *
         * A SECOND CORRECTION TO THE BRIEF, MEASURED. The brief expected a disabled
         * control here. `ExportReadiness` renders the export button inside
         * `{pendingZero && dryRunOk && …}`, so on a record that still owes blocking
         * questions the control does not EXIST — the gate is an ABSENCE, not a greyed
         * button, and the screen says why in its own words instead. That is a stronger
         * property than the one the brief asked for, and it is asserted as what it is.
         */
        await page.goto(`/record/${id}/export`);
        /*
         * ADDRESSED BY LEVEL AND A SUBSTRING RATHER THAN BY `LABELS.screenExport`, and
         * the reason is a toolchain fact rather than a preference: importing
         * `src/lib/labels.ts` pulls `src/lib/api.ts` into the e2e program, which reads
         * `import.meta.env` — a Vite type the e2e `tsconfig` does not carry, so the
         * import fails `tsc` with `Property 'env' does not exist on type 'ImportMeta'`.
         * `recordFields.ts` (imported above) has no such dependency, which is why the
         * field labels ARE read from the app.
         */
        expect(page.url(), 'step 10: A is on the export route').toMatch(/\/export$/);
        await expect(
          page.getByRole('heading', { level: 1 }),
          'step 10: this is the scientist-facing export screen',
        ).toContainText(/export/i);
        await expect(
          page.getByRole('button', { name: 'Export Official Record + Sidecar' }),
          'step 10: and the export control is ABSENT while the record still blocks export',
        ).toHaveCount(0);
        await expect(
          page.locator('.preexport-title'),
          'step 10: the screen says why, and names the count rather than only refusing',
        ).toContainText(/still block export/);
        /*
         * AND STILL NO SUBMIT ANYWHERE. Ready to Export's own copy says it plainly —
         * *"There is no override and no portal submission"* — and this is the screen a
         * reader would look for one on.
         */
        await expect(
          page.getByRole('button', { name: /^Submit/i }),
          'step 10: the export screen offers no Submit either',
        ).toHaveCount(0);

        /*
         * (b) NO PERMITTED MCP TOOL CAN ACCEPT, SUBMIT OR EXPORT.
         *
         * `PERMITTED_TOOL_NAMES` is parsed out of `mcp/policy.py` rather than fetched,
         * and the reason is measured below: this deployment mounts NO MCP transport,
         * so there is no `tools/list` to call. Reading the policy source is the
         * established precedent here — `src/__tests__/connect-your-agent.test.tsx`
         * does exactly this, and its own comment records the defect that hardened the
         * parser (a quoted phrase in a comment INSIDE the literal read as an extra
         * tool), which is why comment text is stripped.
         *
         * The Python-side proofs are CITED, not reproduced:
         * `apps/api/tests/test_mcp_boundaries.py`
         *   ::test_a_scope_named_submit_cannot_be_expressed_at_all
         *   ::test_registering_a_submit_tool_raises_rather_than_being_ignored
         *   ::test_no_mcp_scope_can_reach_an_accepting_finalising_or_exporting_operation
         */
        const policySource = readFileSync(
          join(repoRoot(), 'apps/api/isaac_api/mcp/policy.py'),
          'utf8',
        );
        const block = policySource.match(/PERMITTED_TOOL_NAMES = frozenset\(\s*\{([^}]*)\}/);
        expect(block, 'step 10: PERMITTED_TOOL_NAMES is readable in policy.py').toBeTruthy();
        const toolNames =
          (block as RegExpMatchArray)[1]
            .split('\n')
            .map((line) => line.replace(/#.*$/, ''))
            .join('\n')
            .match(/"([^"]+)"/g)
            ?.map((quoted) => quoted.slice(1, -1)) ?? [];
        expect(toolNames.length, 'step 10: the permitted set is non-empty').toBeGreaterThan(0);
        for (const forbidden of ['accept', 'approve', 'submit', 'export', 'publish', 'delete']) {
          expect(
            toolNames.filter((name) => name.includes(forbidden)),
            `step 10: no permitted tool name contains "${forbidden}" — ${JSON.stringify(toolNames)}`,
          ).toEqual([]);
        }
        const mcp = await request.post(`${TRUSTED_API_BASE}/mcp`, {
          headers: { 'content-type': 'application/json' },
          data: { jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} },
        });
        expect(
          mcp.status(),
          'step 10: this deployment mounts no MCP transport, so there is no route at all',
        ).toBe(404);
      });

      // ══ STEP 11 — the whole record screen, by keyboard alone ════════════════
      await test.step('11 · every workspace is reachable and usable by keyboard', async () => {
        await openWorkspace(page, id, 'fields');

        /*
         * THE SPINE FIRST, THEN THE WORKSPACES. `WorkflowSpine` renders the
         * server-derived pipeline above `RecordWorkspaceNav` in the same sidebar, so a
         * Tab walk from the top of the page meets it first. It is walked THROUGH
         * rather than activated: its steps are gated destinations that would leave the
         * record screen, and this step is about the record's own four workspaces.
         */
        for (const workspace of ['Record Fields', 'Runs', 'Capture & Proposals', 'Graph'] as const) {
          await page.locator('body').click({ position: { x: 2, y: 2 } });
          await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
          await tabUntil(
            page,
            `step 11: the ${workspace} workspace link`,
            (active) => active.tag === 'A' && active.text === workspace,
          );
          await page.keyboard.press('Enter');
          await expect(
            page.getByRole('link', { name: workspace, exact: true }),
            `step 11: Enter moved aria-current to ${workspace}`,
          ).toHaveAttribute('aria-current', 'page');

          /*
           * AND THE WORKSPACE'S OWN CONTENT IS IN THE KEYBOARD ORDER RIGHT AFTER IT.
           *
           * STATED PRECISELY, BECAUSE THE APP DOES NOT DO WHAT THE BRIEF ASSUMED: this
           * application does NOT move focus into the newly opened region — activating
           * an in-app `<Link>` leaves focus on the link, which is ordinary SPA
           * behaviour and is not a defect on its own, since the sidebar precedes
           * `<main>` in DOM order and a skip link exists. What CAN be asserted, and is
           * the property a keyboard reader actually needs, is that continuing to Tab
           * from the activated link lands inside the workspace panel that was just
           * opened — and inside `<main>`, not back into some other rail.
           */
          /*
           * AGAIN, THE GUARANTEE IS `tabUntil`'S THROW, not a count assertion (m-2).
           * Reaching the next line means a focusable element inside `<main>` and
           * inside SOME workspace panel was reached within 60 presses; WHICH panel is
           * the assertion below, and that one can fail.
           */
          await tabUntil(
            page,
            `step 11: a focusable control inside the ${workspace} workspace`,
            (active) => active.inMain && active.workspacePanel !== null,
            60,
          );
          const active = await activeElement(page);
          expect(
            active.workspacePanel,
            `step 11: and the panel it landed in is the one ${workspace} opened`,
          ).toBe(
            {
              'Record Fields': 'record-workspace-fields',
              Runs: 'record-workspace-runs',
              'Capture & Proposals': 'record-workspace-capture',
              Graph: 'record-workspace-graph',
            }[workspace],
          );
        }

        // ---- and the Assistant drawer, at 768 ---------------------------------
        /*
         * 768 IS WHERE THE RAIL BECOMES A SLIDE-OVER. `AssistantDrawer`'s trigger is
         * CSS-hidden at desktop, so this is the only width at which the dialog
         * semantics apply at all — which is why the viewport moves here rather than
         * this being asserted at 1280 where it would silently test nothing.
         */
        await page.setViewportSize({ width: 768, height: 1024 });
        await page.locator('body').click({ position: { x: 2, y: 2 } });
        await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
        await tabUntil(
          page,
          'step 11: the Assistant drawer trigger',
          (active) => active.className.includes('assistant-drawer-trigger'),
        );
        await page.keyboard.press('Enter');
        const drawer = page.locator('.assistant-drawer-panel');
        await expect(
          drawer,
          'step 11: the drawer opened as a modal dialog',
        ).toHaveAttribute('aria-modal', 'true');
        const composer = page.getByLabel('Ask the assistant a question');
        await tabUntil(
          page,
          'step 11: the assistant composer, from inside the open drawer',
          (active) => active.ariaLabel === 'Ask the assistant a question',
          40,
        );
        await expect(composer, 'step 11: and it is the composer that has focus').toBeFocused();
        await page.keyboard.press('Escape');
        await expect(
          drawer,
          'step 11: Escape closes it again',
        ).not.toHaveAttribute('aria-modal', 'true');
        await page.setViewportSize({ width: 1280, height: 800 });
      });
    } finally {
      await second.context.close();
    }
  });

  /**
   * THE NARROW VIEWPORTS, ON THEIR OWN RECORD.
   *
   * A SEPARATE TEST RATHER THAN A LOOP INSIDE THE ONE ABOVE, for a reason the walk
   * makes unavoidable: an arrival is announced ONCE, and the running total is
   * cumulative, so re-observing "an arrival is legible" at five widths inside that
   * test would mean either five colleagues' acts (five different assertions) or four
   * observations of one already-standing note (which is a weaker claim wearing the
   * same words). Here the arrival happens once, at the widest of the five, and the
   * remaining four assert LEGIBILITY of the standing note and the card — which is
   * exactly what a viewport pass is for.
   */
  test('the arrival and the card stay legible from 1280 down to 320', async ({
    page,
    browser,
    request,
    server,
  }) => {
    test.setTimeout(300_000);

    const second = await openSecondScientist(browser);
    const bPage = second.page;
    try {
      const id = await createExperimentThroughTheUi(page, 'Two-actor, narrow viewports');
      await addRunThroughTheUi(page, 1);
      const runs = await server.runs(id);
      expect(runs, 'one run is enough for a run-scoped proposal').toHaveLength(1);

      await switchWorkspace(page, 'capture');
      await expect(
        page.getByRole('region', { name: 'Ingestion Proposals' }).locator('.proposals-empty'),
        'A’s review surface starts empty, so the arrival below is unambiguous',
      ).toBeVisible();
      await plantSameDocumentMark(page);

      // B, in its own browser, mints through the capture panel.
      await bPage.goto(`/record/${id}?view=capture`);
      const minted = await bFinalizesATranscript(bPage, runs[0].id, TRANSCRIPT_TEXT);
      expect(minted, 'B minted at least one proposal').toBeGreaterThanOrEqual(1);
      expect(
        (await server.proposals(id)).proposals.length,
        'and the server holds exactly those',
      ).toBe(minted);

      const proposals = page.getByRole('region', { name: 'Ingestion Proposals' });
      const arrivalNote = proposals.locator('.proposals-arrival-note-text');
      await expect(arrivalNote, 'A is told, at the widest viewport').toBeVisible({
        timeout: DISCOVERY_DEADLINE,
      });
      await assertSameDocument(page, 'and A has not reloaded');

      /*
       * THE FOUR NARROWER WIDTHS. 1024 is the drawer breakpoint, 768 a tablet, 390 a
       * current phone, 320 the narrowest width this repository's own a11y baseline
       * measures (`e2e/a11y-baseline.ts`'s `NARROW_WIDTHS`).
       */
      const viewports = [
        { width: 1024, height: 768 },
        { width: 768, height: 1024 },
        { width: 390, height: 844 },
        { width: 320, height: 568 },
      ] as const;

      const card = proposalCard(page, TRANSCRIPT_TARGETS.temperature.path);
      for (const viewport of viewports) {
        const at = `${viewport.width}x${viewport.height}`;
        await test.step(`legible at ${at}`, async () => {
          await page.setViewportSize({ width: viewport.width, height: viewport.height });

          await expect(
            arrivalNote,
            `${at}: the arrival note is still visible — it has no fixed width and must not ` +
              'be pushed off screen',
          ).toBeVisible();
          await expect(
            card,
            `${at}: and the card a reader was sent to is on screen`,
          ).toBeVisible();
          await expect(
            card.locator('.proposal-value-body').first(),
            `${at}: with the proposed value readable`,
          ).toContainText(String(TRANSCRIPT_TARGETS.temperature.value));
          await expect(
            card.locator('.proposal-scope'),
            `${at}: and the run it is about still named`,
          ).toHaveText(`On run ${runs[0].label}`);
          /*
           * AND THE CARD IS NOT MERELY "VISIBLE" WHILE BEING OFF THE SIDE. A box whose
           * right edge sits past the viewport passes `toBeVisible` and is unreadable,
           * which is precisely the failure a narrow pass exists to catch.
           */
          const box = await card.boundingBox();
          expect(box, `${at}: the card has a box`).not.toBeNull();
          expect(
            Math.round(box!.x + box!.width),
            `${at}: the card’s right edge is inside the viewport`,
          ).toBeLessThanOrEqual(viewport.width);

          const overflow = await horizontalOverflow(page);
          expect(
            overflow.scrollWidth,
            `${at}: the page does not scroll sideways — scrollWidth ${overflow.scrollWidth} vs ` +
              `clientWidth ${overflow.clientWidth}`,
          ).toBe(overflow.clientWidth);
        });
      }

      await assertSameDocument(page, 'no viewport change reloaded the page');
      // Restored, so nothing after this test inherits a 320px window.
      await page.setViewportSize({ width: 1280, height: 800 });
      expect(
        (await server.proposals(id)).proposals.length,
        'and looking at a record at five widths created nothing',
      ).toBe(minted);
      expect(
        (await request.get(`${TRUSTED_API_BASE}/experiments/${id}`)).ok(),
        'the record is still there',
      ).toBeTruthy();
    } finally {
      await second.context.close();
    }
  });
});

/**
 * The repository root, WALKED UP FROM THE WORKING DIRECTORY.
 *
 * NOT `__dirname` AND NOT `import.meta.url` — `two-actor-workflow.spec.ts` records
 * paying for the first (Playwright loads specs as ES modules, where the CommonJS
 * global does not exist). Walking up from `process.cwd()` holds whether Playwright
 * is invoked from `apps/web` (the documented way) or from the repository root (the
 * way CI does it). A MISS THROWS: a spec that silently found no policy file would
 * report success for zero coverage.
 */
function repoRoot(): string {
  const marker = join('apps', 'api', 'isaac_api', 'mcp', 'policy.py');
  let dir = resolve(process.cwd());
  for (;;) {
    if (existsSync(join(dir, marker))) return dir;
    const parent = dirname(dir);
    if (parent === dir) {
      throw new Error(
        `could not find ${marker} in any ancestor of ${process.cwd()}. Step 10 reads the ` +
          'permitted MCP tool set out of that file; without it there is nothing to check.',
      );
    }
    dir = parent;
  }
}
