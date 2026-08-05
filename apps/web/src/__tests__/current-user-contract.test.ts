import { describe, it, expect, vi } from 'vitest';

import {
  CURRENT_USER_TRUST_BASES,
  DISQUALIFIED_IDENTITY_HEADERS,
  HEADER_OBSERVATION_6A,
  IDENTITY_CANDIDATE_HEADERS,
  canPersonalize,
  disabledCurrentUserSource,
  type CurrentUserSubject,
  type DisqualifiedIdentityHeader,
} from '../lib/currentUserContract';
import { personalStatisticsSourceFor, unconfiguredMyStatsSource } from '../lib/myStatsContract';
import {
  ALL_CURRENT_USER_STATES,
  currentUserSourceReporting,
  fixtureCurrentUser,
} from '../test/adapterFixtures';

/**
 * The CURRENT-USER boundary.
 *
 * `docs/identity-trust-contract.md` §8 forbids building an identity SEAM, and
 * this file's job is to prove that what was built is not one: it reads no
 * header, cannot mint a trusted principal, cannot be pointed at the two
 * disqualified headers, and unlocks nothing when it does report somebody.
 *
 * The §6A findings this file encodes, stated at their real strength:
 *
 *   · All seven candidate headers arrive; ISAAC consumes NONE of them.
 *   · `X-authentik-entitlements` and `X-Isaac-Edge` came back carrying the
 *     client's own canary, so they are permanently disqualified (§6A.2).
 *   · For the other five the canary was NOT FOUND — which §6A.1 is explicit does
 *     NOT prove the client's copy was removed. Nothing here says it does.
 */

describe('the §6A observation, as encoded', () => {
  it('covers the seven candidate headers as a SET', () => {
    expect([...IDENTITY_CANDIDATE_HEADERS].sort()).toEqual(
      [
        'x-authentik-email',
        'x-authentik-entitlements',
        'x-authentik-groups',
        'x-authentik-name',
        'x-authentik-uid',
        'x-authentik-username',
        'x-isaac-edge',
      ].sort(),
    );
    expect(Object.keys(HEADER_OBSERVATION_6A).sort()).toEqual([...IDENTITY_CANDIDATE_HEADERS].sort());
  });

  it('records that ISAAC consumes none of them', () => {
    for (const name of IDENTITY_CANDIDATE_HEADERS) {
      expect(HEADER_OBSERVATION_6A[name].consumedByIsaac, name).toBe(false);
    }
  });

  it('records all seven as present, and groups as the one list-shaped value', () => {
    for (const name of IDENTITY_CANDIDATE_HEADERS) {
      expect(HEADER_OBSERVATION_6A[name].present, name).toBe(true);
    }
    const listShaped = IDENTITY_CANDIDATE_HEADERS.filter(
      (name) => HEADER_OBSERVATION_6A[name].shape === 'list',
    );
    expect(listShaped).toEqual(['x-authentik-groups']);
  });
});

