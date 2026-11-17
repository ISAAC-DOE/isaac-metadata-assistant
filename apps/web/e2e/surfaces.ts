/**
 * The surface catalogue — the single list every sweeping spec iterates.
 *
 * IMPORTANT, and verified against `apps/web/src/lib/routes.ts` + `App.tsx`:
 * several things the product calls "screens" are TABS, not routes. The
 * Validator, the Schema Reference, the Graph browser, API Access and the
 * Endpoint Explorer are all `?tab=` deep links onto three real routes. The
 * Assistant has no route at all — it is a panel, so it is covered by
 * `assistantMounts` below rather than by a surface of its own.
 *
 * `ready` is the locator that proves the surface finished its data fetch.
 * Without it the sweep would race the `role="status"` loading panel and axe
 * would scan a skeleton.
 */

import { SEED } from './env';

/**
 * Which workspace scope a surface has to be opened in.
 *
 *   ordinary — the permanently EMPTY ordinary workspace. No header is sent, and
 *              the surface must render what the app really shows there.
 *   example  — inside the run's shared worked-example session, because the
 *              surface addresses one of the five built-in example records, which
 *              exist NOWHERE else. The `app` fixture enters the scope before
 *              navigating; a spec never has to remember to.
 *
 * Explicit per surface rather than inferred from the path: the inference would be
 * "does the path contain a record id", which is exactly the kind of rule that
 * silently stops holding when a surface gains a query parameter.
 */
export type SurfaceScope = 'ordinary' | 'example';

export interface Surface {
  /** Stable key used in test titles and in the a11y baseline. Never rename casually. */
  readonly id: string;
  /** Human name for report output. */
  readonly name: string;
  readonly path: string;
  /** Which workspace scope this surface is opened in. Required — see `SurfaceScope`. */
  readonly scope: SurfaceScope;
  /**
   * Playwright locator description proving the surface is loaded. Expressed as
   * a role+name pair so it asserts accessible structure while it waits.
   */
  readonly ready: { role: Parameters<import('@playwright/test').Page['getByRole']>[0]; name: string | RegExp };
  /** Surfaces that legitimately have no `<h1>` (recorded, not excused — see FINDINGS). */
  readonly expectH1?: boolean;
  /**
   * The surface is a LOCAL-BUILD destination whose API the e2e backend does not serve
   * (`/api/local-bundles/*` exists only on a server started with `ISAAC_LOCAL_BUNDLES_DIR`),
   * so `app.open()` enables the build flag for this page and answers that API from the
   * SYNTHETIC fixtures in `e2e/local-imports-mock.ts`, IN THE BROWSER. Every other surface
   * is opened with neither, so the rest of the catalogue measures exactly the app it did.
   */
  readonly localImportsMock?: true;
}

const recordSub = (id: string, sub: string) => `/record/${id}/${sub}`;

