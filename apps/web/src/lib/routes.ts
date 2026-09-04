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
 * The Review Record screen's four WORKSPACES — the record's own fields, its
 * runs, the capture-and-proposals pipeline, and the experiment-scoped graph —
 * on the SAME `?tab=`-style mechanism as Settings, Governance and Statistics.
 * ~~A fourth use of one convention, not a fourth convention.~~ — THE SIXTH, and
 * the miscount was inherited rather than introduced here: `?tab=` on Settings,
 * Governance and Statistics, `?view=` here and again on Evidence, and `?run=`
 * below all read and write one parameter the same way. Corrected rather than
 * deleted because the sentence's point — one convention, reused — is the reason
 * this list could gain two members without gaining a mechanism.
 *
 * Deep-linkability is the point: a graph a scientist reached by clicking and
 * cannot then link a colleague to is half a feature. Anything unrecognised
 * falls back to `fields`, so there is no dead route and an old bookmark still
 * lands on the record.
 *
 * ── IT WENT FROM TWO MEMBERS TO FOUR, AND THE MECHANISM DID NOT CHANGE. ─────
 *
 * `fields` and `graph` were two RENDERINGS of one record and were switched by a
 * `.section-tabs` bar at the top of the main column. `runs` and `capture` are
 * different CONTENT of the same record, and the switcher is now the record's own
 * sidebar (`RecordWorkspaceNav`) rather than a second navigation bar — one place
 * a reader looks for "where can I go from here", beside the workflow spine that
 * already answers "where am I in the pipeline". The two lists are deliberately
 * unlike each other: the spine is SERVER-DERIVED and GATED, and these four are
 * ungated local destinations that carry no completion state and never look like
 * workflow steps.
 *
 * `fields` stays FIRST and stays the fallback, so `/record/<id>` bare is exactly
 * the screen it has always been.
 */
export const RECORD_VIEW_PARAM = 'view';

export const RECORD_VIEW_IDS = ['fields', 'runs', 'capture', 'graph'] as const;

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

/**
 * The Evidence screen's two VIEWS — the evidence LIST (the trail rail, the
 * classification, the reconciliation and the source preview, exactly as they
 * were) and the evidence GRAPH.
 *
 * The SAME `?view=` mechanism, deliberately reusing `RECORD_VIEW_PARAM`'s name
 * rather than minting a second one: the two screens are different routes, so
 * `?view=` cannot collide, and a scientist who has learned what `?view=` means
 * on the record screen has learned it here too.
 *
 * `list` is the fallback for anything unrecognised, so an old bookmark to
 * `/record/<id>/evidence` lands on precisely the screen it always did — the
 * addition is not allowed to move anyone's existing entry point.
 *
 * The FOCUS RUN param above is read on this screen too: `?view=graph&run=<id>`
 * opens the graph anchored on one run. An id naming no LOADED run is stated
 * rather than guessed (see `buildEvidenceGraph` step 7).
 */
export const EVIDENCE_VIEW_PARAM = RECORD_VIEW_PARAM;

export const EVIDENCE_VIEW_IDS = ['list', 'graph'] as const;

export type EvidenceViewId = (typeof EVIDENCE_VIEW_IDS)[number];

export function isEvidenceView(value: string | null | undefined): value is EvidenceViewId {
  return EVIDENCE_VIEW_IDS.includes(value as EvidenceViewId);
}

/**
 * COMPARE RUNS — the record screen's "show me these two runs against each other"
 * mode, on the SAME `?param=` mechanism as `tab`, `view` and `run`. A sixth use of
 * one convention, and the value is read with `useSearchParams` and written by
 * COPYING the existing `URLSearchParams`, so nothing else on the record URL is
 * dropped by entering or leaving a comparison.
 *
 * IT IS A REPEATED PARAMETER — `?compare=RUN003&compare=RUN014` — and that is the
 * one place this differs from its five siblings, so it is justified rather than
 * assumed. The alternatives were a comma-joined single value and two numbered
 * parameters. A comma-joined value has to encode "one chosen, one still to choose"
 * as a trailing comma, which is a state a reader can produce by hand and which
 * every consumer then has to special-case; two numbered parameters make
 * `compare1` and `compare2` two concepts where there is one, and invite a
 * `compare2` with no `compare1`. `getAll` gives the SET of runs being compared as
 * one thing, degrades honestly to one and to none, and needs no delimiter that a
 * run id might one day contain.
 *
 * WHY IT IS IN THE URL AT ALL. A comparison is the single most linkable artifact
 * this screen produces — "these two runs differ here" is exactly the sentence a
 * scientist sends to a colleague — and selection held in `useState` cannot be
 * linked, bookmarked or reloaded back into. The same defect (a view reachable by
 * clicking but not by link) has already been shipped twice in this repository and
 * fixed twice.
 *
 * THE VALUES ARE RUN IDS AND ARE NEVER VALIDATED HERE. The section resolves each
 * against the server and says honestly when no such run exists, exactly as Focus
 * Run does. An absent parameter means "not comparing", so there is no dead route.
 */
