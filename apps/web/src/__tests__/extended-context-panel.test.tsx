import { describe, it, expect, afterEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { ExtendedContextPanel, GROUP_COLLAPSE_THRESHOLD } from '../components/ExtendedContextPanel';
import { LABELS } from '../lib/labels';
import { api, ApiError } from '../lib/api';
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
    // Overridden per entry by the paging tests, which need the RENDERED text to say
    // which entry it is — a list of 300 identical literals cannot show that index 299
    // arrived.

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

  it('a companion that ACCOUNTS FOR NOTHING neither claims nor denies that content was lost', async () => {
    /*
     * ── THE THIRD EMPTY STATE, AND THE TWO FALSE CLAIMS IT REPLACES ───────────
     *
     * The first version rendered, in this exact state:
     *
     *     "This record holds an extended context companion with no entry this build
     *      can present. Nothing has been discarded — see the count above."
     *
     * Both halves were wrong at once. **"Nothing has been discarded" is not knowable
     * here** — a persisted document whose `entries` is not a list hydrates to exactly
     * this shape, and in that case the stored content really was dropped with no count
     * recording it. And **"see the count above" named a row that is not on screen**:
     * the `unreadable_entries` line is gated on `> 0`, so in this state the only count
     * above reads `0 entries on this record`. A scientist reviewing a corrupted import
     * was told, by the surface built to disclose loss, that no loss occurred.
     *
     * MEASURED REACHABILITY (and the reviewer's stated trigger was wrong, so this is
     * asserted rather than assumed): going through a SAVE cannot reach it —
     * `state_payload` answers `None` for an empty companion, so nothing persists and
     * the route reads back `present: false`. It is reachable from a persisted DOCUMENT
     * this build would not write, which is precisely the class §11's persisted-value
     * rule exists for. `test_extended_context_surface.py` pins both halves.
     */
    mount(
      body({
        entries: [],
        present: true,
        entry_count: 0,
        total: 0,
        matched: 0,
        returned: 0,
        unreadable_entries: 0,
        concept_count: 0,
        by_level: { '1': 0, '2': 0, '3': 0, '4': 0 },
      }),
    );
    await screen.findByText(/lists no entries/i);
    const text = document.body.textContent ?? '';
    // NEITHER FALSE CLAIM SURVIVES.
    expect(text).not.toMatch(/nothing has been discarded/i);
    expect(text).not.toMatch(/see the count above/i);
    // AND IT DOES NOT OVER-CORRECT INTO THE OPPOSITE ASSERTION either: the panel
    // cannot know that content WAS lost, so it must not say so.
    expect(text).not.toMatch(/was discarded|were discarded|content was lost/i);
    // What it does say: the observable facts, and what it cannot determine.
    expect(screen.getByText(/records none as unreadable/i)).toBeTruthy();
    expect(screen.getByText(/cannot say what it held/i)).toBeTruthy();
    // It is distinct from the ABSENT state, which is the common case.
    expect(screen.queryByText(LABELS.extendedContextEmpty)).toBeNull();
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
    await screen.findByText(/cannot read any of its 2 entries/i);
    expect(screen.queryByText(LABELS.extendedContextEmpty)).toBeNull();
    // COUNTED AND NEVER RENDERED — the reader is told the record holds more than
    // the list shows, and nothing is invented about what it holds.
    expect(screen.getByText(/2 entries this build cannot read/i)).toBeTruthy();
    /* THE NUMBER IS NAMED INLINE rather than by pointing at the neighbouring count
       row. That row IS rendered in this case — but a sentence that depends on a
       neighbour being present is a sentence that goes wrong when the neighbour's
       condition changes, which is exactly how the third case came to cite a row
       that is not on screen. */
    expect(document.body.textContent ?? '').not.toMatch(/see the count above/i);
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
    // …and none of that is inside the raw-entry disclosure, so a value never appears
    // without its provenance. (The shared `Disclosure` since the final review of
    // #279; this used to query a native `<details>`.)
    const rawBody = card.querySelector('.extctx-details .disclosure-body')!;
    expect(rawBody).not.toBeNull();
    expect(rawBody.contains(provenance)).toBe(false);
    expect(rawBody.contains(card.querySelector('.extctx-literal'))).toBe(false);
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
  it('is behind a CLOSED shared Disclosure and is not the scientist’s first reading', async () => {
    /*
     * THE DEFECT THIS REFUSES WAS SHIPPED ONCE, on the Activity panel, and fixed.
     * A `<pre>` of the entry as the primary view is developer-side JSON wearing a
     * product surface.
     *
     * INVERTED FROM "a closed native <details>" (final review of #279, P1): the raw
     * entry now sits in the shared `Disclosure`, like every other disclosure on the
     * record screen. The property is unchanged — closed by default, the JSON inside,
     * the human reading outside.
     */
    mount(body());
    await screen.findByText('Spec User String');
    const card = document.querySelector('.extctx-entry')!;
    expect(card.querySelector('details')).toBeNull();
    const trigger = within(card as HTMLElement).getByRole('button', {
      name: 'Everything This Entry Records',
    });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    const rawBody = card.querySelector('.extctx-details .disclosure-body') as HTMLElement;
    expect(rawBody.hidden).toBe(true);
    const pre = card.querySelector('pre.extctx-raw')!;
    expect(rawBody.contains(pre)).toBe(true);
    // And the human reading — concept, literal, source — is outside it.
    expect(rawBody.contains(card.querySelector('.extctx-literal'))).toBe(false);
    expect(rawBody.contains(card.querySelector('.extctx-concept'))).toBe(false);
    fireEvent.click(trigger);
    expect(pre).toBeVisible();
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

  /*
   * ── THE INVERTED TEST ───────────────────────────────────────────────────────
   *
   * ~~"asks the server for a larger page rather than filtering what it already
   * has"~~ — that test PINNED THE DEFECT. It asserted `second > first` on the
   * `limit` argument, which is exactly what growing `limit` and never sending
   * `offset` does, so it passed on a panel that could not reach past entry 199 of a
   * 300-entry record. The SUBJECT is kept — a "Show more" must ask the server rather
   * than filter what it already holds — and the assertion is corrected to the thing
   * that makes the content reachable.
   */
  it('pages by OFFSET, so every entry is reachable past the server clamp', async () => {
    /*
     * THE STUB CLAMPS EXACTLY AS THE SERVER DOES — `limit` capped at 200, `has_more`
     * computed from `total` — because that combination IS the defect. A stub that
     * honoured any `limit` would have let the old implementation pass, which is how
     * the defect survived its own test.
     *
     * Reproduced server-side first, over HTTP: `limit=250/300/1000` all answered
     * `limit=200, returned=200, has_more=true`, with the highest entry rendered
     * stuck at index 199.
     */
    const CLAMP = 200;
    const TOTAL = 300;
    const calls: { limit?: number; offset?: number }[] = [];
    vi.spyOn(api, 'getExtendedContext').mockImplementation(async (_id, options) => {
      calls.push({ limit: options?.limit, offset: options?.offset });
      const limit = Math.min(options?.limit ?? 50, CLAMP);
      const offset = options?.offset ?? 0;
      const slice = Array.from(
        { length: Math.max(0, Math.min(limit, TOTAL - offset)) },
        (_unused, i) => entry({ entry_id: `e${offset + i}`, raw_literal: `LIT-e${offset + i}` }),
      );
      return body({
        entries: slice,
        total: TOTAL,
        matched: TOTAL,
        entry_count: TOTAL,
        returned: slice.length,
        limit,
        offset,
        has_more: offset + slice.length < TOTAL,
      });
    });
    render(<ExtendedContextPanel experimentId="demo" collapsedByDefault={false} />);
    // 300 entries of ONE concept: a single concept group, CLOSED because the record
    // holds more than `GROUP_COLLAPSE_THRESHOLD` (since the grouping change). Its row
    // counts what is loaded, never a record total.
    await screen.findByRole('button', { name: /Spec User String\s*50 shown so far/ });

    // Six clicks at a 50-entry page walks the whole 300.
    for (let click = 0; click < 6; click += 1) {
      const more = screen.queryByRole('button', { name: 'Show more' });
      if (more === null) break;
      fireEvent.click(more);
      await waitFor(() => expect(calls.length).toBe(click + 2));
    }

    // EVERY REQUEST AFTER THE FIRST CARRIED AN OFFSET. That is the whole fix: the old
    // implementation sent none, ever.
    expect(calls.slice(1).every((c) => (c.offset ?? 0) > 0)).toBe(true);
    // …and it never asked for more than the server's own window, so the clamp is
    // never the thing bounding the read.
    expect(calls.every((c) => (c.limit ?? 0) <= CLAMP)).toBe(true);

    // THE LAST ENTRY IS REACHABLE — index 299, which the old panel could never reach.
    // One click opens its group (a closed group renders no cards); every entry is
    // then on screen.
    fireEvent.click(screen.getByRole('button', { name: /Spec User String\s*300 entries/ }));
    expect(await screen.findByText('LIT-e299')).toBeTruthy();
    expect(screen.getByText('LIT-e0')).toBeTruthy();
    expect(document.querySelectorAll('.extctx-entry')).toHaveLength(TOTAL);
    // …and the control is GONE rather than permanently offered.
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull();
  },
  // 15 s, not vitest's 5 s default (2026-09-23): this test renders 300 entries across
  // server-clamped pages, and each entry now carries a HelpTip and a run-label lookup.
  // Measured 2.36 s alone and 6.2 s inside a full parallel run — and, once grouped
  // with every card rendered hidden, a 15 s TIMEOUT in a loaded parallel run. A closed
  // group now renders no cards, so the pages append as one group row and the 300
  // cards render once, when the group is opened. It asserts REACHABILITY, not speed,
  // so the budget hides no defect.
  15_000);

  it('the control disappears at the end rather than staying permanently dead', async () => {
    // MUTATION-GUARDED against the specific symptom: `has_more` stayed true forever
    // because the clamp made every further request identical, so the button was
    // present on a panel that could not add a row.
    mount(body({ entries: [entry()], total: 1, entry_count: 1, returned: 1, has_more: false }));
    await screen.findByText('ffilter35');
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull();
  });

  it('a FAILED "Show more" discloses beside the list and never destroys it', async () => {
    /*
     * `CLAUDE.md` §11's 2026-09-10 rule, which this repository learned by destroying a
     * scientist's typed text with a failed background read. The entries on screen are
     * the reader's; a failed request for MORE of them is no reason to take them away.
     */
    let call = 0;
    vi.spyOn(api, 'getExtendedContext').mockImplementation(async () => {
      call += 1;
      if (call === 1) {
        return body({
          entries: [entry({ entry_id: 'kept', raw_literal: 'LIT-kept' })],
          total: 2,
          matched: 2,
          entry_count: 2,
          returned: 1,
          has_more: true,
        });
      }
      throw new ApiError('the read did not complete');
    });
    render(<ExtendedContextPanel experimentId="demo" collapsedByDefault={false} />);
    await screen.findByText('LIT-kept');
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));

    await screen.findByText(/could not be read just now/i);
    // THE LIST IS STILL THERE — no `BackendDown`, no blanked panel.
    expect(screen.getByText('LIT-kept')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
    // …and the count still describes the record, not what survived.
    expect(screen.getByText(/2 entries on this record/)).toBeTruthy();
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
    // With no label resolved (the runs read is not answered here), the run is named by
    // its id — never wrong, only less friendly. Split across elements since the final
    // review of #279, so the scope cell is read as a whole.
    const scope = [...cards[1].querySelectorAll('.extctx-provenance-pair')].find(
      (pair) => pair.querySelector('dt')?.textContent === 'Scope',
    )!;
    expect(scope.querySelector('dd')?.textContent).toBe('On run run-1');
  });

  it('MUTATION-GUARDED (final review of #279, P1): a run reads by its LABEL, with the id one hover away', async () => {
    vi.spyOn(api, 'listRuns').mockResolvedValue({
      runs: [
        { id: 'run-1', label: 'Legacy 3 · 02 · SYN2 · base' },
        { id: 'run-2', label: 'Legacy 1' },
        { id: 'run-3', label: 'Legacy 1' },
      ],
    } as never);
    mount(
      body({
        entries: [
          entry({ entry_id: 'a', scope: 'run', run_id: 'run-1' }),
          entry({ entry_id: 'b', scope: 'run', run_id: 'run-2' }),
          entry({ entry_id: 'c', scope: 'run', run_id: 'run-9' }),
        ],
      }),
    );
    const run = await screen.findByText('Legacy 3 · 02 · SYN2 · base');
    expect(run).toHaveAttribute('title', 'run-1');
    const cards = document.querySelectorAll('.extctx-entry');
    // A label two runs share is disambiguated by the id beside it.
    expect(cards[1].textContent).toContain('Legacy 1');
    expect(cards[1].querySelector('.extctx-run-id')?.textContent).toContain('run-2');
    // A run the label read did not cover is named by its id.
    expect(within(cards[2] as HTMLElement).getByText('run-9')).toBeTruthy();
    // The raw id never leads the first card's scope line.
    expect(cards[0].querySelector('.extctx-run-id')).toBeNull();
  });

  it('never reads the runs when no shown entry is run-scoped', async () => {
    const spy = vi.spyOn(api, 'listRuns');
    mount(body());
    await screen.findByText('Spec User String');
    expect(spy).not.toHaveBeenCalled();
  });
});

/* ── what a scientist reads first (final review of #279, P1) ────────────── */

describe('the default reading is the scientist’s words, and nothing is lost', () => {
  it('a concept reads as its humanized key; the key itself is in the title and one `?` away', async () => {
    mount(body({ entries: [entry({ concept: 'legacy_run_or_file_number' })] }));
    // The humanized name heads the concept GROUP (since the grouping change); the
    // card beneath it leads with the literal, and keeps the key in its `?`.
    const heading = await screen.findByText('Legacy Run Or File Number');
    expect(heading.closest('.extctx-group')).not.toBeNull();
    expect(heading).toHaveAttribute('title', 'legacy_run_or_file_number');
    const card = document.querySelector('.extctx-entry') as HTMLElement;
    const tip = within(card).getByRole('button', { name: 'About This Entry' });
    fireEvent.click(tip);
    expect(within(card).getByText('legacy_run_or_file_number', { selector: 'code' })).toBeVisible();
  });

  it('the registry’s reason is behind the entry’s `?`, verbatim, not in the default reading', async () => {
    const REASON = 'REFUSED ON PURPOSE, AND THIS IS THE ONE ENTRY THAT WOULD BE HARMFUL TO FIX.';
    mount(body({ entries: [entry({ reason: REASON })] }));
    await screen.findByText('Spec User String');
    const card = document.querySelector('.extctx-entry') as HTMLElement;
    const reason = within(card).getByText(REASON);
    expect(reason).not.toBeVisible();
    fireEvent.click(within(card).getByRole('button', { name: 'About This Entry' }));
    expect(reason).toBeVisible();
  });

  it('a normalisation rule id is one `?` away inside the SAME pair, not in the visible label', async () => {
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
    await screen.findByText('35 mm');
    const pair = screen.getByText('35 mm').closest('.extctx-provenance-pair') as HTMLElement;
    const rule = within(pair).getByText('bl15.filter_index_v1');
    expect(rule).not.toBeVisible();
    fireEvent.click(within(pair).getByRole('button', { name: 'Which Rule Read This' }));
    expect(rule).toBeVisible();
  });

  it('the intro is ONE visible line that still says it is not official; the server’s sentence is its `?`', async () => {
    mount(body());
    const line = await screen.findByText(/Not an official ISAAC record, and nothing here is a field value\./);
    expect(line).toBeVisible();
    const full = screen.getByText(NOT_OFFICIAL);
    expect(full).not.toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'About Extended Context' }));
    expect(full).toBeVisible();
  });
});

