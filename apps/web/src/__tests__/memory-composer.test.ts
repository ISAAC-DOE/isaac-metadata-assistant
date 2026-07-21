import { describe, it, expect } from 'vitest';
import {
  compose,
  count,
  MEMORY_CATALOG,
  MEMORY_UNAVAILABLE_CATALOG,
} from '../lib/assistantComposer';
import { SOURCE_LABELS } from '../lib/assistant';
import { graphStatusAvailable, graphStatusUnavailable } from '../test/apiFixtures';
import type { ApiGraphStatus, GroundingState } from '../lib/types';

/*
 * P25.7 — Project Memory composer (`context: 'memory'`). A PURE, synchronous
 * function over the ALREADY-fetched GET /api/graph/status response the screen
 * holds. No fetch, no I/O, no graph import. Three chips when memory is
 * available (provenance / freshness / included scope); a single replacement
 * chip when it is unavailable — never four chips at once. Every reply is
 * `answered from: Project Memory`, carries the leads-to-verify framing, and
 * NEVER states a validation verdict. The four memory-plane axes are reported
 * SEPARATELY — never collapsed into one universal freshness word.
 */

// A shape-faithful memory state built from the real available fixture. Only
// `graph` is read by the memory composer; overrides tune the individual axes.
function memoryState(overrides: Partial<ApiGraphStatus> = {}): GroundingState {
  const graph = { ...graphStatusAvailable, ...overrides } as ApiGraphStatus;
  return { context: 'memory', graph };
}

// Regexes mirroring the panel's verdict guard + the tasking guard list. `\b`
// word boundaries deliberately do NOT match "validation" inside "validation
// verdict" (an honest, allowed phrase).
const VERDICT = /\b(PASS|FAIL)\b/;
const VALID_WORD = /\b(in)?valid\b/i;
const INVALID_AGAINST = /\b(in)?valid against\b/i;

describe('MEMORY_CATALOG — the three available-memory chips (order + source labels)', () => {
  it('is exactly [memory_provenance, memory_freshness, included_scope] in order', () => {
    expect(MEMORY_CATALOG.map((c) => c.id)).toEqual([
      'memory_provenance',
      'memory_freshness',
      'included_scope',
    ]);
  });

  it('every chip answers from the graph plane and renders as "Project Memory"', () => {
    for (const chip of MEMORY_CATALOG) {
      expect(chip.source).toBe('graph');
      expect(SOURCE_LABELS[chip.source]).toBe('Project Memory');
    }
  });

  it('maps each chip to its approved final label', () => {
    expect(MEMORY_CATALOG.map((c) => c.label)).toEqual([
      'Where do these leads come from?',
      'Is project memory current?',
      'What sources are included?',
    ]);
  });
});

describe('MEMORY_UNAVAILABLE_CATALOG — the single replacement chip', () => {
  it('is exactly [memory_unavailable] — never supplements the three chips', () => {
    expect(MEMORY_UNAVAILABLE_CATALOG.map((c) => c.id)).toEqual(['memory_unavailable']);
  });

  it('answers from the graph plane and uses the approved label', () => {
    const [chip] = MEMORY_UNAVAILABLE_CATALOG;
    expect(chip.source).toBe('graph');
    expect(chip.label).toBe('Why is memory unavailable?');
  });
});

describe('compose({context:"memory"}) — available, all four axes healthy', () => {
  const out = compose(memoryState()); // integrity verified, policy+indexed current, provider set

  it('renders exactly the three approved chips, in order, all answered from Project Memory', () => {
    expect(out.prompts.map((p) => p.text)).toEqual([
      'Where do these leads come from?',
      'Is project memory current?',
      'What sources are included?',
    ]);
    for (const p of out.prompts) {
      expect(p.answer).toBeDefined();
      expect(p.answer!.answeredFrom).toBe('graph');
      expect(SOURCE_LABELS[p.answer!.answeredFrom]).toBe('Project Memory');
    }
    // never four chips at once
    expect(out.prompts.length).toBe(3);
  });

  it('the default reply is the provenance chip, with the leads-to-verify framing', () => {
    expect(out.reply.text).toBe(
      'Leads come from indexed project files and concepts (provider: sanitized-snapshot). ' +
        'Project memory returns leads to verify — never a validation verdict.',
    );
    expect(out.reply.answeredFrom).toBe('graph');
  });

  it('the freshness chip states all three axes on one clean line (no caveats when healthy)', () => {
    const freshness = out.prompts[1].answer!;
    expect(freshness.text).toBe(
      'Snapshot integrity: verified; policy consistency: current; indexed sources: current.',
    );
  });

  it('the scope chip echoes file_count via count() and the refresh caveat', () => {
    const scope = out.prompts[2].answer!;
    expect(scope.text).toBe(
      'This snapshot indexes 190 project files. That scope covers files already in the snapshot; ' +
        'newly added indexable files require a Graphify refresh.',
    );
  });
});

