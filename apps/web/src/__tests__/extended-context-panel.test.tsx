import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import { ExtendedContextPanel } from '../components/ExtendedContextPanel';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import type {
  ApiExtendedContextEntry,
  ApiExtendedContextResponse,
} from '../lib/types';

/**
 * `CTX-004` — THE EXTENDED CONTEXT PANEL, tested against the ways it could be WRONG.
 *
 * Each case names the defect it refuses rather than the code it exercises. Three of
 * them are defect classes this repository has shipped once and recorded: a count
 * taken from a fetched array, raw JSON as a scientist's primary reading, and a
 * normal absence rendered as an error.
 *
 * The fourth is specific to this surface and is the one that matters most. Every
 * entry here LOOKS like a field value — it carries a concept, a literal, a unit and
 * an `official_path` — and it is not one. A panel that let a reader believe
 * otherwise would put unvalidated text where a scientist expects a schema-checked
 * value, which is precisely what `DEC-41` level 4 is defined as not being.
 */

afterEach(() => {
  vi.restoreAllMocks();
});

function entry(over: Partial<ApiExtendedContextEntry> = {}): ApiExtendedContextEntry {
  return {
    entry_id: 'ctx_1',
    concept: 'spec_user_string',
    raw_literal: 'ffilter35',
    source: 'synthetic/mini/01_SYN1.0001',
    locator: 'line 3 header #C',
    placement_level: 4,
    placement_name: 'ISAAC Extended Context',
    scope: 'experiment',
    run_id: null,
    source_type: 'unknown',
    normalized_value: null,
    unit: null,
    normalization_rule: null,
    determinism: 'read',
    profile_id: null,
    profile_version: null,
    reading_scope: null,
    parser_id: null,
    timestamp_utc: null,
    official_path: null,
    reason: '',
    unresolved_questions: [],
    is_official_field_value: false,
    ...over,
  };
}

const NOT_OFFICIAL =
  'This is an ISAAC Extended Context companion, not an official ISAAC record and ' +
  'not part of one.';

function body(over: Partial<ApiExtendedContextResponse> = {}): ApiExtendedContextResponse {
  const entries = over.entries ?? [entry()];
  return {
    entries,
    total: entries.length,
    matched: entries.length,
    returned: entries.length,
    limit: 50,
    offset: 0,
    has_more: false,
    not_official: NOT_OFFICIAL,
    placement_hierarchy: { '4': 'ISAAC Extended Context' },
    present: true,
    entry_count: entries.length,
    unreadable_entries: 0,
    concept_count: 1,
    run_count: 0,
    by_level: { '1': 0, '2': 0, '3': 0, '4': entries.length },
    generated_utc: '2099-01-01T00:00:00Z',
    artifact_kind: 'isaac_extended_context',
    artifact_version: '1',
    open_domain_questions: [],
    ...over,
  };
}

function mount(payload: ApiExtendedContextResponse) {
  const spy = vi.spyOn(api, 'getExtendedContext').mockResolvedValue(payload);
  render(<ExtendedContextPanel experimentId="demo" collapsedByDefault={false} />);
  return spy;
}

/* ── the empty state, which is the COMMON case ──────────────────────────── */

