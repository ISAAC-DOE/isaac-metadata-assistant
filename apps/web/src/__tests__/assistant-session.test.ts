/*
 * P29.1 — ephemeral assistant session context (contract).
 *
 * TEST-FIRST (authored BEFORE implementation; RED until lib/assistantSession.ts
 * exists). The session context is EPHEMERAL and NON-AUTHORITATIVE: browser-session
 * scoped (sessionStorage + in-memory), keyed by experiment id, cleared on reset,
 * and leak-safe. It holds conversation presentation + a staged proposal + the last
 * observed record version — NEVER confirmed record data, evidence, validation,
 * audit, export state, secrets, tokens, or private paths. localStorage/IndexedDB
 * are NOT used. A version change invalidates actionable proposals grounded in an
 * older revision; historical non-actionable messages may remain but must be
 * flagged as previous context.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import {
  appendMessage,
  clearAllSessions,
  clearSession,
  invalidateStaleProposals,
  loadSession,
  stageProposal,
} from '../lib/assistantSession';

const EXP_A = '01EXPERIMENTA0000000000000';
const EXP_B = '01EXPERIMENTB0000000000000';

function msg(text: string, extra: Record<string, unknown> = {}) {
  return { role: 'assistant' as const, text, recordRev: 3, ...extra };
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  clearAllSessions();
});

describe('P29.1 ephemeral session context', () => {
  it('an unknown experiment starts with an empty session', () => {
    const s = loadSession(EXP_A);
    expect(s.messages).toEqual([]);
    expect(s.proposal ?? null).toBeNull();
  });

  it('appends and round-trips messages within one experiment', () => {
    appendMessage(EXP_A, msg('what is missing?'));
    appendMessage(EXP_A, msg('two fields need you'));
    expect(loadSession(EXP_A).messages.map((m) => m.text)).toEqual([
      'what is missing?',
      'two fields need you',
    ]);
  });

  it('isolates experiments — no cross-record conversation leakage', () => {
    appendMessage(EXP_A, msg('A-only message'));
    expect(loadSession(EXP_B).messages).toEqual([]);
    appendMessage(EXP_B, msg('B-only message'));
    expect(loadSession(EXP_A).messages.map((m) => m.text)).toEqual(['A-only message']);
    expect(loadSession(EXP_B).messages.map((m) => m.text)).toEqual(['B-only message']);
  });

  it('clearSession clears only that experiment; clearAllSessions (reset) wipes all', () => {
    appendMessage(EXP_A, msg('a'));
    appendMessage(EXP_B, msg('b'));
    clearSession(EXP_A);
    expect(loadSession(EXP_A).messages).toEqual([]);
    expect(loadSession(EXP_B).messages.length).toBe(1);
    clearAllSessions(); // Reset Demo semantics
    expect(loadSession(EXP_B).messages).toEqual([]);
  });

  it('a staged proposal records its source revision', () => {
    stageProposal(EXP_A, { field: 'sample.material', value: 'TiO2', sourceRev: 5 });
    const p = loadSession(EXP_A).proposal;
    expect(p?.field).toBe('sample.material');
    expect(p?.sourceRev).toBe(5);
    expect(p?.stale ?? false).toBe(false);
  });

  it('a version change invalidates an actionable proposal grounded in an older rev', () => {
    stageProposal(EXP_A, { field: 'sample.material', value: 'TiO2', sourceRev: 5 });
    invalidateStaleProposals(EXP_A, 6); // record advanced 5 -> 6
    const p = loadSession(EXP_A).proposal;
    expect(p?.stale).toBe(true); // marked stale, not silently confirmable
    // same-rev must NOT invalidate
    stageProposal(EXP_B, { field: 'x', value: 'y', sourceRev: 6 });
    invalidateStaleProposals(EXP_B, 6);
    expect(loadSession(EXP_B).proposal?.stale ?? false).toBe(false);
  });

  it('uses sessionStorage, never localStorage', () => {
    appendMessage(EXP_A, msg('persist me'));
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBeGreaterThan(0);
  });

  it('never persists secrets, bearer tokens, or private paths (leak-safe)', () => {
    appendMessage(EXP_A, msg('answer', {
      authorization: 'Bearer super-secret-token',
      token: 'super-secret-token',
      sourcePath: '/Users/krish/private/raw.h5',
    }));
    stageProposal(EXP_A, {
      field: 'x',
      value: 'y',
      sourceRev: 1,
      authorization: 'Bearer another-token',
      path: '/Users/krish/secret',
    } as never);
    const blob = JSON.stringify(sessionStorage);
    expect(blob).not.toContain('super-secret-token');
    expect(blob).not.toContain('another-token');
    expect(blob).not.toContain('/Users/');
    expect(blob.toLowerCase()).not.toContain('bearer ');
  });

  it('strips NESTED secrets/paths/verdicts (deep sanitization, not just top-level)', () => {
    // proposal.value is `unknown` — the most exposed channel. A secret nested
    // under it, inside an array, under an allowlisted object-valued key, or a
    // raw secret string in an allowlisted string field must all be scrubbed.
    stageProposal(EXP_A, {
      field: 'sample.material',
      value: {
        authorization: 'Bearer NESTED-SECRET-1',
        path: '/Users/krish/raw.h5',
        hash: 'a'.repeat(64),
        list: [{ token: 'Bearer NESTED-SECRET-2' }],
        validate: { ok: true },
        evidence: [{ sha256: 'b'.repeat(64) }],
      },
      sourceRev: 1,
    } as never);
    appendMessage(EXP_A, msg('nested', {
      // an allowlisted key holding an object with a secret inside
      resultType: { authorization: 'Bearer NESTED-SECRET-3' } as never,
      // a raw secret string inside an allowlisted STRING field
      text: 'my token is Bearer NESTED-SECRET-4 and path /Users/krish/x',
    }));
    const blob = JSON.stringify(sessionStorage);
    expect(blob).not.toContain('NESTED-SECRET-1');
    expect(blob).not.toContain('NESTED-SECRET-2');
    expect(blob).not.toContain('NESTED-SECRET-3');
    expect(blob).not.toContain('NESTED-SECRET-4');
    expect(blob).not.toContain('/Users/');
    expect(blob).not.toContain('a'.repeat(64));
    expect(blob).not.toContain('b'.repeat(64));
    expect(blob).not.toContain('"validate"');
    expect(blob).not.toContain('"evidence"');
  });

  it('does not persist confirmed-record / verdict fields into the session blob', () => {
    // Even if a caller tries to stash authoritative verdicts, they must not persist.
    appendMessage(EXP_A, msg('ok', { validate: { ok: true }, exported: true, draft: { secret: 1 } } as never));
    const blob = JSON.stringify(sessionStorage);
    expect(blob).not.toContain('"draft"');
    expect(blob).not.toContain('"validate"');
  });
});
