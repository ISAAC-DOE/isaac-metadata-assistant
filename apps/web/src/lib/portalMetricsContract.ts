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
 * into an "Other" row, so a consumer states how many categories were withheld
 * and nothing about them.
 *
 * WHAT THIS DOES NOT DO, corrected after review said the opposite. An earlier
 * version of this comment claimed the design avoided differencing because "an
 * 'Other' row with a count is itself a figure and can be differenced against
 * the total". Omitting the row does not remove the total: `platform_record_total`
 * is a declared dataset over the SAME population, so when exactly one category
 * is withheld its count is recoverable as `total - sum(published)`. Measured:
 * categories 900 / 95 / 1 against a total of 996 recovers the 1 exactly. And
 * `withheldCategoryCount` itself tells an attacker how many unknowns to solve
 * for.
 *
 * A floor is NOT safe against a co-published total over the same population.
 * {@link suppressSmallCohorts} therefore does not stop at hiding one category —
 * see the absorption rule there.
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
/**
 * THE AUTHORIZATION GATE ON EVER CONNECTING THIS.
 *
 * Stated here because a seam with no gate on it is an invitation, and the
 * sibling module `currentUserContract.ts` cites its own gate while this one —
 * the module actually named after the portal — cited none.
 *
 * `docs/portal-identity-and-metrics-audit.md` §6 records that there is NO
 * authorization to ingest portal metrics, and §7 that the metrics this
 * application would want cannot be built honestly from what the portal exposes.
 * Dean's direction is that portal usage metrics are not to be ported or reused:
 * no request count, no username, no IP address, no personal portal activity.
 * Nothing in this module may be wired to a portal endpoint on the strength of
 * the types existing.
 *
 * `PORTAL_MIN_COHORT_SIZE = 5` DOES NOT DISCHARGE Q23. Q23 asks Dean which
 * aggregates an ordinary signed-in user may see and what minimum aggregation
 * threshold he wants enforced, and records that neither application has one
 * today. Five is this module's defensive default so that the screening code has
 * a number to test against — it is not an answer to a question only he can
 * answer, and it must not be cited as one.
 */
export type PortalForbiddenCategory =
  | 'email_address'
  | 'orcid_id'
  | 'ip_address'
  | 'user_identifier'
  | 'per_user_request_count'
  | 'record_identifier'
  | 'record_title'
  | 'small_cohort'
  // A value under a count-shaped key that is not a number at all. Not a
  // disclosure in itself — it is a shape this module does not understand, and
  // an unparseable count must fail closed rather than pass through unscreened.
  | 'malformed_count';

