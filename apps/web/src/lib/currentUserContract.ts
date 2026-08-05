/*
 * Current user — the TYPED DOMAIN MODEL and its INACTIVE provider boundary.
 *
 * ── Read this before wiring anything to it ──────────────────────────────────
 *
 * THIS BUILD HAS NO CURRENT USER, and this module is the shape a future one
 * would fill. It is not a source waiting to be switched on, and it is
 * deliberately not an identity SEAM.
 *
 * `docs/identity-trust-contract.md` §8 records the standing decision — "do not
 * build a live identity seam. Wire nothing until Q1–Q4 and Q6 are answered" —
 * and gives the reason that governs this file: a no-op abstraction invites a
 * non-no-op consumer, i.e. a `get_principal()`-shaped affordance is exactly what
 * lets a later slice write `uploaded_by=principal.subject` without reopening the
 * trust question. So everything below is arranged so that consumer cannot be
 * written by accident:
 *
 *   · NOTHING HERE READS A HEADER. There is no request object, no `Headers`, no
 *     `document.cookie`, no fetch, and no parser. The header NAMES appear only
 *     as string literals in a frozen observation table, and no function in this
 *     file takes a header collection as an argument.
 *   · THE ONLY IMPLEMENTATION RETURNS `disabled`. {@link disabledCurrentUserSource}
 *     takes no configuration and holds no state.
 *   · A `CurrentUser` CANNOT BE MINTED WITHOUT LABELLING ITSELF. Its required
 *     `trustBasis` field has exactly one member today — `'test_fixture'` — so
 *     production code that constructs one has to say, in the type system, that
 *     what it built is a fixture. See {@link CurrentUserTrustBasis}.
 *   · TWO HEADERS ARE UNTYPEABLE AS A SUBJECT SOURCE.
 *     {@link UsableIdentityClaimHeader} excludes them at compile time; see the
 *     disqualification note below.
 *
 * ── The disqualification, and exactly what §6A does and does not establish ───
 *
 * `docs/identity-trust-contract.md` §6A is the durable record of the one
 * observation of this deployment's identity headers (hosted commit `d521dd7`,
 * reported 2026-08-02; the probe that made it has since been removed). Three
 * findings from it are encoded here:
 *
 *   1. All seven candidate headers ARRIVE at the pod, and **ISAAC consumes none
 *      of them** — the backend reads only `authorization`, `If-None-Match`,
 *      `If-Match` and `X-Filename` (§1.2).
 *   2. `X-authentik-entitlements` and `X-Isaac-Edge` came back carrying the
 *      CLIENT's own planted canary, so §6A.2 disqualifies them **permanently**
 *      from authentication, authorization, role assignment, proof that Authentik
 *      was traversed, and proof that the caller is an institutional user —
 *      unless the infrastructure changes and is independently re-verified.
 *      `X-Isaac-Edge` cannot witness edge traversal, which is the one job its
 *      name implies.
 *   3. For `username`, `uid`, `email`, `name` and `groups` the edge supplied the
 *      value and did **not** append the client's canary. **IT DOES NOT FOLLOW
 *      THAT THE CLIENT'S COPY WAS REMOVED** — §6A.1 names two scenarios that
 *      produce the same signature, one of which means the client *did* influence
 *      the header. {@link HeaderObservation.clientCanarySurvived} is therefore
 *      documented as "not found in either compared form", never as "stripped".
 *
 * Nothing observed proves the caller was authenticated, and Q4 (can an
 * in-cluster caller reach the Service bypassing Authentik?) is untouched by it.
 *
 * ── What this module must never grow into ───────────────────────────────────
 *
 *   · No stamping of `attribution.uploaded_by`. The truth core refuses a
 *     draft-authored value for that field by design (commit `bdff8f5`,
 *     "fix(truth): refuse a draft-authored attribution.uploaded_by"). Nothing
 *     here supplies one, and nothing here should be used to.
 *   · No display of a name, email, uid or group, not even as a greeting.
 *   · No role, permission, or entitlement decision.
 */

