/*
 * Portal metrics — the TYPED CONTRACT and its INACTIVE provider boundary.
 *
 * ── What this is, and what it is not ────────────────────────────────────────
 *
 * A future ISAAC deployment may be able to state platform-wide figures — how
 * many records the platform holds, how they divide by domain — from a source
 * outside this application. This module is the shape that answer would take.
 *
 * IT IS NOT CONNECTED, AND IT CANNOT BE. The one implementation shipped here
 * ({@link unconfiguredPortalMetricsSource}) holds no URL, no host, no token
 * field and no credential, and there is no function in this file that opens a
 * connection. Every read in this app goes through `apps/web/src/lib/api.ts` —
 * the only production module that CALLS `fetch` (`lib/apiDocsModel.ts` contains
 * the word inside a code sample it renders for a reader, not as a call) — and
 * this file neither imports it nor reaches it.
 *
 * ── Why it is inactive, stated without naming an internal decision ──────────
 *
 * The rendered copy in {@link PORTAL_METRICS_UNAVAILABLE_COPY} says only that
 * the metrics are not connected for this deployment, because that is the whole
 * of what a reader needs and the whole of what this application can observe.
 * The governance context lives in the project's own documents, not on a product
 * screen.
 *
 * ── The disclosure rules, which are the reason this file exists at all ──────
 *
 * A platform-wide figure is an aggregate over OTHER PEOPLE'S work, so the risk
 * is not that a number is wrong — it is that a number, or a category name
 * beside it, identifies somebody. Eight kinds of output are forbidden outright,
 * enumerated in {@link PORTAL_FORBIDDEN_CATEGORIES} and detected by
 * {@link screenPortalPayload}. A payload that trips any of them is REFUSED
 * whole ({@link acceptPortalPayload}) rather than edited: a redactor that
 * removes an email and serves the rest leaves the burden of completeness on the
 * redactor, while a refusal fails closed.
 *
 * "THE PAYLOAD" MEANS THE FRESHNESS LABELS TOO. {@link PortalMetricsFreshness}
 * carries two provider-supplied DISPLAY STRINGS on every `ready` state, so it is
 * a disclosure channel of exactly the same kind as the figures beside it, and
 * {@link acceptPortalPayload} screens the two together. It did not, until an
 * independent review measured a freshness label carrying an address, an ORCID
 * and an IP reaching `ready` intact while the same two strings handed to
 * {@link screenPortalPayload} returned all three categories — the guard existed
 * and one of the two display channels was simply never passed to it.
 *
 * The subtle one is the eighth. A count of 1 in a category is a per-record fact
 * wearing aggregate clothing, and two coarse breakdowns can be intersected down
 * to an individual — the reasoning
 * `docs/superpowers/plans/2026-07-31-baseline-completion-matrix.md` §4.3 sets
 * out for the database recon. See {@link PORTAL_MIN_COHORT_SIZE} for what this
 * contract does about it, and for the honest note that the number is this
 * contract's own choice.
 */

/* ---- dataset identity ---------------------------------------------------- */

/**
 * The six platform-wide views this contract covers.
 *
 * Every one is a COUNT over records. None is a count over people, sessions,
 * requests or visits — those are not merely unavailable, they are the shape of
 * figure this application has committed not to state about anybody (see the
 * privacy disclosure on the Statistics screen).
 */
export type PortalMetricId =
  | 'platform_record_total'
  | 'records_by_domain'
  | 'records_by_experiment_type'
  | 'records_by_schema_version'
  | 'validation_outcome_totals'
  | 'submission_volume_over_time';

/* ---- payload shapes ------------------------------------------------------ */

/** A single platform-wide total. */
export interface PortalMetricTotal {
  count: number;
  /** What one unit is, in words, for the caption. Never assumed by a consumer. */
  unitLabel: string;
}

/** One named category and its count. `label` is display text, `key` is stable. */
export interface PortalMetricCategoryCount {
  key: string;
  label: string;
  count: number;
}

