/**
 * RECORD VERIFICATION / STATISTICS — every runtime state the section can be in,
 * driven in a real browser at every width the product claims to support, each
 * one screenshotted AND asserted.
 * @responsive
 *
 * ── What this file is for ───────────────────────────────────────────────────
 *
 * `src/__tests__/record-verification.test.tsx` drives these states in jsdom,
 * where no layout exists and nothing can be looked at. Nothing anywhere put the
 * section's FAILURE, STALE, REFRESHING and REFRESH-FAILED states in front of a
 * real layout engine at 320px, which is precisely where a panel of long
 * JSON-pointer schema paths and a grouped bar chart are most likely to come
 * apart.
 *
 * A NOTE ON THE CROSS-REFERENCES BELOW. This file was written on a local
 * integration branch where five PRs were merged together, and its production
 * home is PR #63, which owns `RecordVerification.tsx`. Two neighbours it cites —
 * `specs/visual-sweep.spec.ts` and the 1440 entry in `specs/layout-widths.spec.ts`
 * — belong to the visual-sweep work and are NOT on this branch. The citations are
 * kept because they are accurate about where that reasoning is written down, and
 * flagged here because a reference that resolves to nothing is worse than one
 * that is explained. Nothing in this file DEPENDS on either: it never reads
 * `layout-baseline.ts`, so sweeping 1440 needs no baseline entry from them.
 *
 * IT IS NOT A PIXEL BASELINE. `toHaveScreenshot` is not used and no PNG is
 * committed, for three reasons: there is no webfont, so macOS and
 * `ubuntu-latest` disagree permanently; CLAUDE.md §9 forbids committing derived
 * artifacts; and a pixel diff answers "did anything change?", which is not the
 * question. The assertions answer what has an objective answer; the images are
 * for what does not.
 *
 * ── THE HONESTY RULE, WHICH IS THE POINT OF THIS FILE ───────────────────────
 *
 * This screen reports on TWO corpora that carry very different weight, and one
 * of them has never been read. The authorized 30-record private sample is an
 * approved capability that HAS NOT RUN — no scan of it has ever executed, here
 * or anywhere. A screenshot captioned in a way that implies otherwise would be a
 * false record of a measurement, which is the exact defect class CLAUDE.md §15
 * catalogues this project shipping and correcting repeatedly.
 *
 * So every state id — and therefore every attachment name, which embeds it —
 * ends in exactly ONE of four provenance classifiers, and
 * `PROVENANCE_CLASSIFIERS` is asserted to partition the declared set:
 *
 *   `real-public-reference`   the figures on screen were produced by the real
 *                             backend's real run over the ten PUBLIC upstream
 *                             ISAAC example records vendored in this repo. No
 *                             interception, or interception only of a LATER
 *                             re-read (state 7), which is stated in the label.
 *   `synthetic-fixture`       the figures on screen were fabricated by this
 *                             spec or by `src/test/verificationFixtures.ts`.
 *                             They describe nothing real, and no run — public
 *                             or private — produced them.
 *   `intercepted-error`       no figure is on screen; the state was produced by
 *                             an injected failure (an error envelope, or a
 *                             request the transport was made to give up on).
 *   `unavailable-state`       no figure is on screen; the PRODUCT itself is
 *                             saying it has nothing to state yet (a read in
 *                             flight, a run in progress, an unattributable
 *                             personal dashboard). Nothing is claimed and
 *                             nothing failed.
 *
 * State 4 — the authorized-private aggregate — is a SHAPE ONLY, and its label
 * says so in words: "shape only — no private run has occurred". It exists to
 * prove the section can render that corpus's disclosure without ever mixing it
 * up with the public one, and for nothing else.
 *
 * ── Where the images come from, stated so nobody over-reads them ────────────
 *
 * Each state names the ELEMENT that IS the state and that element is
 * screenshotted, not the frame. This app's scroll container is not the document
 * (`div.screen-card` is `overflow: hidden`, `main#main` is `overflow: auto` —
 * see `helpers/layout.ts`), so a `fullPage` shot would be the first screenful
 * and would cut a long report in half. An element shot scrolls the whole element
 * through the viewport and captures all of it, which is what a reviewer of a
 * seven-panel section needs.
 *
 * ── One project, six widths ────────────────────────────────────────────────
 *
 * Same mechanism and the same reason as `layout-widths.spec.ts` and
 * `visual-sweep.spec.ts`: extra Playwright projects multiply the WHOLE suite
 * (axe scans included) and perturb the count-based ratchet in
 * `e2e/a11y-baseline.ts`. So this file runs in ONE project and moves the
 * viewport itself. `@responsive` is only the tag the config maps to more than
 * one project; the skips elsewhere are visible in the report on purpose.
 *
 * ── The `app` fixture is deliberately NOT used ─────────────────────────────
 *
 * `app.goto()` injects a stylesheet that zeroes every animation. That is right
 * for a layout spec and wrong here: with it injected, "reduced motion is
 * respected" would be a test of the injected stylesheet rather than of the app's
 * own `@media (prefers-reduced-motion: reduce)` block (`src/styles/base.css:267`).
 * This file navigates with a bare `page.goto` so the reduced-motion assertion is
 * genuinely probative. Statistics is an ORDINARY-scope surface (the workspace is
 * permanently empty), so no worked-example scope is needed and none is entered —
 * nothing here reads, writes or touches the shared session the other projects
 * are measuring.
 *
 * ── Read-only, and nothing is polled — WHAT IS AND IS NOT ENFORCED ─────────
 *
 * `GET /api/runtime/verification` is the only backend call this file causes on
 * purpose, and it is a read. Every mutation of behaviour here is a `page.route`
 * inside the browser: the intercepted requests never leave the page.
 *
 * The section itself does not poll — one read on mount, one more per press
 * (`RecordVerification.tsx`'s `useVerificationReport`, which holds a single
 * effect per `attempt` with an `alive` flag and a cleanup). But read that as a
 * statement about the product TODAY, not as something this file holds in place.
 * An independent review added a real uncleaned `setInterval` re-reading the
 * endpoint every 700ms and ALL ELEVEN TESTS STILL PASSED; the whole-test request
 * total moved from 1939 to 1965 and nothing looked at it. The network guard
 * below allowlists ORIGINS, so any number of same-origin API calls is permitted.
 *
 * An earlier version of this paragraph asserted the no-polling property flatly,
 * which read as a guarantee this suite provides. It does not, and the honest
 * form is that the guard would not notice.
 */

import { API_BASE, BASE_URL } from '../env';
import { expect, test } from '../fixtures';
import { horizontalPageScroll, render, renderedFontFamily, findClippedText } from '../helpers/layout';
import { VERIFICATION_MODE_LABELS } from '../../src/lib/verificationContract';
import {
  verificationErrorEnvelope,
  verificationFailureEnvelope,
  verificationReportOk,
  verificationReportPrivateSample,
  verificationRunningEnvelope,
} from '../../src/test/verificationFixtures';
import type { APIRequestContext, Locator, Page, Route } from '@playwright/test';

/** The single project this file runs in. See the header. */
const HOST_PROJECT = 'desktop-1280x800';

/**
 * The widths swept. 1440 is the widest layout an ordinary modern laptop renders;
 * 320 is the WCAG 1.4.10 reflow width and the narrowest the product claims to
 * support; 390 is the modern iPhone width.
 *
 * The list the brief names, which is `visual-sweep.spec.ts`'s list minus 375:
 * 375 is already a Playwright project of its own and 390 and 320 bracket it, so
 * running it here would buy a third measurement between two it sits between.
 * Stated rather than left as an apparent omission.
 */
const WIDTHS = [1440, 1280, 1024, 768, 390, 320] as const;

/** Taller than the width sweep's 812, to put more of each panel in a shot. */
const VIEWPORT_HEIGHT = 900;

/**
 * The four provenance classifiers. EVERY state id ends with exactly one, and the
 * membership test below proves it — a state whose id carried none, or two, would
 * produce an attachment a reviewer could not source.
 */
const PROVENANCE_CLASSIFIERS = [
  'real-public-reference',
  'synthetic-fixture',
  'intercepted-error',
  'unavailable-state',
] as const;

/**
 * THE DECLARED SET. Every id here must be captured at every width, and nothing
 * outside it may be captured. Ordering here does not matter (the comparison is
 * on sorted sets); ordering in `STATES` does not matter either — each state
 * navigates for itself and cleans up its own routes.
 */
const EXPECTED_STATE_IDS = [
  'read-in-flight-unavailable-state',
  'run-in-progress-unavailable-state',
  'report-shown-real-public-reference',
  'private-sample-disclosure-synthetic-fixture',
  'stale-report-synthetic-fixture',
  'refreshing-over-stale-synthetic-fixture',
  'last-known-good-after-failed-refresh-real-public-reference',
  'source-did-not-answer-intercepted-error',
  'transport-timeout-intercepted-error',
  'program-error-intercepted-error',
  'technical-details-collapsed-real-public-reference',
  'technical-details-expanded-real-public-reference',
  'my-stats-no-attribution-unavailable-state',
] as const;

type StateId = (typeof EXPECTED_STATE_IDS)[number];

/* ─────────────────────────────────────────────────────────────────────────────
 * Wire bodies
 * ────────────────────────────────────────────────────────────────────────────*/

/** The route glob for the one endpoint this file intercepts. Host-agnostic. */
const VERIFICATION_ROUTE = '**/api/runtime/verification';

