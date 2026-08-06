/*
 * My Stats — the TYPED FUTURE CONTRACT and its adapter boundary.
 *
 * ── Read this before wiring anything to it ──────────────────────────────────
 *
 * THERE IS NO PERSONAL DATA IN THIS BUILD, and this module is the shape a future
 * one would fill, not a source that is waiting to be switched on. Two facts, both
 * checkable in this repository, are the reason:
 *
 *   1. THERE IS NO TRUSTED USER IDENTITY. `docs/identity-trust-contract.md` §6A
 *      records the one observation of the deployment's identity headers: all
 *      seven candidate headers arrive at the pod and **ISAAC consumes none of
 *      them**. Two of them (`X-authentik-entitlements`, `X-Isaac-Edge`) arrived
 *      carrying a value the CLIENT planted, so they are permanently disqualified
 *      from identifying anybody. Nothing observed even proves the caller was
 *      authenticated.
 *   2. THERE IS NO RECORD OWNERSHIP. `attribution.uploaded_by` fails closed by
 *      design — the truth core refuses a draft-authored value for it (commit
 *      `bdff8f5`, "fix(truth): refuse a draft-authored attribution.uploaded_by").
 *      So no record in this workspace can be attributed to a person, and no
 *      query over records can be scoped to "mine".
 *
 * Therefore every dataset below is `access-pending`, and the ONE implementation
 * this module ships ({@link unconfiguredMyStatsSource}) returns exactly that. It
 * performs NO fetch, reads NO header, and cannot be configured into one by
 * accident: there is no URL, no token field, and no code path that would send a
 * request.
 *
 * ── What is deliberately NOT here ───────────────────────────────────────────
 *
 *   · No fallback to workspace-wide totals. `lib/statisticsModel.ts`
 *     `deriveWorkspaceTotals` exists one import away and is the single most
 *     tempting wrong answer: relabelled "my records", a workspace count becomes
 *     a false personal claim without a line of new arithmetic.
 *   · No worked-example records as personal records. The five built-in examples
 *     belong to a demonstration session, not to a reader.
 *   · No zeros. `access-pending` is a THIRD state, distinct from `empty`,
 *     precisely so a UI can never render "0 records" — which asserts that the
 *     reader has no activity, when what is true is that this build cannot
 *     attribute activity to anyone.
 *   · No header-derived identity of any kind, not even as a display name.
 */

import type { CurrentUserState } from './currentUserContract';

/* ---- dataset identity -------------------------------------------------- */

/**
 * The eight personal views this contract covers. Ids are stable strings so a
 * future adapter, its tests, and the UI's section anchors all name the same
 * dataset without a magic string in three places.
 */
export type MyStatsDatasetId =
  | 'workflow_counts'
  | 'readiness_trend'
  | 'validation_issues_over_time'
  | 'evidence_support_distribution'
  | 'exports_over_time'
  | 'common_blockers'
  | 'recent_activity'
  | 'owned_vs_collaborated';

/* ---- the shapes the views would render -------------------------------- */

/** One named category and its count. The unit is named by the dataset, not here. */
export interface MyStatsCategoryCount {
  key: string;
  label: string;
  count: number;
}

/**
 * One observation in an ordered series.
 *
 * `periodLabel` is a DISPLAY string produced by whatever supplies the series;
 * this contract deliberately does not carry a timestamp, because a client that
 * receives an instant will format it in the reader's locale and a client that
 * receives a bucket label will not silently re-bucket it. Whoever aggregates
 * owns the calendar.
 */
export interface MyStatsSeriesPoint {
  key: string;
  periodLabel: string;
  count: number;
}

/** User-scoped counts of the reader's own records by workflow step. */
export interface MyStatsWorkflowCounts {
  byStep: readonly MyStatsCategoryCount[];
  /** The reader's own record total — never a workspace total. */
  recordsCounted: number;
}

/** How many of the reader's records were export-ready, per period. */
export interface MyStatsReadinessTrend {
  points: readonly MyStatsSeriesPoint[];
  /** What one point spans, in words ("per week"). Required for the caption. */
  periodLabel: string;
}

/** Schema-validation issues raised against the reader's records, per period. */
export interface MyStatsValidationIssuesOverTime {
  points: readonly MyStatsSeriesPoint[];
  periodLabel: string;
  /**
   * Whether a point counts ISSUES or RECORDS-WITH-ISSUES. Two different
   * quantities that a single number cannot distinguish, and the unit a chart
   * caption must state — the same conflation `EvidenceTotals` keeps apart with
   * `totalFields` beside `recordsCounted`.
   */
  unit: 'issues' | 'records';
}