/**
 * A categorical breakdown.
 *
 * `withheldCategoryCount` is carried BESIDE the categories rather than folded
 * into an "Other" row, because an "Other" row with a count is itself a figure
 * and can be differenced against the total. A consumer states how many
 * categories were withheld and nothing about them.
 */
export interface PortalMetricCategories {
  categories: readonly PortalMetricCategoryCount[];
  unitLabel: string;
  withheldCategoryCount: number;
}

/**
 * One observation in an ordered series.
 *
 * `periodLabel` is a DISPLAY string produced by whoever aggregated, for the same
 * reason `MyStatsSeriesPoint` carries one: a client that receives an instant
 * formats it in the reader's locale, and a client that receives a bucket label
 * does not silently re-bucket it. Whoever aggregates owns the calendar.
 */
export interface PortalMetricSeriesPoint {
  key: string;
  periodLabel: string;
  count: number;
}

export interface PortalMetricSeries {
  points: readonly PortalMetricSeriesPoint[];
  /** What one point spans, in words ("per month"). Required for the caption. */
  periodLabel: string;
  unitLabel: string;
}

/** Every dataset's payload type, keyed by its id. */
export interface PortalMetricPayloads {
  platform_record_total: PortalMetricTotal;
  records_by_domain: PortalMetricCategories;
  records_by_experiment_type: PortalMetricCategories;
  records_by_schema_version: PortalMetricCategories;
  validation_outcome_totals: PortalMetricCategories;
  submission_volume_over_time: PortalMetricSeries;
}

/* ---- freshness ----------------------------------------------------------- */

/**
 * When the figure was true, and of what.
 *
 * BOTH FIELDS ARE DISPLAY STRINGS supplied by the provider, and both are
 * required on a `ready` state. A platform aggregate with no stated observation
 * time is the most quietly misleading figure a dashboard can carry: it reads as
 * "now" and is not. `observedAtLabel` is nullable because a provider that
 * genuinely does not know must be able to say so — a consumer then states that
 * it is unknown, and must never substitute the moment it received the response.
 *
 * `coverageLabel` names the POPULATION ("all published records"), which a bare
 * timestamp does not. A total over a filtered subset presented as a platform
 * total is the other half of the same defect.
 *
 * BOTH ARE SCREENED, for the reason the module head gives: a display string a
 * provider composes is exactly where "read by ops@internal.example.invalid"
 * ends up. See {@link acceptPortalPayload}, and see {@link IPV6_PATTERN} for the
 * one false positive that screening a human-written time label introduces.
 */
export interface PortalMetricsFreshness {
  observedAtLabel: string | null;
  coverageLabel: string;
}

/* ---- states -------------------------------------------------------------- */

/**
 * Why a platform metric cannot be shown.
 *
 * A CLOSED SET OF REASONS, AND DELIBERATELY NOT A MESSAGE. An upstream error
 * string can carry a host name, a URL, a query, a stack frame or a principal,
 * and the shortest path from "show the error" to "leak the deployment topology"
 * is a `message` field on this union. {@link mapPortalFailure} classifies and
 * discards; {@link PORTAL_METRICS_UNAVAILABLE_COPY} supplies the words.
 */
export type PortalMetricsUnavailableReason =
  /** No source is configured. The state of this build. */
  | 'not_configured'
  /** A configured source could not be reached. */
  | 'unreachable'
  /** A configured source did not answer inside {@link PORTAL_METRICS_TIMEOUT_MS}. */
  | 'timed_out'
  /** A configured source answered with a refusal. */
  | 'refused'
  /** A configured source answered in a shape this contract does not recognise. */
  | 'malformed'
  /** An answer arrived and was refused by {@link screenPortalPayload}. */
  | 'withheld';

export const PORTAL_METRICS_UNAVAILABLE_REASONS: readonly PortalMetricsUnavailableReason[] =
  Object.freeze([
    'not_configured',
    'unreachable',
    'timed_out',
    'refused',
    'malformed',
    'withheld',
  ] as const);