/* ---- the seven candidate headers, and what §6A saw ---------------------- */

/**
 * The seven header names §6A's observation covered, lower-cased.
 *
 * Lower-case because HTTP header names are case-insensitive and every
 * comparison in this file is exact-string; the mixed-case spellings in the
 * document (`X-authentik-username`) are the same names.
 *
 * THIS TUPLE IS NOT AN ALLOWLIST AND NOTHING READS HEADERS BY IT. It exists so
 * the observation can be written down in code beside the type that depends on
 * it, and so the disqualified pair can be DERIVED from the observation rather
 * than hand-listed twice.
 *
 * It is also NOT the complete set of headers the edge injects: §7 Q1 is only
 * PARTIALLY answered, because the probe tested this fixed seven-name allowlist.
 * A header arriving under a name not on this list remains entirely unknown.
 */
export const IDENTITY_CANDIDATE_HEADERS = Object.freeze([
  'x-authentik-username',
  'x-authentik-uid',
  'x-authentik-email',
  'x-authentik-name',
  'x-authentik-groups',
  'x-authentik-entitlements',
  'x-isaac-edge',
] as const);

export type IdentityCandidateHeader = (typeof IDENTITY_CANDIDATE_HEADERS)[number];

/**
 * What §6A's table records for one header.
 *
 * `consumedByIsaac` is `false` for all seven. §6A flags that this field in the
 * probe's own output was a code constant echoed back rather than a measurement —
 * the independent evidence is the grep in §1.2 showing the backend reads four
 * headers, none of them identity. It is recorded here as the documented fact,
 * not as something this module measured.
 */
export interface HeaderObservation {
  /** The header arrived at the pod. */
  readonly present: boolean;
  /** `classify_shape`'s verdict: exactly one value, or one value with separators. */
  readonly shape: 'scalar' | 'list';
  /** No ISAAC code path reads it (§1.2, by grep over the backend). */
  readonly consumedByIsaac: false;
  /**
   * Whether the client's planted canary came back.
   *
   * `false` means the canary was NOT FOUND in either compared form — as a whole
   * value, or as a `,`/`|`-delimited segment. §6A.1 is explicit that this does
   * **not** prove the client's copy was removed: a copy joined on a separator
   * outside `{",", "|"}`, or passed through truncated, re-encoded, case-folded
   * or quoted, yields the identical signature.
   *
   * `true` means the one value that arrived WAS the client's own, so the edge
   * was not observed to supply that header at all.
   */
  readonly clientCanarySurvived: boolean;
}

/**
 * §6A's table, transcribed. The source of truth is the document; this is a copy
 * kept in code so the disqualification below can be derived from it.
 *
 * OPERATOR TESTIMONY, NOT A CAPTURED ARTIFACT — §6A says so itself: the probe
 * wrote no file and the response body was not committed. One request, one path,
 * one moment.
 */
export const HEADER_OBSERVATION_6A: Readonly<
  Record<IdentityCandidateHeader, HeaderObservation>
> = Object.freeze({
  'x-authentik-username': { present: true, shape: 'scalar', consumedByIsaac: false, clientCanarySurvived: false },
  'x-authentik-uid': { present: true, shape: 'scalar', consumedByIsaac: false, clientCanarySurvived: false },
  'x-authentik-email': { present: true, shape: 'scalar', consumedByIsaac: false, clientCanarySurvived: false },
  'x-authentik-name': { present: true, shape: 'scalar', consumedByIsaac: false, clientCanarySurvived: false },
  'x-authentik-groups': { present: true, shape: 'list', consumedByIsaac: false, clientCanarySurvived: false },
  'x-authentik-entitlements': { present: true, shape: 'scalar', consumedByIsaac: false, clientCanarySurvived: true },
  'x-isaac-edge': { present: true, shape: 'scalar', consumedByIsaac: false, clientCanarySurvived: true },
});

