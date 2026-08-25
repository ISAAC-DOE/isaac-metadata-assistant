/*
 * A REHYDRATED PROPOSAL IS UNTRUSTED INPUT, AND NOTHING TREATED IT THAT WAY.
 *
 * WHY THIS FILE EXISTS. `lib/assistantSession.ts` sanitizes on the way OUT and
 * cast on the way IN. `readStorage` did
 *
 *     parsed.proposal && typeof parsed.proposal === 'object'
 *       ? (parsed.proposal as Proposal)
 *       : null
 *
 * into a type whose declaration ends `[key: string]: unknown`. So every key a
 * `sessionStorage` payload carries survived rehydration — including `origin`,
 * which is the field that says what produced the value, and `confirmationState`,
 * which is one of the three things `confirmProposal` checks before it writes.
 *
 * WHAT IS AND IS NOT REACHABLE TODAY, measured rather than asserted, because the
 * difference decides how this file is allowed to describe itself.
 *
 *   rg -n "stageProposal" apps/web/src -g '*.ts' -g '*.tsx' | grep -v __tests__
 *     → lib/assistantSession.ts:288 (the definition), and nothing else
 *
 *   rg -n "session\.proposal" apps/web/src -g '*.ts' -g '*.tsx'
 *     → __tests__/record-session.test.tsx:111, and nothing else
 *
 * So: no production code persists a proposal, and no production code reads the
 * rehydrated one. `useRecordSession` returns it on its `session` field and every
 * screen ignores that field; `AssistantPanel`'s `proposal` prop is never passed by
 * any mount, and its staged proposal comes from `proposeForField` in the same tick.
 * THIS IS NOT A LIVE VULNERABILITY. It is not exploitable today by anyone, and it
 * was never exploitable remotely — writing the payload requires already running
 * script in the origin.
 *
 * WHY IT IS WORTH CLOSING ANYWAY. `AssistantPanel` declares `proposal?: Proposal`
 * for exactly one purpose — to be handed the session's staged proposal — and the
 * hook already computes it. The day one line wires those together, a hand-written
 * `sessionStorage` entry reaches `confirmProposal`, which checks
 * `confirmationState`, `sourceRev` and (via the panel) `experimentId`, and checks
 * NOTHING about where the value came from. That is the path a model's output would
 * take if a model were ever wired in, and `docs/ai-integration-decision-packet.md`
 * §6.3 — "a model-proposed value is never `verified` on the model's word" — is the
 * invariant it would walk around. Closing it while it is cheap and untangled is
 * the point; closing it after the wire exists means auditing the wire instead.
 *
 * WHAT IS ASSERTED
 * ================
 * §1 a forged `origin` does not survive rehydration — the whole proposal is
 *    dropped, fail-closed, rather than admitted with a laundered label.
 * §2 the origins this application actually produces DO survive, so the guard is a
 *    gate and not a blanket refusal. Without this, §1 would pass against a
 *    `readStorage` that returned `null` unconditionally.
 * §3 the keys the write path refuses to store are refused on the read path too.
 *    That symmetry is what makes §1 mean something: a forger who can invent an
 *    `origin` can also invent a `confirmationState`.
 * §4 negative controls — the fixture writer really does reach cold storage, so
 *    §1 cannot pass by never having read anything.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { PROPOSAL_ORIGINS } from '../lib/assistantAgent';
import { clearAllSessions, loadSession } from '../lib/assistantSession';

/** The real storage key `assistantSession` uses. Duplicated deliberately: a test
 *  that imported the prefix would still pass if the prefix changed under it, and
 *  the point here is to write the bytes a hostile script would write. */
const STORAGE_PREFIX = 'isaac.assistant.session.';

/** A distinct id per test, so `getState`'s in-memory mirror is always cold and the
 *  read really does go through `readStorage`. A shared id would let one test's
 *  mirror entry answer the next test's `loadSession` without touching storage. */