/**
 * A dataset's state. THREE members.
 *
 * There is no `access_pending` here, and the difference from `MyStatsState` is
 * the point: a personal figure is withheld because this build cannot tell who
 * is asking, whereas a platform figure is simply not connected. Reusing the
 * personal union would have made the two read alike on screen.
 */
export type PortalMetricState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T; freshness: PortalMetricsFreshness }
  | { status: 'unavailable'; reason: PortalMetricsUnavailableReason };

/* ---- forbidden disclosures ----------------------------------------------- */

/**
 * The eight kinds of output a platform metric must never carry.
 *
 * Each is detected by {@link screenPortalPayload}. The detectors are
 * deliberately BROAD — a false positive costs a refused panel, a false negative
 * costs a disclosure — and each one's known blind spots are stated on it.
 */
export type PortalForbiddenCategory =
  | 'email_address'
  | 'orcid_id'
  | 'ip_address'
  | 'user_identifier'
  | 'per_user_request_count'
  | 'record_identifier'
  | 'record_title'
  | 'small_cohort';

export const PORTAL_FORBIDDEN_CATEGORIES: readonly PortalForbiddenCategory[] = Object.freeze([
  'email_address',
  'orcid_id',
  'ip_address',
  'user_identifier',
  'per_user_request_count',
  'record_identifier',
  'record_title',
  'small_cohort',
] as const);

/**
 * The smallest category count this contract will carry.
 *
 * STATED HERE BECAUSE THE PROJECT STATES NO NUMBER. The baseline matrix §4.3
 * requires that "any *new* aggregate must suppress or bucket cells below a
 * stated threshold" and records that no minimum-cell-size suppression exists
 * anywhere in the codebase — it asks for a floor without fixing one. Five is
 * this contract's choice, not a project-wide constant, and it is a floor rather
 * than a guarantee: §4.3's other two rules (no cross-tabulation that narrows to
 * an individual, no caller-parameterized aggregation) are not enforceable from
 * here at all, because they are properties of what a provider computes.
 *
 * A count of exactly 0 is NOT small-cohort: it identifies nobody, and it is a
 * real measurement a provider is entitled to report.
 */
export const PORTAL_MIN_COHORT_SIZE = 5;

/** An email address anywhere in a string. */
const EMAIL_PATTERN = /[^\s@,;]+@[^\s@,;]+\.[A-Za-z]{2,}/;

/** An ORCID iD: four hyphenated groups, the last digit possibly `X`. */
const ORCID_PATTERN = /\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b/;

/** A dotted quad. Deliberately not range-checked — `999.1.1.1` is still refused. */
const IPV4_PATTERN = /\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/;

/**
 * Two or more colon-separated hex groups: an IPv6 address or a fragment of one.
 *
 * KNOWN FALSE POSITIVE, stated rather than narrowed, and stated at exactly the
 * width it was MEASURED at: a SPACE-DELIMITED wall-clock time is two
 * colon-separated groups of hex-legal digits, so
 * `1 January 2099, 00:00:00 UTC` in a {@link PortalMetricsFreshness} label is
 * reported as an `ip_address` and refuses the panel.
 *
 * The ISO-8601 form of the same instant — `2099-01-01T00:00:00Z` — does **not**
 * trip. THE MECHANISM STATED HERE WAS WRONG and is corrected rather than deleted:
 * it said "because `T` and `Z` are not hex-legal and so destroy the `\b`
 * boundaries". `\b` is a transition between a WORD character and a non-word one;
 * hex-legality is a property of this pattern's character classes, which is a
 * different thing — and on the trailing side the old sentence had the direction
 * backwards. Measured, each boundary fails independently and either alone
 * suffices:
 *
 *   · LEADING — `T` is a WORD character adjacent to `00`, so no `\b` exists
 *     before the time. Hex-legality plays no part here: make the trailing side
 *     clean and `2099-01-01T00:00:00 ` still matches nothing.
 *   · TRAILING — `Z` is likewise a word character, so no `\b` exists after the
 *     final `00`: make the leading side clean and `2099-01-01 00:00:00Z` also
 *     matches nothing. Hex-legality DOES matter here, in the OPPOSITE direction
 *     — a hex-legal trailing character is ABSORBED into the closing
 *     `[0-9A-Fa-f]{1,4}` group and the match SUCCEEDS: ` 00:00:00A` matches
 *     `00:00:00A`, while ` 00:00:00Z` matches nothing.
 *
 * (Written the other way round first, as though any seconds-precision timestamp
 * were refused; the ISO case was then measured and came back clean. Recorded
 * because a guard's blind spots are only useful at their real width.)
 *
 * So nothing is unstateable, and refusing is the documented trade of this whole
 * file — a false positive costs a refused panel, a false negative costs a
 * disclosure. The alternative (exempting the freshness fields from one detector)
 * is the redactor design {@link acceptPortalPayload} rejects. A provider that
 * wants seconds precision writes an ISO instant; `fixtureFreshness` states a time
 * without seconds and also passes. `a space-delimited clock time in a freshness
 * label is refused as an address` pins both halves, so this is a decision on
 * record rather than a surprise.
 */
