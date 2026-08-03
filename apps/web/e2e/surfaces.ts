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

export interface Surface {
  /** Stable key used in test titles and in the a11y baseline. Never rename casually. */
  readonly id: string;
  /** Human name for report output. */
  readonly name: string;
  readonly path: string;
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
    name: 'My Experiments',
    path: '/experiments',
    ready: { role: 'heading', name: 'My Experiments' },
  },
  {
    id: 'load',
    name: 'Load Materials',
    path: '/load',
    ready: { role: 'button', name: 'Run the Worked Example' },
    // FINDING A11Y-05: this surface renders no <h1>. Recorded, not waived.
    expectH1: false,
  },
  {
    id: 'record-detail',
    name: 'Record Detail (needs attention)',
    path: `/record/${SEED.partial}`,
    ready: { role: 'heading', name: 'Review Record' },
  },
  {
    id: 'guided-completion',
    name: 'Guided Completion',
    path: recordSub(SEED.partial, 'complete'),
    ready: { role: 'heading', name: /Answer \d+ Question/ },
  },
  {
    id: 'evidence',
    name: 'Evidence & File Preview',
    path: recordSub(SEED.partial, 'evidence'),
    ready: { role: 'heading', name: 'Evidence & File Preview' },
  },
  {
    id: 'export-readiness',
    name: 'Export Readiness (in review)',
    path: recordSub(SEED.review, 'export'),
    ready: { role: 'heading', name: /Ready to Export|Export/ },
  },
  {
    id: 'export-readiness-done',
    name: 'Export Readiness (exported)',
    path: recordSub(SEED.done, 'export'),
    ready: { role: 'heading', name: /Export/ },
  },
  {
    id: 'memory',
    name: 'Project Memory — Overview',
    path: '/memory',
    ready: { role: 'heading', name: 'Project Memory' },
  },
  {
    id: 'memory-graph',
    name: 'Project Memory — Graph',
    path: '/memory?tab=graph',
    ready: { role: 'heading', name: 'Graph' },
  },
  {
    id: 'governance',
    name: 'Governance & Safety — Policy',
    path: '/governance',
    ready: { role: 'heading', name: 'Governance & Safety' },
  },
  {
    id: 'validator',
    name: 'Governance & Safety — Validator',
    path: '/governance?tab=validator',
    ready: { role: 'heading', name: 'Standalone Validator' },
  },
  {
    id: 'schema-reference',
    name: 'Governance & Safety — Schema Reference',
    path: '/governance?tab=schema',
    ready: { role: 'heading', name: 'Governance & Safety' },
  },
  {
    id: 'statistics',
    name: 'Statistics',
    path: '/statistics',
    ready: { role: 'heading', name: 'Workspace at a Glance' },
  },
  {
    id: 'settings',
    name: 'Settings & API — Overview',
    path: '/settings',
    ready: { role: 'heading', name: 'Runtime Status' },
  },
  {
    id: 'settings-privacy',
    name: 'Settings & API — Data & Privacy',
    path: '/settings?tab=privacy',
    ready: { role: 'heading', name: 'Settings & API' },
  },
  {
    id: 'settings-about',
    name: 'Settings & API — About',
    path: '/settings?tab=about',
    ready: { role: 'heading', name: 'Identity' },
  },
  {
    id: 'settings-api',
    name: 'Settings & API — API Access',
    path: '/settings?tab=api',
    ready: { role: 'heading', name: 'How Access Works Today' },
  },
  {
    id: 'settings-explorer',
    name: 'Settings & API — Endpoint Explorer',
    path: '/settings?tab=explorer',
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
 */
export const ASSISTANT_MOUNTS: readonly { id: string; path: string; asideName: RegExp }[] = [
  { id: 'record-detail', path: `/record/${SEED.partial}`, asideName: /^Assistant/ },
  { id: 'guided-completion', path: recordSub(SEED.partial, 'complete'), asideName: /^Assistant/ },
  { id: 'evidence', path: recordSub(SEED.partial, 'evidence'), asideName: /^Assistant/ },
  { id: 'export-readiness', path: recordSub(SEED.review, 'export'), asideName: /^Assistant/ },
  { id: 'memory', path: '/memory', asideName: /^Assistant/ },
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
    tabs: ['Overview', 'Data & Privacy', 'About', 'API Access', 'Endpoint Explorer'],
    panelIdPrefix: 'settings-tabpanel-',
  },
] as const;
