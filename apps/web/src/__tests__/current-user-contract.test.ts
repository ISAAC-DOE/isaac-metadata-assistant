import { describe, it, expect, vi } from 'vitest';

import {
  CURRENT_USER_TRUST_BASES,
  DISQUALIFIED_IDENTITY_HEADERS,
  HEADER_OBSERVATION_6A,
  IDENTITY_CANDIDATE_HEADERS,
  canPersonalize,
  disabledCurrentUserSource,
  type CurrentUserSubject,
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
    /* The type is hand-written because `filter` cannot narrow one. This is the
       assertion that keeps the two halves from drifting apart. */
    const fromType: readonly ('x-authentik-entitlements' | 'x-isaac-edge')[] = [
      'x-authentik-entitlements',
      'x-isaac-edge',
    ];
    expect([...fromType].sort()).toEqual([...DISQUALIFIED_IDENTITY_HEADERS].sort());
  });

  it('a disqualified header is not assignable as a subject source', () => {
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
  });
});

describe('the shipped source is inactive by construction', () => {
  it('answers disabled and nothing else', () => {
    expect(disabledCurrentUserSource.get()).toEqual({ status: 'disabled' });
    expect(disabledCurrentUserSource.id).toBe('disabled');
    expect(Object.isFrozen(disabledCurrentUserSource)).toBe(true);
  });

  it('sends no request and reads no cookie when asked', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    try {
      disabledCurrentUserSource.get();
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
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
