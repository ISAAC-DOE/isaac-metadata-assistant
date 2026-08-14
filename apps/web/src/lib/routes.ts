/*
 * Route constants. Record sub-surfaces (S4/S5/S6) are nested under /record/:id
 * and are reachable only when the WorkflowSpine gate allows.
 */

/**
 * Settings page tabs are deep-linkable through a stable `?tab=` query parameter
 * — the SAME mechanism `GovernancePage` already uses, rather than a third
 * convention. The tab id is the query VALUE, so every link stays relative to the
 * router `basename` ('' locally, '/krish' in the deployed build) and no surface
 * ever writes a base path of its own.
 *
 * An absent, empty or unrecognised value falls back to `overview` without
 * throwing, so there is no dead route.
 */
export const SETTINGS_TAB_PARAM = 'tab';

/*
 * `help` (R0) is the Help & Tutorial tab — the one permanent home of the guided
 * walkthrough's replay control. It is a tab id like the other five, so it is
 * deep-linkable (`/settings?tab=help`) by exactly the same mechanism, and the
 * walkthrough's own last step links to it rather than describing where to find it.
 */
/*
 * `mcp` is Connect Your Agent — the surface that describes ISAAC's agent
 * (machine-callable tool) interface to a human. It sits with the other two
 * "reaching this build as a program" tabs rather than at the end, because it
 * reports state like the five before it and offers no action; `help` stays last
 * for the reason given above.
 */
export const SETTINGS_TAB_IDS = [
  'overview',
  'privacy',
  'about',
  'api',
  'explorer',
  'mcp',
  'help',
] as const;

export type SettingsTabId = (typeof SETTINGS_TAB_IDS)[number];

export function isSettingsTab(value: string | null | undefined): value is SettingsTabId {
  return SETTINGS_TAB_IDS.includes(value as SettingsTabId);
}

/**
 * Statistics tabs, on the SAME `?tab=` mechanism as Settings and Governance —
 * the third use of one convention, not a third convention.
 *
 * Deep-linkability is the point rather than a nicety: a tab held only in
 * `useState` cannot be linked to, bookmarked, or reloaded back into, and that
 * exact defect was already shipped once on Governance (the Validator tab was
 * unreachable by link) and fixed there. Anything unrecognised falls back to
 * `general` without throwing, so there is no dead route.
 *
 * `general` is the workspace-wide material; `mine` is the personal tab.
 */
export const STATISTICS_TAB_PARAM = 'tab';

export const STATISTICS_TAB_IDS = ['general', 'mine'] as const;

export type StatisticsTabId = (typeof STATISTICS_TAB_IDS)[number];

export function isStatisticsTab(value: string | null | undefined): value is StatisticsTabId {
  return STATISTICS_TAB_IDS.includes(value as StatisticsTabId);
}

/**
 * The Review Record screen's two VIEWS — the field workbench and the
 * experiment-scoped graph — on the SAME `?tab=`-style mechanism as Settings,
 * Governance and Statistics. A fourth use of one convention, not a fourth
 * convention.
 *
 * Deep-linkability is the point: a graph a scientist reached by clicking a tab
 * and cannot then link a colleague to is half a feature. Anything unrecognised
 * falls back to `fields`, so there is no dead route and an old bookmark still
 * lands on the record.
 */
export const RECORD_VIEW_PARAM = 'view';

export const RECORD_VIEW_IDS = ['fields', 'graph'] as const;

export type RecordViewId = (typeof RECORD_VIEW_IDS)[number];

export function isRecordView(value: string | null | undefined): value is RecordViewId {
  return RECORD_VIEW_IDS.includes(value as RecordViewId);
}