/* ── summary first, then drill down (final review of #279) ──────────────── */

describe('a large companion reads as concept groups with counts, not a flat dump', () => {
  /* The GROUP's own row — not the per-entry "Everything This Entry Records"
     disclosures nested inside it, which share the `Disclosure` classes. */
  const GROUP_TRIGGER = '.extctx-group-disclosure > .disclosure-heading > .disclosure-trigger';
  const GROUP_SUMMARY = `${GROUP_TRIGGER} > .disclosure-summary`;
  /** Rendered and not inside any `hidden` subtree. */
  const isShown = (el: Element) => el.closest('[hidden]') === null;

  function manyEntries(): ApiExtendedContextEntry[] {
    const five = Array.from({ length: 5 }, (_, i) =>
      entry({ entry_id: `u${i}`, concept: 'spec_user_string', raw_literal: `user-${i}`, locator: `line ${i}` }),
    );
    const two = Array.from({ length: 2 }, (_, i) =>
      entry({ entry_id: `f${i}`, concept: 'spec_file_declaration', raw_literal: `file-${i}`, locator: `row ${i}` }),
    );
    return [five[0], two[0], ...five.slice(1), two[1]];
  }

  it(`MUTATION-GUARDED: above ${GROUP_COLLAPSE_THRESHOLD} entries every group is CLOSED, and its concept and count are visible`, async () => {
    mount(body({ entries: manyEntries(), concept_count: 2 }));
    const user = await screen.findByRole('button', { name: /Spec User String\s*5 entries/ });
    const file = screen.getByRole('button', { name: /Spec File Declaration\s*2 entries/ });
    expect(user).toHaveAttribute('aria-expanded', 'false');
    expect(file).toHaveAttribute('aria-expanded', 'false');
    // Groups in the order each concept first appears.
    const headings = [...document.querySelectorAll(GROUP_SUMMARY)].map((n) => n.textContent);
    expect(headings).toEqual(['Spec User String', 'Spec File Declaration']);
    // No card is rendered until a group is opened — the summary IS the first reading,
    // and a closed group costs nothing to render however large it is …
    expect(document.querySelectorAll('.extctx-entry')).toHaveLength(0);
    // … and one click reaches every entry of a group.
    fireEvent.click(user);
    expect(document.querySelectorAll('.extctx-entry')).toHaveLength(5);
  });

  it('opening a group reveals EXACTLY that group’s entries, each with its provenance visible', async () => {
    mount(body({ entries: manyEntries(), concept_count: 2 }));
    const file = await screen.findByRole('button', { name: /Spec File Declaration\s*2 entries/ });
    fireEvent.click(file);
    const visible = [...document.querySelectorAll('.extctx-entry')].filter(isShown);
    // Exactly the opened group's cards exist — the other group rendered none.
    expect(document.querySelectorAll('.extctx-entry')).toHaveLength(visible.length);
    expect(visible.map((card) => card.querySelector('.extctx-literal')?.textContent)).toEqual([
      'file-0',
      'file-1',
    ]);
    for (const card of visible) {
      const provenance = card.querySelector('.extctx-provenance') as HTMLElement;
      expect(provenance).toBeVisible();
      expect(provenance.textContent).toContain('synthetic/mini/01_SYN1.0001');
      expect(provenance.textContent).toMatch(/row \d/);
    }
  });

  it(`at ${GROUP_COLLAPSE_THRESHOLD} entries or fewer the groups stay OPEN, so a small companion reads at a glance`, async () => {
    const six = manyEntries().slice(0, GROUP_COLLAPSE_THRESHOLD);
    mount(body({ entries: six, concept_count: 2 }));
    await screen.findByText('Spec User String');
    for (const trigger of document.querySelectorAll(GROUP_TRIGGER)) {
      expect(trigger).toHaveAttribute('aria-expanded', 'true');
    }
    expect(document.querySelectorAll('.extctx-entry')).toHaveLength(GROUP_COLLAPSE_THRESHOLD);
    for (const card of document.querySelectorAll('.extctx-entry')) expect(card).toBeVisible();
  });

  it('a group the reader opened stays open when "Show more" appends a page', async () => {
    let call = 0;
    vi.spyOn(api, 'getExtendedContext').mockImplementation(async () => {
      call += 1;
      const page1 = manyEntries();
      const page2 = [entry({ entry_id: 'u9', concept: 'spec_user_string', raw_literal: 'user-9' })];
      return body({
        entries: call === 1 ? page1 : page2,
        total: 8,
        matched: 8,
        returned: call === 1 ? 7 : 1,
        offset: call === 1 ? 0 : 7,
        has_more: call === 1,
        concept_count: 2,
      });
    });
    render(<ExtendedContextPanel experimentId="demo" collapsedByDefault={false} />);
    fireEvent.click(await screen.findByRole('button', { name: /Spec User String\s*5 shown so far/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));
    const user = await screen.findByRole('button', { name: /Spec User String\s*6 entries/ });
    expect(user).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('user-9')).toBeVisible();
  });

  it('while the list is PARTIAL a group counts what is loaded, never claiming a record total', async () => {
    mount(
      body({
        entries: manyEntries(),
        total: 40,
        matched: 40,
        has_more: true,
        concept_count: 2,
      }),
    );
    expect(await screen.findByRole('button', { name: /Spec User String\s*5 shown so far/ })).toBeTruthy();
    expect(screen.queryByText('5 entries')).toBeNull();
  });
});