describe('memory_provenance — provider parenthetical drop rules', () => {
  const provenance = (graph: Partial<ApiGraphStatus>) =>
    compose(memoryState(graph)).prompts[0].answer!.text;

  it('shows the provider parenthetical when provider is present', () => {
    expect(provenance({ provider: 'sanitized-snapshot' })).toBe(
      'Leads come from indexed project files and concepts (provider: sanitized-snapshot). ' +
        'Project memory returns leads to verify — never a validation verdict.',
    );
  });

  const dropped =
    'Leads come from indexed project files and concepts. ' +
    'Project memory returns leads to verify — never a validation verdict.';

  it("drops the parenthetical when provider is the sentinel 'unavailable'", () => {
    expect(provenance({ provider: 'unavailable' })).toBe(dropped);
  });

  it('drops the parenthetical when provider is an empty / whitespace string', () => {
    expect(provenance({ provider: '' })).toBe(dropped);
    expect(provenance({ provider: '   ' })).toBe(dropped);
  });

  it('never renders "undefined"/"null" if provider is absent', () => {
    // provider is contract-non-optional, but guard against a type-illegal absence.
    const text = provenance({ provider: undefined as unknown as string });
    expect(text).toBe(dropped);
    expect(text).not.toMatch(/undefined|null/);
  });
});

