import { describe, it, expect, vi, afterEach } from 'vitest';

import {
  PORTAL_FORBIDDEN_CATEGORIES,
  PORTAL_METRICS_TIMEOUT_MS,
  PORTAL_METRICS_UNAVAILABLE_COPY,
  PORTAL_METRICS_UNAVAILABLE_REASONS,
  PORTAL_METRIC_VIEWS,
  PORTAL_MIN_COHORT_SIZE,
  acceptPortalPayload,
  mapPortalFailure,
  screenPortalPayload,
  suppressSmallCohorts,
  unconfiguredPortalMetricsSource,
  withPortalTimeout,
  type PortalForbiddenCategory,
  type PortalMetricsSource,
} from '../lib/portalMetricsContract';
import {
  LEAKY_PORTAL_PAYLOADS,
  failingPortalMetricsSource,
  fixtureDomainBreakdown,
  fixtureFreshness,
  fixtureIsoInstantFreshness,
  fixtureLeakyFreshness,
  fixturePlatformTotal,
  fixtureSecondsPrecisionFreshness,
  fixtureSeries,
  fixtureSmallCohortBreakdown,
  leakyPortalMetricsSource,
  populatedPortalMetricsSource,
} from '../test/adapterFixtures';

/**
 * The PORTAL METRICS boundary — the inactive one.
 *
 * What this file pins, in the order the risks matter:
 *
 *  1. The shipped source cannot send a request and cannot be configured into
 *     one. Asserted structurally (no URL/token-shaped field, no `fetch`) rather
 *     than by reading the source text alone.
 *  2. Every failure path discards what it was given. An upstream error carrying
 *     a host, a URL and a token must contribute NOTHING to the state or to the
 *     sentence a reader sees.
 *  3. Each of the eight forbidden disclosures is detected, and the detection
 *     BITES: a payload carrying one is refused whole, and the offending text
 *     appears nowhere in the resulting state.
 *  4. The declared shapes can actually carry an answer — proved with the
 *     test-only populated source, which is the only place a `ready` state
 *     exists in this repository.
 */

afterEach(() => {
  vi.useRealTimers();
});

/** Every method name on the source interface, so a sweep cannot silently shrink. */
const SOURCE_METHODS = [
  'platformRecordTotal',
  'recordsByDomain',
  'recordsByExperimentType',
  'recordsBySchemaVersion',
  'validationOutcomeTotals',
  'submissionVolumeOverTime',
] as const;

type SourceMethod = (typeof SOURCE_METHODS)[number];

const callAll = (source: PortalMetricsSource) =>
  SOURCE_METHODS.map((name) => source[name as SourceMethod]());