describe('the collapsed panel really hides its body (final review of #279)', () => {
  it('MUTATION-GUARDED: `.extctx-body[hidden]` restores display:none over the body’s own `display: flex`', () => {
    /*
     * jsdom applies no stylesheet, so the `hidden`-attribute tests above could never
     * see this: `.extctx-body { display: flex }` beat the user-agent `[hidden]` rule
     * and the "collapsed" panel rendered all 38 cards of an imported record under a
     * header reading aria-expanded="false".
     */
    const css = readFileSync(join(__dirname, '../components/extendedContext.css'), 'utf8').replace(
      /\/\*[\s\S]*?\*\//g,
      '',
    );
    expect(css).toMatch(/\.extctx-body\s*\{[^}]*display:\s*flex/);
    expect(css).toMatch(/\.extctx-body\[hidden\]\s*\{[^}]*display:\s*none/);
  });
});

describe('a nested disclosure shows its OWN state (final review of #279)', () => {
  it('MUTATION-GUARDED: the chevron turns only for its own open disclosure, never an ancestor’s', () => {
    /*
     * A concept group holds one "Everything This Entry Records" disclosure per card.
     * The shared rule used a DESCENDANT selector, so every closed inner row showed an
     * open chevron inside an open group — measured in a browser on the imported
     * record. Child combinators bind the chevron to its own trigger.
     */
    const css = readFileSync(join(__dirname, '../components/disclosure.css'), 'utf8').replace(
      /\/\*[\s\S]*?\*\//g,
      '',
    );
    const rotate = /([^{}]+)\{[^}]*transform:\s*rotate\(90deg\)[^}]*\}/.exec(css);
    expect(rotate).not.toBeNull();
    const selectors = rotate![1].split(',').map((sel) => sel.trim());
    expect(selectors.length).toBeGreaterThan(0);
    for (const sel of selectors) {
      expect(sel).toMatch(/^\.disclosure\.is-open\s*>/);
      expect(sel).toMatch(/>\s*\.disclosure-chevron$/);
    }
  });
});