const IPV6_PATTERN = /\b(?:[0-9A-Fa-f]{1,4}:){2,}[0-9A-Fa-f]{1,4}\b/;

/**
 * A ULID — 26 characters of Crockford base32, which is the id shape this
 * project's official records carry (`records/<ULID>.json`).
 *
 * THIS IS A VALUE-SHAPE DETECTOR AND IT IS THE ONLY ONE FOR AN ID, so it is the
 * only thing that catches a record id under an innocuous key (`key`, `label`) —
 * which {@link RECORD_ID_KEY_PATTERN} cannot see and which is the form the defect
 * would really take. It went unexercised until an independent review deleted the
 * line that uses it and measured the whole suite still passing: the one
 * `record_identifier` fixture named the id in its KEY, so the key pattern caught
 * it first and this pattern was covered by nothing. The
 * `record_identifier_value` fixture in `test/adapterFixtures.ts` exists solely to
 * bite here.
 */
const ULID_PATTERN = /\b[0-9A-HJKMNP-TV-Z]{26}\b/;

/** Object keys that name a person-scoped attribute rather than an aggregate. */
const USER_KEY_PATTERN = /(^|_)(user|username|uid|login|account|actor|owner|principal|subject|uploaded_by|grantee|orcid|email)(_|$)/i;

/** Object keys that count something PER PERSON, however coarsely. */
const PER_USER_KEY_PATTERN = /(per_user|by_user|per_account|by_account|user_count|unique_users|active_users)/i;

/** Object keys carrying a record's identity or its human-authored title. */
const RECORD_ID_KEY_PATTERN = /(^|_)(record_id|experiment_id|record_ids|experiment_ids)(_|$)/i;
const RECORD_TITLE_KEY_PATTERN = /(^|_)(title|record_title|experiment_title|titles)(_|$)/i;

/** Keys whose numeric values are category counts subject to the cohort floor. */
const COUNT_KEY_PATTERN = /^(count|records_affected)$/;

/**
 * Every forbidden disclosure category present in a payload, as a SORTED SET.
 *
 * Walks the whole structure — objects, arrays, strings, numbers — and reports
 * every category it finds rather than the first, so a caller sees the full
 * picture in one pass and a test can assert an exact set.
 *
 * WHAT IT CANNOT SEE, stated because a guard that looks complete is worse than
 * one that admits its edges:
 *
 *   · A bare surname, a lab name, or an institution. There is no pattern for a
 *     person's name and this file does not pretend to have one.
 *   · An identifier this project does not use — a UUID, an internal numeric id,
 *     a DOI. Only the ULID shape is recognised.
 *   · A record title carried under a key this list does not name (`label`,
 *     `description`), because those keys legitimately carry category names.
 *   · Cross-tabulation and differencing (§4.3 rules 2 and 3). A payload can be
 *     entirely clean by this function and still be reconstructible against a
 *     second one.
 */
export function screenPortalPayload(value: unknown): PortalForbiddenCategory[] {
  const found = new Set<PortalForbiddenCategory>();
  walkPortalPayload(value, null, found);
  return PORTAL_FORBIDDEN_CATEGORIES.filter((category) => found.has(category));
}