let seq = 0;
function freshId(): string {
  seq += 1;
  return `01EXPERIMENT${String(seq).padStart(14, '0')}`;
}

/** Write a raw session blob the way a same-origin script would — bypassing
 *  `stageProposal`, and therefore bypassing the write-path sanitizer entirely. */
function plantStoredProposal(id: string, proposal: Record<string, unknown>): void {
  sessionStorage.setItem(
    `${STORAGE_PREFIX}${id}`,
    JSON.stringify({ messages: [], proposal }),
  );
}

/** A proposal shaped exactly like a real staged one, except for `origin`. Every
 *  other field is what `stageAnswer` would have produced, so a refusal below can
 *  only be about the origin. */
function forged(origin: unknown): Record<string, unknown> {
  return {
    field: 'sample.material',
    value: 'TiO2',
    sourceRev: 5,
    confirmationState: 'pending',
    origin,
  };
}

beforeEach(() => {
  clearAllSessions();
});

// --- §1 a forged origin does not survive ------------------------------------

describe('§1 · a rehydrated proposal claiming an origin this app cannot produce is dropped', () => {
  it.each([
    'model',
    'assistant-seam',
    'llm',
    'provider',
    'mcp',
    'transcription-seam',
    'candidate',
    'user-confirmed',
    '',
  ])('origin %o does not rehydrate', (origin) => {
    const id = freshId();
    plantStoredProposal(id, forged(origin));
    // FAIL-CLOSED, and the whole proposal rather than the offending key. Stripping
    // `origin` alone would rehydrate an unlabelled proposal that then satisfies
    // every check `confirmProposal` makes — a laundered value is worse than a
    // refused one, because nothing downstream can tell it was ever questioned.
    expect(loadSession(id).proposal).toBeNull();
  });

  it.each([null, 42, true, { nested: 'object' }, ['array']])(
    'a non-string origin (%o) does not rehydrate',
    (origin) => {
      const id = freshId();
      plantStoredProposal(id, forged(origin));
      expect(loadSession(id).proposal).toBeNull();
    },
  );

  it('a proposal with no origin at all does not rehydrate', () => {
    // ABSENCE IS NOT A FREE PASS. If it were, a forger would simply omit the key,
    // and the allowlist would be decoration. Nothing legitimate is lost: every
    // proposal this application constructs is given an origin by `stageAnswer`.
    const id = freshId();
    plantStoredProposal(id, { field: 'sample.material', value: 'TiO2', sourceRev: 5 });
    expect(loadSession(id).proposal).toBeNull();
  });

  it('the messages beside it are unaffected — a refused proposal is not a refused session', () => {
    // The conversation log is presentation history and is not a write path. A
    // dropped proposal must not take the transcript with it, or the guard becomes
    // a reason not to have the guard.
    const id = freshId();
    sessionStorage.setItem(
      `${STORAGE_PREFIX}${id}`,
      JSON.stringify({
        messages: [{ role: 'assistant', text: 'A grounded answer.' }],
        proposal: forged('model'),
      }),
    );
    const session = loadSession(id);
    expect(session.proposal).toBeNull();
    expect(session.messages.map((m) => m.text)).toEqual(['A grounded answer.']);
  });
});

// --- §2 the real origins still pass -----------------------------------------

describe('§2 · the origins this application produces DO rehydrate', () => {
  it('the allowlist is the set the code can actually produce, and is not empty', () => {
    // Read from the module rather than restated here, so a narrowing of the
    // allowlist cannot leave this file asserting the old set.
    expect([...PROPOSAL_ORIGINS].sort()).toEqual([
      'candidate (evidence-grounded)',
      'user',
      'user-provided',
    ]);
  });

  it.each([...PROPOSAL_ORIGINS])('origin %o rehydrates intact', (origin) => {
    const id = freshId();
    plantStoredProposal(id, forged(origin));
    const p = loadSession(id).proposal;
    expect(p).not.toBeNull();
    expect(p?.origin).toBe(origin);
    // And the fields a legitimate proposal needs came through untouched.
    expect(p?.field).toBe('sample.material');
    expect(p?.value).toBe('TiO2');
    expect(p?.sourceRev).toBe(5);
  });
});