describe('the shipped source is inactive by construction', () => {
  it('reports itself unconfigured and answers every dataset with not_configured', () => {
    expect(unconfiguredPortalMetricsSource.configured).toBe(false);
    expect(callAll(unconfiguredPortalMetricsSource)).toEqual(
      SOURCE_METHODS.map(() => ({ status: 'unavailable', reason: 'not_configured' })),
    );
  });

  it('exposes the SET of methods the interface declares — not merely a count', () => {
    /* A count would pass if a method were renamed. The set is the assertion,
       and `id`/`configured` are named too so a new data-carrying property
       cannot appear unnoticed. */
    expect(Object.keys(unconfiguredPortalMetricsSource).sort()).toEqual(
      ['configured', 'id', ...SOURCE_METHODS].sort(),
    );
  });

  it('carries no URL, host, token or credential in any form', () => {
    /* WEAK ON ITS OWN, AND SAYING SO IS THE POINT: `JSON.stringify` drops
       functions, so this walks `{ id, configured }` and a method body containing
       `fetch('https://…')` would pass it untouched. It is kept because it pins the
       DATA properties and the property NAMES; the claim that no method can reach a
       network is carried by the fetch spy below, by `Object.isFrozen`, and above
       all by the module source scan that follows. */
    const serialised = JSON.stringify(unconfiguredPortalMetricsSource);
    expect(serialised).not.toMatch(/https?:/i);
    expect(serialised).not.toMatch(/token|secret|bearer|api[_-]?key|password/i);
    for (const key of Object.keys(unconfiguredPortalMetricsSource)) {
      expect(key).not.toMatch(/url|endpoint|host|origin|base|token|key|secret/i);
    }
  });

  it('the module SOURCE holds no URL, host, transport or API-client call', async () => {
    /*
     * THE SCAN THAT WOULD ACTUALLY BITE, and the one the serialisation test above
     * cannot be: it reads the module's own text, so a URL inside a method body — the
     * form the defect would really take — is visible to it.
     *
     * Comments are stripped first, because this module's head DISCUSSES `fetch`,
     * URLs and hosts at length in order to explain why it holds none. A whole-text
     * scan would be satisfied by deleting that explanation, which is the inversion
     * `my-stats.test.tsx` trap 1 already names. Stripping is deliberately naive
     * (block comments, then whole-line `//`); it is sound HERE because this file
     * contains no `/*` inside a string or regular expression — checked.
     */
    const raw = String((await import('../lib/portalMetricsContract?raw')).default);
    const code = raw.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^[ \t]*\/\/.*$/gm, ' ');

    // The stripper must have left the CODE behind, or every assertion below is
    // vacuous. These are three things only the code can contain.
    expect(code).toContain('unconfiguredPortalMetricsSource');
    expect(code).toContain('PORTAL_MIN_COHORT_SIZE = 5');
    // …and it must have removed the prose that would otherwise trip the scans.
    expect(raw).toMatch(/\bfetch\b/);
    expect(code).not.toMatch(/\bfetch\b/);

    expect(code, 'no URL or protocol').not.toMatch(/https?:\/\//i);
    expect(code, 'no transport of its own').not.toMatch(
      /XMLHttpRequest|EventSource|sendBeacon|WebSocket|\bimport\s*\(/,
    );
    expect(code, "no call through this app's API client").not.toMatch(/\bapi\s*\.\s*[a-zA-Z]/);
    expect(code, 'no header access').not.toMatch(/headers\s*[.[]/);
    expect(code, 'no cookie or browser storage').not.toMatch(
      /document\s*\.\s*cookie|localStorage|sessionStorage/,
    );
    // …and it cannot even IMPORT the API client. Matched on import statements, so
    // deleting the explanation rather than the dependency cannot satisfy it.
    for (const line of code.match(/^import[\s\S]*?from\s+'[^']+';$/gm) ?? []) {
      expect(line, 'must not import the API client').not.toMatch(/lib\/api'|\/api'$/);
    }
  });

  it('sends no request when every dataset is asked', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    try {
      callAll(unconfiguredPortalMetricsSource);
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('is frozen, so a caller cannot swap a method for one that does fetch', () => {
    expect(Object.isFrozen(unconfiguredPortalMetricsSource)).toBe(true);
  });
});

describe('failure mapping discards everything it was handed', () => {
  /** An error of the shape a misconfigured client really produces. */
  const leakyError = Object.assign(
    new TypeError(
      'fetch failed: https://metrics.internal.example.invalid/v1/summary?token=s3cr3t-abc — ' +
        'connect ECONNREFUSED 192.0.2.9:8443 for user fixture-person@example.invalid',
    ),
    { config: { url: 'https://metrics.internal.example.invalid', token: 's3cr3t-abc' } },
  );

  it('returns a reason from the CLOSED set and nothing else', () => {
    const reason = mapPortalFailure(leakyError);
    expect(PORTAL_METRICS_UNAVAILABLE_REASONS).toContain(reason);
    expect(typeof reason).toBe('string');
  });

  it('leaks no host, URL, token, address or address-holder into the state or the copy', () => {
    const state = { status: 'unavailable', reason: mapPortalFailure(leakyError) } as const;
    const rendered = `${JSON.stringify(state)} ${PORTAL_METRICS_UNAVAILABLE_COPY[state.reason]}`;
    for (const needle of [
      'metrics.internal.example.invalid',
      's3cr3t-abc',
      '192.0.2.9',
      'fixture-person@example.invalid',
      'ECONNREFUSED',
    ]) {
      expect(rendered).not.toContain(needle);
    }
  });

  it('classifies the four shapes it claims to, and defaults the rest to refused', () => {
    expect(mapPortalFailure(Object.assign(new Error('x'), { name: 'AbortError' }))).toBe('timed_out');
    expect(mapPortalFailure(Object.assign(new Error('x'), { name: 'TimeoutError' }))).toBe('timed_out');
    expect(mapPortalFailure(new TypeError('x'))).toBe('unreachable');
    expect(mapPortalFailure(new SyntaxError('x'))).toBe('malformed');
    expect(mapPortalFailure(new Error('x'))).toBe('refused');
    // Non-errors must not throw on the way to a reason.
    expect(mapPortalFailure(null)).toBe('refused');
    expect(mapPortalFailure('a string')).toBe('refused');
    expect(mapPortalFailure(undefined)).toBe('refused');
  });

  it('every reason has copy, and no copy states a number or a zero', () => {
    expect(Object.keys(PORTAL_METRICS_UNAVAILABLE_COPY).sort()).toEqual(
      [...PORTAL_METRICS_UNAVAILABLE_REASONS].sort(),
    );
    for (const reason of PORTAL_METRICS_UNAVAILABLE_REASONS) {
      const copy = PORTAL_METRICS_UNAVAILABLE_COPY[reason];
      expect(copy.length).toBeGreaterThan(40);
      expect(copy, `"${reason}" copy must state no digit`).not.toMatch(/\d/);
    }
  });
});

describe('the timeout is a combinator, not a client', () => {
  it('resolves with the settled value when the promise answers in time', async () => {
    await expect(withPortalTimeout(Promise.resolve(7), 50)).resolves.toEqual({
      kind: 'settled',
      value: 7,
    });
  });

  it('reports timed_out when nothing answers, without rejecting', async () => {
    vi.useFakeTimers();
    const outcome = withPortalTimeout(new Promise<number>(() => {}), PORTAL_METRICS_TIMEOUT_MS);
    await vi.advanceTimersByTimeAsync(PORTAL_METRICS_TIMEOUT_MS);
    await expect(outcome).resolves.toEqual({ kind: 'failed', reason: 'timed_out' });
  });

  it('maps a rejection through mapPortalFailure and never rejects itself', async () => {
    await expect(
      withPortalTimeout(Promise.reject(new TypeError('connect ECONNREFUSED 192.0.2.9')), 50),
    ).resolves.toEqual({ kind: 'failed', reason: 'unreachable' });
  });

  it('a late settle does not overwrite an already-reported timeout', async () => {
    vi.useFakeTimers();
    let settle: (n: number) => void = () => {};
    const pending = new Promise<number>((resolve) => {
      settle = resolve;
    });
    const outcome = withPortalTimeout(pending, 10);
    await vi.advanceTimersByTimeAsync(10);
    settle(99);
    await expect(outcome).resolves.toEqual({ kind: 'failed', reason: 'timed_out' });
  });
});

type LeakyCase = keyof typeof LEAKY_PORTAL_PAYLOADS;

/**
 * What each fixture CASE must be reported as — keyed by case name, because
 * `record_identifier` has two detectors and therefore two cases.
 *
 * Sets, not counts. `requests_per_user` legitimately trips two categories and
 * that pair is written out rather than glossed as "at least one".
 */
const EXPECTED_BY_CASE: Record<LeakyCase, PortalForbiddenCategory[]> = {
  email_address: ['email_address'],
  orcid_id: ['orcid_id'],
  ip_address: ['ip_address'],
  user_identifier: ['user_identifier'],
  per_user_request_count: ['user_identifier', 'per_user_request_count'],
  record_identifier: ['record_identifier'],
  // A real ULID under `label` — no KEY pattern names `label`, so only the
  // value-shape detector can report this one.
  record_identifier_value: ['record_identifier'],
  record_title: ['record_title'],
  small_cohort: ['small_cohort'],
};

describe('forbidden disclosures — each category is detected', () => {
  it('the fixture cases cover every category the contract declares, and each is expected', () => {
    /* Coverage is asserted as a SET UNION over the cases rather than as
       "one fixture per category": a category with two detectors needs two cases,
       and keying the fixtures by category made that unrepresentable. Pinning the
       expectation map's keys to the fixture's keys is what stops a new case being
       added with no stated expectation. */
    const covered = new Set(Object.values(EXPECTED_BY_CASE).flat());
    expect([...covered].sort()).toEqual([...PORTAL_FORBIDDEN_CATEGORIES].sort());
    expect(Object.keys(EXPECTED_BY_CASE).sort()).toEqual(Object.keys(LEAKY_PORTAL_PAYLOADS).sort());
  });

  it.each((Object.keys(LEAKY_PORTAL_PAYLOADS) as LeakyCase[]).map((name) => [name] as const))(
    '%s trips every category it is built to trip',
    (name) => {
      const found = screenPortalPayload(LEAKY_PORTAL_PAYLOADS[name]);
      for (const category of EXPECTED_BY_CASE[name]) {
        expect(found, `${name} must report ${category}, got ${JSON.stringify(found)}`).toContain(
          category,
        );
      }
    },
  );

  it('reports the EXACT set for each payload, so a detector cannot over-report', () => {
    for (const [name, want] of Object.entries(EXPECTED_BY_CASE) as [
      LeakyCase,
      PortalForbiddenCategory[],
    ][]) {
      expect(
        screenPortalPayload(LEAKY_PORTAL_PAYLOADS[name]).sort(),
        `payload "${name}"`,
      ).toEqual([...want].sort());
    }
  });

  it('a ULID under an innocuous key is reported — the value-shape detector, alone', () => {
    /* THE NEGATIVE CONTROL FOR THIS ONE IS DELETING `ULID_PATTERN`'s line from
       `screenPortalPayload`; before this case existed, that deletion left every
       test in this file passing. `label` is matched by no key pattern, so nothing
       but the value-shape detector can report it. */
    expect(screenPortalPayload({ label: 'Record 01ARZ3NDEKTSV4RRFFQ69G5FAV' })).toEqual([
      'record_identifier',
    ]);
    // …and the shape, not the word: the same sentence without the id is clean.
    expect(screenPortalPayload({ label: 'Record' })).toEqual([]);
    // 25 and 27 characters are not ULIDs, so the length is really being checked.
    expect(screenPortalPayload({ label: '01ARZ3NDEKTSV4RRFFQ69G5FA' })).toEqual([]);
    expect(screenPortalPayload({ label: '01ARZ3NDEKTSV4RRFFQ69G5FAVX' })).toEqual([]);
  });

  it('finds a disclosure nested inside arrays and objects, not only at the top', () => {
    expect(
      screenPortalPayload({
        categories: [{ key: 'a', label: 'ok', count: 40 }, { key: 'b', label: 'x@y.invalid', count: 40 }],
      }),
    ).toEqual(['email_address']);
  });

  it('a clean payload reports nothing — so the screener is not simply always positive', () => {
    expect(screenPortalPayload(fixtureDomainBreakdown)).toEqual([]);
    expect(screenPortalPayload(fixturePlatformTotal)).toEqual([]);
    expect(screenPortalPayload(fixtureSeries)).toEqual([]);
  });

  it('a category count of zero is NOT a small cohort — it identifies nobody', () => {
    expect(screenPortalPayload({ count: 0 })).toEqual([]);
    expect(screenPortalPayload({ count: PORTAL_MIN_COHORT_SIZE })).toEqual([]);
    expect(screenPortalPayload({ count: PORTAL_MIN_COHORT_SIZE - 1 })).toEqual(['small_cohort']);
  });
});

describe('a screened payload is refused WHOLE, not edited', () => {
  it('acceptPortalPayload returns withheld and carries none of the offending text', () => {
    const state = acceptPortalPayload(
      { categories: [{ key: 'a', label: 'fixture-owner@example.invalid', count: 40 }] },
      fixtureFreshness,
    );
    expect(state).toEqual({ status: 'unavailable', reason: 'withheld' });
    expect(JSON.stringify(state)).not.toContain('fixture-owner');
    expect(JSON.stringify(state)).not.toContain('@example.invalid');
  });

  it('a source whose ONE dataset leaks withholds that dataset and keeps the others', () => {
    const leaked = leakyPortalMetricsSource.recordsByDomain();
    expect(leaked).toEqual({ status: 'unavailable', reason: 'withheld' });
    expect(JSON.stringify(leaked)).not.toContain('example.invalid');
    // The refusal is scoped to the answer that tripped, not to the source.
    expect(leakyPortalMetricsSource.platformRecordTotal().status).toBe('ready');
  });

  it('acceptPortalPayload passes a clean payload through with its freshness', () => {
    expect(acceptPortalPayload(fixturePlatformTotal, fixtureFreshness)).toEqual({
      status: 'ready',
      data: fixturePlatformTotal,
      freshness: fixtureFreshness,
    });
  });

  /*
   * THE FRESHNESS IS THE SECOND DISPLAY CHANNEL, and it was unscreened.
   *
   * `PortalMetricsFreshness` is two provider-composed DISPLAY STRINGS that ride on
   * every `ready` state, so it can carry exactly what a figure can. An independent
   * review measured this pair reaching `ready` intact while the same two strings
   * handed to `screenPortalPayload` returned all three categories — the guard
   * existed and one of its two inputs was never passed to it.
   */
  it('refuses a leaking FRESHNESS label even when the data is clean', () => {
    // First: the screener really does see all three, so the test below is about
    // the wiring rather than about the detectors.
    expect(screenPortalPayload(fixtureLeakyFreshness).sort()).toEqual(
      ['email_address', 'ip_address', 'orcid_id'].sort(),
    );

    for (const [label, data] of [
      ['total', fixturePlatformTotal],
      ['categories', fixtureDomainBreakdown],
      ['series', fixtureSeries],
    ] as const) {
      // The data is clean on its own — the refusal can only come from the label.
      expect(screenPortalPayload(data), label).toEqual([]);
      const state = acceptPortalPayload(data, fixtureLeakyFreshness);
      expect(state, label).toEqual({ status: 'unavailable', reason: 'withheld' });
      const serialised = JSON.stringify(state);
      for (const needle of ['ops@internal.example.invalid', '192.0.2.9', '0000-0001-2345-6789']) {
        expect(serialised, `${label} must not carry "${needle}"`).not.toContain(needle);
      }
    }
  });

  it('wrapping the pair cannot itself cause a refusal — the clean fixture still passes', () => {
    /* `{ data, freshness }` introduces two new object keys into the walk. Neither
       trips a key pattern, and this is the assertion that says so rather than
       leaving it to inspection. */
    expect(screenPortalPayload({ data: fixtureDomainBreakdown, freshness: fixtureFreshness })).toEqual(
      [],
    );
    expect(acceptPortalPayload(fixtureDomainBreakdown, fixtureFreshness).status).toBe('ready');
  });

  it('a space-delimited clock time in a freshness label is refused as an address', () => {
    /*
     * NOT A LEAK, AND NOT A BUG — the documented trade on `IPV6_PATTERN`. Two
     * colon-separated groups of hex-legal digits are an IPv6 fragment as far as a
     * broad detector can tell, so ` 00:00:00 ` in a label refuses the panel.
     *
     * ITS WIDTH WAS MEASURED, and it is narrower than it first appeared: the ISO
     * form of the same instant passes, because `T` and `Z` are not hex-legal and
     * destroy the word boundaries the pattern needs. Both halves are asserted, so
     * the blind spot is recorded at its real width rather than at a guessed one —
     * and so a future change to the pattern that widens the refusal to ISO
     * timestamps fails here.
     */
    expect(screenPortalPayload(fixtureSecondsPrecisionFreshness)).toEqual(['ip_address']);
    expect(acceptPortalPayload(fixturePlatformTotal, fixtureSecondsPrecisionFreshness)).toEqual({
      status: 'unavailable',
      reason: 'withheld',
    });

    // The ISO-8601 instant is clean, so seconds precision IS stateable.
    expect(screenPortalPayload(fixtureIsoInstantFreshness)).toEqual([]);
    expect(acceptPortalPayload(fixturePlatformTotal, fixtureIsoInstantFreshness).status).toBe('ready');

    // …and the shipped fixture label states a time WITHOUT seconds, and passes.
    expect(screenPortalPayload(fixtureFreshness)).toEqual([]);
  });
});

describe('small-cohort suppression', () => {
  it('drops categories below the floor, keeps zeros, and counts what it dropped', () => {
    const suppressed = suppressSmallCohorts(fixtureSmallCohortBreakdown);
    expect(suppressed.categories.map((c) => c.key)).toEqual(['big', 'none']);
    expect(suppressed.withheldCategoryCount).toBe(1);
  });

  it('a suppressed breakdown then passes screening — the two agree on the floor', () => {
    expect(screenPortalPayload(fixtureSmallCohortBreakdown)).toEqual(['small_cohort']);
    expect(screenPortalPayload(suppressSmallCohorts(fixtureSmallCohortBreakdown))).toEqual([]);
  });

  it('adds to an existing withheld tally rather than replacing it', () => {
    const twice = suppressSmallCohorts(
      suppressSmallCohorts({ ...fixtureSmallCohortBreakdown, withheldCategoryCount: 3 }),
    );
    expect(twice.withheldCategoryCount).toBe(4);
  });
});

describe('the declared shapes can carry an answer (test-only source)', () => {
  it('every dataset reaches ready, with freshness', () => {
    for (const state of callAll(populatedPortalMetricsSource)) {
      expect(state.status).toBe('ready');
      if (state.status === 'ready') {
        expect(state.freshness.coverageLabel.length).toBeGreaterThan(0);
      }
    }
  });

  it('a failing source reports the reason it was built with, for every dataset', () => {
    for (const reason of PORTAL_METRICS_UNAVAILABLE_REASONS) {
      expect(callAll(failingPortalMetricsSource(reason))).toEqual(
        SOURCE_METHODS.map(() => ({ status: 'unavailable', reason })),
      );
    }
  });
});

describe('the planned views', () => {
  it('name every dataset exactly once, and each states its unit', () => {
    const ids = PORTAL_METRIC_VIEWS.map((v) => v.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const view of PORTAL_METRIC_VIEWS) {
      expect(view.title.length).toBeGreaterThan(0);
      /* The section's own copy claims "each description names the unit it would
         count", so this asserts the literal phrase rather than a loose alternation
         — the earlier `/records|version/` was satisfied by a description that
         named no unit at all, which is exactly the claim-without-a-guard shape
         this repo has been bitten by. */
      expect(view.description, `"${view.id}"`).toContain('counted in records');
    }
  });

  it('no view description states a figure, a zero, or a person-scoped quantity', () => {
    for (const view of PORTAL_METRIC_VIEWS) {
      expect(view.description).not.toMatch(/\d/);
      expect(view.description).not.toMatch(/\buser|\bvisit|\brequest|\bsession|\bperson/i);
    }
  });
});