/** Fields of the reader's records by evidence-support class. Counts FIELDS. */
export interface MyStatsEvidenceSupportDistribution {
  byClass: readonly MyStatsCategoryCount[];
  totalFields: number;
  recordsCounted: number;
}

/** Official records the reader exported, per period. */
export interface MyStatsExportsOverTime {
  points: readonly MyStatsSeriesPoint[];
  periodLabel: string;
}

/** What most often stops the reader's records from exporting. */
export interface MyStatsCommonBlockers {
  blockers: readonly MyStatsCategoryCount[];
  /** How many of the reader's records contributed. Blockers may overlap, so
   *  this is NOT the sum of `blockers` and must never be presented as one. */
  recordsCounted: number;
}

/** One entry in the reader's own recent activity. */
export interface MyStatsActivityEntry {
  key: string;
  /** What happened, already phrased for display. */
  summary: string;
  /** When, already formatted by whoever supplied it. See MyStatsSeriesPoint. */
  whenLabel: string;
  /** In-app route for the affected record, or `null` if there is none. */
  href: string | null;
}

export interface MyStatsRecentActivity {
  entries: readonly MyStatsActivityEntry[];
}

/**
 * The reader's records split by their relationship to them.
 *
 * `collaborated` is a SEPARATE axis and may overlap `owned` — a record can be
 * both authored and worked on by others — so the two must not be added together
 * and no total is carried here to invite it. Same shape of trap as
 * `ExportGate.staleArtifacts`.
 */
export interface MyStatsOwnedVsCollaborated {
  owned: number;
  collaborated: number;
}

/** Every dataset's payload type, keyed by its id. */
export interface MyStatsPayloads {
  workflow_counts: MyStatsWorkflowCounts;
  readiness_trend: MyStatsReadinessTrend;
  validation_issues_over_time: MyStatsValidationIssuesOverTime;
  evidence_support_distribution: MyStatsEvidenceSupportDistribution;
  exports_over_time: MyStatsExportsOverTime;
  common_blockers: MyStatsCommonBlockers;
  recent_activity: MyStatsRecentActivity;
  owned_vs_collaborated: MyStatsOwnedVsCollaborated;
}

/* ---- the four states a dataset can be in ------------------------------ */

/**
 * Why a personal dataset cannot be shown. Each value names a DIFFERENT missing
 * precondition, so a UI states the accurate one instead of a generic apology.
 *
 *   · `no_signed_in_account` — nothing establishes who the reader is.
 *   · `no_record_ownership`  — records carry no attribution to scope by.
 *   · `not_recorded`         — nothing in this build measures the quantity.
 */
export type MyStatsPendingReason =
  | 'no_signed_in_account'
  | 'no_record_ownership'
  | 'not_recorded';

/**
 * A dataset's state. FOUR members, and `access_pending` is why this union exists
 * rather than a nullable payload:
 *
 *   · `loading` — a request is in flight.
 *   · `ready` — a payload arrived. May legitimately be EMPTY of rows.
 *   · `access_pending` — the precondition for a personal answer is absent. NOT
 *     an error, NOT empty, and never rendered as a zero.
 *   · `unavailable` — a configured source was asked and failed. A real fault.
 *
 * Collapsing `access_pending` into `ready` with zeroed rows is the exact defect
 * this type exists to make unrepresentable.
 */
export type MyStatsState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'access_pending'; reason: MyStatsPendingReason }
  | { status: 'unavailable'; message: string };

/* ---- the adapter boundary --------------------------------------------- */

/**
 * The seam a future personal-statistics source implements.
 *
 * One method per dataset rather than one `get(id)`: a discriminated lookup would
 * either lose the per-dataset payload type or need a cast at every call site,
 * and the whole value of this file is that `readinessTrend()` cannot return a
 * workflow count.
 *
 * Every method is synchronous and returns a STATE, not a promise. That is
 * deliberate for the only implementation that exists: it answers immediately and
 * has nothing to await. A real source will front this with its own fetching
 * layer and hand the resolved state down — which keeps the network out of this
 * contract, and keeps this contract impossible to accidentally point at a URL.
 */