export const SURFACES: readonly Surface[] = [
  {
    id: 'experiments',
    name: 'My Experiments (ordinary, empty)',
    path: '/experiments',
    // The PERMANENT ordinary state: no rows, the real empty state. Measured as
    // its own surface because that is what a reader of this deployment sees.
    scope: 'ordinary',
    ready: { role: 'heading', name: 'My Experiments' },
  },
  {
    // NEW, and it replaces coverage that would otherwise have been LOST rather
    // than adding coverage that never existed. `experiments` used to render five
    // seeded rows, so `ExperimentQueue`, `ExperimentRow`, the group headings and
    // the queue subcount were swept by axe, the layout probes, the width sweep
    // and the zoom project. With the ordinary list empty, none of that markup
    // renders on `experiments` any more. This surface is the same route inside a
    // worked-example session, where the queue is populated — so both states are
    // measured instead of one being quietly dropped.
    id: 'experiments-example',
    name: 'My Experiments (worked example)',
    path: '/experiments',
    scope: 'example',
    ready: { role: 'heading', name: 'My Experiments' },
  },
  /*
   * ~~`load` — "Load Materials", `/load`~~ — RETIRED 2026-11-16: `/load` redirects to My
   * Experiments, which `experiments` scans. It recorded no a11y cell; its three layout
   * entries went with it.
   */
  {
    /*
     * HISTORICAL IMPORT — since 2026-11-16 the guide to importing a past beamtime with the
     * Claude Code skill. The in-browser import flow this surface used to scan (an empty
     * session list, and `e2e/mutation/imports-session-a11y.spec.ts` for an open session)
     * is gone. The page is static: it reads nothing from the API, so the `<h1>` would do
     * as a gate; the last section's heading is used so the scan waits for the whole page.
     */
    id: 'imports',
    name: 'Historical Import (skill guide)',
    path: '/imports',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'If something goes wrong' },
  },
  {
    /*
     * THE READY GATE IS THE PAGE `h1`'s WORKSPACE LINE, AND IT USED TO BE A RACE.
     *
     * It read `{ role: 'heading', name: 'Review Record' }`. That heading is
     * `<h1 class="sr-only">` in `RecordWorkbench`'s `bundle.status !== 'data'`
     * branch — i.e. it renders while the record is still LOADING and again when
     * the API is down (`BackendDown`) — and until UX-002 the loaded branch
     * rendered the same string, so the gate happened to resolve on both. UX-002
     * replaced the loaded branch's heading with the visible
     * `h1.record-page-title` (`<workspace>` / `<record title>`), which left
     * `Review Record` as a heading that exists ONLY when the record has not
     * resolved. A gate that resolves on the loading branch lets axe, the width
     * sweep, the layout probes and the 200% pass measure a `role="status"`
     * skeleton — or `BackendDown` — and report it as this surface.
     *
     * `Record Fields` is the `.eyebrow` inside that `h1`, so it cannot render
     * before `bundle.status === 'data'`. It is the workspace name rather than
     * the record title on purpose: this gate's job is "the loaded branch
     * mounted", and pinning the seed's scientific title here would make every
     * sweeping spec restate fixture content. That the `h1` names the RECORD is
     * asserted where it belongs — `specs/workspace-scope.spec.ts` and
     * `specs/record-identity.spec.ts`.
     */
    id: 'record-detail',
    name: 'Record Detail (needs attention)',
    path: `/record/${SEED.partial}`,
    scope: 'example',
    ready: { role: 'heading', name: /^Record Fields/ },
  },
  {
    /*
     * THE RUNS WORKSPACE — `?view=runs`, and NOT the same DOM as `record-detail`.
     *
     * The record screen's four destinations are `?view=` deep links on one route
     * (`RECORD_VIEW_IDS`), and `record-detail` lands on `fields`, which is what the
     * route defaults to. So until this entry existed, axe, the 320/390 narrow sweep,
     * the five-project layout probes and the 200% zoom pass had never loaded the run
     * list, its search and filter controls, its paging, a `RunCard`'s accordion or
     * `ValidateReview` on ANY surface — several hundred lines of markup on a measured
     * route, unmeasured. That is the same failure mode `evidence-graph` and
     * `statistics-example` were added to fix, and it is worth naming as the same one.
     *
     * `ready` waits on the Runs section's own heading rather than the page `h1`: the
     * screen heading renders while the runs list is still fetching, and scanning in
     * between would audit a `role="status"` loading panel.
     */
    id: 'record-runs',
    name: 'Record Detail — Runs',
    path: `/record/${SEED.partial}?view=runs`,
    scope: 'example',
    ready: { role: 'heading', name: 'Runs' },
  },
  {
    /*
     * THE CAPTURE & PROPOSALS WORKSPACE — `?view=capture`, the third `?view=` deep
     * link, and unmeasured for the same reason the entry above was. It mounts three
     * panels no other surface reaches on this route: transcript capture (its voice
     * controls, its seam-status disclosure and its textarea), the unmapped-notes
     * queue, and the ingestion-proposals list.
     *
     * `ready` USED TO WAIT on the transcript panel's own heading. It no longer can,
     * and the reason is a deliberate product change rather than a broken selector:
     * the capture workspace now lands on the three-route CHOOSER (`CaptureIntake`),
     * and the panel — which the chooser opens — renders nothing at all until it
     * does, because two entry points for one action was the defect that change
     * fixed. So the probe is the chooser's own heading, which is what a reader
     * actually meets on arrival.
     *
     * *** WHAT THIS DOES AND DOES NOT DO TO COVERAGE, stated because `ready`
     * silently decides what gets scanned. *** The panel's closed-state entry (its
     * heading and its one button) leaves this scan; the chooser's three cards,
     * three action controls and advisory limit note enter it — so the surface gains
     * controls rather than losing them. What is UNCHANGED is the gap
     * `a11y-baseline.ts` already records in full: the panel's textarea, run select,
     * candidate list, decision controls and every voice control are STILL UNSCANNED,
     * because this scan does not press the entry. That gap was not created here and
     * is not closed here; driving the disclosure remains its own slice, exactly as
     * that note says.
     */
    /*
     * 2026-09-22 (owner QA C1): this is now CAPTURE HOME only — the four ways in
     * and a one-line summary. The notes queue and the proposals list it used to
     * mount moved to `record-proposals` below, and the transcript form to
     * `record-capture-write`; both are registered IN THE SAME CHANGE, for the
     * `QA-018` reason `record-activity` records, so no panel leaves the sweep.
     */
    id: 'record-capture',
    name: 'Record Detail — Capture',
    path: `/record/${SEED.partial}?view=capture`,
    scope: 'example',
    ready: { role: 'heading', name: /How do you want to get this experiment in\?/i },
  },
  {
    /*
     * THE FOCUSED WRITE VIEW (2026-09-22, C2). It closes a gap the entry above
     * recorded for as long as it existed: the transcript textarea and run select
     * were NEVER scanned, because the scan did not press the panel's entry. Here
     * the address itself opens them. New cells; only Linux CI can measure them.
     */
    id: 'record-capture-write',
    name: 'Record Detail — Capture · Write It Down',
    path: `/record/${SEED.partial}?view=capture&method=write`,
    scope: 'example',
    ready: { role: 'heading', name: 'Write It Down' },
  },
  {
    /*
     * THE FOCUSED VOICE VIEW (2026-09-22, C3): the Claude path read from
     * `mcp.posture`, and the local recorder behind its disclosure (collapsed, so
     * the recorder's own controls are scanned only once a reader opens it — the
     * same bound the capture entry above always had).
     */
    id: 'record-capture-voice',
    name: 'Record Detail — Capture · Record at the Instrument',
    path: `/record/${SEED.partial}?view=capture&method=voice`,
    scope: 'example',
    ready: { role: 'heading', name: 'Record at the Instrument' },
  },
  {
    /*
     * THE FOCUSED PROPOSALS VIEW (2026-09-22, N3/P3) — the ingestion-proposals list
     * and the unmapped-notes queue, which `record-capture` scanned until they moved
     * here. Registered with the move so their coverage is continuous.
     */
    id: 'record-proposals',
    name: 'Record Detail — Proposals',
    path: `/record/${SEED.partial}?view=proposals`,
    scope: 'example',
    ready: { role: 'heading', name: 'Suggestions' },
  },
  {
    /*
     * *** QA-018 CLOSED, 2026-09-13. THIS WORKSPACE HAD NEVER BEEN
     * ACCESSIBILITY-SCANNED — before or after UX-002 put a visible `h1` on it. ***
     *
     * `record-graph` appeared nowhere in this file; its only two references in the
     * whole of `e2e/` were inside `specs/visual-sweep.spec.ts`, which takes
     * screenshots and asserts nothing about accessibility. So three of the record's
     * four workspaces were axe- and narrow-width-measured and the fourth was
     * screenshot-swept only — on what was, until `EVG-002`, the most control-dense
     * surface on the record screen (34 buttons, 145 text elements).
     *
     * THE LEDGER SAID THIS WOULD MINT FRESH BASELINE CELLS ON BOTH PLATFORMS AND SO
     * WAS "not a one-line change". It measured otherwise, and the measurement is why
     * it could be closed here: the FIRST scan reported exactly two rules —
     * `[serious] list` (1 node) and `[minor] aria-allowed-role` (3 nodes) — with ONE
     * root cause, `role="note"` overriding the implicit `listitem` role on three
     * `<li>`s. Removing it (see `ExperimentGraphPanel.tsx`) cleared both.
     *
     * **So this surface is added with NO baseline entry at all: it audits clean.**
     * That is the outcome to preserve — a new cell here would be recorded debt, and
     * there is none to record.
     *
     * It is still reached by ADDRESS only, which is deliberate (`EVG-002` removed
     * the sidebar link) and is precisely why it must be scanned: a destination a
     * scientist can still bookmark and open is a destination that has to be usable.
     */
    id: 'record-graph',
    name: 'Record Detail — Graph',
    path: `/record/${SEED.partial}?view=graph`,
    scope: 'example',
    ready: { role: 'heading', name: /Experiment Graph/i },
  },
  {
    /*
     * `record-activity` — REGISTERED WITH THE WORKSPACE, NOT AFTER IT (`ACT-003`).
     *
     * `QA-018` is the precedent and the reason this entry exists in the same change
     * as the panel rather than a later one. That item closed a gap where
     * `record-graph` "had never been accessibility-scanned" — three of the record's
     * four workspaces were axe- and narrow-width-measured and the fourth was not,
     * because it had simply never been added here. A fifth workspace shipped without
     * an entry would repeat that exactly, and the argument `record-graph`'s own note
     * makes applies unchanged: a destination a scientist can open is a destination
     * that has to be usable.
     *
     * THE CONSEQUENCE IS ACCEPTED RATHER THAN AVOIDED: adding a surface here means
     * the sweep scans it at every viewport and produces NEW baseline cells, which
     * only Linux CI can measure. That round trip is the cost of the surface being
     * covered, and skipping it to avoid the cost is the thing `QA-018` names.
     */
    id: 'record-activity',
    name: 'Record Detail — Activity',
    path: `/record/${SEED.partial}?view=activity`,
    scope: 'example',
    ready: { role: 'heading', name: /Activity History/i },
  },
  {
    id: 'guided-completion',
    name: 'Guided Completion',
    path: recordSub(SEED.partial, 'complete'),
    scope: 'example',
    ready: { role: 'heading', name: /Answer \d+ Question/ },
  },
  {
    id: 'evidence',
    name: 'Evidence & File Preview',
    path: recordSub(SEED.partial, 'evidence'),
    scope: 'example',
    ready: { role: 'heading', name: 'Evidence & File Preview' },
  },
  {
    /*
     * The Evidence GRAPH, which is a `?view=` deep link on the Evidence route and
     * NOT the same DOM as the entry above it.
     *
     * `evidence` lands on the LIST view — that is what the route defaults to — so
     * until this entry existed, axe, the 320/390 narrow sweep, the five-project
     * layout probes and the 200% zoom pass had never loaded the graph panel at
     * all. Its canvas, its `role="tree"`, its kind-filter chips, its details pane
     * and its notes were unmeasured markup on a measured route, which is the
     * failure mode `statistics-example` was added to fix and is worth naming as
     * the same one.
     *
     * `ready` waits on the panel's own heading rather than the page `h1`: the
     * screen heading renders while the graph is still fetching this experiment's
     * runs, and scanning in between would audit a `role="status"` loading panel.
     */
    id: 'evidence-graph',
    name: 'Evidence & File Preview — Graph',
    path: `${recordSub(SEED.partial, 'evidence')}?view=graph`,
    scope: 'example',
    ready: { role: 'heading', name: 'Evidence Graph' },
  },
  {
    id: 'export-readiness',
    name: 'Export Readiness (in review)',
    path: recordSub(SEED.review, 'export'),
    scope: 'example',
    ready: { role: 'heading', name: /Ready to Export|Export/ },
  },
  {
    id: 'export-readiness-done',
    name: 'Export Readiness (exported)',
    path: recordSub(SEED.done, 'export'),
    scope: 'example',
    ready: { role: 'heading', name: /Export/ },
  },
  /*
   * ~~`memory`, `memory-graph` — Project Memory~~ — RETIRED 2026-11-16: Project Memory is
   * a developer tool behind `VITE_ISAAC_DEV_TOOLS=1`, which this suite's build does not
   * set, so `/memory` redirects to My Experiments. Neither recorded an a11y cell.
   */
  {
    /*
     * QA-020 — the not-found state, enrolled deliberately and with its cost known.
     *
     * `QA-018`'s closure recorded the lesson in its own commit subject: adding an
     * entry here enrols a surface in THIRTEEN sweeps, not one, and mints fresh
     * baseline cells on BOTH platforms. It is enrolled anyway, because the
     * alternative is a scientist-facing screen that no axe or narrow-width run has
     * ever measured — which is exactly the gap `QA-018` existed to close, and
     * shipping a NEW one while closing the old would be the worse trade.
     *
     * `scope: 'ordinary'` because this screen reads no record and needs no worked
     * example: it is reachable at any unrecognised address, in any scope.
     */
    id: 'not-found',
    name: 'Page not found',
    path: '/an-address-no-route-declares',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Page not found' },
  },
  /*
   * ~~`governance` — "Governance & Safety — Policy", path `/governance`~~ — RETIRED
   * 2026-10-12, and the retirement is a de-duplication, not a coverage loss. The
   * Policy tab moved to Settings › Privacy & Governance (`DEC-28`), and
   * `/governance` (no tab, or `?tab=policy`) now REDIRECTS there, so this entry
   * would scan exactly the DOM `settings-privacy` already scans. It recorded no
   * baseline cell, so no count moves with it.
   */
  {
    id: 'validator',
    name: 'Governance & Safety — Validator',
    path: '/governance?tab=validator',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Standalone Validator' },
  },
  {
    id: 'schema-reference',
    name: 'Governance & Safety — Schema Reference',
    path: '/governance?tab=schema',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Governance & Safety' },
  },
  {
    id: 'statistics',
    name: 'Statistics (ordinary, empty)',
    path: '/statistics',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Records' },
  },
  {
    // NEW, for the same reason `experiments-example` is, and it was MISSED when that
    // one was added. `statistics` fell 48 -> 18 tolerated a11y nodes in the
    // tutorial-scope slice and the drop was NOT compensated: every figure on this
    // page is derived from `GET /api/runtime/records`, so in the ordinary (permanently
    // empty) workspace the per-record breakdown rows — the four record cards' real
    // counts, the workflow spine's bars, the five evidence chips, the export-gate rows
    // — simply do not render. That markup now exists ONLY inside a worked-example
    // session, and until this entry existed it was scanned by no surface in any
    // project: 30 nodes of recorded debt stopped being measured while reading as an
    // accessibility improvement.
    id: 'statistics-example',
    name: 'Statistics (worked example)',
    path: '/statistics',
    scope: 'example',
    ready: { role: 'heading', name: 'Records' },
  },
  /*
   * ~~`statistics-build` — Statistics → Build & Verification~~ — RETIRED 2026-11-16: a
   * developer tab behind `VITE_ISAAC_DEV_TOOLS=1`; without it `?tab=build` shows Overview,
   * which `statistics` scans. It recorded no a11y cell.
   */
  /*
   * ── SETTINGS IS FOUR TABS OF WIDGETS SINCE 2026-10-12 ─────────────────────
   *
   * Seven tabs became Overview · Privacy & Governance · Integrations · Advanced.
   * Every retired `?tab=` id is an alias onto one of the four, so the entries
   * below KEEP their ids and their paths — `settings-api` still opens
   * `?tab=api`, `settings-explorer` still opens `?tab=explorer` — which means
   * the e2e sweep exercises the aliases in a real browser, and the
   * `settings-explorer` cells keep their measured history instead of being
   * re-keyed under a name no darwin run has seen. What each path now SCANS is
   * the tab its alias lands on, and the names say so.
   *
   * TWO ENTRIES ARE RETIRED as exact duplicates, and neither recorded a cell:
   * `settings-about` (`?tab=about` lands on Overview, which `settings` scans)
   * and `settings-connect` (`?tab=mcp` lands on Integrations, which
   * `settings-api` scans).
   */
  {
    id: 'settings',
    name: 'Settings — Overview',
    path: '/settings',
    scope: 'ordinary',
    /* The gate follows a heading a reader actually sees, and one that renders
       only after `/api/about` resolves would be stricter still — `Version`
       (~~`This Build`~~, renamed 2026-11-17) renders at once, so the gate is the
       widget's own title. */
    ready: { role: 'heading', name: 'Version' },
  },
  /*
   * ~~`settings-privacy` — "Settings — Privacy & Governance", `?tab=privacy`~~ —
   * RETIRED 2026-11-02 with the tab (owner's direction: no standing disclaimers).
   * `?tab=privacy` now lands on Overview, which `settings` scans; its facts are the
   * Data card there. It recorded no a11y cell, so no count moves with it.
   */
  {
    id: 'settings-api',
    name: 'Settings — Integrations (via ?tab=api)',
    path: '/settings?tab=api',
    scope: 'ordinary',
    /* ~~'No API Keys in This Build'~~ — retired 2026-11-02; the widget's own title. */
    ready: { role: 'heading', name: 'API Access' },
  },
  /*
   * ~~`settings-explorer` — Settings → Advanced, `?tab=explorer`~~ — RETIRED 2026-11-16:
   * Advanced is a developer tab behind `VITE_ISAAC_DEV_TOOLS=1`; without it `?tab=explorer`
   * lands on Integrations, which `settings-api` scans. It recorded no a11y cell.
   */
  /*
   * ~~`settings-connect` — "Settings — Connect Your Agent", `?tab=mcp`~~ — RETIRED
   * 2026-10-12 as a duplicate: `?tab=mcp` now lands on Integrations, which
   * `settings-api` scans whole (the Connect Your Agent widget included). Its
   * cells were all deleted earlier (2026-09-15, a real palette fix), so no
   * count moves with it. The reasoning that ADDED it — a Settings surface no
   * suite opens is a surface nothing checks — is unchanged and is satisfied by
   * `settings-api`.
   */
  /*
   * ── SCHEMA PROPOSALS AND LOCAL IMPORTS, ADDED 2026-10-29 (audit) ──────────
   *
   * Neither destination was in this catalogue, so no axe scan, no 320/390 narrow
   * sweep, no five-project layout probe and no 200% pass had ever loaded either —
   * the `QA-018` gap again, for two screens a scientist can open from the nav.
   * Registered with the cost `QA-020` states: new cells, measured on the platform
   * that runs them (darwin locally, linux from CI).
   *
   * Schema Proposals has been ONE PAGE since 2026-11-02 (no tablist): the form, the
   * proposals beside it, and the whole vocabulary folded below the form. The three ids
   * are kept so every sweep keyed on them still runs, each now a different way in:
   * `?tab=browse` (an old link, still honoured) opens the folded vocabulary, so its gate
   * is the vocabulary's "Source" segmented control; the plain page's gate is the form's one
   * "List" choice; `?tab=proposals` scrolls to the Proposals column, whose named region
   * is its gate. The first two render only once the vocabulary has arrived; the region
   * is there from the start, so `app.open`'s loading-panel wait is what keeps the scan
   * off the skeleton (the read-only e2e backend holds no proposals).
   */
  {
    id: 'schema-proposals',
    name: 'Schema Proposals — Look Up an Existing List (opened)',
    path: '/schema-proposals?tab=browse',
    scope: 'ordinary',
    ready: { role: 'radiogroup', name: 'Source' },
  },
  {
    id: 'schema-proposals-propose',
    name: 'Schema Proposals — Propose a Change',
    path: '/schema-proposals?tab=propose',
    scope: 'ordinary',
    ready: { role: 'combobox', name: 'List' },
  },
  {
    id: 'schema-proposals-list',
    name: 'Schema Proposals — Proposals',
    path: '/schema-proposals?tab=proposals',
    scope: 'ordinary',
    ready: { role: 'region', name: 'Proposals' },
  },
  /*
   * Local Imports is a LOCAL-BUILD destination (`VITE_ISAAC_LOCAL_IMPORTS=1`) over an
   * API the e2e backend does not serve — see `localImportsMock` and
   * `e2e/local-imports-mock.ts`. Both views are gated on headings inside their
   * `status === 'data'` branches. The questions fixture carries a 57-character value
   * every run of one group suggests, so the narrow sweeps measure the
   * "Accept <long value>" buttons at 320/390 and at 200% zoom.
   */
  {
    id: 'local-imports',
    name: 'Local Imports — Import Progress (synthetic, mocked API)',
    path: '/local-imports',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Import Progress' },
    localImportsMock: true,
  },
  {
    id: 'local-imports-questions',
    name: 'Local Imports — One Bundle’s Questions (synthetic, mocked API)',
    path: '/local-imports?bundle=synthetic-beamtime',
    scope: 'ordinary',
    ready: { role: 'heading', name: /^Questions/ },
    localImportsMock: true,
  },
] as const;