describe('an absent companion', () => {
  it('states a fact about the record and never reads as an error or a missing file', async () => {
    mount(
      body({
        entries: [],
        present: false,
        entry_count: 0,
        total: 0,
        matched: 0,
        returned: 0,
        concept_count: 0,
        by_level: { '1': 0, '2': 0, '3': 0, '4': 0 },
      }),
    );
    expect(await screen.findByText(LABELS.extendedContextEmpty)).toBeTruthy();
    // NO ERROR AFFORDANCE OF ANY KIND. Extended context arrives only through
    // historical import, so almost every record has none; an alert, a retry or a
    // "missing artifact" would tell nearly every reader something went wrong.
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('button', { name: /retry|reload/i })).toBeNull();
    expect(document.body.textContent).not.toMatch(/missing|error|failed|unavailable/i);
  });

  it('is NOT the same state as a companion whose entries cannot be read', async () => {
    /*
     * THE TWO WOULD BE ONE IF THE PANEL BRANCHED ON `entry_count === 0`, and
     * collapsing them is exactly what `hydrate`'s "never discards" promise exists to
     * prevent: a companion that holds something unreadable is not a companion that
     * holds nothing, and telling a scientist "this record states no extended
     * context" there would be false.
     */
    mount(
      body({
        entries: [],
        present: true,
        entry_count: 0,
        total: 0,
        matched: 0,
        returned: 0,
        unreadable_entries: 2,
        concept_count: 0,
      }),
    );
    await screen.findByText(/no entry this build can present/i);
    expect(screen.queryByText(LABELS.extendedContextEmpty)).toBeNull();
    // COUNTED AND NEVER RENDERED — the reader is told the record holds more than
    // the list shows, and nothing is invented about what it holds.
    expect(screen.getByText(/2 entries this build cannot read/i)).toBeTruthy();
  });
});

/* ── the claim this surface must never get wrong ────────────────────────── */

describe('nothing here reads as an official field value', () => {
  it("renders the server's own denial verbatim rather than a paraphrase", async () => {
    mount(body());
    expect(await screen.findByText(NOT_OFFICIAL)).toBeTruthy();
  });

  it('asserts no validity, no pass/fail and no completion anywhere on the panel', async () => {
    /*
     * A WORD-LEVEL BAN, because the failure here is a word rather than a control.
     * "Valid", "verified" or "complete" beside a level-4 literal would assert the
     * one thing the artifact is defined as not carrying, and no test that only
     * checked for a green badge would catch prose.
     */
    mount(body({ entries: [entry(), entry({ entry_id: 'ctx_2' })] }));
    await screen.findAllByText('spec_user_string');
    const text = document.body.textContent ?? '';
    for (const banned of [
      /\bvalid\b/i,
      /\binvalid\b/i,
      /\bverified\b/i,
      /\bpass\b/i,
      /\bfail\b/i,
      /\bcomplete\b/i,
      /\bexportable\b/i,
    ]) {
      // `not_official` is the server's own sentence and legitimately uses some of
      // these words to DENY them, so it is removed before the sweep — the claim
      // being tested is about the panel's own copy.
      const own = text.replace(NOT_OFFICIAL, '');
      expect(own, `panel copy asserts ${banned}`).not.toMatch(banned);
    }
  });

  it('never presents official_path as a field the entry fills', async () => {
    /*
     * THE SUBTLEST WAY TO GET THIS WRONG. `official_path` names where the REGISTRY
     * says the schema's home for the CONCEPT is, and an entry at level 4 is
     * precisely one whose information is not there. Rendering it as a labelled
     * field beside the literal would read as "this literal is the value at this
     * path", which is the inversion the whole artifact exists to prevent.
     */
    mount(body({ entries: [entry({ official_path: 'system.technique' })] }));
    await screen.findByText('spec_user_string');
    // It is reachable in the raw disclosure (nothing is hidden), and it is NOT a
    // labelled row beside the literal.
    const cards = document.querySelectorAll('.extctx-entry');
    expect(cards).toHaveLength(1);
    const provenance = cards[0].querySelector('.extctx-provenance');
    expect(provenance?.textContent ?? '').not.toContain('system.technique');
  });
});

/* ── provenance, and the literal ────────────────────────────────────────── */

