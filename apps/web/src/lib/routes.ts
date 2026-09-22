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
 *
 * ── A THIRD TAB, `build`, ADDED 2026-09-15 ─────────────────────────────────
 *
 * `general` used to hold BOTH "how is my science doing" and "how is this build
 * doing" — record verification over a corpus of official records, the platform
 * adapter boundary, the runtime facts, the served memory snapshot, the official
 * schema's own shape, and the API surface. Measured at 1440x900 on a populated
 * workspace, the tab was 3,744 px of main scroll with 425 visible text
 * elements, and the FIRST viewport was entirely an engineering QA program —
 * not one workspace figure was above the fold.
 *
 * `build` is where that material now lives. Nothing is deleted, nothing becomes
 * unreachable, and every section keeps its heading, its states and its tests;
 * what changes is that a scientist's default tab answers a scientist's
 * question. The id is deliberately NOT `technical` or `advanced`: the tab holds
 * facts about the BUILD (and the corpus it was verified against), which is what
 * its label says.
 *
 * `general` remains the fallback for anything unrecognised, so every existing
 * `/statistics` link, bookmark and test entry still lands where it did.
 */
export const STATISTICS_TAB_PARAM = 'tab';

export const STATISTICS_TAB_IDS = ['general', 'mine', 'build'] as const;

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

/* `activity` JOINED 2026-09-17 (`ACT-003`). It is a DESTINATION, not a workflow
   step: there is no derivable criterion for "the history is finished", so it
   carries no completion state — the same argument `workflow.py:128-149` makes for
   submission and the capture group makes for itself. Appended last so no existing
   bookmark or test changes meaning, and `fields` remains what a bare
   `/record/<id>` resolves to. */
/* `proposals` JOINED 2026-09-22 (owner QA, N3/C1/P3): proposal review and the
   unmapped-notes queue left Capture Home for ONE focused review surface. Appended
   last for the same reason `activity` was — no existing bookmark changes meaning.
   It is a DESTINATION, not a workflow step (DEC-14's argument, unchanged). */
export const RECORD_VIEW_IDS = [
  'fields',
  'runs',
  'capture',
  'graph',
  'activity',
  'proposals',
] as const;

export type RecordViewId = (typeof RECORD_VIEW_IDS)[number];

export function isRecordView(value: string | null | undefined): value is RecordViewId {
  return RECORD_VIEW_IDS.includes(value as RecordViewId);
}

/**
 * WHICH CAPTURE TASK IS OPEN — `?view=capture&method=write`.
 *
 * Capture Home (`?view=capture`, no method) offers four ways in; three of them open
 * a FOCUSED task view on this same record screen, addressed by this parameter so a
 * task can be linked, bookmarked and reached again with Back. The fourth way in
 * (enter the scan) is the Runs workspace and needs no method of its own.
 *
 * Same `?param=` convention as `view`/`run`/`compare`: read with
 * `useSearchParams`, anything unrecognised falls back to Capture Home, so there
 * is no dead route.
 */
export const RECORD_CAPTURE_METHOD_PARAM = 'method';

export const CAPTURE_METHOD_IDS = ['write', 'voice', 'files'] as const;

export type CaptureMethodId = (typeof CAPTURE_METHOD_IDS)[number];

/** `home` is Capture Home — the chooser — and is what no/unknown `method` means. */
export type CaptureView = CaptureMethodId | 'home';

