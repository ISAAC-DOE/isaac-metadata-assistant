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

export const SETTINGS_TAB_IDS = ['overview', 'privacy', 'about', 'api', 'explorer'] as const;

export type SettingsTabId = (typeof SETTINGS_TAB_IDS)[number];

export function isSettingsTab(value: string | null | undefined): value is SettingsTabId {
  return SETTINGS_TAB_IDS.includes(value as SettingsTabId);
}

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
  record: (id: string) => `/record/${id}`,
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