/**
 * SCHEMA PATHS AUTHORED BY THIS SPEC. They describe nothing real and no run
 * produced them.
 *
 * They exist because the real public-reference report currently has ZERO format
 * findings, so both issue histograms are empty and the schema-path chart is not
 * drawn at all — which means the brief's "long JSON-pointer paths wrap" could
 * only ever be answered by absence. These are deliberately longer than anything
 * the real report has emitted, so the wrap measurement has something to measure
 * at 320px. They are shipped only inside `synthetic-fixture` states.
 */
const LONG_SCHEMA_PATHS = [
  'properties/measurement_series/items/properties/instrument/properties/beamline/properties/monochromator_energy_calibration_uncertainty',
  'properties/dataset/properties/raw_data_pointer/properties/checksum_sha256_of_the_referenced_artifact',
  'properties/sample/properties/composition/items/properties/element_fraction_uncertainty_upper_bound',
] as const;

const LONG_PATH_HISTOGRAM = {
  cells: [
    { key: LONG_SCHEMA_PATHS[0], count: 12 },
    { key: LONG_SCHEMA_PATHS[1], count: 9 },
    { key: LONG_SCHEMA_PATHS[2], count: 7 },
  ],
  suppressed_categories: 2,
  suppressed_total: 6,
  floor: 5,
};

/**
 * The authorized-private-sample SHAPE. **No private run has occurred**; this is
 * `src/test/verificationFixtures.ts`'s hand-written body with this file's long
 * schema paths substituted in. Every number in it is invented.
 *
 * It is imported rather than retyped so that a change to the wire contract
 * breaks this spec too, instead of leaving it asserting against a shape the
 * backend no longer sends.
 */
const PRIVATE_SAMPLE_SHAPE = {
  ...verificationReportPrivateSample,
  format_shadow: {
    ...verificationReportPrivateSample.format_shadow,
    records_passing: 21,
    records_failing: 9,
    failures_by_schema_path: LONG_PATH_HISTOGRAM,
  },
  /**
   * THE TWO DATABASE SAFEGUARDS ARE OVERRIDDEN TO `not_applicable`, AND THIS IS
   * THE MOST IMPORTANT LINE IN THE FILE.
   *
   * `verificationReportPrivateSample` sets both to `'verified'` — reasonably,
   * for a unit test that needs to prove the affirmative rendering exists. But
   * this spec does something a unit test does not: it PHOTOGRAPHS the result and
   * attaches the image as evidence. An independent review caught what that
   * combination produced. The captured element read:
   *
   *     Records Evaluated  30
   *     Read-Only Database Access       Verified
   *     Parameterized Database Queries  Verified
   *
   * in the affirmative tone — a green picture of a completed read-only pass over
   * 30 private production records. **No private record has ever been evaluated
   * and no database connection has ever been opened.** The only disclaimer was
   * the Playwright attachment NAME, and the attachment name does not travel with
   * the file: on disk it is `playwright-report/data/<sha1>.png`, which CI
   * uploads as an artifact. The caption stays in the report; the image walks
   * away on its own.
   *
   * That is a false record of a measurement — the exact defect class this file's
   * own header is written to prevent, produced by the file itself.
   *
   * `not_applicable` is not a weaker claim than `verified`; it is the TRUE one.
   * `verificationContract.ts:182-196` calls keeping these three states distinct
   * "the single most consequential rule in this module", and renders a distinct
   * reason for `not_applicable`: this run opened no connection, so there was no
   * transaction to keep read-only and no query to parameterize. That sentence is
   * exactly right about the authorized-but-unexecuted private mode, so the fix
   * makes the capture MORE faithful to the product, not less.
   *
   * The record counts are deliberately left alone. They are what makes the
   * disclosure render at all, the state exists to prove the section names this
   * corpus without borrowing the public one's label, and the burnt-in provenance
   * stamp (see `stampProvenance`) now says on the image itself that every figure
   * in it was fabricated.
   */
  safeguards: {
    ...verificationReportPrivateSample.safeguards,
    transaction_read_only: 'not_applicable',
    parameterized_queries_only: 'not_applicable',
  },
};

/** A synthetic PUBLIC-mode report aged past the backend's 3600s cache lifetime. */
const STALE_PUBLIC_SHAPE = {
  ...verificationReportOk,
  metadata: { ...verificationReportOk.metadata, cache_age_seconds: 7200 },
  format_shadow: {
    ...verificationReportOk.format_shadow,
    failures_by_schema_path: LONG_PATH_HISTOGRAM,
  },
};

/* ─────────────────────────────────────────────────────────────────────────────
 * Small helpers
 * ────────────────────────────────────────────────────────────────────────────*/

const PUBLIC_LABEL = VERIFICATION_MODE_LABELS.public_reference;
const PRIVATE_LABEL = VERIFICATION_MODE_LABELS.authorized_private_sample;

/** The section `StatsSection` renders for Record Verification. */
const section = (page: Page): Locator =>
  page.locator('section[aria-labelledby="stats-verification"]');

/**
 * What each classifier says, in words, when it is burnt into the image.
 *
 * Short enough to survive 320px, and phrased so the reader needs no key: the
 * word "FABRICATED" does not require knowing what `synthetic-fixture` means.
 */
const STAMP_TEXT: Record<(typeof PROVENANCE_CLASSIFIERS)[number], string> = {
  'real-public-reference': '',
  'synthetic-fixture': 'SYNTHETIC — every figure below is FABRICATED. No run produced it.',
  'intercepted-error': 'SYNTHETIC — failure injected by the test. No real failure occurred.',
  'unavailable-state': 'TEST CAPTURE — nothing is claimed here; the product has nothing to state yet.',
};

/**
 * Burn the provenance into the captured pixels, and return a handle that removes it.
 *
 * WHY THIS EXISTS, since a reviewer will otherwise reasonably ask why the test
 * injects DOM into the product it is measuring. Every assertion in this file has
 * already run by the time this is called, so the stamp cannot influence a single
 * one — and it is removed immediately after `screenshot()`, before the next state.
 *
 * The file previously carried its provenance ONLY in the `testInfo.attach` name.
 * That is a real disclosure inside the HTML report, and it is worth nothing once
 * the image leaves it: Playwright writes attachments to
 * `playwright-report/data/<sha1>.png`, whose filename contains neither the state
 * id nor the classifier, and CI uploads that whole directory as an artifact. An
 * independent review found the consequence — a green, affirmative capture of a
 * completed private database run over 30 production records, with the read-only
 * transaction check reading "Verified", when no private record has ever been
 * evaluated and no database connection has ever been opened. A screenshot pasted
 * into a slide deck or a mentor e-mail carries its pixels and nothing else.
 *
 * `real-public-reference` is stamped with NOTHING, on purpose. Those figures were
 * produced by the real backend's real run over the ten public upstream records,
 * so a "synthetic" banner would be its own false statement — and stamping every
 * image identically would make the stamp meaningless, which is how a disclaimer
 * becomes decoration.
 */
async function stampProvenance(target: Locator, stateId: string): Promise<() => Promise<void>> {
  const classifier = PROVENANCE_CLASSIFIERS.find((c) => stateId.endsWith(c));
  const text = classifier ? STAMP_TEXT[classifier] : '';
  // An UNCLASSIFIED id is stamped as unattributable rather than left bare: the
  // partition test would fail for it anyway, but it runs in a SEPARATE test, so
  // without this the width sweep would still have attached a clean-looking image
  // first. Never leave the strongest-looking artifact as the unlabelled one.
  const banner = text || (classifier ? '' : 'UNATTRIBUTED CAPTURE — provenance unknown.');
  if (!banner) return async () => undefined;

  await target.evaluate((el, msg) => {
    const node = el.ownerDocument.createElement('div');
    node.setAttribute('data-e2e-provenance-stamp', '');
    node.textContent = msg;
    node.style.cssText = [
      'background:#7f1d1d',
      'color:#fff',
      'font:700 12px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace',
      'padding:6px 8px',
      'margin:0 0 8px',
      'border-radius:4px',
      'text-align:left',
      'letter-spacing:.02em',
      // The stamp must never be the thing that is clipped away.
      'position:relative',
      'z-index:2147483647',
      'white-space:normal',
      'overflow-wrap:anywhere',
    ].join(';');
    el.prepend(node);
  }, banner);

  // Removed through the same element handle, so a state whose route teardown has
  // already run cannot leave the stamp behind for the next capture.
  return async () => {
    await target
      .evaluate((el) => {
        el.querySelectorAll('[data-e2e-provenance-stamp]').forEach((n) => n.remove());
      })
      .catch(() => undefined);
  };
}

/** A bare navigation — no injected stylesheet. See the header. */
async function open(page: Page, path: string): Promise<void> {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main#main')).toBeVisible({ timeout: 20_000 });
}

/** Fulfil the verification read with a body, in the browser. Nothing is sent. */
async function serve(page: Page, body: unknown): Promise<void> {
  await page.route(VERIFICATION_ROUTE, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  );
}