function walkPortalPayload(
  value: unknown,
  key: string | null,
  found: Set<PortalForbiddenCategory>,
): void {
  if (key !== null) {
    // `per_user` is checked BEFORE the general person-scoped key pattern, and
    // both may fire: `requests_per_user` is a per-person count AND a
    // person-scoped key, and reporting only one of them would understate it.
    if (PER_USER_KEY_PATTERN.test(key)) found.add('per_user_request_count');
    if (USER_KEY_PATTERN.test(key)) found.add('user_identifier');
    if (RECORD_ID_KEY_PATTERN.test(key)) found.add('record_identifier');
    if (RECORD_TITLE_KEY_PATTERN.test(key)) found.add('record_title');
  }

  if (typeof value === 'string') {
    if (EMAIL_PATTERN.test(value)) found.add('email_address');
    if (ORCID_PATTERN.test(value)) found.add('orcid_id');
    if (IPV4_PATTERN.test(value) || IPV6_PATTERN.test(value)) found.add('ip_address');
    if (ULID_PATTERN.test(value)) found.add('record_identifier');
    return;
  }

  if (typeof value === 'number') {
    if (
      key !== null &&
      COUNT_KEY_PATTERN.test(key) &&
      Number.isFinite(value) &&
      value > 0 &&
      value < PORTAL_MIN_COHORT_SIZE
    ) {
      found.add('small_cohort');
    }
    return;
  }

  if (Array.isArray(value)) {
    // The array's own key still applies to each element: `record_ids: [...]`
    // must be caught on the strings inside it as well as on the key.
    for (const item of value) walkPortalPayload(item, key, found);
    return;
  }

  if (value !== null && typeof value === 'object') {
    for (const [childKey, childValue] of Object.entries(value as Record<string, unknown>)) {
      walkPortalPayload(childValue, childKey, found);
    }
  }
}

/**
 * A `ready` state for a screened payload, or `withheld` if anything trips.
 *
 * FAIL CLOSED AND REFUSE WHOLE. Nothing is edited out and served: a redactor
 * that removes an email and keeps the rest puts the burden of completeness on
 * the redactor, and this file has already listed four things its detectors
 * cannot see. A refused panel states that it was withheld and shows no figure.
 *
 * THE DATA AND THE FRESHNESS ARE SCREENED TOGETHER, in one pass over
 * `{ data, freshness }`, because both are rendered and a guard applied to one of
 * two display channels is not a guard. The wrapper's own two keys (`data`,
 * `freshness`) trip no key pattern, so wrapping cannot itself cause a refusal.
 *
 * The refusal is still ALL OR NOTHING across the pair: a clean figure with a
 * leaking freshness label is withheld whole rather than served without its
 * observation time. That is deliberate — {@link PortalMetricsFreshness} is
 * documented as required on `ready` precisely because an undated platform
 * aggregate reads as "now", so serving the figure while dropping the label would
 * trade a disclosure for a misdating.
 */
export function acceptPortalPayload<T>(
  data: T,
  freshness: PortalMetricsFreshness,
): PortalMetricState<T> {
  if (screenPortalPayload({ data, freshness }).length > 0) {
    return { status: 'unavailable', reason: 'withheld' };
  }
  return { status: 'ready', data, freshness };
}

/**
 * Drop every category below {@link PORTAL_MIN_COHORT_SIZE}, counting how many
 * were dropped.
 *
 * A count of 0 is KEPT — it identifies nobody. Existing `withheldCategoryCount`
 * from an upstream suppression is added to, never replaced, so two passes do not
 * lose the first pass's tally.
 */
export function suppressSmallCohorts(
  breakdown: PortalMetricCategories,
  minCount: number = PORTAL_MIN_COHORT_SIZE,
): PortalMetricCategories {
  const kept = breakdown.categories.filter(
    (row) => row.count === 0 || row.count >= minCount,
  );
  return {
    ...breakdown,
    categories: kept,
    withheldCategoryCount:
      breakdown.withheldCategoryCount + (breakdown.categories.length - kept.length),
  };
}