export interface MyStatsSource {
  readonly id: string;
  workflowCounts(): MyStatsState<MyStatsWorkflowCounts>;
  readinessTrend(): MyStatsState<MyStatsReadinessTrend>;
  validationIssuesOverTime(): MyStatsState<MyStatsValidationIssuesOverTime>;
  evidenceSupportDistribution(): MyStatsState<MyStatsEvidenceSupportDistribution>;
  exportsOverTime(): MyStatsState<MyStatsExportsOverTime>;
  commonBlockers(): MyStatsState<MyStatsCommonBlockers>;
  recentActivity(): MyStatsState<MyStatsRecentActivity>;
  ownedVsCollaborated(): MyStatsState<MyStatsOwnedVsCollaborated>;
}

/**
 * Which precondition each dataset is waiting on, in this build.
 *
 * All eight need an identity; six of them additionally need per-record
 * attribution. The distinction is kept because it is the honest one — signing in
 * would not by itself make "my records by workflow step" answerable while
 * `attribution.uploaded_by` still fails closed.
 */
export const MY_STATS_PENDING_REASON: Readonly<Record<MyStatsDatasetId, MyStatsPendingReason>> =
  Object.freeze({
    workflow_counts: 'no_record_ownership',
    readiness_trend: 'no_record_ownership',
    validation_issues_over_time: 'not_recorded',
    evidence_support_distribution: 'no_record_ownership',
    exports_over_time: 'not_recorded',
    common_blockers: 'no_record_ownership',
    recent_activity: 'not_recorded',
    owned_vs_collaborated: 'no_record_ownership',
  });

/**
 * THE ONLY IMPLEMENTATION IN THIS BUILD. Every method returns `access_pending`
 * with the reason for that dataset.
 *
 * It takes no configuration, holds no state, opens no connection and reads no
 * header — so there is no switch to flip and nothing that could begin answering
 * with somebody else's data. `id` is a plain string so a UI or a test can state
 * which source answered without pretending it is a URL.
 */
export const unconfiguredMyStatsSource: MyStatsSource = Object.freeze({
  id: 'unconfigured',
  workflowCounts: () => pending<MyStatsWorkflowCounts>('workflow_counts'),
  readinessTrend: () => pending<MyStatsReadinessTrend>('readiness_trend'),
  validationIssuesOverTime: () =>
    pending<MyStatsValidationIssuesOverTime>('validation_issues_over_time'),
  evidenceSupportDistribution: () =>
    pending<MyStatsEvidenceSupportDistribution>('evidence_support_distribution'),
  exportsOverTime: () => pending<MyStatsExportsOverTime>('exports_over_time'),
  commonBlockers: () => pending<MyStatsCommonBlockers>('common_blockers'),
  recentActivity: () => pending<MyStatsRecentActivity>('recent_activity'),
  ownedVsCollaborated: () => pending<MyStatsOwnedVsCollaborated>('owned_vs_collaborated'),
});

/**
 * The `access_pending` state for one dataset, carrying that dataset's own reason.
 *
 * The type parameter is supplied EXPLICITLY at every call site above rather than
 * inferred. Inference would leave `T` as `unknown`, and an
 * `MyStatsState<unknown>` is not assignable to `MyStatsState<MyStatsWorkflowCounts>`
 * — so the annotation on `unconfiguredMyStatsSource` would be doing no checking
 * at all if it compiled. It is the one place the per-dataset payload types are
 * proved to line up with the method that returns them.
 */
function pending<T>(id: MyStatsDatasetId): MyStatsState<T> {
  return { status: 'access_pending', reason: MY_STATS_PENDING_REASON[id] };
}

/**
 * Which personal-statistics source answers for a given reader.
 *
 * IT RETURNS THE SAME SOURCE FOR EVERY STATE, INCLUDING `present`, AND THAT IS
 * THE ASSERTION. Knowing who the reader is would not, by itself, make a single
 * dataset above answerable: six of the eight additionally need per-record
 * attribution, and `attribution.uploaded_by` fails closed by design (commit
 * `bdff8f5`). So identity does not unlock personal data here, and this function
 * is where that is written down — a future slice that wires a real current-user
 * source has to change THIS line to start showing anything, rather than getting
 * personal figures as a side effect of signing somebody in.
 *
 * Written as an exhaustive switch rather than `return unconfiguredMyStatsSource`
 * so that adding a state to {@link CurrentUserState} is a compile error here
 * instead of silently inheriting the constant.
 */
export function personalStatisticsSourceFor(state: CurrentUserState): MyStatsSource {
  switch (state.status) {
    case 'disabled':
    case 'absent':
    case 'unavailable':
    case 'untrusted':
    case 'present':
      return unconfiguredMyStatsSource;
  }
}