/**
 * A route with two PHASES — the shape both refresh states need: a good result on
 * screen, then a re-read that hangs or fails. Returns the switch that ends the
 * first phase.
 *
 * ── Why a switch and not "the first request" ────────────────────────────────
 *
 * MEASURED, and it cost two failing states before it was: under the Vite dev
 * server the app runs inside React's `<StrictMode>` (`src/main.tsx:25`), which
 * deliberately invokes every effect TWICE in development. So the mount issues
 * `GET /api/runtime/verification` twice, not once — the hook's `alive` flag
 * discards the first, exactly as designed, and nothing is wrong. But a handler
 * keyed on "call number 1" would then serve the SECOND, discarded read the
 * failure body and leave the section stuck in its loading state, and the failure
 * would look like a product defect rather than a test artefact.
 *
 * Phases are switched by the test at the moment it presses Refresh, which is the
 * boundary the states actually care about and is independent of how many reads
 * the mount happens to issue.
 */
async function servePhased(
  page: Page,
  first: (route: Route) => Promise<void>,
  rest: (route: Route) => Promise<void>
): Promise<() => void> {
  let inRest = false;
  await page.route(VERIFICATION_ROUTE, async (route) => {
    if (inRest) await rest(route);
    else await first(route);
  });
  return () => {
    inRest = true;
  };
}

/**
 * What the REAL backend says right now, read out of band.
 *
 * Used for two things: to prefer the real `running` state over an intercepted
 * one when the backend genuinely is mid-sweep (the brief's requirement), and to
 * refuse to run the real-report states against a backend that is not ready
 * rather than mislabel whatever came back.
 */
async function realStatus(request: APIRequestContext): Promise<string> {
  const res = await request.get(`${API_BASE}/runtime/verification`, { failOnStatusCode: false });
  if (!res.ok()) return `http_${res.status()}`;
  const body = (await res.json()) as { status?: unknown };
  return typeof body.status === 'string' ? body.status : 'unreadable';
}

/**
 * Wait for the real report to exist. The backend's sweep takes ~20s after boot
 * and answers `running` until it lands; the result is then cached for an hour.
 * Bounded, and it FAILS rather than skipping — a real-corpus state that cannot
 * be reached is a finding.
 */
async function waitForRealReport(request: APIRequestContext): Promise<string> {
  const deadline = Date.now() + 120_000;
  let status = await realStatus(request);
  while (status === 'running' && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 2_000));
    status = await realStatus(request);
  }
  return status;
}

/* ─────────────────────────────────────────────────────────────────────────────
 * The states
 * ────────────────────────────────────────────────────────────────────────────*/

interface Ctx {
  page: Page;
  request: APIRequestContext;
  width: number;
  /** Set by a state that had to fall back from the real thing; appended to the
   *  attachment label so the report says which one a reviewer is looking at. */
  note: (text: string) => void;
}

interface VerificationState {
  readonly id: StateId;
  /** One line for the attachment name — what a reviewer is looking at, and
   *  where its data came from. */
  readonly what: string;
  /** Reach the state and return the ELEMENT THAT IS THE STATE (screenshotted,
   *  and checked for a real hit box). Must throw if the state is not reached. */
  readonly reach: (ctx: Ctx) => Promise<Locator>;
  /** Console messages this state DELIBERATELY causes. Anything else fails. */
  readonly allowedConsole?: readonly RegExp[];
  /** Does this state put a decoded report (figures, charts, safeguards) on
   *  screen? Drives the shared report assertions. */
  readonly rendersReport?: boolean;
  /** Which corpus the report on screen claims, when it renders one. */
  readonly corpus?: 'public' | 'private';
  /** Does this state render this file's long authored schema paths? */
  readonly longPaths?: boolean;
  readonly cleanup?: (ctx: Ctx) => Promise<void>;
}

/** Release handles for held-open routes, so cleanup can never leave one hanging. */
const HOLD_RELEASE_MS = 45_000;

function gate(): { wait: Promise<void>; release: () => void } {
  let release!: () => void;
  const wait = new Promise<void>((r) => (release = r));
  setTimeout(release, HOLD_RELEASE_MS);
  return { wait, release };
}

let openGates: (() => void)[] = [];