/**
 * Every route the Assistant panel mounts on. Verified in the running app:
 * an `<aside>` with the accessible name "Assistant" on every mount (Project Memory's
 * "Assistant (advisory)" was retired 2026-11-02), containing `role="log"`.
 *
 * Carries its own `scope` for the same reason `Surface` does: all four mounts are
 * record surfaces and exist only inside a worked-example session. (Project Memory's
 * mount went behind the developer flag on 2026-11-16.)
 */
export const ASSISTANT_MOUNTS: readonly {
  id: string;
  path: string;
  scope: SurfaceScope;
  asideName: RegExp;
}[] = [
  { id: 'record-detail', path: `/record/${SEED.partial}`, scope: 'example', asideName: /^Assistant/ },
  {
    id: 'guided-completion',
    path: recordSub(SEED.partial, 'complete'),
    scope: 'example',
    asideName: /^Assistant/,
  },
  { id: 'evidence', path: recordSub(SEED.partial, 'evidence'), scope: 'example', asideName: /^Assistant/ },
  { id: 'export-readiness', path: recordSub(SEED.review, 'export'), scope: 'example', asideName: /^Assistant/ },
  // ~~`memory`~~ — retired 2026-11-16: `/memory` is behind the developer flag.
] as const;

/** Surfaces that own a `role="tablist"`, with the expected tab labels. */
export const TABBED_SURFACES = [
  // ~~`memory`~~ — retired 2026-11-16: `/memory` is behind the developer flag.
  {
    id: 'governance',
    /* Policy moved to Settings (2026-10-12) and a bare `/governance` redirects
       there, so the tablist is reached by naming one of its two tabs. */
    path: '/governance?tab=validator',
    tablistName: 'Governance & Safety sections',
    tabs: ['Validator', 'Schema Reference'],
    panelIdPrefix: 'governance-tabpanel-',
  },
  {
    id: 'settings',
    path: '/settings',
    tablistName: 'Settings sections',
    // R0 added 'Help & Tutorial' (the tutorial replay surface). The tab COUNT the
    // APG-structure spec asserts is derived from this array, so the list is the
    // single place a new tab has to be declared — no magic number to chase.
    /* REORDERED AND RENAMED 2026-09-15 — two groups on one flat tablist, the
       four scientist-facing tabs then the three developer ones under an
       "Advanced" marker. ONLY THE ORDER CHANGED — no accessible name did.
       The group reaches assistive technology as an `aria-describedby`
       DESCRIPTION, announced after the name, precisely so that a tab's name
       stays the handle every suite queries it by. `tabs.spec.ts` asserts each
       entry with `toHaveAccessibleName`, an EXACT match, and the tab COUNT the
       APG-structure spec asserts is derived from this array, so the list stays
       the single place a tab is declared. */
    /* FOUR TABS SINCE 2026-10-12 — Overview · Privacy & Governance ·
       Integrations · Advanced. The tab COUNT the APG-structure spec asserts is
       derived from this array, so the list stays the single place a tab is
       declared. */
    /* THREE TABS SINCE 2026-11-02 — Privacy & Governance was retired. */
    /* TWO SINCE 2026-11-16 — Advanced is behind the developer flag. */
    tabs: ['Overview', 'Integrations'],
    panelIdPrefix: 'settings-tabpanel-',
  },
  // ~~`statistics`~~ — retired 2026-11-16: with Build & Verification behind the developer
  // flag and My Stats not offered, Overview is the whole page and no tablist is drawn.
  // Schema Proposals' own tablist (2026-10-29) was removed on 2026-11-02, when the
  // screen became one page with no tabs; its three surfaces above still catalogue it.
] as const;