export const RECORD_COMPARE_PARAM = 'compare';

/**
 * TWO. Not `n`, and the number is a decision rather than a first iteration.
 *
 * A two-column table can put an address, both values and the relation between them
 * on one line at a readable width; a third column makes "these differ" ambiguous
 * about WHICH pair differs, and the honest rendering of an n-way comparison is a
 * different component with a different summary. A link naming more than two runs
 * is therefore not silently truncated — the surface says which ones it is not
 * comparing.
 */
export const RUN_COMPARE_MAX = 2;

/**
 * WHICH ADDRESS A LINK INTO FOCUS RUN IS ABOUT — `?at=field:sample.material.name`.
 *
 * A SCROLL TARGET AND NOTHING ELSE, and the limit is the point. Compare Runs links
 * every differing cell back to the run it was read from; before this the
 * destination knew only WHICH RUN, so a reader following a difference at one
 * address landed on a card carrying every address and had to find it again. The
 * section brings the matching `[data-address]` element into view and marks it.
 *
 * IT SELECTS, FILTERS AND CHANGES NOTHING. An address the focused run does not
 * render — a stale link, a cleared override, a different record — leaves the page
 * exactly as it would have been without the parameter, which is why it needs no
 * validation and can never produce a dead route. It is deliberately NOT read as
 * "show only this address": hiding the rest would answer a narrower question than
 * the reader asked, and would do it on the strength of a query parameter they may
 * not have noticed following.
 */
export const RECORD_ADDRESS_PARAM = 'at';

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
  /** A deep link to ONE run on a record, e.g.
   *  `/record/<id>?view=runs&run=<runId>`. Same division of labour as
   *  `settingsTab` and `recordView`: whole-URL links use this, while the Runs
   *  section itself enters and leaves focus by copying its own
   *  `URLSearchParams` so any other query parameter survives.
   *
   *  IT NAMES THE WORKSPACE NOW, and it has to. A run lives on the `runs`
   *  workspace, and a URL that carried only `?run=` would land the reader on
   *  Record Fields with a focused run they cannot see. The screen ALSO reads a
   *  bare `?run=` as `runs` (see `RecordWorkbench`), so every link minted before
   *  this change still opens the run it names — the redundancy is deliberate:
   *  one half serves old links, the other makes new ones self-describing. */
  recordRun: (id: string, runId: string) =>
    `/record/${id}?${RECORD_VIEW_PARAM}=runs&${RECORD_RUN_PARAM}=${encodeURIComponent(runId)}`,
  /** A deep link to a comparison of two runs, e.g.
   *  `/record/<id>?view=runs&compare=<runA>&compare=<runB>`. It names the
   *  workspace for the reason `recordRun` above states, and the screen reads a
   *  bare `?compare=` as `runs` so links minted before that still land right.
   *  Same division of labour as
   *  `recordRun`: whole-URL links use this, while the Runs section adds and
   *  removes runs by copying its own `URLSearchParams`. It builds whatever it is
   *  given — including one id, which is a half-made selection and a legitimate
   *  thing to link to — and never pads the list to two. */
  recordCompare: (id: string, runIds: readonly string[]) =>
    `/record/${id}?${RECORD_VIEW_PARAM}=runs${runIds
      .map((runId) => `&${RECORD_COMPARE_PARAM}=${encodeURIComponent(runId)}`)
      .join('')}`,
  complete: (id: string) => `/record/${id}/complete`,
  evidence: (id: string) => `/record/${id}/evidence`,
  /** A deep link to ONE Evidence view, e.g. `/record/<id>/evidence?view=graph`.
   *  Same division of labour as `recordView`: whole-URL links use this, while
   *  the screen itself switches views by copying its own `URLSearchParams` so
   *  a `?run=` focus survives the switch. */
  evidenceView: (id: string, view: EvidenceViewId) =>
    `/record/${id}/evidence?${EVIDENCE_VIEW_PARAM}=${view}`,
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