const STATES: readonly VerificationState[] = [
  {
    id: 'read-in-flight-unavailable-state',
    what:
      'A read still in flight — the polite status panel, not a blank panel and not a zero. ' +
      'The REAL request is HELD OPEN by the browser and released afterwards; nothing is faked ' +
      'and no figure is shown.',
    async reach({ page }) {
      const g = gate();
      openGates.push(g.release);
      await page.route(VERIFICATION_ROUTE, async (route) => {
        await g.wait;
        await route.continue();
      });
      await open(page, '/statistics');
      const s = section(page);
      await expect(s).toBeVisible({ timeout: 20_000 });
      const loading = s.locator('div.fetch-state[role="status"]');
      await expect(loading).toBeVisible({ timeout: 20_000 });
      await expect(loading).toContainText(/Loading the verification report/i);
      // Nothing is claimed while the read is in flight.
      await expect(s.locator('.stats-cards')).toHaveCount(0);
      await expect(s.getByRole('button', { name: 'Refresh the verification report' })).toHaveCount(0);
      return s;
    },
    async cleanup({ page }) {
      openGates.forEach((r) => r());
      openGates = [];
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'run-in-progress-unavailable-state',
    what:
      'The verification program is mid-run — stated as running, with no earlier result shown ' +
      'in its place and no count assumed to be zero.',
    async reach({ page, request, note }) {
      /*
       * PREFER THE REAL ONE. The backend genuinely answers `running` for ~20s
       * after boot and then caches the result for an hour, so whether this is
       * reachable for real depends entirely on when the suite is run. Which one
       * happened is recorded in the attachment label rather than left implicit.
       */
      const live = await realStatus(request);
      if (live === 'running') {
        note('REAL backend `running` — the sweep was genuinely in progress, not intercepted');
      } else {
        note(
          `INTERCEPTED status envelope — the real backend answered "${live}", so its ~20s ` +
            'running window had already elapsed and could not be observed'
        );
        await serve(page, verificationRunningEnvelope);
      }
      await open(page, '/statistics');
      const s = section(page);
      await expect(s.getByText('Verification Run in Progress')).toBeVisible({ timeout: 20_000 });
      await expect(s).toContainText(/no results to state yet/i);
      await expect(s).toContainText(/No earlier result is shown in its place/i);
      await expect(s.locator('.stats-cards')).toHaveCount(0);
      return s;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'report-shown-real-public-reference',
    what:
      'The REAL report from the REAL backend, over the ten PUBLIC upstream ISAAC example ' +
      'records vendored in this repository. No interception anywhere in this state.',
    rendersReport: true,
    corpus: 'public',
    async reach({ page, request }) {
      const status = await waitForRealReport(request);
      expect(
        status,
        'the real backend must be able to produce a real public-reference report for this ' +
          'state; anything else would mean captioning some other body as the real one'
      ).toBe('ok');
      await open(page, '/statistics');
      const s = section(page);
      await expect(s.getByRole('heading', { name: 'Record Verification' })).toBeVisible({
        timeout: 30_000,
      });
      await expect(s.locator('.stats-cards')).toHaveCount(1, { timeout: 30_000 });
      return s;
    },
  },
  {
    id: 'private-sample-disclosure-synthetic-fixture',
    what:
      'The authorized-private-sample corpus disclosure — shape only — no private run has ' +
      'occurred. Every number in this capture was fabricated by the test suite; it exists ' +
      'only to prove the section names that corpus without ever borrowing the public one’s label.',
    rendersReport: true,
    corpus: 'private',
    longPaths: true,
    async reach({ page }) {
      await serve(page, PRIVATE_SAMPLE_SHAPE);
      await open(page, '/statistics');
      const s = section(page);
      await expect(s.locator('.stats-verify-corpus-label')).toHaveText(PRIVATE_LABEL, {
        timeout: 20_000,
      });
      // The wire token, verbatim and beside the product label — never instead.
      await expect(s.locator('.stats-verify-corpus-mode .mono')).toHaveText(
        'authorized_private_sample'
      );
      await expect(s.locator('.stats-cards')).toHaveCount(1);
      return s;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'stale-report-synthetic-fixture',
    what:
      'A cached result older than the backend’s own one-hour lifetime — the figures look ' +
      'identical to a fresh run, so the age is stated in words. Synthetic body; describes no run.',
    rendersReport: true,
    corpus: 'public',
    longPaths: true,
    async reach({ page }) {
      await serve(page, STALE_PUBLIC_SHAPE);
      await open(page, '/statistics');
      const s = section(page);
      await expect(s.locator('.stats-cards')).toHaveCount(1, { timeout: 20_000 });
      const stale = s.locator('div.stats-unavailable').filter({ hasText: /past the/i }).first();
      await expect(stale).toBeVisible();
      await expect(stale).toContainText(/2 hours ago/);
      await expect(stale).toContainText(/past the 60 minutes the API holds one for/i);
      await expect(stale).toContainText(/a newer run may already have replaced them/i);
      return s;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'refreshing-over-stale-synthetic-fixture',
    what:
      'A re-read in flight while the STALE result stays on screen — the control is busy and ' +
      'disabled, and the copy says the figures below are still the ones last read. Synthetic body.',
    rendersReport: true,
    corpus: 'public',
    longPaths: true,
    async reach({ page }) {
      const g = gate();
      openGates.push(g.release);
      const beginRefreshPhase = await servePhased(
        page,
        (route) =>
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(STALE_PUBLIC_SHAPE),
          }),
        async (route) => {
          await g.wait;
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(STALE_PUBLIC_SHAPE),
          });
        }
      );
      await open(page, '/statistics');
      const s = section(page);
      await expect(s.locator('.stats-cards')).toHaveCount(1, { timeout: 20_000 });

      const live = s.locator('p.stats-verify-live[role="status"]');
      await expect(live, 'the live region must exist before it has anything to say').toHaveCount(1);
      await expect(live).toHaveText('');

      const refresh = s.getByRole('button', { name: 'Refresh the verification report' });
      beginRefreshPhase();
      await refresh.click();

      await expect(refresh).toHaveAttribute('aria-busy', 'true');
      await expect(refresh).toBeDisabled();
      // Its accessible NAME must not change — see `ReadControls`.
      await expect(refresh).toHaveText('Refresh the verification report');
      await expect(s.locator('.stats-verify-refreshing')).toContainText(
        /the results below are still the ones last read/i
      );
      await expect(live).toHaveText('Re-reading the verification report.');
      // The previous result is still on screen, not replaced by a skeleton.
      await expect(s.locator('.stats-cards')).toHaveCount(1);
      await expect(s.locator('div.stats-unavailable').filter({ hasText: /past the/i })).toHaveCount(1);
      return s;
    },
    async cleanup({ page }) {
      openGates.forEach((r) => r());
      openGates = [];
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'last-known-good-after-failed-refresh-real-public-reference',
    what:
      'A re-read that FAILED while the last good result stays on screen. The figures are the ' +
      'REAL public-reference report (the first read was not intercepted); only the SECOND ' +
      'request was made to fail, in the browser.',
    rendersReport: true,
    corpus: 'public',
    allowedConsole: [/Failed to load resource/i, /net::ERR_/i],
    async reach({ page, request }) {
      const status = await waitForRealReport(request);
      expect(status, 'the good result under this failure must be the real one').toBe('ok');
      const beginRefreshPhase = await servePhased(
        page,
        (route) => route.continue(),
        (route) => route.abort('connectionrefused')
      );
      await open(page, '/statistics');
      const s = section(page);
      await expect(s.locator('.stats-cards')).toHaveCount(1, { timeout: 30_000 });
      const before = await s.locator('.stats-cards').innerText();

      const refresh = s.getByRole('button', { name: 'Refresh the verification report' });
      beginRefreshPhase();
      await refresh.click();

      const failed = s
        .locator('div.stats-unavailable')
        .filter({ hasText: /did not return anything/i })
        .first();
      await expect(failed).toBeVisible({ timeout: 20_000 });
      await expect(failed).toContainText(/what is shown below is the result of the last read that did/i);
      await expect(failed).toContainText(/It has not been replaced by a guess/i);
      await expect(failed).toContainText(/it is older than it says/i);

      await expect(s.locator('p.stats-verify-live[role="status"]')).toHaveText(
        /could not be re-read\. The results shown are the ones last read successfully\./
      );
      // The control is offered again rather than left stuck busy.
      await expect(refresh).toBeEnabled();
      await expect(refresh).toHaveAttribute('aria-busy', 'false');
      // THE POINT OF THE STATE: the good measurement survived, byte for byte.
      expect(
        await s.locator('.stats-cards').innerText(),
        'a failed re-read must not disturb the figures already read'
      ).toBe(before);
      return s;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'source-did-not-answer-intercepted-error',
    what:
      'The API answered `unavailable` — the ONE word the backend collapses "did not run", ' +
      '"a source did not answer" and "timed out" onto. The copy names the possibilities and ' +
      'asserts none of them, and it does NOT claim a database was involved.',
    allowedConsole: [],
    async reach({ page }) {
      await serve(page, verificationFailureEnvelope);
      await open(page, '/statistics');
      const s = section(page);
      const panel = s.locator('div.stats-chart-state').first();
      await expect(panel).toBeVisible({ timeout: 20_000 });
      await expect(panel).toContainText('Verification Results Unavailable');
      await expect(panel).toContainText(/does not say which of several causes applies/i);
      await expect(panel).toContainText(/no count is assumed to be zero/i);
      await expect(s.locator('.stats-cards')).toHaveCount(0);
      /*
       * THE HONESTY ASSERTION FOR THIS STATE. The envelope carries no metadata
       * block at all, so nothing on the wire says a database was reached — or
       * that one exists. Copy naming one would be a claim about an event nobody
       * observed, and CLAUDE.md §15 records this project shipping exactly that.
       *
       * A TIMEOUT IS NOT ON THIS LIST, deliberately: the panel's copy names "a
       * read may have timed out" as ONE OF several possibilities it explicitly
       * declines to choose between, which is the honest reading of a status word
       * the backend collapses `not_run`, `unavailable` and `timeout` onto
       * (`verification._PROVIDER_STATUS`). Naming possibilities without
       * asserting one is the behaviour under test, not a violation of it.
       */
      expect(
        await panel.innerText(),
        'the `unavailable` panel must not name a source the wire does not carry'
      ).not.toMatch(/database|postgres|datastore/i);
      return s;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'transport-timeout-intercepted-error',
    what:
      'The request itself timed out at the transport (`net::ERR_TIMED_OUT`), so NO body ' +
      'arrived at all. A genuinely different state from the `unavailable` envelope above: ' +
      'the report cannot even say that it has nothing to say. Retry is offered.',
    allowedConsole: [/Failed to load resource/i, /net::ERR_/i],
    async reach({ page }) {
      await page.route(VERIFICATION_ROUTE, (route) => route.abort('timedout'));
      await open(page, '/statistics');
      const s = section(page);
      const panel = s.locator('div.stats-unavailable').first();
      await expect(panel).toBeVisible({ timeout: 20_000 });
      await expect(panel).toContainText(/could not be read from the API/i);
      await expect(panel).toContainText(/no count is assumed to be zero/i);
      const retry = s.getByRole('button', { name: 'Retry' });
      await expect(retry).toBeVisible();
      await expect(s.locator('.stats-cards')).toHaveCount(0);
      /*
       * The rejection's text is deliberately never rendered — it can carry a URL,
       * a status line or a stack. Asserted rather than trusted.
       */
      const text = await panel.innerText();
      expect(text, 'a transport failure must not leak a URL or a stack onto the screen').not.toMatch(
        /https?:\/\/|net::ERR_|TypeError|at \w+ \(/
      );
      return s;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'program-error-intercepted-error',
    what:
      'The verification program ran and raised — the safe generic error. The exception text ' +
      'is never on the wire and never on the screen.',
    allowedConsole: [],
    async reach({ page }) {
      await serve(page, verificationErrorEnvelope);
      await open(page, '/statistics');
      const s = section(page);
      const panel = s.locator('div.stats-chart-state').first();
      await expect(panel).toBeVisible({ timeout: 20_000 });
      await expect(panel).toContainText('Verification Results Unavailable');
      await expect(panel).toContainText(/reported an error and produced no result/i);
      await expect(s.locator('.stats-cards')).toHaveCount(0);
      const text = await panel.innerText();
      expect(text, 'the safe generic error must carry no exception detail').not.toMatch(
        /Traceback|Exception|https?:\/\/|\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\.py|at \w+ \(/
      );
      // It is NOT the `unavailable` wording — the two states say different things.
      expect(text).not.toMatch(/does not say which of several causes applies/i);
      return s;
    },
    async cleanup({ page }) {
      await page.unrouteAll({ behavior: 'ignoreErrors' });
    },
  },
  {
    id: 'technical-details-collapsed-real-public-reference',
    what:
      'The Statistics page’s Technical Details region as it arrives: collapsed, its heading ' +
      'readable inside the summary, its body not rendered. Real backend throughout.',
    async reach({ page, request }) {
      const status = await waitForRealReport(request);
      expect(status).toBe('ok');
      await open(page, '/statistics');
      const details = page.locator('details.stats-technical');
      await expect(details).toHaveCount(1, { timeout: 20_000 });
      await expect(details.getByRole('heading', { name: 'Technical Details' })).toBeVisible();
      expect(await details.evaluate((el) => (el as HTMLDetailsElement).open)).toBe(false);
      /*
       * MEASURED, not assumed. A CLOSED `<details>` keeps its children in layout
       * with `content-visibility: hidden` in Chromium, so a bounding box is not
       * evidence either way — `checkVisibility` is (see `helpers/layout.ts`).
       */
      const bodyRendered = await details.evaluate((el) => {
        const body = el.querySelector('.stats-technical-body');
        if (body === null) return null;
        return (body as Element & { checkVisibility: (o: Record<string, boolean>) => boolean })
          .checkVisibility({ contentVisibilityAuto: true });
      });
      expect(bodyRendered, 'the collapsed region must not paint its body').toBe(false);
      return details;
    },
  },
  {
    id: 'technical-details-expanded-real-public-reference',
    what:
      'The same region opened from the keyboard — the build’s own runtime, schema, memory ' +
      'and API facts. Real backend throughout.',
    async reach({ page, request }) {
      const status = await waitForRealReport(request);
      expect(status).toBe('ok');
      await open(page, '/statistics');
      const details = page.locator('details.stats-technical');
      await expect(details).toHaveCount(1, { timeout: 20_000 });
      // `> summary`, not `summary`: every chart's data table is a nested
      // `<details>` of its own, so the descendant selector matches four.
      // Through the KEYBOARD, because "keyboard operable" is the claim the
      // component's own comment makes for choosing a native disclosure.
      await details.locator('> summary').focus();
      await page.keyboard.press('Enter');
      await expect
        .poll(() => details.evaluate((el) => (el as HTMLDetailsElement).open), { timeout: 10_000 })
        .toBe(true);
      const body = details.locator('.stats-technical-body');
      await expect(body).toBeVisible();
      await expect(body.getByRole('heading', { name: 'Runtime' })).toBeVisible({ timeout: 20_000 });
      return details;
    },
  },
  {
    id: 'my-stats-no-attribution-unavailable-state',
    what:
      'My Stats — the truthful unavailable gate. Not a zero, not an error, not a skeleton: ' +
      'the tab states that this build cannot attribute any record to any reader.',
    async reach({ page }) {
      await open(page, '/statistics?tab=mine');
      const panel = page.locator('div.statistics[role="tabpanel"]');
      await expect(panel).toBeVisible({ timeout: 20_000 });
      await expect(panel.getByRole('heading', { name: 'Personal Statistics' })).toBeVisible();
      await expect(panel.getByText('Not Available in This Preview').first()).toBeVisible();
      await expect(panel).toContainText(/It is not showing zero/i);
      await expect(panel).toContainText(
        /none of the figures below are zero — they are absent/i
      );
      // NOTHING is drawn: no chart, no stat card, no figure of any kind.
      await expect(panel.locator('figure.stats-chart')).toHaveCount(0);
      await expect(panel.locator('.stats-cards')).toHaveCount(0);
      /*
       * `MyStats` issues no request at all — stated in `MyStats.tsx`'s own
       * header as rule 2, and TRUSTED HERE RATHER THAN PROVED.
       *
       * The previous sentence claimed "the whole-test request log below is what
       * proves it". It does not, and an independent review demonstrated the gap
       * by making `MyStats` fetch `/api/runtime/records` on mount: all eleven
       * tests still passed. The log allowlists ORIGINS (Vite and the API), so a
       * same-origin request is invisible to it — including, as the review also
       * showed, a hypothetical `127.0.0.1/api/portal/metrics`, which the
       * portal-telemetry check cannot see either because that check matches
       * HOSTNAMES.
       *
       * What IS enforced here is structural: `.stats-cards` and
       * `figure.stats-chart` must not appear inside the personal panel, which
       * catches corpus figures arriving in the shapes they are actually drawn
       * in. A relabelled workspace count in a bare paragraph would still pass —
       * so this is a real guard with a known edge, not a proof.
       */
      return panel;
    },
  },
];

/* ─────────────────────────────────────────────────────────────────────────────
 * Shared assertions — the ones that must hold in EVERY state
 * ────────────────────────────────────────────────────────────────────────────*/

/** Origins the page is permitted to talk to: the Vite server and the API. */
const ALLOWED_ORIGINS = [new URL(BASE_URL).origin, new URL(API_BASE).origin];

/**
 * Hosts that would mean this screen phoned something home. Matched against the
 * HOST only — a path containing the word "metrics" is a product route, not a
 * beacon, and conflating the two would make the check impossible to keep true.
 */
const TELEMETRY_HOSTS =
  /(^|\.)(sentry|segment|google-analytics|googletagmanager|analytics|telemetry|plausible|posthog|datadoghq|newrelic|mixpanel|amplitude|hotjar|fullstory|bugsnag|portal)\./i;

/**
 * Strings that must never appear in the rendered page.
 *
 * The ULID pattern is the shape every ISAAC record id has; the rest are the
 * credential carriers this app's request layer composes. All are checked against
 * the rendered TEXT and against the markup, because an id can hide in an
 * attribute as easily as in a text node.
 */
const FORBIDDEN_IN_DOM: readonly { name: string; re: RegExp }[] = [
  { name: 'an ISAAC record id (ULID shape)', re: /\b[0-9A-HJKMNP-TV-Z]{26}\b/ },
  { name: 'a canonical seed record id', re: /01SYNTHXANESSEED/ },
  { name: 'a bearer credential', re: /Bearer\s+\S/ },
  { name: 'an Authorization header', re: /Authorization\s*:/i },
  { name: 'the tutorial session header', re: /X-Isaac-Tutorial-Session/i },
  { name: 'an api key', re: /\bapi[_-]?key\b/i },
  { name: 'a password', re: /\bpassword\b/i },
];

interface Finding {
  state: string;
  detail: string;
}

/** Every assertion that must hold whatever the state is. Findings, not throws,
 *  so one broken state cannot hide the other twelve. */
async function commonAssertions(
  page: Page,
  state: { id: string },
  push: (detail: string) => void
): Promise<void> {
  // ── 1. the document never scrolls sideways ────────────────────────────────
  const doc = await horizontalPageScroll(page);
  if (doc.docScrollWidth > doc.docClientWidth + 1) {
    push(`the document scrolls horizontally: ${doc.docScrollWidth} > ${doc.docClientWidth}`);
  }

  // ── 2. no text is clipped away entirely ───────────────────────────────────
  // Content-loss tiers only, and deliberately not baseline-filtered: this asks
  // "can the reader see this at all?", which nothing is allowed to fail.
  const clipped = (await findClippedText(page)).filter(
    (c) => c.kind === 'total-loss' || c.kind === 'critical-loss'
  );
  if (clipped.length) push(`text is not readable on screen:\n${render(clipped)}`);

  // ── 3. nothing private, and no credential, in the DOM ─────────────────────
  const { text, html } = await page.evaluate(() => {
    const main = document.querySelector('main#main');
    return { text: (main as HTMLElement | null)?.innerText ?? '', html: main?.innerHTML ?? '' };
  });
  for (const forbidden of FORBIDDEN_IN_DOM) {
    const hit = forbidden.re.exec(text) ?? forbidden.re.exec(html);
    if (hit !== null) push(`the page contains ${forbidden.name}: ${JSON.stringify(hit[0])}`);
  }

  // ── 4. reduced motion is genuinely respected ──────────────────────────────
  // No stylesheet is injected by this file (see the header), so this measures
  // the APP's own `@media (prefers-reduced-motion: reduce)` block.
  const motion = await page.evaluate(() => {
    const matches = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const parse = (value: string) =>
      value
        .split(',')
        .map((part) => {
          const t = part.trim();
          if (t.endsWith('ms')) return parseFloat(t) / 1000;
          return parseFloat(t) || 0;
        })
        .reduce((a, b) => Math.max(a, b), 0);
    let worst = 0;
    let culprit = '';
    for (const el of Array.from(document.querySelectorAll('main#main *'))) {
      const cs = getComputedStyle(el);
      const d = Math.max(parse(cs.transitionDuration), parse(cs.animationDuration));
      if (d > worst) {
        worst = d;
        culprit = el.tagName.toLowerCase() + (el.className ? `.${String(el.className).split(/\s+/)[0]}` : '');
      }
    }
    return { matches, worst, culprit };
  });
  if (!motion.matches) push('the context does not report prefers-reduced-motion: reduce');
  // 1ms is the value `base.css` collapses everything to; anything above it means
  // a rule escaped the media query.
  if (motion.worst > 0.002) {
    push(
      `an animation survives reduced motion: ${motion.culprit} runs for ${motion.worst}s ` +
        '(the app collapses every duration to 0.001ms under the media query)'
    );
  }

  // ── 5. the page tablist is correctly wired ────────────────────────────────
  const tabs = await page.evaluate(() => {
    const list = document.querySelector('[role="tablist"]');
    if (list === null) return { found: false, label: null as string | null, tabs: [] as unknown[] };
    const items = Array.from(list.querySelectorAll('[role="tab"]')).map((t) => {
      const controls = t.getAttribute('aria-controls');
      const panel = controls === null ? null : document.getElementById(controls);
      return {
        name: (t as HTMLElement).innerText.trim(),
        selected: t.getAttribute('aria-selected'),
        controls,
        panelRole: panel?.getAttribute('role') ?? null,
        panelLabelledBy: panel?.getAttribute('aria-labelledby') ?? null,
        id: t.id,
        tabIndex: (t as HTMLElement).tabIndex,
      };
    });
    return { found: true, label: list.getAttribute('aria-label'), tabs: items };
  });
  if (!tabs.found) {
    push('the Statistics page renders no role="tablist"');
  } else {
    const items = tabs.tabs as {
      name: string;
      selected: string | null;
      controls: string | null;
      panelRole: string | null;
      panelLabelledBy: string | null;
      id: string;
      tabIndex: number;
    }[];
    if (tabs.label === null || tabs.label.length === 0) push('the tablist has no accessible name');
    if (items.length !== 2) push(`expected 2 tabs, found ${items.length}`);
    const selected = items.filter((t) => t.selected === 'true');
    if (selected.length !== 1) push(`exactly one tab must be selected; ${selected.length} are`);
    for (const t of selected) {
      if (t.controls === null) push(`the selected tab "${t.name}" has no aria-controls`);
      if (t.panelRole !== 'tabpanel') {
        push(`the selected tab "${t.name}" controls an element whose role is ${t.panelRole}`);
      }
      if (t.panelLabelledBy !== t.id) {
        push(
          `the panel for "${t.name}" is labelled by ${t.panelLabelledBy}, not by its tab (${t.id})`
        );
      }
    }
    // Exactly one tab in the tab order — the roving-tabindex contract.
    const inOrder = items.filter((t) => t.tabIndex >= 0);
    if (inOrder.length !== 1) push(`exactly one tab may be in the tab order; ${inOrder.length} are`);
  }

  // ── 6. the section's live region exists before it has anything to say ─────
  if (state.id !== 'my-stats-no-attribution-unavailable-state') {
    const live = await page.locator('p.stats-verify-live[role="status"]').count();
    // The live region is inside the report branch only — it must exist wherever
    // a refresh control could be pressed, and it is asserted directly by the two
    // refresh states. Here we only require that when it exists it is a status
    // region, which the selector already encodes; absence is legitimate for the
    // loading and not-ready branches.
    if (live > 1) push(`${live} verification live regions; there must be at most one`);
  }
}

/**
 * The assertions that only apply where a decoded report is on screen.
 */
async function reportAssertions(
  page: Page,
  state: Pick<VerificationState, 'corpus' | 'longPaths'>,
  push: (detail: string) => void
): Promise<{ charts: number; longPathLines: number[] }> {
  const s = section(page);

  // ── the corpus labels are never interchangeable ───────────────────────────
  // THE LABEL CHECK AND THE TOKEN CHECK ARE NOT EQUALLY STRONG, and reading
  // them as one guard overstates this file.
  //
  // `PUBLIC_LABEL`/`PRIVATE_LABEL` are imported from `verificationContract` —
  // the module under test. Comparing the DOM against them proves the two labels
  // are DIFFERENT FROM EACH OTHER and that the right one of the pair is on
  // screen. It cannot prove either is TRUE. An independent review rewrote the
  // private label to "Completed live run over the 30 private production
  // records" and all eleven tests here passed. (Vitest
  // `src/__tests__/record-verification.test.tsx` does catch that — 4 failures —
  // so the property is covered; it is just not covered HERE, and this file used
  // to imply otherwise.)
  //
  // The WIRE TOKENS below are a different matter: 'authorized_private_sample'
  // and 'public_reference' are hardcoded literals in this file, owned by nobody
  // else, so that comparison is genuinely independent of the module it tests. It
  // is the stronger of the two, which is why the token is asserted verbatim
  // beside the label rather than instead of it.
  const sectionText = await s.innerText();
  const wantLabel = state.corpus === 'private' ? PRIVATE_LABEL : PUBLIC_LABEL;
  const otherLabel = state.corpus === 'private' ? PUBLIC_LABEL : PRIVATE_LABEL;
  const wantToken = state.corpus === 'private' ? 'authorized_private_sample' : 'public_reference';
  const otherToken = state.corpus === 'private' ? 'public_reference' : 'authorized_private_sample';
  if (!sectionText.includes(wantLabel)) push(`the corpus label "${wantLabel}" is not on screen`);
  if (sectionText.includes(otherLabel)) {
    push(`the OTHER corpus's label "${otherLabel}" appears while reporting the ${state.corpus} corpus`);
  }
  if (!sectionText.includes(wantToken)) push(`the wire token "${wantToken}" is not rendered verbatim`);

  // ── no private capture may show a DATABASE safeguard as "Verified" ────────
  //
  // The one assertion in this file that is about the world rather than about
  // the DOM. No private record has ever been evaluated and no database
  // connection has ever been opened, so a capture of the private corpus stating
  // that a read-only transaction or a parameterized query was VERIFIED is a
  // false record of a measurement — the defect an independent review found here,
  // where the fixture said `verified` and the sweep photographed it.
  //
  // It reads the RENDERED WORDS, not the fixture: a body that reintroduces
  // `'verified'`, or a product change that folded `not_applicable` into it (the
  // collapse `verificationContract.ts:182-196` exists to prevent), both fail.
  // Deliberately NOT symmetrical — the public corpus really does run, and this
  // says nothing about it.
  if (state.corpus === 'private') {
    for (const label of ['Read-Only Database Access', 'Parameterized Database Queries']) {
      const row = s.locator('.stats-verify-safeguard', { hasText: label });
      if ((await row.count()) === 0) continue;
      const rowText = await row.first().innerText();
      if (/\bVerified\b/.test(rowText)) {
        push(
          `the private-corpus capture states "${label}" as Verified. No private run has ` +
            `occurred and no database connection has ever been opened, so this image would ` +
            `be a false record of a measurement`
        );
      }
    }
  }

  if (sectionText.includes(otherToken)) {
    push(`the OTHER corpus's wire token "${otherToken}" appears while reporting the ${state.corpus} corpus`);
  }

  // ── every chart carries a text summary AND a data table ───────────────────
  const charts = await s.locator('figure.stats-chart').count();
  if (charts === 0) push('a report is on screen but it drew no chart at all');
  const chartAudit = await s.evaluate((root) => {
    const out: { caption: string; summary: string; table: boolean; rows: number; toggle: string }[] = [];
    for (const fig of Array.from(root.querySelectorAll('figure.stats-chart'))) {
      const table = fig.querySelector('details.stats-chart-table-wrap table');
      out.push({
        caption: fig.querySelector('figcaption')?.textContent?.trim() ?? '',
        summary: fig.querySelector('p.sr-only')?.textContent?.trim() ?? '',
        table: table !== null,
        rows: table === null ? 0 : table.querySelectorAll('tbody tr').length,
        toggle:
          fig.querySelector('details.stats-chart-table-wrap > summary')?.textContent?.trim() ?? '',
      });
    }
    return out;
  });
  for (const c of chartAudit) {
    if (c.caption.length === 0) push('a chart has no visible caption');
    if (c.summary.length < 20) {
      push(`the chart "${c.caption}" has no textual summary (got ${JSON.stringify(c.summary)})`);
    }
    if (!c.table) push(`the chart "${c.caption}" offers no data-table alternative`);
    if (c.rows === 0) push(`the chart "${c.caption}" has a data table with no rows`);
    if (!/data table/i.test(c.toggle)) {
      push(`the chart "${c.caption}" data table is not offered in words (got ${JSON.stringify(c.toggle)})`);
    }
  }

  // ── status is not conveyed by colour alone ────────────────────────────────
  const safeguards = await s.evaluate((root) => {
    return Array.from(root.querySelectorAll('.stats-verify-safeguard')).map((row) => ({
      label: row.querySelector('.stats-verify-safeguard-label')?.textContent?.trim() ?? '',
      state: row.querySelector('.stats-verify-state')?.getAttribute('data-state') ?? '',
      word: row.querySelector('.stats-verify-state')?.textContent?.trim() ?? '',
      detail: row.querySelector('.stats-verify-safeguard-detail')?.textContent?.trim() ?? '',
      tone: row.getAttribute('data-tone') ?? '',
    }));
  });
  if (safeguards.length !== 6) push(`expected 6 tri-state safeguards, found ${safeguards.length}`);
  const WORD_FOR: Record<string, string> = {
    verified: 'Verified',
    not_applicable: 'Not applicable',
    unverified: 'Unverified',
  };
  for (const row of safeguards) {
    if (row.label.length === 0) push('a safeguard row has no label');
    if (row.detail.length === 0) push(`the safeguard "${row.label}" states no reason in words`);
    const expected = WORD_FOR[row.state];
    if (expected === undefined) push(`the safeguard "${row.label}" has an unknown state "${row.state}"`);
    else if (row.word !== expected) {
      push(
        `the safeguard "${row.label}" is in state ${row.state} but reads "${row.word}" — the three ` +
          'states must never share a word'
      );
    }
    // The one collapse this screen must never make.
    if (row.state === 'not_applicable' && /verified/i.test(row.word)) {
      push(`"${row.label}" renders not_applicable as an affirmative`);
    }
    if (row.state === 'not_applicable' && row.tone === 'good') {
      push(`"${row.label}" gives not_applicable the affirmative tone`);
    }
  }
  /*
   * Every tone-tinted group says what it is in words.
   *
   * THE RULE IS NARROWER THAN "every group has a sentence", and the narrowing is
   * a decision rather than an accommodation. `data-tone` is the only colour on
   * these boxes, and `good`/`attention` are JUDGEMENTS — "this is the outcome you
   * wanted" / "look at this" — which is exactly what may not be carried by
   * colour alone. `neutral` asserts nothing, so a label is a complete
   * non-colour identity for it.
   *
   * Measured consequence, recorded so a later reader does not think it was
   * missed: `MutationPanel`'s "How Much Was Attempted" group is the one
   * `neutral` group on the screen and the one with no `summary` prop
   * (`RecordVerification.tsx:811`). Its three siblings all carry both. That is
   * an inconsistency in the copy, not a colour-only status, and this probe
   * deliberately does not fail on it.
   */
  const toneGroups = await s.evaluate((root) =>
    Array.from(root.querySelectorAll('.stats-verify-group')).map((g) => ({
      tone: g.getAttribute('data-tone') ?? '',
      label: g.querySelector('.stats-mini-label')?.textContent?.trim() ?? '',
      note: g.querySelector('.stats-verify-group-note')?.textContent?.trim() ?? '',
    }))
  );
  for (const g of toneGroups) {
    if (g.label.length === 0) push(`a ${g.tone}-toned group carries no label`);
    if (!['good', 'neutral', 'attention'].includes(g.tone)) {
      push(`the group "${g.label}" has an unknown tone "${g.tone}"`);
    }
    if (g.tone !== 'neutral' && g.note.length === 0) {
      push(
        `the group "${g.label}" is tinted "${g.tone}" — a judgement — but states no sentence, so ` +
          'the judgement exists only as colour'
      );
    }
  }

  // ── nothing inside the section overflows its own box ──────────────────────
  const overflow = await s.evaluate((root) => {
    const out: string[] = [];
    // Tag + id + first two classes. The id matters: "div overflows by 450px" is
    // not actionable and P3 below proves the difference.
    const name = (e: Element) =>
      e.tagName.toLowerCase() +
      (e.id ? `#${e.id}` : '') +
      (typeof e.className === 'string' && e.className.trim()
        ? `.${e.className.trim().split(/\s+/).slice(0, 2).join('.')}`
        : '');
    for (const el of Array.from(root.querySelectorAll('*'))) {
      // A closed <details> keeps its children in layout; their geometry is not
      // a fact about anything the reader can see.
      if (el.closest('details:not([open])') !== null) continue;
      // `.stats-scroll` is the ONE deliberate inner scroller on this screen: a
      // wide data table is allowed to scroll inside its own box.
      if (el.classList.contains('stats-scroll') || el.closest('.stats-scroll') !== null) continue;
      /*
       * `.sr-only` is the visually-hidden CLIP-RECT pattern
       * (`src/styles/base.css:293` — `width: 1px; height: 1px; overflow: hidden;
       * clip: rect(0,0,0,0)`). `scrollWidth > clientWidth` is its DEFINITION,
       * not a defect: this screen's chart summary sentences and the
       * verification live region are all `.sr-only`, and every one of them was
       * reported as an overflow before this line existed. Nothing is hidden BY
       * them — they are hidden, on purpose, and read aloud rather than drawn.
       */
      if (el.classList.contains('sr-only') || el.closest('.sr-only') !== null) continue;
      const cs = getComputedStyle(el);
      if (!/hidden|clip|auto|scroll/.test(cs.overflowX)) continue;
      if (el.scrollWidth > el.clientWidth + 1) {
        out.push(`${name(el)} overflows: scrollWidth ${el.scrollWidth} > clientWidth ${el.clientWidth}`);
      }
    }
    return out;
  });
  for (const o of overflow) push(`inside the section, ${o}`);

  // ── long JSON-pointer schema paths WRAP, measured as real line boxes ──────
  const longPathLines: number[] = [];
  if (state.longPaths === true) {
    const measured = await s.evaluate((root) => {
      const out: { text: string; lines: number; overflow: number }[] = [];
      for (const el of Array.from(root.querySelectorAll('.stats-chart-row-label'))) {
        const text = el.textContent ?? '';
        if (!text.startsWith('properties/')) continue;
        // One client rect per LINE BOX. Real geometry — no CSS string is read,
        // and it works whatever `display` the element ends up with.
        const range = document.createRange();
        range.selectNodeContents(el);
        out.push({
          text,
          lines: range.getClientRects().length,
          overflow: el.scrollWidth - el.clientWidth,
        });
      }
      return out;
    });
    if (measured.length !== 3) {
      push(`expected this state's 3 authored schema paths on screen, measured ${measured.length}`);
    }
    for (const m of measured) {
      longPathLines.push(m.lines);
      if (m.overflow > 1) {
        push(
          `the schema path "${m.text.slice(0, 40)}…" overflows its own box by ${m.overflow}px ` +
            'instead of wrapping'
        );
      }
      if (m.lines === 0) push(`the schema path "${m.text.slice(0, 40)}…" produced no line box at all`);
    }
  }

  return { charts, longPathLines };
}

/* ─────────────────────────────────────────────────────────────────────────────
 * The run
 * ────────────────────────────────────────────────────────────────────────────*/

const DECLARED = [...EXPECTED_STATE_IDS].sort();

test.describe('statistics · record verification runtime states', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(
      testInfo.project.name !== HOST_PROJECT,
      `runs only in ${HOST_PROJECT}; it moves the viewport itself rather than adding projects`
    );
  });

  test('@responsive the declared state set, the implemented list and the provenance rule agree', () => {
    expect(
      STATES.map((s) => s.id).sort(),
      'EXPECTED_STATE_IDS is the contract; STATES implements it. A mismatch means a state was ' +
        'added to one and not the other — the silent omission this set exists to prevent.'
    ).toEqual(DECLARED);
    expect(new Set(STATES.map((s) => s.id)).size, 'duplicate state id').toBe(STATES.length);

    // THE HONESTY RULE, enforced structurally: exactly one classifier per id.
    for (const id of EXPECTED_STATE_IDS) {
      const hits = PROVENANCE_CLASSIFIERS.filter((c) => id.endsWith(c));
      expect(
        hits,
        `"${id}" must end in exactly one provenance classifier so that every attachment name ` +
          'carries one. See the file header.'
      ).toHaveLength(1);
    }

    // And the one state whose caption is load-bearing carries its words.
    const privateState = STATES.find((s) => s.corpus === 'private');
    expect(privateState, 'the private-corpus state must exist').toBeTruthy();
    expect(privateState!.id).toContain('synthetic-fixture');
    expect(
      privateState!.what,
      'the private-sample capture must say in words that no private run has occurred'
    ).toContain('shape only — no private run has occurred');
  });

  for (const width of WIDTHS) {
    test(`@responsive width ${width}: reach, assert and capture every verification state`, async (
      { page, consoleErrors, request },
      testInfo
    ) => {
      // Thirteen states, several of which drive a multi-step interaction and one
      // of which may wait out a ~20s backend sweep.
      test.setTimeout(900_000);

      await page.setViewportSize({ width, height: VIEWPORT_HEIGHT });

      /** Every URL the page requested, for the whole test. */
      const requested: string[] = [];
      page.on('request', (r) => requested.push(r.url()));

      const captured: string[] = [];
      const unreachable: string[] = [];
      const findings: Finding[] = [];
      const consoleFindings: string[] = [];
      let attachments = 0;
      let maxCharts = 0;
      const wrapLines: number[] = [];
      let font = '(not measured)';

      const ctx: Ctx = { page, request, width, note: () => undefined };

      for (const state of STATES) {
        const notes: string[] = [];
        const consoleBefore = consoleErrors.length;
        const stateCtx: Ctx = { ...ctx, note: (t) => notes.push(t) };
        const push = (detail: string) => findings.push({ state: state.id, detail });

        try {
          const target = await state.reach(stateCtx);

          // The viewport is set before the first navigation, but a panel that
          // mounts from a follow-up render can settle after it; re-assert so
          // every measurement is taken at the width in the test title.
          await page.setViewportSize({ width, height: VIEWPORT_HEIGHT });
          if (font === '(not measured)') font = await renderedFontFamily(page);

          await commonAssertions(page, state, push);
          if (state.rendersReport === true) {
            const r = await reportAssertions(page, state, push);
            maxCharts = Math.max(maxCharts, r.charts);
            wrapLines.push(...r.longPathLines);
          }

          // The element that IS the state must be a real, on-screen box — a
          // screenshot of a 1x1 `sr-only` carrier looks like a clean capture.
          const box = await target.boundingBox();
          if (box === null || box.width < 8 || box.height < 8) {
            push(`the state's own element has no real box: ${JSON.stringify(box)}`);
          }

          // ── console ────────────────────────────────────────────────────────
          const allowed = state.allowedConsole ?? [];
          const fresh = consoleErrors.slice(consoleBefore);
          const unexpected = fresh.filter((m) => !allowed.some((re) => re.test(m)));
          if (unexpected.length) {
            consoleFindings.push(`${state.id}: ${unexpected.join(' | ')}`);
          }

          // ── the artifact ──────────────────────────────────────────────────
          await target.scrollIntoViewIfNeeded().catch(() => undefined);
          // The provenance goes into the PIXELS, not just the attachment name.
          // See `stampProvenance`: the name stays behind in the HTML report and
          // the image does not.
          const unstamp = await stampProvenance(target, state.id);
          const shot = await target.screenshot({ animations: 'disabled' });
          await unstamp();
          const suffix = notes.length ? ` [${notes.join('; ')}]` : '';
          await testInfo.attach(`${width}px · ${state.id} — ${state.what}${suffix}`, {
            body: shot,
            contentType: 'image/png',
          });
          attachments += 1;
          captured.push(state.id);
        } catch (err) {
          // The first SIX lines, not the first: Playwright puts the locator, the
          // expected value and the received value on separate lines, and a
          // one-line excerpt of a `toHaveCount` failure names neither.
          unreachable.push(
            `${state.id}: ${(err as Error).message
              .split('\n')
              .filter((l) => l.trim().length > 0)
              .slice(0, 6)
              .join(' / ')}`
          );
        } finally {
          if (state.cleanup) await state.cleanup(stateCtx).catch(() => undefined);
        }
      }

      /* ── the network boundary, over the WHOLE test ────────────────────────*/
      const offSite = requested.filter((u) => {
        try {
          return !ALLOWED_ORIGINS.includes(new URL(u).origin);
        } catch {
          return true;
        }
      });
      const beacons = requested.filter((u) => {
        try {
          return TELEMETRY_HOSTS.test(new URL(u).hostname);
        } catch {
          return false;
        }
      });

      testInfo.annotations.push({
        type: 'statistics-states',
        description:
          `width ${width} — font: ${font}; ${captured.length}/${STATES.length} states captured ` +
          `as ${attachments} attachment(s); ${requested.length} request(s), all to ` +
          `${ALLOWED_ORIGINS.join(' + ')}; ${findings.length} finding(s); ` +
          `max charts in one state: ${maxCharts}; long-path line boxes: ${wrapLines.join(',') || 'n/a'}.`,
      });
      // eslint-disable-next-line no-console
      console.log(
        `[statistics-states] ${width}px — captured ${captured.length}/${STATES.length}, ` +
          `${attachments} attachments, ${requested.length} requests` +
          (unreachable.length ? `; UNREACHABLE: ${unreachable.join(' | ')}` : '')
      );

      /* ── THE SET, not a count ────────────────────────────────────────────*/
      expect(
        [...captured].sort(),
        unreachable.length
          ? `States that could not be reached at ${width}px. Each is a FINDING — either the state ` +
            `is genuinely broken at this width, or this spec's route to it is wrong. Nothing is ` +
            `skipped silently:\n${unreachable.join('\n')}`
          : `The captured set must equal the declared set at ${width}px.`
      ).toEqual(DECLARED);

      expect(
        findings.map((f) => `${f.state}: ${f.detail}`),
        `Assertion failures at ${width}px (font: ${font}). Screenshots alone are not ` +
          'verification; these are the questions with objective answers.'
      ).toEqual([]);

      expect(
        consoleFindings,
        `Unexpected console errors or uncaught page errors at ${width}px. Each state declares the ` +
          'messages it deliberately causes; anything else is a defect:\n' + consoleFindings.join('\n')
      ).toEqual([]);

      expect(
        offSite,
        `This screen requested an origin outside ${ALLOWED_ORIGINS.join(' + ')} at ${width}px. ` +
          'Statistics reads the ISAAC API and nothing else.'
      ).toEqual([]);
      expect(beacons, `A telemetry/analytics/portal host was contacted at ${width}px.`).toEqual([]);

      /* ── the probes must have had something to measure ───────────────────*/
      // A silent pass is the one outcome these checks must not be able to
      // produce, so the coverage they achieved is asserted rather than assumed.
      expect(
        maxCharts,
        'no state put the two issue-distribution charts on screen, so the chart summary / data ' +
          'table assertions only ever saw the validator comparison'
      ).toBeGreaterThanOrEqual(3);
      expect(
        wrapLines.length,
        'the long-schema-path wrap measurement found nothing to measure at any width'
      ).toBeGreaterThan(0);
      if (width <= 768) {
        expect(
          Math.max(...wrapLines),
          `at ${width}px at least one 100+ character JSON-pointer schema path must occupy more ` +
            'than one line box — if every one is a single line the text is not wrapping, it is ' +
            'being laid out wider than the box'
        ).toBeGreaterThan(1);
      }
    });
  }
});

/**
 * ── PROBE SELF-CHECK ───────────────────────────────────────────────────────
 *
 * The sweep above ran 78 captures and reported ZERO findings. That is exactly
 * the output a probe with a bug in it would produce, so the four probes whose
 * silence carries the most weight are falsified here against INJECTED DOM — the
 * technique `specs/visual-sweep.spec.ts` and `specs/layout-widths.spec.ts`
 * already use.
 *
 * Every mutation is browser-side only; nothing is written to the backend, and
 * the injected bodies for P3/P4 are `synthetic-fixture` shapes, never the
 * private one.
 *
 * The page-scroll check is deliberately NOT self-checked: it compares
 * `documentElement.scrollWidth` with `clientWidth` and has no intermediate logic
 * to get wrong. `findClippedText` is not self-checked here either —
 * `layout-widths.spec.ts` cases T1/E1/C1/I1 already falsify it against the
 * geometry of measured defects, and a second copy would be a second place to
 * update.
 */
test.describe('probe self-check (injected DOM)', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== HOST_PROJECT, `runs only in ${HOST_PROJECT}`);
  });

  test('@responsive P1: the DOM scan catches a record id that reached the page', async ({ page }) => {
    await open(page, '/statistics');
    const clean: string[] = [];
    await commonAssertions(page, { id: 'selfcheck-p1-clean' }, (d) => clean.push(d));
    expect(clean, 'the real page must be clean before anything is injected').toEqual([]);

    await page.evaluate(() => {
      const p = document.createElement('p');
      p.id = 'selfcheck-p1';
      // A well-formed ULID that is not one of this repo's seed ids — the point
      // is the SHAPE, which is what a leaked record id would have.
      p.textContent = 'Record 01ARZ3NDEKTSV4RRFFQ69G5FAV was evaluated';
      document.querySelector('main#main')!.appendChild(p);
    });
    const dirty: string[] = [];
    await commonAssertions(page, { id: 'selfcheck-p1-dirty' }, (d) => dirty.push(d));
    expect(dirty.join('\n')).toMatch(/contains an ISAAC record id \(ULID shape\)/);
  });

  test('@responsive P2: the reduced-motion probe catches an animation that escaped', async ({ page }) => {
    await open(page, '/statistics');
    await page.evaluate(() => {
      const style = document.createElement('style');
      style.textContent = '@keyframes selfcheckSpin { to { opacity: 0.5; } }';
      document.head.appendChild(style);
      const d = document.createElement('div');
      d.id = 'selfcheck-p2';
      /*
       * `!important` INLINE, and it has to be. `base.css`'s reduced-motion block
       * collapses `*` to 0.001ms with `!important`, and an author `!important`
       * beats a normal inline declaration — so an ordinary inline animation
       * would be neutralised by the very rule under test and would falsify
       * nothing. This is the only way to inject motion the app's CSS does not
       * already kill, which is itself a measurement of how thorough that rule is.
       */
      d.setAttribute(
        'style',
        'animation-name: selfcheckSpin !important; animation-duration: 5s !important; ' +
          'animation-iteration-count: infinite !important; width: 10px; height: 10px;'
      );
      document.querySelector('main#main')!.appendChild(d);
    });
    const found: string[] = [];
    await commonAssertions(page, { id: 'selfcheck-p2' }, (d) => found.push(d));
    expect(found.join('\n')).toMatch(/an animation survives reduced motion: div\.?.* runs for 5s/);
  });

  test('@responsive P3: the section overflow probe catches a clipped box — and still ignores the sr-only clip-rect pattern', async ({
    page,
  }) => {
    await serve(page, PRIVATE_SAMPLE_SHAPE);
    await open(page, '/statistics');
    const s = section(page);
    await expect(s.locator('.stats-cards')).toHaveCount(1, { timeout: 20_000 });

    const clean: string[] = [];
    await reportAssertions(page, { corpus: 'private' }, (d) => clean.push(d));
    expect(clean, 'the rendered section must be clean before anything is injected').toEqual([]);

    await s.evaluate((root) => {
      const clipped = document.createElement('div');
      clipped.id = 'selfcheck-p3-clipped';
      clipped.setAttribute('style', 'overflow-x: hidden; width: 50px;');
      const wide = document.createElement('div');
      wide.setAttribute('style', 'width: 500px;');
      wide.textContent = 'wider than its parent';
      clipped.appendChild(wide);
      root.appendChild(clipped);

      // The exclusion, proved rather than asserted: a genuine `.sr-only`
      // carrier overflows BY DEFINITION and must not be reported.
      const hidden = document.createElement('p');
      hidden.id = 'selfcheck-p3-sr-only';
      hidden.className = 'sr-only';
      hidden.textContent = 'A long visually-hidden sentence that no reader ever sees drawn.';
      root.appendChild(hidden);
    });

    const found: string[] = [];
    await reportAssertions(page, { corpus: 'private' }, (d) => found.push(d));
    const joined = found.join('\n');
    expect(joined).toMatch(/div#selfcheck-p3-clipped overflows: scrollWidth 500 > clientWidth 50/);
    expect(joined, 'the sr-only clip-rect pattern must never be reported').not.toMatch(/sr-only/);
  });

  test('@responsive P4: the wrap measurement catches a path laid out wider than its box', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: VIEWPORT_HEIGHT });
    await serve(page, PRIVATE_SAMPLE_SHAPE);
    await open(page, '/statistics');
    const s = section(page);
    await expect(s.locator('.stats-cards')).toHaveCount(1, { timeout: 20_000 });

    const clean = await (async () => {
      const out: string[] = [];
      const r = await reportAssertions(page, { corpus: 'private', longPaths: true }, (d) => out.push(d));
      return { out, r };
    })();
    expect(clean.out, 'the three real authored paths must wrap cleanly at 320px').toEqual([]);
    expect(
      Math.max(...clean.r.longPathLines),
      'the control measurement must show real wrapping, or P4 proves nothing'
    ).toBeGreaterThan(1);

    // A fourth label that CANNOT wrap: one line box, and 100+ characters of it
    // laid out beyond a 100px clipping box.
    await s.evaluate((root, path) => {
      const row = document.createElement('div');
      row.className = 'stats-chart-row';
      const label = document.createElement('span');
      label.className = 'stats-chart-row-label';
      label.id = 'selfcheck-p4';
      label.setAttribute('style', 'white-space: nowrap !important; overflow: hidden; width: 100px; display: block;');
      label.textContent = path;
      row.appendChild(label);
      root.querySelector('.stats-chart-plot')!.appendChild(row);
    }, LONG_SCHEMA_PATHS[0]);

    const found: string[] = [];
    await reportAssertions(page, { corpus: 'private', longPaths: true }, (d) => found.push(d));
    const joined = found.join('\n');
    expect(joined).toMatch(/overflows its own box by \d+px instead of wrapping/);
    // And the count guard fires too, so a path silently disappearing would also
    // be caught rather than passing as "nothing to measure".
    expect(joined).toMatch(/expected this state's 3 authored schema paths on screen, measured 4/);
  });
});