// --- §3 the read path refuses what the write path refuses --------------------

describe('§3 · rehydration trusts no key the write path would have stripped', () => {
  it('strips keys that are not on the persistence allowlist', () => {
    const id = freshId();
    plantStoredProposal(id, {
      ...forged('user'),
      // None of these is on `SAFE_KEYS`, so none of them could have been STORED by
      // `stageProposal`. Their presence means the blob was hand-written, and
      // `confirmationState` in particular is one of the three gates
      // `confirmProposal` gets to check.
      confirmationState: 'pending',
      experimentId: 'not-this-record',
      classification: 'supported',
      producingTool: 'a-model',
      explanation: 'because a model said so',
    });
    const p = loadSession(id).proposal;
    expect(p).not.toBeNull();
    for (const key of [
      'confirmationState',
      'experimentId',
      'classification',
      'producingTool',
      'explanation',
    ]) {
      expect(p, `${key} survived rehydration`).not.toHaveProperty(key);
    }
  });

  it('a stripped confirmationState fails closed at the write boundary', async () => {
    // Not a claim about `confirmProposal`'s internals — a demonstration that the
    // stripping above lands on the safe side. `confirmProposal` admits only
    // `confirmationState === 'pending'`, so a rehydrated proposal that lost the key
    // is refused before any api call, which is the outcome to want.
    const { confirmProposal } = await import('../lib/assistantAgent');
    const id = freshId();
    plantStoredProposal(id, { ...forged('user'), confirmationState: 'pending' });
    const p = loadSession(id).proposal;
    expect(p).not.toBeNull();
    const api = {
      submitAnswer: () => {
        throw new Error('the api must not be touched');
      },
      editField: () => {
        throw new Error('the api must not be touched');
      },
    };
    const res = await confirmProposal(
      p as never,
      {
        experimentId: id,
        recordRev: 5,
        version: 'genabc.5',
        workflow: { current_step: 'complete_metadata', ordered_steps: [] },
        evidence: [],
        pending: [],
      },
      api as never,
    );
    expect(res.status).toBe('stale');
  });

  it('the deep scrubber still runs on a rehydrated value', () => {
    // `deepSanitize` is what keeps a bearer token out of storage. Running it on the
    // way in as well means a planted blob cannot put one INTO the running app's
    // state either.
    const id = freshId();
    plantStoredProposal(id, {
      ...forged('user'),
      value: { note: 'Bearer planted-secret-value' },
    });
    const p = loadSession(id).proposal;
    expect(JSON.stringify(p)).not.toContain('planted-secret-value');
  });
});

// --- §4 negative controls ----------------------------------------------------

describe('§4 · the fixture really reaches cold storage', () => {
  it('a planted blob with a legitimate origin proves the read path was exercised', () => {
    // If `plantStoredProposal` wrote to the wrong key, or the in-memory mirror
    // answered first, every assertion in §1 would pass while measuring nothing:
    // `loadSession` on an unknown id returns an empty state whose proposal is
    // already `null`. This is the test that distinguishes "refused" from "never
    // read", and §2's assertions rest on it.
    const id = freshId();
    plantStoredProposal(id, forged('user-provided'));
    expect(loadSession(id).proposal?.origin).toBe('user-provided');
  });

  it('the mirror is genuinely cold for a fresh id', () => {
    const id = freshId();
    // Nothing written at all → an empty state, so the fixture's write is what makes
    // the difference in every test above.
    expect(loadSession(id).proposal).toBeNull();
    expect(loadSession(id).messages).toEqual([]);
  });
});