describe('the permanent disqualification (§6A.2)', () => {
  it('is DERIVED from the observation — the two whose canary survived', () => {
    expect([...DISQUALIFIED_IDENTITY_HEADERS].sort()).toEqual(
      ['x-authentik-entitlements', 'x-isaac-edge'].sort(),
    );
    expect(
      IDENTITY_CANDIDATE_HEADERS.filter(
        (name) => HEADER_OBSERVATION_6A[name].clientCanarySurvived,
      ).sort(),
    ).toEqual([...DISQUALIFIED_IDENTITY_HEADERS].sort());
  });

  it('the disqualified TYPE and the derived set name the same two headers', () => {
    /*
     * THE ANNOTATION IS THE ASSERTION, and the previous version of this test did
     * not have it. It declared a hand-written literal union inline and compared it
     * to the runtime set, so it never mentioned `DisqualifiedIdentityHeader` at
     * all: narrowing that type to `'x-isaac-edge'` alone left `tsc -b` clean and
     * this test green, silently re-permitting `'x-authentik-entitlements'` as a
     * `CurrentUserSubject.observedFrom` — which §6A.2 disqualifies permanently.
     *
     * Annotated with the real type, a narrowing makes the second element
     * unassignable (TS2322) and a widening breaks the set comparison below. The
     * two halves of the guard now cover the two directions.
     */
    const fromType: readonly DisqualifiedIdentityHeader[] = [
      'x-authentik-entitlements',
      'x-isaac-edge',
    ];
    expect([...fromType].sort()).toEqual([...DISQUALIFIED_IDENTITY_HEADERS].sort());
  });

  it('NEITHER disqualified header is assignable as a subject source', () => {
    const usable: CurrentUserSubject = {
      kind: 'authentik_username',
      value: 'x',
      observedFrom: 'x-authentik-username',
    };
    expect(usable.observedFrom).toBe('x-authentik-username');

    const rejected: CurrentUserSubject = {
      kind: 'authentik_uid',
      value: 'x',
      // @ts-expect-error — §6A.2 disqualifies this header permanently, and the
      // type makes reaching for it a compile error rather than a review catch.
      observedFrom: 'x-isaac-edge',
    };
    // The value is still present at RUNTIME (TypeScript erases), so the guard
    // that bites is `tsc`. Reading it here keeps the binding used and states
    // plainly which layer is doing the work.
    expect(rejected.observedFrom).toBe('x-isaac-edge');

    /* BOTH, not one. Only `x-isaac-edge` was pinned here, so the entitlements
       header — the other half of the same §6A.2 finding — could be re-permitted
       without a single test or type error. `@ts-expect-error` bites in both
       directions: if a narrowing ever makes this assignment legal, the unused
       expectation is itself a compile error (TS2578). */
    const alsoRejected: CurrentUserSubject = {
      kind: 'authentik_username',
      value: 'x',
      // @ts-expect-error — §6A.2 disqualifies entitlements permanently too: the one
      // value that arrived was the client's own, so it identifies nobody.
      observedFrom: 'x-authentik-entitlements',
    };
    expect(alsoRejected.observedFrom).toBe('x-authentik-entitlements');
  });
});

describe('the shipped source is inactive by construction', () => {
  it('answers disabled and nothing else', () => {
    expect(disabledCurrentUserSource.get()).toEqual({ status: 'disabled' });
    expect(disabledCurrentUserSource.id).toBe('disabled');
    expect(Object.isFrozen(disabledCurrentUserSource)).toBe(true);
  });

  /*
   * THE TITLE USED TO CLAIM MORE THAN THE BODY ASSERTED. It said "reads no
   * cookie" and spied only `fetch`, so adding `void document.cookie; void
   * window.localStorage;` to `get()` left all of this file passing. A cookie is
   * the most plausible route a future SPA slice takes from "no identity" to a
   * username, so it is now instrumented rather than asserted in prose.
   */
  it('sends no request and reads no cookie or browser storage when asked', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    /* An OWN accessor on `document`, shadowing the prototype's. Removing it again
       restores jsdom's real behaviour, which assigning the descriptor back would
       not (there was no own property to restore). */
    const cookieGetter = vi.fn(() => '');
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get: cookieGetter,
      set: () => {},
    });
    const localGet = vi.spyOn(window.localStorage, 'getItem');
    const sessionGet = vi.spyOn(window.sessionStorage, 'getItem');

    try {
      disabledCurrentUserSource.get();
      expect(fetchSpy, 'fetch').not.toHaveBeenCalled();
      expect(cookieGetter, 'document.cookie').not.toHaveBeenCalled();
      expect(localGet, 'localStorage.getItem').not.toHaveBeenCalled();
      expect(sessionGet, 'sessionStorage.getItem').not.toHaveBeenCalled();

      /* THE SPY IS PROVED TO WORK, so "not called" means something. Without this,
         a getter that jsdom had made non-configurable — leaving the real accessor
         in place — would report "never read" for every possible implementation. */
      expect(document.cookie).toBe('');
      expect(cookieGetter).toHaveBeenCalledTimes(1);
    } finally {
      Reflect.deleteProperty(document, 'cookie');
      localGet.mockRestore();
      sessionGet.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it('takes no arguments, so there is no header map to hand it', () => {
    expect(disabledCurrentUserSource.get.length).toBe(0);
  });

  it('exposes the SET of properties the interface declares and no data field', () => {
    expect(Object.keys(disabledCurrentUserSource).sort()).toEqual(['get', 'id']);
  });
});