describe('memory_freshness — per-axis caveats appended SEPARATELY (§6)', () => {
  const freshness = (graph: Partial<ApiGraphStatus>) =>
    compose(memoryState(graph)).prompts[1].answer!.text;

  const INTEGRITY_CAVEAT = (v: string) =>
    `Snapshot integrity is ${v} — the snapshot artifact itself could not be fully verified.`;
  const POLICY_STALE =
    'The shipped sanitization/exclusion policy or its versions differ from what this snapshot was built under.';
  const POLICY_UNKNOWN = 'Policy consistency: comparison could not be established.';
  const INDEXED_UNKNOWN = 'Indexed-source status: comparison could not be established.';

  it.each(['malformed', 'unsupported', 'unknown'] as const)(
    'integrity %s → integrity caveat only, policy/indexed clean',
    (integrity) => {
      const text = freshness({ integrity, memory_policy: 'current', indexed_sources: 'current' });
      expect(text).toBe(
        `Snapshot integrity: ${integrity}; policy consistency: current; indexed sources: current. ` +
          INTEGRITY_CAVEAT(integrity),
      );
      expect(text).not.toContain(POLICY_STALE);
      expect(text).not.toContain(POLICY_UNKNOWN);
      expect(text).not.toContain(INDEXED_UNKNOWN);
    },
  );

  it('integrity verified → NO integrity caveat', () => {
    const text = freshness({ integrity: 'verified', memory_policy: 'current', indexed_sources: 'current' });
    expect(text).toBe(
      'Snapshot integrity: verified; policy consistency: current; indexed sources: current.',
    );
    expect(text).not.toContain('could not be fully verified');
  });

  it('memory_policy stale → the exact policy-drift caveat, stated separately', () => {
    const text = freshness({ integrity: 'verified', memory_policy: 'stale', indexed_sources: 'current' });
    expect(text).toBe(
      'Snapshot integrity: verified; policy consistency: stale; indexed sources: current. ' + POLICY_STALE,
    );
  });

  it('memory_policy unknown → the policy comparison-could-not-be-established caveat', () => {
    const text = freshness({ integrity: 'verified', memory_policy: 'unknown', indexed_sources: 'current' });
    expect(text).toBe(
      'Snapshot integrity: verified; policy consistency: unknown; indexed sources: current. ' + POLICY_UNKNOWN,
    );
  });

  it('indexed_sources unknown → the indexed-source comparison caveat', () => {
    const text = freshness({ integrity: 'verified', memory_policy: 'current', indexed_sources: 'unknown' });
    expect(text).toBe(
      'Snapshot integrity: verified; policy consistency: current; indexed sources: unknown. ' + INDEXED_UNKNOWN,
    );
  });

  it('indexed_sources "stale" is runtime-unreachable → NO stale sentence is ever emitted', () => {
    // Construct the type-illegal-at-runtime `stale` value and prove the live path
    // emits neither the unknown caveat nor the documented-but-unreachable stale
    // wording. The base line still echoes the axis value honestly.
    const text = freshness({ integrity: 'verified', memory_policy: 'current', indexed_sources: 'stale' });
    expect(text).toBe(
      'Snapshot integrity: verified; policy consistency: current; indexed sources: stale.',
    );
    expect(text).not.toContain('no longer match the versions verified');
    expect(text).not.toContain(INDEXED_UNKNOWN);
  });

  it('TYPE-ONLY invariant: all-degraded-but-available (integrity/policy/indexed all unknown) states each axis caveat SEPARATELY', () => {
    // This 4-sentence state is type-constructible but backend-unreachable at
    // runtime (a real available snapshot has integrity=verified). We pin it to
    // prove that even in the maximal-degradation available state the composer
    // states each axis precisely and separately — never merged into one word.
    const text = freshness({
      integrity: 'unknown',
      memory_policy: 'unknown',
      indexed_sources: 'unknown',
    });
    expect(text).toBe(
      'Snapshot integrity: unknown; policy consistency: unknown; indexed sources: unknown. ' +
        INTEGRITY_CAVEAT('unknown') +
        ' ' +
        POLICY_UNKNOWN +
        ' ' +
        INDEXED_UNKNOWN,
    );
    // each axis caveat is present and distinct (four sentences total)
    expect(text).toContain(INTEGRITY_CAVEAT('unknown'));
    expect(text).toContain(POLICY_UNKNOWN);
    expect(text).toContain(INDEXED_UNKNOWN);
    // never collapsed into one universal freshness/verdict word
    expect(text).not.toMatch(/\b(stale overall|unhealthy|out of date overall)\b/i);
    expect(text).not.toMatch(VERDICT);
    expect(text).not.toMatch(VALID_WORD);
  });

  it('several unhealthy axes → each stated SEPARATELY, never collapsed into one word', () => {
    const text = freshness({ integrity: 'verified', memory_policy: 'stale', indexed_sources: 'unknown' });
    expect(text).toBe(
      'Snapshot integrity: verified; policy consistency: stale; indexed sources: unknown. ' +
        POLICY_STALE +
        ' ' +
        INDEXED_UNKNOWN,
    );
    // never collapsed into a single universal freshness verdict word
    expect(text).not.toMatch(/\b(stale overall|unhealthy|out of date overall)\b/i);
    // never says memory is "behind the working tree"
    expect(text).not.toMatch(/behind the working tree/i);
  });
});

describe('included_scope — grounds on file_count only (never served_file_count)', () => {
  const scope = (graph: Partial<ApiGraphStatus>) =>
    compose(memoryState(graph)).prompts[2].answer!.text;

  it('pluralizes correctly at n=2', () => {
    expect(scope({ file_count: 2 })).toBe(
      'This snapshot indexes 2 project files. That scope covers files already in the snapshot; ' +
        'newly added indexable files require a Graphify refresh.',
    );
  });

  it('uses the singular at n=1', () => {
    expect(scope({ file_count: 1 })).toBe(
      'This snapshot indexes 1 project file. That scope covers files already in the snapshot; ' +
        'newly added indexable files require a Graphify refresh.',
    );
    // no raw pluralization placeholder survives
    expect(scope({ file_count: 1 })).not.toMatch(/file\(s\)/);
  });

  it('file_count null → the honest unavailable-count string (never a fabricated number)', () => {
    const text = scope({ file_count: null });
    expect(text).toBe('The indexed-file count is unavailable for this snapshot.');
    expect(text).not.toMatch(/undefined|null|NaN/);
  });

  it('ignores served_file_count entirely (grounds on file_count)', () => {
    // served_file_count differs from file_count; the echoed number is file_count.
    const text = scope({ file_count: 42, served_file_count: 999 });
    expect(text).toContain('42 project files');
    expect(text).not.toContain('999');
  });
});