/* ---- failure mapping ----------------------------------------------------- */

/**
 * Classify a thrown value into one of the closed reasons, DISCARDING it.
 *
 * The returned reason is derived from the error's SHAPE, never from its text,
 * and nothing the error carried is returned or retained. That is what stops an
 * upstream message — which can name a host, a URL, a query string or a
 * principal — from reaching a screen.
 *
 * The classification itself is coarse on purpose: `AbortError` and a
 * `DOMException` named `TimeoutError` are the two shapes a browser produces for
 * an abandoned request, a `TypeError` is what `fetch` rejects with when it never
 * got a response, and everything else is `refused`. A wrong bucket costs a less
 * precise sentence; reading the message to do better would defeat the point.
 */
export function mapPortalFailure(error: unknown): PortalMetricsUnavailableReason {
  const name =
    typeof error === 'object' && error !== null && typeof (error as { name?: unknown }).name === 'string'
      ? (error as { name: string }).name
      : '';
  if (name === 'AbortError' || name === 'TimeoutError') return 'timed_out';
  if (name === 'TypeError') return 'unreachable';
  if (name === 'SyntaxError') return 'malformed';
  return 'refused';
}

/* ---- timeout ------------------------------------------------------------- */

/** How long a configured source would be given to answer. */
export const PORTAL_METRICS_TIMEOUT_MS = 5000;

/**
 * The outcome of racing a caller-supplied promise against the timeout.
 *
 * `failed` carries a REASON, not the rejection value, for the same reason
 * {@link PortalMetricState} does.
 */
export type PortalTimeoutOutcome<T> =
  | { kind: 'settled'; value: T }
  | { kind: 'failed'; reason: PortalMetricsUnavailableReason };

/**
 * Race a promise the CALLER already has against the timeout.
 *
 * This is a combinator, not a client: it takes a pending promise and cannot
 * originate one, so adding it does not give this module the ability to send a
 * request. It never rejects — a rejection becomes
 * `{ kind: 'failed', reason: mapPortalFailure(error) }`, so a consumer has no
 * catch block in which to accidentally render an upstream message.
 *
 * A late settle after the timeout is ignored rather than overwriting the
 * timed-out outcome; the timer is cleared on the normal path so a test using
 * fake timers does not leave one armed.
 */
export function withPortalTimeout<T>(
  pending: Promise<T>,
  timeoutMs: number = PORTAL_METRICS_TIMEOUT_MS,
): Promise<PortalTimeoutOutcome<T>> {
  return new Promise<PortalTimeoutOutcome<T>>((resolve) => {
    let done = false;
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      resolve({ kind: 'failed', reason: 'timed_out' });
    }, timeoutMs);
    pending.then(
      (value) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve({ kind: 'settled', value });
      },
      (error: unknown) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve({ kind: 'failed', reason: mapPortalFailure(error) });
      },
    );
  });
}

/* ---- the provider boundary ----------------------------------------------- */

/**
 * The seam a future platform-metrics source implements.
 *
 * One method per dataset rather than one `get(id)`, for the reason
 * `MyStatsSource` gives: a discriminated lookup either loses the per-dataset
 * payload type or needs a cast at every call site, and the value of this file is
 * that `recordsByDomain()` cannot return a series.
 *
 * Every method is SYNCHRONOUS and returns a STATE. A real source fronts this
 * with its own fetching layer and hands the resolved state down, which keeps the
 * network out of the contract and keeps the contract impossible to point at a
 * URL. `configured` is a plain boolean a UI can read without calling anything.
 */
export interface PortalMetricsSource {
  readonly id: string;
  readonly configured: boolean;
  platformRecordTotal(): PortalMetricState<PortalMetricTotal>;
  recordsByDomain(): PortalMetricState<PortalMetricCategories>;
  recordsByExperimentType(): PortalMetricState<PortalMetricCategories>;
  recordsBySchemaVersion(): PortalMetricState<PortalMetricCategories>;
  validationOutcomeTotals(): PortalMetricState<PortalMetricCategories>;
  submissionVolumeOverTime(): PortalMetricState<PortalMetricSeries>;
}