/**
 * The headers §6A.2 disqualifies permanently — DERIVED from the observation
 * above rather than hand-listed, so the two cannot drift apart.
 *
 * The rule encoded: a header whose one arriving value was the client's own
 * cannot identify anybody, cannot witness edge traversal, and cannot carry a
 * role. §6A.2 states the disqualification is permanent "unless infrastructure
 * changes and is independently re-verified".
 */
export const DISQUALIFIED_IDENTITY_HEADERS: readonly IdentityCandidateHeader[] = Object.freeze(
  IDENTITY_CANDIDATE_HEADERS.filter(
    (name) => HEADER_OBSERVATION_6A[name].clientCanarySurvived,
  ),
);

/**
 * The same two, as a TYPE.
 *
 * Written out rather than derived, because `filter` is a runtime operation and
 * cannot narrow a type. `the disqualified type and the derived set name the same
 * two headers` in `current-user-contract.test.ts` compares the two as SETS, so a
 * future change to the observation table that is not mirrored here fails.
 */
export type DisqualifiedIdentityHeader = 'x-authentik-entitlements' | 'x-isaac-edge';

/**
 * The only header names a subject may ever claim to have come from.
 *
 * This is the compile-time half of §6A.2's disqualification: assigning
 * `'x-isaac-edge'` to a {@link CurrentUserSubject.observedFrom} is a type error,
 * so a future slice cannot reach for it casually. `a disqualified header is not
 * assignable as a subject source` pins that with `@ts-expect-error`.
 *
 * Being usable as a NAME here is not permission to trust the header's VALUE.
 * Q4 and Q6 are unanswered, and §6A proves nothing about authentication.
 */
export type UsableIdentityClaimHeader = Exclude<
  IdentityCandidateHeader,
  DisqualifiedIdentityHeader
>;

/* ---- the domain model --------------------------------------------------- */

/**
 * Where a `CurrentUser` came from — and today there is exactly ONE member.
 *
 * `'test_fixture'` is the only basis this build can produce, so any code that
 * constructs a `CurrentUser` must literally label it a fixture. A real basis
 * (something like a verified edge assertion) may be added only when the trust
 * boundary is settled: §7 Q4 (can the Service be reached bypassing Authentik?)
 * and Q6 (are group claims authoritative?) are both open, and §8's decision —
 * "wire nothing until Q1–Q4 and Q6 are answered" — still binds.
 *
 * `the trust basis union has exactly the one member` asserts the SET, so adding
 * a member is a deliberate, reviewed act rather than a quiet widening.
 */
export type CurrentUserTrustBasis = 'test_fixture';

/** Every trust basis this build recognises. Asserted as a set by the tests. */
export const CURRENT_USER_TRUST_BASES: readonly CurrentUserTrustBasis[] =
  Object.freeze(['test_fixture'] as const);

/**
 * Which claim a subject key is.
 *
 * Both candidates are recorded because §6A.3 says the choice is live and
 * **neither is confirmed**: the username is the required COMPATIBILITY key
 * (every upstream ownership, ACL and audit row is keyed to it — §5.1, §9.1),
 * while `X-authentik-uid` is now known to reach the pod and is the better
 * lifecycle candidate in the abstract. UID permanence is Q17 and username
 * non-reassignability is Q5; both are institutional lifecycle facts no
 * observation can settle, so this type records the options and picks neither.
 *
 * Email is absent on purpose and permanently: §9 disqualifies it as the stable
 * identifier. ORCID is absent for the same reason at greater strength — §9.1
 * states it is scientific-credit metadata and "must never confer authorization".
 */
export type CurrentUserSubjectKind = 'authentik_username' | 'authentik_uid';