/**
 * FOCUS RUN — the record screen's "show me this one run and nothing else" mode,
 * on the SAME `?param=` mechanism as `tab` and `view`. A fifth use of one
 * convention, not a fifth convention: the value is read with `useSearchParams`
 * and written by COPYING the existing `URLSearchParams`, so `?view=graph` and
 * anything else already on the record URL survives being focused and unfocused.
 *
 * WHY IT IS IN THE URL AT ALL, rather than in `useState` inside the Runs
 * section. The Runs list is now BOUNDED — a scientist looking at run 214 of 320
 * reached it through a search and two Load Mores, and a run held only in
 * component state cannot be linked to, cannot be bookmarked, and is gone after a
 * reload. "Here is the run I mean" is exactly the thing a scientist sends to a
 * colleague, and the same defect (a view reachable by clicking but not by link)
 * was already shipped once on Governance and fixed there.
 *
 * The value is a RUN ID and is never validated here — the section resolves it
 * against the server and says honestly when no such run exists. An absent or
 * empty value simply means "not focused", so there is no dead route.
 */
export const RECORD_RUN_PARAM = 'run';

export const ROUTES = {
  experiments: '/experiments',
  load: '/load',
  memory: '/memory',
  governance: '/governance',
  statistics: '/statistics',
  settings: '/settings',
  /**
   * A deep link to one Settings & API tab, e.g. `/settings?tab=explorer`.
   *
   * Deliberately NOT used for switching tabs from inside `SettingsPage`. That
   * screen switches by copying the current `URLSearchParams` and calling
   * `setSearchParams`, which PRESERVES any other query parameter on the URL;
   * building a fresh path from this helper and navigating to it would silently
   * drop them. So this helper is for the cases that legitimately need a whole
   * URL — an external/shared deep link, a cross-surface link INTO one tab, and a
   * test's router entry — while the page itself keeps the param-preserving
   * mechanism.
   *
   * The drift that arrangement risks (this helper and the real mechanism
   * disagreeing on the parameter or the path) is guarded in
   * `__tests__/settings-page.test.tsx`, which asserts that activating a tab in the
   * app produces exactly the query string this helper builds for that tab.
   */
  settingsTab: (tab: SettingsTabId) => `/settings?${SETTINGS_TAB_PARAM}=${tab}`,
  /** A deep link to one Statistics tab, e.g. `/statistics?tab=mine`. Same
   *  division of labour as `settingsTab`: whole-URL links use this, while the
   *  page itself switches tabs by copying its own `URLSearchParams` so any other
   *  query parameter survives. */
  statisticsTab: (tab: StatisticsTabId) => `/statistics?${STATISTICS_TAB_PARAM}=${tab}`,
  record: (id: string) => `/record/${id}`,
  /** A deep link to one Review Record view, e.g. `/record/<id>?view=graph`.
   *  Same division of labour as `settingsTab`: whole-URL links use this, while
   *  the screen itself switches views by copying its own `URLSearchParams` so
   *  any other query parameter survives. */
  recordView: (id: string, view: RecordViewId) =>
    `/record/${id}?${RECORD_VIEW_PARAM}=${view}`,
  /** A deep link to ONE run on a record, e.g. `/record/<id>?run=<runId>`. Same
   *  division of labour as `settingsTab` and `recordView`: whole-URL links use
   *  this, while the Runs section itself enters and leaves focus by copying its
   *  own `URLSearchParams` so any other query parameter survives. */
  recordRun: (id: string, runId: string) =>
    `/record/${id}?${RECORD_RUN_PARAM}=${encodeURIComponent(runId)}`,
  complete: (id: string) => `/record/${id}/complete`,
  evidence: (id: string) => `/record/${id}/evidence`,
  export: (id: string) => `/record/${id}/export`,
} as const;

// Path patterns for the router definitions.
export const ROUTE_PATTERNS = {
  experiments: '/experiments',
  load: '/load',
  memory: '/memory',
  governance: '/governance',
  statistics: '/statistics',
  settings: '/settings',
  record: '/record/:id',
  complete: '/record/:id/complete',
  evidence: '/record/:id/evidence',
  export: '/record/:id/export',
} as const;