describe('every value is shown with where it came from', () => {
  it('renders the literal verbatim, with its source and locator, outside any disclosure', async () => {
    mount(
      body({
        entries: [
          entry({ raw_literal: '  ffilter35  ', source: 'a/b.0001', locator: 'line 9' }),
        ],
      }),
    );
    await screen.findByText('spec_user_string');
    const card = document.querySelector('.extctx-entry')!;
    // The literal is NOT trimmed, normalised or shortened — what the source said.
    expect(card.querySelector('.extctx-literal')?.textContent).toBe('  ffilter35  ');
    const provenance = card.querySelector('.extctx-provenance')!;
    expect(provenance.textContent).toContain('a/b.0001');
    expect(provenance.textContent).toContain('line 9');
    // …and none of that is inside the `<details>`, so a value never appears
    // without its provenance.
    expect(card.querySelector('details')?.contains(provenance)).toBe(false);
  });

  it('shows a normalized reading ONLY beside the named rule that produced it', async () => {
    /*
     * A CLEANED READING WHOSE DERIVATION NOBODY CAN NAME IS A GUESS (§5). The
     * server requires `normalization_rule` whenever `determinism` is not `read`, so
     * a value arriving without one means something unexpected happened upstream —
     * and the honest response is to show the literal alone, which is never wrong.
     */
    mount(
      body({
        entries: [
          entry({
            normalized_value: 35,
            unit: 'mm',
            normalization_rule: 'bl15.filter_index_v1',
            determinism: 'normalized',
          }),
        ],
      }),
    );
    await screen.findByText('spec_user_string');
    /* SCOPED TO THE PROVENANCE LIST, not to the document. The raw disclosure
       carries the whole entry verbatim, so a document-wide query for the rule name
       matches twice — and the claim under test is that the rule appears BESIDE the
       reading a scientist sees, not merely somewhere in the JSON. */
    const provenance = document.querySelector('.extctx-provenance') as HTMLElement;
    expect(within(provenance).getByText(/bl15\.filter_index_v1/)).toBeTruthy();
    expect(within(provenance).getByText('35 mm')).toBeTruthy();
  });

  it('withholds a normalized reading that arrives with no rule, and still shows the literal', async () => {
    // MUTATION-GUARDED: dropping the `normalization_rule !== null` half of the
    // condition makes this red, and it is the half that keeps an unexplained
    // derivation off the screen.
    mount(
      body({
        entries: [entry({ normalized_value: 35, unit: 'mm', normalization_rule: null })],
      }),
    );
    await screen.findByText('spec_user_string');
    expect(screen.queryByText(/35 mm/)).toBeNull();
    expect(screen.getByText('ffilter35')).toBeTruthy();
  });
});

/* ── the raw entry is a disclosure, not the default ─────────────────────── */

describe('raw JSON', () => {
  it('is behind a closed native <details> and is not the scientist’s first reading', async () => {
    /*
     * THE DEFECT THIS REFUSES WAS SHIPPED ONCE, on the Activity panel, and fixed.
     * A `<pre>` of the entry as the primary view is developer-side JSON wearing a
     * product surface.
     */
    mount(body());
    await screen.findByText('spec_user_string');
    const card = document.querySelector('.extctx-entry')!;
    const details = card.querySelector('details')!;
    expect(details.hasAttribute('open')).toBe(false);
    const pre = card.querySelector('pre.extctx-raw')!;
    expect(details.contains(pre)).toBe(true);
    // And the human reading — concept, literal, source — is outside it.
    expect(details.contains(card.querySelector('.extctx-literal'))).toBe(false);
  });
});

/* ── counts come from the server, never from the array ──────────────────── */