describe('compose({context:"memory"}) — unavailable → single replacement chip, no red', () => {
  const out = compose({ context: 'memory', graph: graphStatusUnavailable as ApiGraphStatus });

  it('renders ONLY the replacement chip — never four chips', () => {
    expect(out.prompts.map((p) => p.text)).toEqual(['Why is memory unavailable?']);
    expect(out.prompts.length).toBe(1);
  });

  it('the reply is the approved frontend string (not raw note, not "source files directly")', () => {
    expect(out.reply.text).toBe(
      'Project Memory is unavailable, so no memory-based answer is available here.',
    );
    expect(out.reply.answeredFrom).toBe('graph');
    expect(out.reply.text).not.toContain('answered from source files directly');
    // never leaks the raw internal note
    expect(out.reply.text).not.toContain(graphStatusUnavailable.note);
  });

  it('carries no error/verdict semantics', () => {
    expect(out.reply.text).not.toMatch(VERDICT);
    expect(out.reply.text).not.toMatch(VALID_WORD);
    expect(out.reply.text).not.toMatch(/\berror\b/i);
  });
});

describe('memory composer — guard cleanliness sweep over EVERY composed string', () => {
  const axisValues = ['verified', 'malformed', 'unsupported', 'unknown'] as const;
  const consistency = ['current', 'stale', 'unknown'] as const;

  function everyMemoryString(): string[] {
    const texts: string[] = [];
    // available: sweep every axis + provider + file_count combination surface
    for (const integrity of axisValues) {
      for (const memory_policy of consistency) {
        for (const indexed_sources of consistency) {
          for (const provider of ['sanitized-snapshot', 'unavailable', '']) {
            for (const file_count of [0, 1, 2, 190, null] as (number | null)[]) {
              const out = compose(
                memoryState({ integrity, memory_policy, indexed_sources, provider, file_count }),
              );
              texts.push(out.reply.text, ...out.prompts.map((p) => p.answer?.text ?? ''));
            }
          }
        }
      }
    }
    // unavailable
    const un = compose({ context: 'memory', graph: graphStatusUnavailable as ApiGraphStatus });
    texts.push(un.reply.text, ...un.prompts.map((p) => p.answer?.text ?? ''));
    return texts;
  }

  const ALL = everyMemoryString();

  it('never renders a PASS/FAIL or valid/invalid verdict', () => {
    for (const t of ALL) {
      expect(t).not.toMatch(VERDICT);
      expect(t).not.toMatch(INVALID_AGAINST);
      expect(t).not.toMatch(VALID_WORD);
    }
  });

  it('never renders the literal "undefined" / "null" / "NaN"', () => {
    for (const t of ALL) {
      expect(t).not.toMatch(/\b(undefined|null|NaN)\b/);
    }
  });

  it('never claims related records, record similarity, audit, export-readiness or scientific truth', () => {
    for (const t of ALL) {
      expect(t).not.toMatch(/related records?/i);
      expect(t).not.toMatch(/similar records?|record similarity/i);
      expect(t).not.toMatch(/export[- ]read(y|iness)/i);
      expect(t).not.toMatch(/scientific(ally)? (true|correct|valid|sound)/i);
      // never claims a file was directly inspected/read
      expect(t).not.toMatch(/answered from source files directly/i);
    }
  });

  it('never leaks a machine-local / sensitive absolute path', () => {
    for (const t of ALL) {
      expect(t).not.toMatch(/\/Users\//);
      expect(t).not.toMatch(/\/home\//);
    }
  });
});

describe('count() sanity for the scope chip', () => {
  it('produces grammatical singular/plural without raw placeholders', () => {
    expect(count(1, 'project file')).toBe('1 project file');
    expect(count(2, 'project file')).toBe('2 project files');
    expect(count(0, 'project file')).toBe('0 project files');
  });
});
