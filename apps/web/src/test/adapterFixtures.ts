/*
 * TEST-ONLY populated adapters for the two inactive boundaries.
 *
 * ── Why these exist, and why they live here ─────────────────────────────────
 *
 * `lib/portalMetricsContract.ts` and `lib/currentUserContract.ts` each ship ONE
 * implementation, and it answers "not connected" / "disabled". That is the
 * correct production behaviour and it is also untestable on its own: a contract
 * whose only implementation returns a refusal proves nothing about whether the
 * shapes it declares can actually carry an answer, whether the disclosure
 * screening bites, or whether a UI would render a payload sensibly.
 *
 * So the populated sources live HERE, in `src/test/`, beside `apiFixtures.ts`.
 * That directory is test scaffolding by convention and by enforcement:
 *
 *   · `__tests__/product-facing-language.test.tsx` excludes `test/` from its
 *     scan of user-visible copy, and asserts that it does.
 *   · `__tests__/adapter-fixture-isolation.test.ts` reads every production
 *     source under `apps/web/src` and asserts that NONE of them imports this
 *     module — so nothing in this file can reach a rendered screen.
 *
 * ── The values ──────────────────────────────────────────────────────────────
 *
 * Every figure below is invented for a test and is unmistakably synthetic:
 * round numbers, `example.invalid` hosts, and labels that name themselves as
 * fixtures. Nothing here is derived from a real deployment, a real person, or a
 * real record, and the deliberately "leaky" payloads at the bottom carry
 * addresses and identifiers that are structurally valid and semantically
 * nonsense — they exist to be REFUSED, and a test asserts that they are.
 */

import {
  acceptPortalPayload,
  type PortalMetricCategories,
  type PortalMetricSeries,
  type PortalMetricState,
  type PortalMetricTotal,
  type PortalMetricsFreshness,
  type PortalMetricsSource,
  type PortalMetricsUnavailableReason,
} from '../lib/portalMetricsContract';
import {
  type CurrentUser,
  type CurrentUserSource,
  type CurrentUserState,
} from '../lib/currentUserContract';

/* ---- portal metrics: a populated source -------------------------------- */

export const fixtureFreshness: PortalMetricsFreshness = Object.freeze({
  observedAtLabel: '1 January 2099, 00:00 UTC',
  coverageLabel: 'all records in the fixture platform',
});

export const fixturePlatformTotal: PortalMetricTotal = Object.freeze({
  count: 1200,
  unitLabel: 'records',
});

/**
 * Every category is at or above `PORTAL_MIN_COHORT_SIZE`, so this payload passes
 * screening. `fixtureSmallCohortBreakdown` below is the one that does not.
 */
export const fixtureDomainBreakdown: PortalMetricCategories = Object.freeze({
  categories: Object.freeze([
    { key: 'characterization', label: 'Characterization', count: 700 },
    { key: 'performance', label: 'Performance', count: 400 },
    { key: 'synthesis', label: 'Synthesis', count: 100 },
    { key: 'unassigned', label: 'Unassigned', count: 0 },
  ]),
  unitLabel: 'records',
  withheldCategoryCount: 0,
});

export const fixtureSeries: PortalMetricSeries = Object.freeze({
  points: Object.freeze([
    { key: '2099-01', periodLabel: 'January 2099', count: 300 },
    { key: '2099-02', periodLabel: 'February 2099', count: 450 },
    { key: '2099-03', periodLabel: 'March 2099', count: 450 },
  ]),
  periodLabel: 'per month',
  unitLabel: 'records',
});

/**
 * A source that answers every dataset, routed through `acceptPortalPayload` so
 * the fixture exercises the same screening a real one would. It still holds no
 * URL and issues no request — it returns constants.
 */
export const populatedPortalMetricsSource: PortalMetricsSource = Object.freeze({
  id: 'fixture-populated',
  configured: true,
  platformRecordTotal: () => acceptPortalPayload(fixturePlatformTotal, fixtureFreshness),
  recordsByDomain: () => acceptPortalPayload(fixtureDomainBreakdown, fixtureFreshness),
  recordsByExperimentType: () => acceptPortalPayload(fixtureDomainBreakdown, fixtureFreshness),
  recordsBySchemaVersion: () => acceptPortalPayload(fixtureDomainBreakdown, fixtureFreshness),
  validationOutcomeTotals: () => acceptPortalPayload(fixtureDomainBreakdown, fixtureFreshness),
  submissionVolumeOverTime: () => acceptPortalPayload(fixtureSeries, fixtureFreshness),
});

/** The one `loading` member of the state union, shared by the source below. */
const LOADING = { status: 'loading' } as const;

/** A source stuck in `loading`, for a UI that must not treat it as an answer. */
export const loadingPortalMetricsSource: PortalMetricsSource = Object.freeze({
  id: 'fixture-loading',
  configured: true,
  platformRecordTotal: () => LOADING,
  recordsByDomain: () => LOADING,
  recordsByExperimentType: () => LOADING,
  recordsBySchemaVersion: () => LOADING,
  validationOutcomeTotals: () => LOADING,
  submissionVolumeOverTime: () => LOADING,
});