describe('every count describes the record', () => {
  it('reports the server’s total on the header, not the number of rendered rows', async () => {
    /*
     * `CLAUDE.md` §11's 2026-09-02 rule. A header built on `entries.length` would
     * report a 120-entry record as a 50-entry one — the window bounds what is
     * FETCHED, never what is CLAIMED.
     */
    mount(
      body({
        entries: [entry(), entry({ entry_id: 'ctx_2' })],
        total: 120,
        matched: 120,
        entry_count: 120,
        returned: 2,
        has_more: true,
      }),
    );
    const header = await screen.findByRole('button', {
      name: new RegExp(LABELS.extendedContextHeading),
    });
    expect(header.textContent).toContain('120 entries');
    expect(header.textContent).not.toContain('2 entries');
    expect(screen.getByText(/120 entries on this record/)).toBeTruthy();
    expect(screen.getByText(/Showing the first 2/)).toBeTruthy();
    expect(screen.getByText(/2 of 120 shown/)).toBeTruthy();
  });

  it('renders no count at all until the read answers, rather than a zero it has not established', async () => {
    let resolve!: (v: ApiExtendedContextResponse) => void;
    vi.spyOn(api, 'getExtendedContext').mockReturnValue(
      new Promise<ApiExtendedContextResponse>((r) => {
        resolve = r;
      }),
    );
    render(<ExtendedContextPanel experimentId="demo" collapsedByDefault={false} />);
    const header = screen.getByRole('button', {
      name: new RegExp(LABELS.extendedContextHeading),
    });
    /* A collapsed header with no count is the honest state of a list nobody has
       finished reading; a `0` would be a claim about the record.

       ASSERTED OVER THE `.fg-summary` SLOT, not over the header's whole text: the
       sublabel is the literal `level 4`, so a header-wide "contains no digit" check
       was passing for the wrong reason before the read resolved and would have
       failed for the wrong reason after it. */
    const summary = () => header.querySelector('.fg-summary')?.textContent ?? '';
    expect(summary()).toBe('');
    resolve(body());
    await waitFor(() => expect(summary()).toBe('1 entry'));
  });

  it('asks the server for a larger page rather than filtering what it already has', async () => {
    const spy = mount(
      body({ entries: [entry()], total: 120, entry_count: 120, returned: 1, has_more: true }),
    );
    await screen.findByText('spec_user_string');
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    // The second request asks for a bigger window — it does not re-request the same
    // page and it does not page client-side over rows it never received.
    const first = spy.mock.calls[0][1]?.limit ?? 0;
    const second = spy.mock.calls[1][1]?.limit ?? 0;
    expect(second).toBeGreaterThan(first);
  });
});

/* ── the accordion shell ────────────────────────────────────────────────── */

describe('the collapsed mount', () => {
  it('is a real heading button with the accordion contract, not a div with an onClick', async () => {
    vi.spyOn(api, 'getExtendedContext').mockResolvedValue(body());
    render(<ExtendedContextPanel experimentId="demo" />);
    const header = screen.getByRole('button', {
      name: new RegExp(LABELS.extendedContextHeading),
    });
    expect(header.getAttribute('aria-expanded')).toBe('false');
    expect(header.getAttribute('aria-controls')).toBeTruthy();
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading.contains(header)).toBe(true);
    fireEvent.click(header);
    expect(header.getAttribute('aria-expanded')).toBe('true');
    await screen.findByText('spec_user_string');
  });

  it('reads the record even while collapsed, so the header count is real', async () => {
    // The count on a collapsed header is only honest if the read happened. If the
    // fetch were deferred to the first expand, the header would have to either show
    // nothing forever or show a number nobody had established.
    const spy = vi.spyOn(api, 'getExtendedContext').mockResolvedValue(body());
    render(<ExtendedContextPanel experimentId="demo" />);
    await waitFor(() => expect(spy).toHaveBeenCalled());
  });
});

/* ── the run scope line ─────────────────────────────────────────────────── */

describe('scope', () => {
  it('distinguishes a run-scoped entry from one the run inherits', async () => {
    /*
     * The inheritance must stay VISIBLE. `applying_to_run` deliberately returns both
     * kinds, and a panel that rendered them identically would make a beamtime-wide
     * reading look as though it had been taken on this measurement — the lie
     * `bl15.reconstruct`'s shared-context handling exists to avoid.
     */
    mount(
      body({
        entries: [
          entry({ entry_id: 'a' }),
          entry({ entry_id: 'b', scope: 'run', run_id: 'run-1' }),
        ],
        concept_count: 1,
      }),
    );
    await screen.findAllByText('spec_user_string');
    const cards = document.querySelectorAll('.extctx-entry');
    expect(within(cards[0] as HTMLElement).getByText('On the record')).toBeTruthy();
    expect(within(cards[1] as HTMLElement).getByText('On run run-1')).toBeTruthy();
  });
});
