/*
 * `lib/selfMintedProposals.ts` — the same-tab, in-memory courtesy that stops
 * `IngestionProposalsPanel`'s arrival note firing for a proposal THIS tab just
 * minted via `TranscriptCapturePanel`'s finalize or `UnmappedNotesPanel`'s
 * "Propose a value from this note". m7, independent review of PR-D.
 *
 * WHAT WOULD FAIL BEFORE THE BEHAVIOUR THESE TESTS DEFEND:
 *
 *   1. A version that could not tell one experiment's marks from another's,
 *      so switching records read a PREVIOUS record's self-minted ids as this
 *      one's. (`cross-experiment isolation`)
 *   2. A version that treated a batch as self-minted when it could vouch for
 *      only SOME of the ids in it — the fail-OPEN direction, which would
 *      suppress a genuine arrival riding alongside a self-minted one.
 *      (`MUTATION-GUARDED: fail-closed`)
 *   3. A version with no expiry, growing without bound across a long session,
 *      or one whose TTL was shorter than the poll cadence it exists to
 *      outlast, silently reverting to announcing every self-mint as a
 *      colleague's arrival. (`TTL`)
 *
 * Every id and experiment id below is synthetic; nothing here reaches a backend.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';

import { allProposalsSelfMinted, markSelfMintedProposals } from '../lib/selfMintedProposals';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';

const EXP_A = 'exp-a';
const EXP_B = 'exp-b';

afterEach(() => {
  if (vi.isFakeTimers()) vi.useRealTimers();
});

describe('marking and confirming', () => {
  it('confirms every id it was told this tab minted', () => {
    markSelfMintedProposals(EXP_A, ['p1', 'p2']);
    expect(allProposalsSelfMinted(EXP_A, ['p1', 'p2'])).toBe(true);
    expect(allProposalsSelfMinted(EXP_A, ['p1'])).toBe(true);
    expect(allProposalsSelfMinted(EXP_A, ['p2'])).toBe(true);
  });

  it('MUTATION-GUARDED: fail-closed — one id this tab cannot vouch for makes the WHOLE batch not self-minted', () => {
    /*
     * The fail-open mutant (checking `.some` instead of `.every`, or returning
     * `true` whenever ANY id matches) would suppress the arrival note for a
     * batch that mixes a proposal this tab minted with one a colleague's did —
     * exactly the case this function exists to get right.
     */
    markSelfMintedProposals(EXP_A, ['p1']);
    expect(allProposalsSelfMinted(EXP_A, ['p1', 'a-colleagues-id'])).toBe(false);
  });

  it('an empty list is never self-minted — there is nothing to vouch for', () => {
    markSelfMintedProposals(EXP_A, ['p1']);
    expect(allProposalsSelfMinted(EXP_A, [])).toBe(false);
  });

  it('an experiment nothing was ever marked for is never self-minted', () => {
    expect(allProposalsSelfMinted('never-marked-anything', ['p1'])).toBe(false);
  });

  it('marking again (e.g. a later capture on the same note) is additive, not a reset', () => {
    markSelfMintedProposals(EXP_A, ['p1']);
    markSelfMintedProposals(EXP_A, ['p2']);
    expect(allProposalsSelfMinted(EXP_A, ['p1', 'p2'])).toBe(true);
  });
});

describe('cross-experiment isolation — the "record switch" case', () => {
  it('marking for one experiment never answers for a different one, even with the same proposal id', () => {
    // Synthetic ids are not guaranteed globally unique in a real deployment
    // (ULIDs are, but this proves the isolation does not lean on that) — the
    // SAME id string is used for both experiments deliberately.
    markSelfMintedProposals(EXP_A, ['shared-id']);
    expect(allProposalsSelfMinted(EXP_A, ['shared-id'])).toBe(true);
    expect(allProposalsSelfMinted(EXP_B, ['shared-id'])).toBe(false);
  });

  it('switching to a record nothing was marked for reads as a genuine arrival', () => {
    markSelfMintedProposals(EXP_A, ['p1']);
    // A reader who navigates to a DIFFERENT record next has marked nothing
    // there yet — that record's own arrivals must announce normally.
    expect(allProposalsSelfMinted('a-freshly-opened-record', ['p1'])).toBe(false);
  });
});

describe('TTL — justified against the real poll cadence, not an arbitrary number', () => {
  it('stays self-minted comfortably inside the window', () => {
    vi.useFakeTimers();
    markSelfMintedProposals(EXP_A, ['p1']);
    // One ordinary poll cycle has barely elapsed.
    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    expect(allProposalsSelfMinted(EXP_A, ['p1'])).toBe(true);
  });

  it('MUTATION-GUARDED: expires once comfortably past any reasonable TTL', () => {
    /*
     * Ten poll intervals (80s at today's `POLL_INTERVAL_MS`) is well past the
     * module's documented 30s TTL without hard-coding that constant here — a
     * retuning of the TTL (still justified against the same poll cadence)
     * does not need this test to change. The mutant this guards is "no expiry
     * at all" (an unconditional `true` once marked, ever).
     */
    vi.useFakeTimers();
    markSelfMintedProposals(EXP_A, ['p1']);
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 10);
    expect(allProposalsSelfMinted(EXP_A, ['p1'])).toBe(false);
  });

  it('an id that expired can be re-minted (e.g. a later capture reusing it) and is live again', () => {
    vi.useFakeTimers();
    markSelfMintedProposals(EXP_A, ['p1']);
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 10);
    expect(allProposalsSelfMinted(EXP_A, ['p1'])).toBe(false);
    markSelfMintedProposals(EXP_A, ['p1']);
    expect(allProposalsSelfMinted(EXP_A, ['p1'])).toBe(true);
  });
});
