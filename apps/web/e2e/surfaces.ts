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
  {
    id: 'load',
    name: 'Load Materials',
    path: '/load',
    // ORDINARY on purpose. `/load` renders regardless of what any workspace
    // holds: its "Run the Worked Example" button is an ordinary control that
    // POSTs `/api/demo/run`, and that endpoint's refusal outside a session is a
    // BEHAVIOUR this suite asserts elsewhere rather than a reason to open the
    // surface in a session.
    scope: 'ordinary',
    ready: { role: 'button', name: 'Run the Worked Example' },
    // FINDING A11Y-05: this surface renders no <h1>. Recorded, not waived.
    expectH1: false,
  },
  {
    id: 'record-detail',
    name: 'Record Detail (needs attention)',
    path: `/record/${SEED.partial}`,
    scope: 'example',
    ready: { role: 'heading', name: 'Review Record' },
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
  {
    id: 'memory',
    name: 'Project Memory — Overview',
    path: '/memory',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Project Memory' },
  },
  {
    id: 'memory-graph',
    name: 'Project Memory — Graph',
    path: '/memory?tab=graph',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Graph' },
  },
  {
    id: 'governance',
    name: 'Governance & Safety — Policy',
    path: '/governance',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Governance & Safety' },
  },
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
    ready: { role: 'heading', name: 'Workspace at a Glance' },
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
    ready: { role: 'heading', name: 'Workspace at a Glance' },
  },
  {
    /*
     * The My Stats tab — a NEW surface, added with the tab restructure because it
     * is genuinely new markup that no existing entry reaches: `statistics` and
     * `statistics-example` both open the default `general` tab, so nothing here
     * would have scanned the personal tab's gate, its eight planned-view cards, or
     * their headings.
     *
     * ORDINARY scope on purpose, and it is the honest one for this surface: the
     * tab renders identically in a worked-example session, because it reads
     * nothing at all. Opening it in a session would scan the same DOM twice.
     *
     * `ready` waits on the gate's own title rather than on the page `h1`, so the
     * scan cannot race a tab that has not painted its panel yet.
     */
    id: 'statistics-mine',
    name: 'Statistics — My Stats',
    path: '/statistics?tab=mine',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Personal Statistics' },
  },
  {
    id: 'settings',
    name: 'Settings & API — Overview',
    path: '/settings',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Runtime Status' },
  },
  {
    id: 'settings-privacy',
    name: 'Settings & API — Data & Privacy',
    path: '/settings?tab=privacy',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Settings & API' },
  },
  {
    id: 'settings-about',
    name: 'Settings & API — About',
    path: '/settings?tab=about',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'Identity' },
  },
  {
    id: 'settings-api',
    name: 'Settings & API — API Access',
    path: '/settings?tab=api',
    scope: 'ordinary',
    ready: { role: 'heading', name: 'How Access Works Today' },
  },
  {
    id: 'settings-explorer',
    name: 'Settings & API — Endpoint Explorer',
    path: '/settings?tab=explorer',
    scope: 'ordinary',
    // Wait for the DETAIL pane, not the group list: the list heading renders
    // before the detail mounts, and scanning in between saw an h4 before the
    // h2/h3 above it (an intermittent heading-order failure at zoom-200).
    ready: { role: 'heading', name: /\/api\/about/ },
  },
] as const;

/**
 * Every route the Assistant panel mounts on. Verified in the running app:
 * an `<aside>` with an accessible name of "Assistant" (record surfaces) or
 * "Assistant (advisory)" (Project Memory), containing `role="log"`.
 *
 * Carries its own `scope` for the same reason `Surface` does: four of the five
 * mounts are record surfaces and exist only inside a worked-example session,
 * while Project Memory is an ordinary surface with an advisory panel.
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
  { id: 'memory', path: '/memory', scope: 'ordinary', asideName: /^Assistant/ },
] as const;

/** Surfaces that own a `role="tablist"`, with the expected tab labels. */
export const TABBED_SURFACES = [
  {
    id: 'memory',
    path: '/memory',
    tablistName: 'Project Memory sections',
    tabs: ['Overview', 'Sources', 'Concepts', 'Graph'],
    panelIdPrefix: 'memory-tabpanel-',
  },
  {
    id: 'governance',
    path: '/governance',
    tablistName: 'Governance & Safety sections',
    tabs: ['Policy', 'Validator', 'Schema Reference'],
    panelIdPrefix: 'governance-tabpanel-',
  },
  {
    id: 'settings',
    path: '/settings',
    tablistName: 'Settings & API sections',
    // R0 added 'Help & Tutorial' (the tutorial replay surface). The tab COUNT the
    // APG-structure spec asserts is derived from this array, so the list is the
    // single place a new tab has to be declared — no magic number to chase.
    tabs: [
      'Overview',
      'Data & Privacy',
      'About',
      'API Access',
      'Endpoint Explorer',
      // Connect Your Agent sits between the Explorer and Help: both describe
      // reaching this build as a program, and this one states a deployment state
      // rather than offering an action.
      'Connect Your Agent',
      'Help & Tutorial',
    ],
    panelIdPrefix: 'settings-tabpanel-',
  },
  {
    // Statistics is the FOURTH page-level tablist, and it reuses the shared
    // `RovingTabs` component and the shared `.section-tabs` / `.section-tab`
    // styling rather than introducing a paradigm of its own — so the APG-structure,
    // keyboard and deep-link specs above apply to it unchanged.
    id: 'statistics',
    path: '/statistics',
    tablistName: 'Statistics sections',
    tabs: ['General ISAAC', 'My Stats'],
    panelIdPrefix: 'statistics-tabpanel-',
  },
] as const;