/** A source that fails every dataset with one chosen reason. */
export function failingPortalMetricsSource(
  reason: PortalMetricsUnavailableReason,
): PortalMetricsSource {
  const fail = <T,>(): PortalMetricState<T> => ({ status: 'unavailable', reason });
  return Object.freeze({
    id: `fixture-failing-${reason}`,
    configured: true,
    platformRecordTotal: () => fail<PortalMetricTotal>(),
    recordsByDomain: () => fail<PortalMetricCategories>(),
    recordsByExperimentType: () => fail<PortalMetricCategories>(),
    recordsBySchemaVersion: () => fail<PortalMetricCategories>(),
    validationOutcomeTotals: () => fail<PortalMetricCategories>(),
    submissionVolumeOverTime: () => fail<PortalMetricSeries>(),
  });
}

/* ---- portal metrics: payloads that MUST be refused --------------------- */

/**
 * One payload per forbidden disclosure category, so a test can assert the
 * screener reports the RIGHT category and not merely "something".
 *
 * `per_user_request_count` is the one entry that deliberately trips TWO
 * categories: `requests_per_user` is both a per-person count and a
 * person-scoped key, and the screener reports both by design. The test asserts
 * exact sets, so that pair is stated rather than glossed.
 *
 * The strings are structurally valid and semantically nonsense — an
 * `example.invalid` address, a documentation-range IP, an ORCID whose digits are
 * a counting pattern, a ULID of repeated characters. None of them belongs to
 * anybody.
 */
export const LEAKY_PORTAL_PAYLOADS = Object.freeze({
  email_address: { label: 'Contact fixture-owner@example.invalid', count: 40 },
  orcid_id: { label: 'Author 0000-0001-2345-6789', count: 40 },
  ip_address: { label: 'Origin 192.0.2.7', count: 40 },
  user_identifier: { username: 'fixture-person', count: 40 },
  per_user_request_count: { requests_per_user: 12, count: 40 },
  record_identifier: { record_id: 'fixture', count: 40 },
  record_title: { title: 'A fixture record title', count: 40 },
  small_cohort: { label: 'A tiny category', count: 1 },
});

/** A breakdown with one category below the cohort floor, for suppression tests. */
export const fixtureSmallCohortBreakdown: PortalMetricCategories = Object.freeze({
  categories: Object.freeze([
    { key: 'big', label: 'Big', count: 900 },
    { key: 'tiny', label: 'Tiny', count: 2 },
    { key: 'none', label: 'None', count: 0 },
  ]),
  unitLabel: 'records',
  withheldCategoryCount: 0,
});

/** A source whose one answer trips the screener. It must never render a figure. */
export const leakyPortalMetricsSource: PortalMetricsSource = Object.freeze({
  ...populatedPortalMetricsSource,
  id: 'fixture-leaky',
  recordsByDomain: () =>
    acceptPortalPayload(
      {
        ...fixtureDomainBreakdown,
        categories: [
          ...fixtureDomainBreakdown.categories,
          { key: 'leak', label: 'Contact fixture-owner@example.invalid', count: 40 },
        ],
      },
      fixtureFreshness,
    ),
});

/* ---- current user: populated states ------------------------------------ */

/**
 * A `CurrentUser` this build can legally construct — and note what the type
 * forced: `trustBasis` has one member, `'test_fixture'`, so this object says in
 * the type system that it is a fixture. Production code cannot mint one that
 * claims anything stronger.
 *
 * `observedFrom` is `x-authentik-username`, one of the five headers §6A found
 * the edge supplying. The two disqualified names are not assignable here at all.
 */
export const fixtureCurrentUser: CurrentUser = Object.freeze({
  subject: Object.freeze({
    kind: 'authentik_username',
    value: 'fixture-principal',
    observedFrom: 'x-authentik-username',
  }),
  displayName: 'Fixture Principal',
  trustBasis: 'test_fixture',
});

/** A source that reports one chosen state. Reads nothing, exactly like the real one. */
export function currentUserSourceReporting(state: CurrentUserState): CurrentUserSource {
  return Object.freeze({ id: `fixture-${state.status}`, get: () => state });
}

/**
 * Every state, so a test can sweep the union instead of picking a favourite.
 * `the sweep covers every state in the union` compares this to the states the
 * production switch handles.
 */
export const ALL_CURRENT_USER_STATES: readonly CurrentUserState[] = Object.freeze([
  { status: 'disabled' },
  { status: 'absent' },
  { status: 'unavailable', reason: 'no_identity_contract' },
  { status: 'unavailable', reason: 'source_error' },
  { status: 'unavailable', reason: 'contract_mismatch' },
  { status: 'untrusted', reason: 'disqualified_header_only' },
  { status: 'untrusted', reason: 'unverified_edge_traversal' },
  { status: 'present', user: fixtureCurrentUser },
]);