export function resolveCaptureMethod(search: string | URLSearchParams): CaptureView {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const method = params.get(RECORD_CAPTURE_METHOD_PARAM);
  return CAPTURE_METHOD_IDS.includes(method as CaptureMethodId)
    ? (method as CaptureMethodId)
    : 'home';
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

/*
 * MOVED ABOVE `resolveRecordView` ON 2026-09-13, and the reason is fragility
 * rather than style. It was declared 66 lines BELOW its only reader. That is
 * TDZ-safe at runtime — a module-level `const` is initialised before any exported
 * function is called — so nothing was broken and `tsc` had nothing to report,
 * which is exactly why an independent review had to notice it. It sits with the
 * other two `?`-parameter constants the same function reads, so the three
 * branches of that resolver now read in the order they are declared.
 */
/**
 * WHICH PROPOSAL A LINK INTO THE CAPTURE WORKSPACE IS ABOUT —
 * `?view=capture&proposal=01PROPOSAL…`.
 *
 * The SAME `?param=` mechanism as `tab`, `view`, `run`, `compare` and `at`: the
 * value is read with `useSearchParams` and, where it is written at all, by COPYING
 * the existing `URLSearchParams`, so the proposal id is the query VALUE and every
 * link stays relative to the router `basename` ('' locally, '/krish' in the deployed
 * build). No surface writes a base path of its own.
 *
 * WHY IT EXISTS. An agent that has just made a suggestion needs to be able to say
 * WHERE a person reviews it, and a sentence naming an opaque proposal id is not that
 * — the same "reachable by clicking, not by link" defect `?run=` and `?compare=`
 * each exist to close, for the one surface in this build whose whole job is
 * reviewing something somebody else produced.
 *
 * THE VALUE IS A PROPOSAL ID AND IS NEVER VALIDATED HERE. `IngestionProposalsPanel`
 * resolves it against the window the server actually returned, and says honestly
 * what it found. An absent or EMPTY value simply means "not focused", so there is no
 * dead route.
 *
 * AND WHAT "NOT FOUND" MEANS IS DELIBERATELY NARROWER THAN IT LOOKS, which is why
 * this parameter needs a sentence the other five did not. `?run=` can be resolved
 * against the server by id, so Focus Run can truthfully say "no run with this id is
 * in this record". A proposal CANNOT: the list route serves a WINDOW (oldest first
 * by default, 50 entries), there is no read-one-proposal route, and so a window that
 * does not contain the id is evidence of exactly one thing — that the id is not in
 * THIS window. It is not evidence that the record does not hold it. The panel's
 * disclosure claims only the former, and offers the controls that widen the window;
 * nothing on that surface may ever say the proposal does not exist.
 */
export const RECORD_PROPOSAL_PARAM = 'proposal';

/**
 * WHICH RECORD WORKSPACE A URL RESOLVES TO — the ONE resolution, shared.
 *
 * Extracted 2026-09-13 because it had to be, not for tidiness. It was inline in
 * `RecordWorkbench` and the WCAG 2.4.2 `document.title` floor
 * (`lib/documentTitle.ts`) needs the identical answer: a title naming a
 * workspace the screen is not rendering is a FALSE statement about the page, in
 * the one place a reader cannot see the page to check it. Duplicating the rule
 * would have been two expressions of one decision, which is the shape §15
 * records four separate table-authorization failures under.
 *
 * The rules, in order, and each is load-bearing:
 *
 * 1. An explicit, recognised `?view=` wins. (`isRecordView` rejects anything
 *    else, so an unrecognised value falls through rather than throwing — there
 *    is no dead route.)
 * 2. Otherwise, a URL carrying a RUN ADDRESS — `?run=<id>` or any number of
 *    `?compare=<id>` — resolves to `runs`. This is what makes a run deep link
 *    from outside the screen land on the workspace that can show it, without
 *    every such link having to also spell `view=runs`.
 * 3. Otherwise `fields`, the workspace a bare `/record/<id>` renders.
 */
export function resolveRecordView(search: string | URLSearchParams): RecordViewId {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const requested = params.get(RECORD_VIEW_PARAM);
  const hasProposalAddress = (params.get(RECORD_PROPOSAL_PARAM) ?? '') !== '';
  /*
   * RULE 0 (2026-09-22) — `?view=capture&proposal=<id>` IS A PROPOSAL LINK, and it
   * opens the focused Proposals view.
   *
   * Proposal review used to live on the capture workspace, so every proposal link
   * ever minted names `view=capture` — including the ones the MCP server mints
   * (`apps/api/isaac_api/mcp/links.py::proposal_link`, pinned against
   * `ROUTES.recordProposal` by `apps/api/tests/test_mcp_links.py`). Capture Home no
   * longer mounts the proposals panel, so honouring the literal `view` would land a
   * scientist on a chooser where the id is silently inert. A `method` means the
   * reader chose a capture TASK, which wins over a stale proposal id on the URL.
   */
  if (requested === 'capture' && hasProposalAddress && !params.has(RECORD_CAPTURE_METHOD_PARAM)) {
    return 'proposals';
  }
  if (isRecordView(requested)) return requested;
  /*
   * AN EMPTY PARAMETER IS ABSENT, AND BOTH HALVES NOW AGREE ON THAT.
   *
   * *** THE TWO CHECKS USED TO DISAGREE. Found by independent review,
   * 2026-09-13. *** `run` was `(get(...) ?? '') !== ''`, which treats `?run=` as
   * absent — correct. `compare` was `getAll(...).length > 0`, and `getAll`
   * returns `['']` for `?compare=`, so an EMPTY compare counted as a run address
   * while an empty run did not. Measured:
   *
   *     ?run=&proposal=X       -> capture     (empty run ignored — right)
   *     ?compare=&proposal=X   -> runs        (empty compare honoured — wrong)
   *     ?compare=              -> runs        (same, with nothing to compare)
   *     ?run=                  -> fields
   *
   * The consequence was small and real: a link carrying a valueless `?compare=`
   * opened Runs with nothing selected, and it out-ranked a `?proposal=` that did
   * name something. Filtering empties makes the branch mean what it says — "this
   * URL names a run" — rather than "this URL mentions the word compare".
   */
  const hasRunAddress =
    (params.get(RECORD_RUN_PARAM) ?? '') !== '' ||
    params.getAll(RECORD_COMPARE_PARAM).some((value) => value !== '');
  if (hasRunAddress) return 'runs';
  /*
   * BRANCH 3, ADDED AT MERGE TIME (2026-09-13) rather than by either lane alone.
   *
   * A proposal is reviewed on the `capture` workspace, so a URL carrying only
   * `?proposal=` would otherwise open Record Fields, where
   * `IngestionProposalsPanel` is not mounted and the parameter is silently inert.
   * `ROUTES.recordProposal` mints `view=capture` so new links are
   * self-describing; this covers every link it did not mint, including one built
   * in another language against the relative path -- which is the case the
   * agent-facing deep link exists for.
   *
   * A RUN ADDRESS STILL WINS, above, and the order is a decision rather than an
   * accident: `?run=`/`?compare=` resolved to `runs` before this parameter
   * existed, and a URL carrying both must keep landing exactly where it landed
   * yesterday. The proposal parameter is not lost in that case -- it survives on
   * the address and is honoured the moment the reader opens `capture`, because
   * the two parameters are independent and `RecordWorkspaceNav` copies the whole
   * query string.
   *
   * WHY IT IS HERE AND NOT IN `RecordWorkbench`, where it was written: the WCAG
   * 2.4.2 `document.title` floor calls this function too. Left inline, a
   * `?proposal=` deep link would have RENDERED `Experiment Data` while the
   * page TITLE said `Record Fields`. Neither side of that merge conflict was
   * correct alone.
   *
   * ~~`return hasProposalAddress ? 'capture' : 'fields'`~~ — 2026-09-22: the
   * panel moved to the focused `proposals` view, so that is where a bare
   * `?proposal=` now resolves. The branch order above is unchanged.
   */
  return hasProposalAddress ? 'proposals' : 'fields';
}

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
  /**
   * HISTORICAL IMPORT — one of the three primary destinations, and a route with
   * NO parameters of its own.
   *
   * A session is addressed in component state rather than in the URL, and that
   * is a deliberate DEPARTURE from the `?tab=`/`?view=`/`?run=` convention above
   * — which is why it needs a sentence rather than a silent omission. Everything
   * that convention exists for is a view a scientist would LINK A COLLEAGUE TO:
   * a record's graph, one run, a comparison, one proposal. An import session is
   * none of those. It is not durable (the server says so in every response's
   * `durability`), it holds no scientific state, and its useful output is the
   * PROPOSAL it mints on a record — which already has its own deep link,
   * `ROUTES.recordProposal`. A `?import=` parameter would therefore be a link to
   * a working area that may not exist by the time it is followed, which is a
   * worse defect than not being linkable.
   */
  imports: '/imports',
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
  /** A deep link to ONE proposal on a record, e.g.
   *  `/record/<id>?view=capture&proposal=<proposalId>`. Same division of labour as
   *  `recordRun` and `recordCompare`: whole-URL links use this, while the panel
   *  itself only ever READS the parameter and never writes one.
   *
   *  IT NAMES THE WORKSPACE, for `recordRun`'s reason and one more. A proposal is
   *  reviewed on the `capture` workspace, so a URL carrying only `?proposal=` would
   *  land the reader on Record Fields where the panel is not mounted at all — the
   *  parameter would then be silently inert, which is the closest thing to a lie a
   *  query parameter can be. `RecordWorkbench` ALSO resolves a bare `?proposal=` to
   *  `capture`, exactly as it already does for `?run=`, so a link minted by
   *  something that does not use this helper — an MCP tool building a relative path
   *  in another language, for instance — still opens the workspace that can honour
   *  it. The redundancy is deliberate: one half makes new links self-describing, the
   *  other serves every link this helper did not mint. */
  /*  2026-09-22: the template is UNCHANGED — it is pinned byte-for-byte against the
   *  MCP server's own mint (`apps/api/tests/test_mcp_links.py`) — and
   *  `resolveRecordView`'s rule 0 opens it on the focused Proposals view, where
   *  the panel now lives. */
  recordProposal: (id: string, proposalId: string) =>
    `/record/${id}?${RECORD_VIEW_PARAM}=capture&${RECORD_PROPOSAL_PARAM}=${encodeURIComponent(proposalId)}`,
  /** A deep link to one focused capture task, e.g.
   *  `/record/<id>?view=capture&method=write`. Whole-URL links use this; the
   *  record screen's own controls copy the current query string instead. */
  recordCapture: (id: string, method: CaptureMethodId) =>
    `/record/${id}?${RECORD_VIEW_PARAM}=capture&${RECORD_CAPTURE_METHOD_PARAM}=${method}`,
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
  imports: '/imports',
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