export interface CurrentUserSubject {
  readonly kind: CurrentUserSubjectKind;
  /** The opaque key itself. Never rendered by this build — see the module head. */
  readonly value: string;
  /** Which header the value was claimed from. Disqualified names are untypeable. */
  readonly observedFrom: UsableIdentityClaimHeader;
}

export interface CurrentUser {
  readonly subject: CurrentUserSubject;
  /** A human-readable name, or `null`. Display only, never a key (§9, §9.1). */
  readonly displayName: string | null;
  readonly trustBasis: CurrentUserTrustBasis;
}

/* ---- the states --------------------------------------------------------- */

/**
 * Why a current user could not be read, when a source was asked and answered
 * badly. Distinct from `absent`, which is a successful answer of "nobody".
 */
export type CurrentUserUnavailableReason =
  /** No current-user contract is implemented in this build. */
  | 'no_identity_contract'
  /** A configured source was asked and raised. */
  | 'source_error'
  /** A source answered in a shape this contract does not recognise. */
  | 'contract_mismatch';

/**
 * Why an answer that LOOKED like an identity is refused.
 *
 * `disqualified_header_only` is §6A.2 in one word: the only claim on offer came
 * from a header the client can set freely, so it identifies nobody.
 * `unverified_edge_traversal` is the Q4-shaped refusal: nothing observed proves
 * the request traversed Authentik, and `X-Isaac-Edge` cannot witness it.
 */
export type CurrentUserUntrustedReason =
  | 'disqualified_header_only'
  | 'unverified_edge_traversal';

/**
 * FIVE states, and each one is a different answer.
 *
 *   · `disabled` — no current-user source is wired. NOT an error, NOT "nobody".
 *   · `absent` — a source answered, and there is no signed-in reader.
 *   · `unavailable` — a source was asked and could not answer. A fault.
 *   · `untrusted` — something arrived, and it is refused. See the reasons above.
 *   · `present` — a `CurrentUser` was established.
 *
 * `disabled` and `absent` are kept apart for the same reason `MyStatsState`
 * keeps `access_pending` apart from an empty `ready`: collapsing them would let
 * a UI say "you are not signed in" when the truth is that this build never
 * looked.
 */
export type CurrentUserState =
  | { status: 'disabled' }
  | { status: 'absent' }
  | { status: 'unavailable'; reason: CurrentUserUnavailableReason }
  | { status: 'untrusted'; reason: CurrentUserUntrustedReason }
  | { status: 'present'; user: CurrentUser };

/* ---- the provider boundary ---------------------------------------------- */

/**
 * The seam a future current-user source implements.
 *
 * `get()` is SYNCHRONOUS and takes no arguments — in particular it takes no
 * request, no header map, and no configuration. That is the shape that keeps
 * this boundary incapable of reading anything: a real source would resolve
 * elsewhere and hand the settled state down, exactly as `MyStatsSource` does.
 */
export interface CurrentUserSource {
  readonly id: string;
  get(): CurrentUserState;
}

/**
 * THE ONLY IMPLEMENTATION IN THIS BUILD. Always `disabled`.
 *
 * No configuration, no state, no connection, no header. There is no switch to
 * flip: a different answer requires a different object, written deliberately.
 */
export const disabledCurrentUserSource: CurrentUserSource = Object.freeze({
  id: 'disabled',
  get: (): CurrentUserState => ({ status: 'disabled' }),
});

/**
 * Whether a state permits showing anything scoped to a person.
 *
 * `present` and nothing else. Written as a switch over the discriminant rather
 * than `state.status === 'present'` so adding a state to the union is a compile
 * error here instead of silently defaulting to "not personal" — the safe
 * default is the one worth having, but it should be chosen, not inherited.
 */
export function canPersonalize(state: CurrentUserState): boolean {
  switch (state.status) {
    case 'present':
      return true;
    case 'disabled':
    case 'absent':
    case 'unavailable':
    case 'untrusted':
      return false;
  }
}