export const PORTAL_FORBIDDEN_CATEGORIES: readonly PortalForbiddenCategory[] = Object.freeze([
  'email_address',
  'orcid_id',
  'ip_address',
  'user_identifier',
  'per_user_request_count',
  'record_identifier',
  'record_title',
  'small_cohort',
  'malformed_count',
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
 * Two or more colon-separated hex groups: a full (UNCOMPRESSED) IPv6 address or
 * a fragment of one.
 *
 * THIS PATTERN CATCHES ONLY THE UNCOMPRESSED FORM, and saying the contract
 * refused "IPv6 addresses" was a FALSE GUARANTEE until it was measured. The
 * canonical COMPRESSED forms — `2001:db8::1`, `fe80::1`, `::1`, and the all-zero
 * `::` — carry a `::` run whose empty group breaks the `(?:group:){2,}group`
 * shape this pattern requires, so it matches NONE of them (measured false for all
 * four). The module head and the "WHAT IT CANNOT SEE" list below both implied
 * IPv6 was refused; they were half-right. {@link IPV6_COMPRESSED_PATTERN} closes
 * the gap, and the two are OR'd together at the detection site so `ip_address`
 * fires for either form.
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
 *     before the time: make the trailing side clean and `2099-01-01T00:00:00 `
 *     still matches nothing.
 *   · TRAILING — `Z` is likewise a word character, so no `\b` exists after the
 *     final `00`: make the leading side clean and `2099-01-01 00:00:00Z` also
 *     matches nothing. A hex-legal trailing character is instead ABSORBED into
 *     the closing `[0-9A-Fa-f]{1,4}` group and the match SUCCEEDS: ` 00:00:00A`
 *     matches `00:00:00A`, while ` 00:00:00Z` matches nothing.
 *
 * THE ABSORPTION IS SYMMETRIC, and the second version of this comment claimed it
 * was not — it said "hex-legality plays no part" on the leading side and worked
 * "the OPPOSITE direction" only on the trailing one. Measured, both sides absorb:
 * `a00:00:00 ` matches `a00:00:00`, and `x00:00:00 ` matches nothing. So the
 * leading side has exactly the trailing side's behaviour, and the asserted
 * asymmetry was not a property of the sides at all.
 *
 * What actually protects the ISO form on the leading side is the `{1,4}` LENGTH
 * BUDGET, which no earlier version of this comment mentioned: `01T00` is five
 * characters and cannot fit the opening group. Measured at the boundary —
 * `2099-01-0a00:00:00 ` MATCHES (`0a00` fits in four), `2099-01-01a00:00:00 `
 * does not (`01a00` does not), `f00:00:00 ` matches, `ffff0:00:00 ` does not.
 * `T` being non-hex is a second, redundant reason for that one string; the
 * budget is the reason that generalises. Widen the group and the leading side
 * opens up — which is precisely what the earlier wording would have told a
 * reviewer could not happen.
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
 * The COMPRESSED (`::`) IPv6 form, which {@link IPV6_PATTERN} cannot see.
 *
 * A single `::` run stands in for one or more all-zero groups, so a compressed
 * address may present as few as the two characters `::` — far short of the
 * `(?:group:){2,}group` the uncompressed pattern needs. This matches an optional
 * leading hex group, a literal `::`, and an optional trailing colon-separated
 * run, which catches `2001:db8::1`, `fe80::1`, `::1` and the bare `::` itself
 * (measured true for all four).
 *
 * NEW KNOWN FALSE POSITIVE, and the trade it makes in this file's own "refuse
 * rather than narrow" direction. There is DELIBERATELY no `\b` anchor — a `::`
 * embedded mid-string must still be caught — so ANY string containing `::`
 * between word-ish labels trips it. A C++/Rust-style qualified name in a display
 * label (`Foo::Bar`, `std::vector`, `Module::method`) is reported as an
 * `ip_address` and REFUSES THE PANEL, exactly as the space-delimited clock time
 * does for {@link IPV6_PATTERN}. That is the documented cost of a broad detector:
 * a false positive costs a refused panel, a false negative costs a disclosure,
 * and this file chooses the refusal every time.
 */
const IPV6_COMPRESSED_PATTERN = /(?:[0-9A-Fa-f]{1,4})?::(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?/;

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
 *   · AN ADDRESS NOT WRITTEN AS AN ADDRESS. {@link IPV4_PATTERN} is a dotted
 *     quad, so `192.0.2.7` in its integer or hex form (`3221225991`,
 *     `0xC0000207`) matches nothing here — and a NUMBER never reaches these
 *     detectors at all, because {@link walkPortalPayload} returns on
 *     `typeof value === 'number'`. Under a count-shaped key such a value is still
 *     screened as a COUNT; nothing screens it as an address.
 *   · Cross-tabulation and differencing (§4.3 rules 2 and 3). A payload can be
 *     entirely clean by this function and still be reconstructible against a
 *     second one.
 *
 * An IPv6 address is NO LONGER a blind spot in either form: the uncompressed form
 * ({@link IPV6_PATTERN}) and the compressed `::` form
 * ({@link IPV6_COMPRESSED_PATTERN}) are both caught, and `ip_address` fires if
 * EITHER matches. The residual cost is in the other direction — the compressed
 * detector has no boundary anchor, so a non-address `::` label (`Foo::Bar`,
 * `std::vector`) is a FALSE POSITIVE that refuses the panel rather than a miss
 * that leaks, which is the trade this file makes everywhere.
 */
export function screenPortalPayload(value: unknown): PortalForbiddenCategory[] {
  const found = new Set<PortalForbiddenCategory>();
  walkPortalPayload(value, null, found);
  return PORTAL_FORBIDDEN_CATEGORIES.filter((category) => found.has(category));
}

/**
 * The five VALUE-SHAPE detectors, run over any string — whether it arrived as a
 * value or as an object KEY.
 *
 * Keys were previously tested only against the four key-NAME patterns, so an
 * identifier in key position slipped through entirely. Measured before the fix:
 * `screenPortalPayload({'ops@example.invalid': 40})` returned `[]`. That is not
 * an exotic shape — a breakdown keyed by an identifier is the natural JSON
 * encoding of a categorical aggregate, which makes key position the LIKELIEST
 * place for a leak rather than the least likely.
 */
function screenStringShape(text: string, found: Set<PortalForbiddenCategory>): void {
  if (EMAIL_PATTERN.test(text)) found.add('email_address');
  if (ORCID_PATTERN.test(text)) found.add('orcid_id');
  if (
    IPV4_PATTERN.test(text) ||
    IPV6_PATTERN.test(text) ||
    IPV6_COMPRESSED_PATTERN.test(text)
  ) {
    found.add('ip_address');
  }
  if (ULID_PATTERN.test(text)) found.add('record_identifier');
}

/**
 * Screen a count that may not have arrived as a number.
 *
 * `count: number` is a compile-time annotation, not a runtime fact, and this
 * module's whole premise is that the provider is untrusted. JSON APIs routinely
 * stringify counts. Measured before the fix: `screenPortalPayload({count: '3'})`
 * returned `[]` — a fail-OPEN path in the function whose contract is fail-closed.
 * A non-numeric value under a count key is reported as `malformed` rather than
 * ignored, because a count that is not a number is a shape this module does not
 * understand and must not pass through.
 */
function screenCount(key: string, value: unknown, found: Set<PortalForbiddenCategory>): void {
  if (!COUNT_KEY_PATTERN.test(key)) return;
  const numeric =
    typeof value === 'number'
      ? value
      : typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))
        ? Number(value)
        : null;
  if (numeric === null) {
    found.add('malformed_count');
    return;
  }
  if (Number.isFinite(numeric) && numeric > 0 && numeric < PORTAL_MIN_COHORT_SIZE) {
    found.add('small_cohort');
  }
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
    // The key is also a string, so it gets the value-shape detectors too.
    screenStringShape(key, found);
    if (typeof value !== 'object' || value === null) screenCount(key, value, found);
  }

  if (typeof value === 'string') {
    screenStringShape(value, found);
    return;
  }

  if (typeof value === 'number') {
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
  const kept = [...breakdown.categories].filter(
    (row) => row.count === 0 || row.count >= minCount,
  );
  let withheldHere = breakdown.categories.length - kept.length;

  // THE ABSORPTION RULE. One withheld category is recoverable: subtract the
  // published categories from `platform_record_total` and the withheld count
  // falls out, and the key universe is often enumerable so elimination names it
  // too. While exactly one category would be withheld and a published one
  // remains, absorb the smallest (ties broken by label, ascending, so the result
  // does not depend on provider ordering) until at least two are withheld.
  //
  // A zero-count category is NOT a safe thing to absorb-around: it is kept above
  // because it identifies nobody, but it also cannot mask anything, so it is
  // excluded from the absorption candidates.
  while (withheldHere === 1 && kept.some((row) => row.count > 0)) {
    let victimIndex = -1;
    for (let i = 0; i < kept.length; i += 1) {
      if (kept[i].count === 0) continue;
      if (victimIndex === -1) {
        victimIndex = i;
        continue;
      }
      const best = kept[victimIndex];
      if (
        kept[i].count < best.count ||
        (kept[i].count === best.count && kept[i].label < best.label)
      ) {
        victimIndex = i;
      }
    }
    if (victimIndex === -1) break;
    kept.splice(victimIndex, 1);
    withheldHere += 1;
  }

  return {
    ...breakdown,
    categories: kept,
    withheldCategoryCount: breakdown.withheldCategoryCount + withheldHere,
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
    'Platform-wide record figures are not connected for this deployment, so no platform-wide figure is stated here. Nothing is being hidden and no figure is zero — this application has no source to read one from.',
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