describe('a CurrentUser cannot claim to be trusted', () => {
  it('the trust-basis union has exactly the one member', () => {
    expect([...CURRENT_USER_TRUST_BASES]).toEqual(['test_fixture']);
  });

  it('the only constructible user labels itself a fixture', () => {
    expect(fixtureCurrentUser.trustBasis).toBe('test_fixture');
    expect(CURRENT_USER_TRUST_BASES).toContain(fixtureCurrentUser.trustBasis);
  });
});

describe('the five states are distinguished', () => {
  it('absent is not disabled, and neither is an error', () => {
    expect(currentUserSourceReporting({ status: 'absent' }).get()).toEqual({ status: 'absent' });
    expect(currentUserSourceReporting({ status: 'disabled' }).get()).toEqual({ status: 'disabled' });
    expect(canPersonalize({ status: 'absent' })).toBe(false);
    expect(canPersonalize({ status: 'disabled' })).toBe(false);
  });

  it('unavailable carries the precondition it names, for each reason', () => {
    for (const reason of ['no_identity_contract', 'source_error', 'contract_mismatch'] as const) {
      const state = currentUserSourceReporting({ status: 'unavailable', reason }).get();
      expect(state).toEqual({ status: 'unavailable', reason });
      expect(canPersonalize(state)).toBe(false);
    }
  });

  it('untrusted is refused, including the §6A.2 shape', () => {
    for (const reason of ['disqualified_header_only', 'unverified_edge_traversal'] as const) {
      const state = currentUserSourceReporting({ status: 'untrusted', reason }).get();
      expect(state).toEqual({ status: 'untrusted', reason });
      expect(canPersonalize(state)).toBe(false);
    }
  });

  it('only present permits anything person-scoped', () => {
    expect(canPersonalize({ status: 'present', user: fixtureCurrentUser })).toBe(true);
    const nonPersonal = ALL_CURRENT_USER_STATES.filter((s) => s.status !== 'present');
    expect(nonPersonal.map(canPersonalize)).toEqual(nonPersonal.map(() => false));
  });

  it('the sweep covers every state in the union', () => {
    expect(new Set(ALL_CURRENT_USER_STATES.map((s) => s.status))).toEqual(
      new Set(['disabled', 'absent', 'unavailable', 'untrusted', 'present']),
    );
  });
});

describe('identity alone never selects a personal source', () => {
  it('every state, present included, resolves to the unconfigured personal source', () => {
    for (const state of ALL_CURRENT_USER_STATES) {
      expect(personalStatisticsSourceFor(state), state.status).toBe(unconfiguredMyStatsSource);
    }
  });

  it('and that source still answers access_pending, so nothing is unlocked', () => {
    const source = personalStatisticsSourceFor({ status: 'present', user: fixtureCurrentUser });
    expect(source.workflowCounts()).toEqual({
      status: 'access_pending',
      reason: 'no_record_ownership',
    });
  });
});

describe('nothing here supplies an attribution value', () => {
  it('the module exports no uploaded_by-shaped helper', async () => {
    const contract = await import('../lib/currentUserContract');
    for (const name of Object.keys(contract)) {
      expect(name, `"${name}" reads as an attribution stamper`).not.toMatch(
        /uploaded|attribut|stamp|principal$|getPrincipal/i,
      );
    }
  });
});