/** `not_configured`, for every dataset. */
function notConfigured<T>(): PortalMetricState<T> {
  return { status: 'unavailable', reason: 'not_configured' };
}

/**
 * THE ONLY IMPLEMENTATION IN THIS BUILD.
 *
 * `configured: false`, and every method returns `not_configured`. It takes no
 * options, holds no state, and names no host — there is nothing to fill in and
 * nothing to switch on.
 */
export const unconfiguredPortalMetricsSource: PortalMetricsSource = Object.freeze({
  id: 'unconfigured',
  configured: false,
  platformRecordTotal: () => notConfigured<PortalMetricTotal>(),
  recordsByDomain: () => notConfigured<PortalMetricCategories>(),
  recordsByExperimentType: () => notConfigured<PortalMetricCategories>(),
  recordsBySchemaVersion: () => notConfigured<PortalMetricCategories>(),
  validationOutcomeTotals: () => notConfigured<PortalMetricCategories>(),
  submissionVolumeOverTime: () => notConfigured<PortalMetricSeries>(),
});

/* ---- what the UI says ---------------------------------------------------- */

/**
 * The six planned views, with the quantity each would count.
 *
 * Listed so a reader can see what the section is FOR rather than an
 * unexplained absence — the same reasoning `MY_STATS_VIEWS` records.
 */
export interface PortalMetricViewMeta {
  id: PortalMetricId;
  /** Title Case heading. */
  title: string;
  /** Sentence-case description, naming the quantity and its unit. */
  description: string;
}

export const PORTAL_METRIC_VIEWS: readonly PortalMetricViewMeta[] = Object.freeze([
  {
    id: 'platform_record_total',
    title: 'Records Across the Platform',
    description: 'how many records the wider platform holds, counted in records.',
  },
  {
    id: 'records_by_domain',
    title: 'Records by Scientific Domain',
    description: 'how those records divide across scientific domains, counted in records.',
  },
  {
    id: 'records_by_experiment_type',
    title: 'Records by Experiment Type',
    description: 'how those records divide across experiment types, counted in records.',
  },
  {
    id: 'records_by_schema_version',
    title: 'Records by Schema Version',
    description:
      'how many of those records were written against each version of the official schema, counted in records.',
  },
  {
    id: 'validation_outcome_totals',
    title: 'Schema Validation Outcomes',
    description:
      'how many of those records meet the official schema and how many do not, counted in records.',
  },
  {
    id: 'submission_volume_over_time',
    title: 'Records Added Over Time',
    description: 'how many records the platform gained in each period, counted in records.',
  },
]);

/**
 * The sentence shown in place of each figure.
 *
 * Every one names WHAT IS MISSING and nothing else. None of them states a
 * number, implies a number is zero, blames the reader, or mentions why a
 * connection has not been made — the subject of every sentence is this
 * deployment or the source, and the reason a deployment is configured the way
 * it is belongs in the project's documents rather than on a product screen.
 */
export const PORTAL_METRICS_UNAVAILABLE_COPY: Readonly<
  Record<PortalMetricsUnavailableReason, string>
> = Object.freeze({
  not_configured:
    'Platform usage metrics are not connected for this deployment, so no platform-wide figure is stated here. Nothing is being hidden and no figure is zero — this application has no source to read one from.',
  unreachable:
    'The platform metrics source could not be reached, so no platform-wide figure is stated here.',
  timed_out:
    'The platform metrics source did not answer in time, so no platform-wide figure is stated here.',
  refused:
    'The platform metrics source declined to answer, so no platform-wide figure is stated here.',
  malformed:
    'The platform metrics source answered in a shape this application does not recognise, so nothing from it is shown.',
  withheld:
    'The platform metrics source returned content this application will not display, so the whole answer was discarded rather than edited.',
});

/** The heading above whichever sentence applies. Neutral: nothing here is broken. */
export const PORTAL_METRICS_UNAVAILABLE_TITLE = 'Not Connected';