/* ---- what the UI says about each dataset ----------------------------- */

/**
 * The presentation metadata for one planned view: what it would show, the unit
 * it would count, and the chart form it would take.
 *
 * `form` is declared HERE rather than chosen at render time so the form decision
 * is reviewable next to the data's shape — a count by category is a bar, an
 * ordered series is a line, a composition of one whole is a stack. It is also
 * what a reader is told, so nobody has to guess what "coming later" looks like.
 */
export interface MyStatsViewMeta {
  id: MyStatsDatasetId;
  /** Title Case heading. */
  title: string;
  /** Sentence-case description of the figure, in the unit it would count. */
  description: string;
  form: 'bar chart' | 'line chart' | 'stacked bar' | 'comparison rows' | 'list';
}

/**
 * The eight planned views, in the order the My Stats tab lists them: the
 * snapshot views first, then the over-time views, then the qualitative ones.
 *
 * Every description states a QUANTITY AND ITS UNIT, because "your records" and
 * "your fields" are different numbers and the unit is the thing a personal
 * dashboard is most likely to blur.
 */
export const MY_STATS_VIEWS: readonly MyStatsViewMeta[] = Object.freeze([
  {
    id: 'workflow_counts',
    title: 'Records You Author, by Workflow Step',
    description:
      'how many records you author sit at each step of the five-step workflow, counted once each at their first unsatisfied step.',
    form: 'bar chart',
  },
  {
    id: 'evidence_support_distribution',
    title: 'Evidence Support in Records You Author',
    description:
      'what share of the fields in records you author is supported by evidence, counted in fields rather than in records.',
    form: 'stacked bar',
  },
  {
    id: 'owned_vs_collaborated',
    title: 'Records You Authored and Records You Contributed To',
    description:
      'how many records name you as their author, and how many you contributed to without authoring. A record can be both, so the two are never added together.',
    form: 'comparison rows',
  },
  {
    id: 'common_blockers',
    title: 'What Most Often Blocks Records You Author',
    description:
      'which unmet requirements appear most often across the records you author. One record can carry several, so these do not sum to a record count.',
    form: 'bar chart',
  },
  {
    id: 'readiness_trend',
    title: 'Export Readiness Over Time',
    description: 'how many records you author were ready to export in each period.',
    form: 'line chart',
  },
  {
    id: 'validation_issues_over_time',
    title: 'Validation Issues Over Time',
    description:
      'how many schema-validation issues were raised against the records you author, in each period.',
    form: 'line chart',
  },
  {
    id: 'exports_over_time',
    title: 'Exports You Made Over Time',
    description: 'how many official records you exported in each period.',
    form: 'line chart',
  },
  {
    id: 'recent_activity',
    title: 'Your Recent Activity',
    description:
      'the most recent changes you made, each linking to the record it affected.',
    form: 'list',
  },
]);

/**
 * The sentence a view shows in place of a chart, matched to its own missing
 * precondition.
 *
 * Each one states WHAT IS MISSING and nothing else. In particular none of them
 * says the reader has no records, no activity, or nothing to show — this build
 * cannot know any of that, and saying it would be the fabrication the whole
 * module is arranged to prevent. None of them blames the reader either: the
 * subject of every sentence is the application.
 */
export const MY_STATS_PENDING_COPY: Readonly<Record<MyStatsPendingReason, string>> =
  Object.freeze({
    no_signed_in_account:
      'This view needs a signed-in account, and this preview has none, so there is nobody to describe.',
    no_record_ownership:
      'Records in this preview are not associated with an account, so this view cannot tell which of them are yours. It is not showing zero — it has no way to select your records at all.',
    not_recorded:
      'This preview keeps no history of who changed what, so the figures this view is built from are not recorded anywhere. Nothing is being withheld; there is nothing measured to read.',
  });

/**
 * The SHORT form of each reason, for a per-view marker.
 *
 * Short because it is repeated once per planned view, and the full sentence is
 * stated once at the top of the tab; eight copies of a two-clause explanation is
 * how a page stops being read. Each label still names the missing precondition
 * rather than saying "unavailable", which would be the uninformative version.
 */
export const MY_STATS_PENDING_LABEL: Readonly<Record<MyStatsPendingReason, string>> =
  Object.freeze({
    no_signed_in_account: 'Needs a signed-in account',
    no_record_ownership: 'Needs records linked to an account',
    not_recorded: 'Needs change history this preview does not keep',
  });
