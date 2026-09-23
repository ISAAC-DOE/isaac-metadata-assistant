/*
 * HISTORICAL IMPORT STAGE PIECES — owner QA H1, 2026-09-22.
 *
 * The session became six stages with one in focus; `historical-import.test.tsx`
 * pins the flow and `bl15-import-review.test.tsx` pins the corpus review's
 * invariants. THIS file pins the pieces the archive semantics added, each against
 * the requirement it answers:
 *
 *   §1  conflicts: source by source, four distinct layers, a suggestion that says
 *       it is not authoritative, and NO control for two acquisitions sharing a
 *       legacy number (the "Run 32" case) — the server forbids it
 *   §2  recording a resolution: the three scopes, and `If-Match` exactly where a
 *       rule is stored on a record
 *   §3  temperature: `Not Recorded`, or the source's own words — never a number
 *   §4  Data Quality Notes: the scientist's label, verbatim, never a QC verdict
 *   §5  conventions and operators: which convention, at what scope — people as
 *       provenance only
 *   §6  reading rules: `Unattributed`, and a suggestion adopted only explicitly
 *   §7  HERFD signal: a suggestion shown as Suggested, dual channels both visible
 *   §8  the stage helpers: statuses from the server, never inferred agreement
 *
 * Every payload is hand-built, typed against the client's own interfaces, and
 * unmistakably fake (`ZZ` samples, `FAKE` paths).
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { CONFLICTS_SHOWN_PER_KIND, ImportConflicts, groupRuleChoices } from '../components/ImportConflicts';
import { CorpusReadOverview } from '../components/ImportCorpusReview';
import { ImportRules, SignalSelection } from '../components/ImportRules';
import { ImportCandidateRow } from '../components/ImportCandidateRow';
import { api } from '../lib/api';
import { IMPORT_STAGE_COPY as C } from '../lib/historicalImportContent';
import {
  candidateBucket,
  conflictViews,
  defaultStage,
  signalState,
  summaryItems,
  wouldNotSend,
  type ConflictView,
} from '../lib/importStages';
import { normalizedText, type Bl15CorpusReview } from '../lib/bl15Review';
import type {
  ApiConventionRule,
  ApiImportCandidate,
  ApiImportProfile,
  ApiImportRulesView,
  ApiImportSession,
  ApiImportSignalSelection,
  ApiImportUnitRow,
} from '../lib/types';

const DEST = {
  rows: [{ id: '01RECORDZZ000000000000001', title: 'A fictional ZZ campaign' }],
  failed: false,
  reload: async () => {},
};

/** An `onAct` that simply runs the act, as the screen's own does. */
const runAct = async (_name: string, run: () => Promise<unknown>) => {
  await run();
};

afterEach(() => {
  vi.restoreAllMocks();
});

const reading = (value: string, role: string, path: string, locator: string) => ({
  value,
  role,
  roleMeaning: null,
  sources: [{ path, locator }],
  sourceType: null,
});

function view(overrides: Partial<ConflictView> = {}): ConflictView {
  return {
    key: 'cf-1',
    kind: 'structural',
    topic: 'internal_declaration_vs_filename',
    subject: '07_03_ZZ3_base_after1500Cycling_filter20_800mV',
    explanation: 'A FAKE server explanation of this kind of disagreement.',
    readings: [
      reading('07_03_ZZ3_base_after1400Cycling_filter20_800mV', 'human_label', 'FAKE/07.dat', 'filename'),
      reading('07_03_ZZ3_base_after1500Cycling_filter20_800mV', 'instrument_header', 'FAKE/07.dat', '#F'),
    ],
    distinct: ['after1400Cycling', 'after1500Cycling'],
    recommendation: null,
    resolution: null,
    target: { conflict_id: 'cf-1' },
    resolvable: true,
    forbidden: false,
    stem: '07_03_ZZ3_base_after1500Cycling_filter20_800mV',
    groupToken: '03',
    ...overrides,
  };
}

function renderConflicts(conflicts: ConflictView[]) {
  return render(
    <MemoryRouter>
      <ImportConflicts conflicts={conflicts} importId="IMPZZ" busy={null} onAct={runAct} destinations={DEST} />
    </MemoryRouter>,
  );
}

/* ── §1 conflicts ────────────────────────────────────────────────────────── */

describe('§1 · a conflict is shown source by source, in four distinct layers', () => {
  it('names each source by the kind of claim it makes and shows the token that differs', () => {
    const { container } = renderConflicts([view()]);
    const line = container.querySelector('.hi-conflict-line')!;
    const readings = [...line.querySelectorAll('li')].map((li) => li.textContent?.replace(/\s+/g, ' ').trim());
    expect(readings).toEqual(['Filename after1400Cycling', 'Header after1500Cycling']);
    // The state is icon + word, and nothing is chosen.
    const chip = container.querySelector('.hi-conflict .semantic-status')!;
    expect(chip.textContent).toContain(C.stateLabels.conflict);
    expect(chip.querySelector('svg')).not.toBeNull();
    expect(container.querySelector('.hi-conflict-state')?.textContent).toBe(C.conflicts.noValue);
  });

  it('keeps the four layers separate and labelled', () => {
    const { container } = renderConflicts([view()]);
    const titles = [...container.querySelectorAll('.hi-layer-title')].map((h) =>
      (h.firstChild?.textContent ?? '').trim(),
    );
    expect(titles).toEqual([
      C.layers.sourceFact,
      C.layers.normalized,
      C.layers.suggested,
      C.layers.confirmed,
    ]);
    // The raw source fact keeps its full literal and its locator.
    const facts = container.querySelector('.hi-layer-facts')!.textContent ?? '';
    expect(facts).toContain('07_03_ZZ3_base_after1400Cycling_filter20_800mV');
    expect(facts).toContain('FAKE/07.dat · #F');
  });

  it('shows a suggestion as NOT authoritative, with evidence that does not count marked as such', () => {
    const { container } = renderConflicts([
      view({
        recommendation: {
          status: 'suggested',
          value: '07_03_ZZ3_base_after1500Cycling_filter20_800mV',
          why: 'A FAKE reason the evidence points one way.',
          supports: [
            { sentence: 'An independent FAKE record agrees.', counts: true },
            { sentence: 'The same person wrote this FAKE note.', counts: false },
          ],
          authority: 'suggestion',
        } as never,
      }),
    ]);
    const layer = container.querySelector('.hi-layer-suggested')!;
    expect(layer.querySelector('.hi-layer-flag')?.textContent).toBe(C.layers.nonAuthoritative);
    expect(layer.textContent).toContain('A FAKE reason the evidence points one way.');
    const supports = [...layer.querySelectorAll('.hi-layer-supports li')];
    expect(supports.map((li) => li.className)).toEqual(['', 'is-not-counted']);
    // A suggestion is not a resolution: the confirmed layer still says nothing was chosen,
    // and the row still reads as an open conflict.
    expect(container.querySelector('.hi-conflict-state')?.textContent).toBe(C.conflicts.noValue);
  });

  it('MUTATION-GUARDED: two acquisitions sharing a legacy number get NO resolution control', () => {
    /**
     * MUTATION: dropping `conflict.forbidden ?` from the confirmed layer's branch
     * renders the resolve form here — RED on the radio assertion.
     */
    const { container } = renderConflicts([
      view({
        key: 'cf-32',
        topic: 'duplicate_legacy_number',
        subject: 'legacy 32',
        forbidden: true,
        recommendation: { status: 'forbidden', value: null, why: 'Nobody can say.', supports: [], authority: 'none' } as never,
      }),
    ]);
    const row = container.querySelector('.hi-conflict')!;
    expect(within(row as HTMLElement).queryAllByRole('radio', { hidden: true })).toEqual([]);
    expect(within(row as HTMLElement).queryByRole('button', { name: C.resolve.submit, hidden: true })).toBeNull();
    expect(row.textContent).toContain(C.resolve.forbidden);
  });

  it('keeps the explanation visible once per kind, never inside the closed review', () => {
    const { container } = renderConflicts([view(), view({ key: 'cf-2', subject: 'another FAKE stem' })]);
    const explanation = 'A FAKE server explanation of this kind of disagreement.';
    const shown = [...container.querySelectorAll('.hi-conflict-explanation')].filter(
      (p) => p.textContent === explanation,
    );
    expect(shown).toHaveLength(1);
    expect(shown[0].closest('.disclosure-body')).toBeNull();
  });
});

/* ── §2 recording a resolution ───────────────────────────────────────────── */

describe('§2 · recording a resolution chooses between readings, at a scope the reader picks', () => {
  function openReview(container: HTMLElement) {
    fireEvent.click(within(container).getByRole('button', { name: new RegExp(C.conflicts.review) }));
  }

  it('offers exactly the three scopes, in the owner’s words', () => {
    const { container } = renderConflicts([view()]);
    openReview(container);
    for (const label of Object.values(C.scopeOptions)) {
      expect(screen.getByRole('radio', { name: label })).toBeTruthy();
    }
  });

  it('"Apply only here" records against this import, with NO If-Match', async () => {
    const record = vi.spyOn(api, 'recordImportRule').mockResolvedValue({} as never);
    const getExperiment = vi.spyOn(api, 'getExperiment');
    const { container } = renderConflicts([view()]);
    openReview(container);
    fireEvent.click(screen.getByRole('radio', { name: /after1500Cycling/ }));
    fireEvent.click(screen.getByRole('button', { name: C.resolve.submit }));
    await waitFor(() => expect(record).toHaveBeenCalledTimes(1));
    expect(record.mock.calls[0][1]).toEqual({
      kind: 'conflict_resolution',
      scope: 'import',
      body: { conflict_id: 'cf-1', chosen_value: '07_03_ZZ3_base_after1500Cycling_filter20_800mV' },
    });
    expect(getExperiment).not.toHaveBeenCalled();
  });

  it('a rule for an Experiment reads that record’s version and sends it', async () => {
    const record = vi.spyOn(api, 'recordImportRule').mockResolvedValue({} as never);
    vi.spyOn(api, 'getExperiment').mockResolvedValue({ id: DEST.rows[0].id, version: '9.3' } as never);
    const { container } = renderConflicts([view()]);
    openReview(container);
    fireEvent.click(screen.getByRole('radio', { name: /after1400Cycling/ }));
    fireEvent.click(screen.getByRole('radio', { name: C.scopeOptions.experiment }));
    fireEvent.change(screen.getByRole('combobox'), { target: { value: DEST.rows[0].id } });
    fireEvent.click(screen.getByRole('button', { name: C.resolve.submit }));
    await waitFor(() => expect(record).toHaveBeenCalledTimes(1));
    expect(record.mock.calls[0][1]).toMatchObject({
      scope: 'experiment',
      experimentId: DEST.rows[0].id,
      experimentVersion: '9.3',
    });
  });

  it('sends If-Match on the wire exactly when a version is given', async () => {
    const fetchSpy = vi.fn(async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchSpy);
    await api.recordImportRule('IMPZZ', { kind: 'conflict_resolution', scope: 'import', body: { a: 1 } });
    await api.recordImportRule('IMPZZ', {
      kind: 'conflict_resolution',
      scope: 'experiment',
      experimentId: 'E1',
      experimentVersion: '4',
      body: { a: 1 },
    });
    const [first, second] = fetchSpy.mock.calls as unknown as [string, RequestInit][];
    expect(JSON.stringify(first[1].headers ?? {})).not.toContain('If-Match');
    expect(second[1].headers).toMatchObject({ 'If-Match': '"4"' });
    expect(JSON.parse(String(second[1].body))).toMatchObject({ experiment_id: 'E1', scope: 'experiment' });
    vi.unstubAllGlobals();
  });

  it('a field conflict outside an archive import is not offered a resolution', () => {
    const { container } = renderConflicts([view({ kind: 'field', resolvable: false, target: { candidate_id: 'c' } })]);
    expect(container.textContent).toContain(C.resolve.fixtureOnly);
    expect(within(container).queryAllByRole('radio', { hidden: true })).toEqual([]);
  });
});

/* ── §2b conflicts at scale ──────────────────────────────────────────────── */

/** `n` conflicts of one kind, in sample group `group`. */
const many = (n: number, overrides: Partial<ConflictView> = {}, group = '03') =>
  Array.from({ length: n }, (_, i) =>
    view({
      key: `cf-${overrides.topic ?? 'k'}-${i}`,
      subject: `FAKE_stem_${String(i).padStart(2, '0')}`,
      target: { conflict_id: `cf-${i}` },
      groupToken: group,
      ...overrides,
    }),
  );

describe('§2b · conflicts are grouped by kind, and a long kind shows five then "Show N more"', () => {
  it('every kind states its count and meaning with everything collapsed', () => {
    const conflicts = [
      ...many(12),
      ...many(2, { topic: 'acquired_never_declared', explanation: 'A SECOND FAKE meaning.' }),
    ];
    const { container } = renderConflicts(conflicts);
    const heads = [...container.querySelectorAll('.hi-conflict-group-head')];
    expect(heads).toHaveLength(2);
    expect(heads[0].querySelector('.hi-count')?.textContent).toBe('12');
    expect(heads[1].querySelector('.hi-count')?.textContent).toBe('2');
    // The meaning is on the surface, never behind the review or the Show more.
    for (const head of heads) {
      const meaning = head.querySelector('.hi-conflict-explanation')!;
      expect(meaning.textContent?.length).toBeGreaterThan(0);
      expect(meaning.closest('[hidden]')).toBeNull();
    }
  });

  it('MUTATION-GUARDED: shows exactly the first five, and Show N more reveals exactly the rest', () => {
    /**
     * MUTATION: `hidden={!all && index >= CONFLICTS_SHOWN_PER_KIND - 1}` (an
     * off-by-one) makes this RED on the "exactly five" count.
     */
    const { container } = renderConflicts(many(12));
    const rows = () => [...container.querySelectorAll<HTMLLIElement>('li.hi-conflict')];
    const visible = () => rows().filter((r) => !r.hidden);
    expect(rows()).toHaveLength(12);
    expect(visible()).toHaveLength(CONFLICTS_SHOWN_PER_KIND);
    // The FIRST five, in order.
    expect(visible().map((r) => r.querySelector('.hi-conflict-subject')?.textContent)).toEqual(
      ['00', '01', '02', '03', '04'].map((n) => `FAKE_stem_${n}`),
    );
    const more = screen.getByRole('button', { name: 'Show 7 more' });
    expect(more.getAttribute('aria-expanded')).toBe('false');
    // It names the list it controls and is described by the kind it belongs to.
    expect(document.getElementById(more.getAttribute('aria-controls')!)?.tagName).toBe('UL');
    expect(document.getElementById(more.getAttribute('aria-describedby')!)?.textContent).toContain('12');
    fireEvent.click(more);
    expect(visible()).toHaveLength(12);
    expect(more.getAttribute('aria-expanded')).toBe('true');
    // Announced to a screen reader, in the ONE status region the stage keeps.
    const status = container.querySelectorAll('[role="status"]');
    expect(status).toHaveLength(1);
    expect(status[0].textContent).toBe('7 more shown — all 12 of this kind.');
    fireEvent.click(more);
    expect(visible()).toHaveLength(CONFLICTS_SHOWN_PER_KIND);
  });

  it('a kind with five or fewer has no Show more at all', () => {
    renderConflicts(many(5));
    expect(screen.queryByRole('button', { name: /^Show \d+ more$/ })).toBeNull();
  });

  it('Run 32 is still offered no resolution control, alone or among many', () => {
    const { container } = renderConflicts([
      ...many(7),
      view({ key: 'cf-32', topic: 'duplicate_legacy_number', subject: 'legacy 32', forbidden: true, groupToken: null }),
    ]);
    const group = [...container.querySelectorAll('.hi-conflict-group')].find((g) =>
      g.textContent?.includes('Two files claim the same legacy number'),
    ) as HTMLElement;
    expect(within(group).queryAllByRole('radio', { hidden: true })).toEqual([]);
    expect(within(group).queryByRole('button', { name: C.resolve.groupTitle, hidden: true })).toBeNull();
    expect(within(group).queryByRole('button', { name: C.resolve.submit, hidden: true })).toBeNull();
  });
});

describe('§2c · a whole sample group is resolved at the kind, by the kind of source', () => {
  it('is offered only where a group holds more than one open, resolvable conflict of the kind', () => {
    expect(groupRuleChoices(many(1))).toBeNull();
    expect(groupRuleChoices(many(2, { groupToken: null }))).toBeNull();
    expect(groupRuleChoices(many(3, { forbidden: true }))).toBeNull();
    expect(groupRuleChoices(many(3, { resolvable: false }))).toBeNull();
    expect(groupRuleChoices([...many(2, {}, '03'), ...many(1, {}, '04')])).toEqual({
      roles: ['human_label', 'instrument_header'],
      groups: [{ token: '03', count: 2 }],
    });
  });

  it('records ONE rule for the group — the kind and the chosen role, never a value', async () => {
    const record = vi.spyOn(api, 'recordImportRule').mockResolvedValue({} as never);
    renderConflicts(many(3));
    fireEvent.click(screen.getByRole('button', { name: C.resolve.groupTitle }));
    expect(screen.getByRole('combobox', { name: C.resolve.groupWhich })).toHaveValue('03');
    fireEvent.click(screen.getByRole('radio', { name: 'Header' }));
    fireEvent.click(screen.getByRole('button', { name: C.resolve.groupSubmit }));
    await waitFor(() => expect(record).toHaveBeenCalledTimes(1));
    expect(record.mock.calls[0][1]).toEqual({
      kind: 'conflict_resolution',
      scope: 'import',
      selector: { group_tokens: ['03'] },
      body: { conflict_kind: 'internal_declaration_vs_filename', chosen_source_role: 'instrument_header' },
    });
  });

  it('the per-row form no longer offers the recurring option — it lives at the kind', () => {
    const { container } = renderConflicts(many(3));
    fireEvent.click(within(container.querySelector('li.hi-conflict') as HTMLElement).getByRole('button', { name: C.conflicts.review }));
    const row = container.querySelector('li.hi-conflict') as HTMLElement;
    expect(within(row).queryAllByRole('checkbox')).toEqual([]);
  });
});

describe('§2d · a field disagreement names the field, and each source by its file', () => {
  it('shows the field and the file behind each reading, not "Source · Source"', () => {
    const { container } = renderConflicts([
      view({
        key: 'field-1',
        kind: 'field',
        topic: 'Filter',
        explanation: null,
        readings: [
          { value: '10', role: null, roleMeaning: null, sourceType: null, sources: [{ path: 'FAKE_dir/FAKE_001.dat', locator: 'l1' }] },
          { value: '35', role: null, roleMeaning: null, sourceType: null, sources: [{ path: 'FAKE_notes.txt', locator: 'l2' }] },
        ],
        distinct: null,
        target: { candidate_id: 'c1' },
        groupToken: null,
      }),
    ]);
    expect(container.querySelector('.hi-conflict-topic')?.textContent).toBe('Filter');
    const line = [...container.querySelectorAll('.hi-conflict-line > li')].map((li) => li.textContent?.replace(/\s+/g, ' ').trim());
    expect(line).toEqual(['FAKE_001.dat 10', 'FAKE_notes.txt 35']);
    expect(container.querySelector('.hi-conflict-group-title')?.textContent).toContain(C.conflicts.fieldKindTitle);
    expect(container.querySelector('.hi-conflict-group-head .hi-conflict-explanation')?.textContent).toBe(
      C.conflicts.fieldKindMeaning,
    );
  });
});

/* ── §3–§5 what ISAAC read ───────────────────────────────────────────────── */

/**
 * The committed corpus-review fixture — generated by the real contract (see
 * `bl15-import-review.test.tsx` §1) — with the 2026-09-22 members each test needs
 * laid over it, so everything the overview reads besides them is the real shape.
 */
const BASE_REVIEW = JSON.parse(
  readFileSync(join(__dirname, 'fixtures', 'bl15-corpus-review.json'), 'utf8'),
) as Bl15CorpusReview;

function review(overrides: Partial<Bl15CorpusReview> = {}): Bl15CorpusReview {
  return { ...BASE_REVIEW, ...overrides } as Bl15CorpusReview;
}

const PROFILES: ApiImportProfile[] = [
  {
    profile_id: 'zz_default',
    profile_version: '1',
    display_name: 'FAKE ZZ filename convention v1',
    aliases: [],
    measured_on: 'fixture',
    is_default: true,
  },
];

describe('§3 · temperature is Not Recorded, or the source’s own words', () => {
  it('Not Recorded: an icon-and-word state, the policy one press away, and no number offered', () => {
    const { container } = render(
      <CorpusReadOverview
        review={review({
          temperature: {
            status: 'not_recorded',
            statements: [],
            policy: 'This FAKE corpus states no temperature anywhere, so none is filled in.',
          },
        } as never)}
        profiles={PROFILES}
        units={[]}
      />,
    );
    const fact = [...container.querySelectorAll('.bl15-fact')].find((f) =>
      f.textContent?.includes(C.temperatureTitle),
    )!;
    const chip = fact.querySelector('.semantic-status')!;
    expect(chip.textContent).toContain(C.stateLabels.notRecorded);
    expect(chip.querySelector('svg')).not.toBeNull();
    expect(fact.querySelector('.disclosure-body')?.textContent).toContain('states no temperature anywhere');
    expect(fact.querySelectorAll('input, select, button.btn')).toHaveLength(0);
  });

  it('Stated: the literal verbatim, and NOT the "states no temperature" policy beside it', () => {
    const { container } = render(
      <CorpusReadOverview
        review={review({
          temperature: {
            status: 'stated_in_source',
            statements: [{ raw_literal: 'room temp-ish (FAKE)', source_path: 'FAKE/notes.txt' }],
            policy: BASE_REVIEW.mapping.temperature_absent_reason,
          },
        } as never)}
        profiles={PROFILES}
        units={[]}
      />,
    );
    expect(container.querySelector('q.bl15-quote')?.textContent).toBe('room temp-ish (FAKE)');
    expect(container.textContent).toContain(C.temperatureStated);
    /*
     * NOWHERE on the surface does a sentence deny the statement shown above it.
     * The registry's blocker used to open "this corpus states no temperature
     * anywhere" for every archive; it was corrected at its source (the server's
     * `bl15.mapping.TEMPERATURE_ABSENT_REASON`, pinned in `test_bl15_mapping.py`),
     * and the fixture carries the corrected sentence, which "What cannot be
     * finished here" quotes verbatim. The sentence still names the temperature
     * as a blocker — a statement in words cannot fill `context.temperature_K`.
     */
    expect(BASE_REVIEW.mapping.temperature_absent_reason).not.toContain('states no temperature anywhere');
    expect(BASE_REVIEW.mapping.temperature_absent_reason).toContain('context.temperature_K');
    expect(container.textContent).not.toContain('states no temperature anywhere');
    expect(container.textContent).toContain(BASE_REVIEW.mapping.temperature_absent_reason);
    /*
     * No NUMBER is offered for it. "298" does appear on this surface, and must: it is
     * inside the registry's own sentence forbidding it as a default. What is checked is
     * that it never appears as a VALUE — in the quoted statement, or as a control.
     */
    const temperature = [...container.querySelectorAll('.bl15-fact')].find((f) =>
      f.textContent?.includes(C.temperatureTitle),
    )!;
    for (const q of temperature.querySelectorAll('q')) expect(q.textContent).not.toMatch(/\d/);
    expect(temperature.querySelectorAll('input, select')).toHaveLength(0);
  });
});

describe('§4 · Data Quality Notes are the scientist’s words, never a QC verdict', () => {
  it('uses the server’s own label, quotes each note, and says it is not a verdict', () => {
    const { container } = render(
      <CorpusReadOverview
        review={review({
          data_quality_notes: {
            label: 'Data Quality Notes',
            bound_to_a_measurement: 2,
            unbound: [{ text: 'beam dumped mid-scan (FAKE)', source_path: 'FAKE/notes.txt' }],
          },
        } as never)}
        profiles={PROFILES}
        units={[]}
      />,
    );
    const block = [...container.querySelectorAll('.bl15-fact')].find((f) =>
      f.textContent?.includes('Data Quality Notes'),
    )!;
    expect(block.querySelector('q')?.textContent).toBe('beam dumped mid-scan (FAKE)');
    expect(block.textContent).toContain(C.qualityNote);
    // No QC vocabulary is attached to a note: no verdict chip, no pass/fail word.
    expect(block.querySelector('.semantic-status')).toBeNull();
    expect(block.textContent).not.toMatch(/\b(valid|compromised|pass|fail)\b/i);
  });
});

describe('§5 · a convention reads sources; a person is provenance only', () => {
  it('counts sources per convention by name, and marks an ambiguous tie as a state', () => {
    const { container } = render(
      <CorpusReadOverview
        review={review({
          profile_applicability: { convention_counts: { zz_default: 4, ambiguous: 1 }, ambiguous_sources: 1 },
          beamtime_contributors: [{ name: 'Z. Fakename' }],
        } as never)}
        profiles={PROFILES}
        units={[]}
      />,
    );
    const conventions = [...container.querySelectorAll('.bl15-fact')].find((f) =>
      f.textContent?.includes(C.conventionsTitle),
    )!;
    expect(conventions.textContent).toContain('FAKE ZZ filename convention');
    expect(conventions.textContent).toContain('read 4 sources');
    expect(conventions.textContent).toContain(C.stateLabels.ambiguous);
    // The person appears only under the provenance heading, and the explanation says so.
    const people = [...container.querySelectorAll('.bl15-fact')].find((f) =>
      f.textContent?.includes(C.peopleTitle),
    )!;
    expect(people.textContent).toContain('Z. Fakename');
    expect(people.textContent).toContain('never the actor');
    expect(conventions.textContent).not.toContain('Z. Fakename');
  });
});

/* ── §6 reading rules ────────────────────────────────────────────────────── */

function rule(overrides: Partial<ApiConventionRule> = {}): ApiConventionRule {
  return {
    rule_id: 'RULEZZ1',
    kind: 'conflict_resolution',
    scope: 'import',
    version: 1,
    body: { chosen_value: 'after1500Cycling' },
    selector: { group_tokens: ['03'] },
    experiment_id: null,
    import_id: 'IMPZZ',
    profile_id: null,
    profile_version: null,
    supersedes: null,
    derived_from: null,
    confirmed_utc: '2099-01-01T00:00:00Z',
    confirmed_by: 'unattributed',
    confirmed_trust_basis: 'none',
    version_is_current: true,
    is_official_field_value: false,
    is_evidence: false,
    ...overrides,
  };
}

function rulesView(overrides: Partial<ApiImportRulesView> = {}): ApiImportRulesView {
  return {
    target_experiment_id: null,
    import: [],
    import_durability: 'FAKE durability',
    import_unreadable: 0,
    experiment: [],
    experiment_rules_as_of_version: null,
    experiment_durability: 'FAKE durability',
    reusable_from_other_experiments: [],
    reuse_policy: 'FAKE policy',
    ...overrides,
  };
}

describe('§6 · reading rules are attributed honestly and adopted only on purpose', () => {
  it('a recorded rule says Confirmed by Unattributed, never a name the build cannot verify', () => {
    const { container } = render(
      <ImportRules rules={rulesView({ import: [rule()] })} profiles={PROFILES} importId="IMPZZ" busy={null} onAct={runAct} destinations={DEST} />,
    );
    const row = container.querySelector('.hi-rule')!;
    expect(row.textContent).toContain(`${C.confirmedBy} ${C.unattributed}`);
    expect(row.textContent).not.toContain('unattributed');
  });

  it('a suggestion from another record is NOT applied until adopted, and adoption is one explicit act', async () => {
    const record = vi.spyOn(api, 'recordImportRule').mockResolvedValue({} as never);
    vi.spyOn(api, 'getExperiment').mockResolvedValue({ id: DEST.rows[0].id, version: '2.0' } as never);
    const suggestion = rule({ rule_id: 'RULEZZ-OTHER', scope: 'experiment', experiment_id: 'OTHER' });
    render(
      <ImportRules
        rules={rulesView({
          target_experiment_id: DEST.rows[0].id,
          reusable_from_other_experiments: [
            {
              rule: suggestion,
              from_experiment_id: 'OTHER',
              from_experiment_title: 'Another FAKE record',
              applied_here: false,
              how_to_reuse: 'FAKE',
              matches: { units: 2, stems: [] },
            },
          ],
        })}
        profiles={PROFILES}
        importId="IMPZZ"
        busy={null}
        onAct={runAct}
        destinations={DEST}
      />,
    );
    expect(record).not.toHaveBeenCalled();
    expect(screen.getByText(/would match 2 measurements here/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: C.adopt }));
    await waitFor(() => expect(record).toHaveBeenCalledTimes(1));
    expect(record.mock.calls[0][1]).toMatchObject({
      scope: 'experiment',
      experimentId: DEST.rows[0].id,
      experimentVersion: '2.0',
      derivedFrom: 'RULEZZ-OTHER',
    });
  });

  it('with ONE registered convention there is nothing to switch to, and it says so', () => {
    render(<ImportRules rules={rulesView()} profiles={PROFILES} importId="IMPZZ" busy={null} onAct={runAct} destinations={DEST} />);
    expect(screen.getByText(C.bindingOne)).toBeTruthy();
    expect(screen.queryByRole('button', { name: C.bindingSubmit })).toBeNull();
  });
});

/* ── §7 HERFD signal ─────────────────────────────────────────────────────── */

function selection(overrides: Partial<ApiImportSignalSelection> = {}): ApiImportSignalSelection {
  return {
    selector_id: 'herfd',
    system_id: 'FAKE',
    status: 'proposed',
    reason_code: 'one_live_channel',
    reason: 'Exactly one FAKE channel carries live signal.',
    primary_channel: 'Vortex1',
    assignments: [],
    channels: [
      { channel: 'Vortex1', scans_present: 2, scans_with_edge: 2, share: 1, edge_fraction: 1, liveness: 'live', reason: '' },
      { channel: 'Vortex2', scans_present: 2, scans_with_edge: 0, share: 0, edge_fraction: 0, liveness: 'empty', reason: '' },
    ],
    elements: [{ element: 'Zz', edge: 'K', source_path: 'FAKE/notes.txt', locator: 'line 1', role: 'absorber', rule: 'r' }],
    thresholds: {},
    authority: 'suggestion',
    rule_ref: null,
    evidence_not_used: [],
    writes_a_record_field: false,
    ...overrides,
  };
}

const UNIT = { stem: 'FAKE_07', acquisition_path: 'FAKE/07.dat' } as ApiImportUnitRow;

describe('§7 · the HERFD signal is a suggestion until a scientist confirms it', () => {
  it('a proposed channel reads as Suggested — never Confirmed — with the server’s reason', () => {
    render(
      <SignalSelection unit={UNIT} selection={selection()} importId="IMPZZ" busy={null} onAct={runAct} destinations={DEST} state={signalState(selection())} />,
    );
    expect(screen.getByText('Suggested')).toBeTruthy();
    expect(screen.queryByText('Confirmed')).toBeNull();
    expect(screen.getByText('Exactly one FAKE channel carries live signal.')).toBeTruthy();
    expect(screen.getByRole('button', { name: C.signalConfirm })).toBeTruthy();
  });

  it('a dual-element run shows BOTH live channels, each with its own element, and picks neither', () => {
    const dual = selection({
      status: 'needs_review',
      primary_channel: null,
      reason: 'Two FAKE channels carry live signal.',
      channels: [
        { channel: 'Vortex1', scans_present: 2, scans_with_edge: 2, share: 0.5, edge_fraction: 1, liveness: 'live', reason: '' },
        { channel: 'Vortex3', scans_present: 2, scans_with_edge: 2, share: 0.5, edge_fraction: 1, liveness: 'live', reason: '' },
      ],
    });
    const { container } = render(
      <SignalSelection unit={UNIT} selection={dual} importId="IMPZZ" busy={null} onAct={runAct} destinations={DEST} state={signalState(dual)} />,
    );
    expect(container.querySelector('.hi-signal-line')?.textContent).toContain('2 live channels: Vortex1, Vortex3');
    expect([...container.querySelectorAll('.hi-signal-channel')].map((c) => c.textContent)).toEqual(['Vortex1', 'Vortex3']);
    expect(screen.getByText(C.stateLabels.needsReview)).toBeTruthy();
    expect(screen.getByRole('button', { name: C.signalAssign })).toBeTruthy();
  });
});

/* ── §8 the stage helpers ────────────────────────────────────────────────── */

const candidate = (overrides: Partial<ApiImportCandidate>): ApiImportCandidate =>
  ({
    candidate_id: 'CZZ',
    kind: 'field',
    determinism: 'deterministic',
    rule: 'r',
    supporting_source_ids: ['S1'],
    supporting_statements: [],
    target_field_path: 'sample.material.name',
    proposed_value: 'ZZOxide',
    disagreement: [],
    unresolved_reason: null,
    not_proposable_reason: null,
    proposable: true,
    ...overrides,
  }) as ApiImportCandidate;

describe('§8 · statuses come from the server, and agreement is never inferred', () => {
  it('the bucket follows `review_status` over any local reading', () => {
    expect(candidateBucket(candidate({ review_status: 'needs_review', proposable: true }))).toBe('needsReview');
    expect(candidateBucket(candidate({ review_status: 'sources_conflict' }))).toBe('conflict');
    expect(candidateBucket(candidate({ review_status: 'resolved' }))).toBe('resolved');
  });

  it('shows Sources Agree ONLY when the server says two distinct files agree', () => {
    const { container, rerender } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={candidate({ agreement: 'sources_agree' } as never)} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    expect(container.textContent).toContain(C.stateLabels.sourcesAgree);
    rerender(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={candidate({ agreement: 'single_source' } as never)} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    expect(container.textContent).not.toContain(C.stateLabels.sourcesAgree);
    // Several statements in ONE file are one witness, not agreement.
    rerender(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow
            candidate={candidate({
              supporting_statements: [
                { source_id: 'S1', key: 'k', value: 'ZZOxide', locator: 'line 1' },
                { source_id: 'S1', key: 'k', value: 'ZZOxide', locator: 'line 9' },
              ],
            })}
            filenameOf={(id) => id}
          />
        </ul>
      </MemoryRouter>,
    );
    expect(container.textContent).not.toContain(C.stateLabels.sourcesAgree);
  });

  it('a candidate row shows no raw schema path until the reader asks for it', () => {
    const { container } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={candidate({})} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    const summary = container.querySelector('.disclosure-trigger')!;
    expect(summary.textContent).not.toContain('sample.material.name');
    // ...and it is kept, behind the `?`, for the curator who maps it.
    expect(container.querySelector('.helptip-panel code')?.textContent).toBe('sample.material.name');
  });

  it('opens a reconstructed session on Runs & Candidates, and an empty one on Source Bundle', () => {
    const base = {
      sources: [],
      source_counts: { parsed: 0, total: 0 },
      reconstruction: null,
      workflow: [],
      furthest_step: 'new_import',
    } as unknown as ApiImportSession;
    expect(defaultStage(base)).toBe('sources');
    expect(
      defaultStage({
        ...base,
        sources: [{} as never],
        source_counts: { parsed: 1, total: 1 } as never,
        reconstruction: { candidates: [] } as never,
        furthest_step: 'reconstruct',
      }),
    ).toBe('runs');
  });

  it('the summary counts are the payload’s own', () => {
    const items = summaryItems({
      sources: [{}, {}] as never,
      source_counts: { parsed: 1, total: 2 } as never,
      reconstruction: { candidates: [candidate({}), candidate({ candidate_id: 'C2', proposable: false, unresolved_reason: 'sources_disagree', disagreement: [{ value: 'a', source_ids: ['S1'], locators: ['l'] }, { value: 'b', source_ids: ['S2'], locators: ['l'] }] })] } as never,
      corpus_digest: null,
      corpus_review: undefined,
    } as unknown as ApiImportSession);
    const byId = Object.fromEntries(items.map((i) => [i.id, i.value]));
    expect(byId).toMatchObject({ sources: 2, read: 1, candidates: 2, conflicts: 1, ready: 1 });
  });

  it('says in human words why the rest will not be sent — never a raw error code', () => {
    const rows = wouldNotSend([
      candidate({ proposable: false, unresolved_reason: 'sources_disagree' }),
      candidate({ candidate_id: 'C3', proposable: false, not_proposable_reason: 'x' }),
    ]);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) expect(row.reason).not.toMatch(/_/);
  });

  it('conflictViews marks the duplicate-legacy-number conflict forbidden even without a server flag', () => {
    const views = conflictViews({
      corpus_review: review({
        relationships: {
          units: [],
          groups: [],
          corpus_conflicts: [
            {
              kind: 'duplicate_legacy_number',
              subject: 'legacy 32',
              explanation: 'FAKE',
              readings: [
                { value: 'a', source_path: 'FAKE/a', locator: 'l', source_type: 'spec_acquisition' },
                { value: 'b', source_path: 'FAKE/b', locator: 'l', source_type: 'spec_acquisition' },
              ],
            },
          ],
          unattached: [],
          unit_count: 0,
          conflict_count: 1,
        },
      } as never),
      sources: [],
      reconstruction: null,
      archive: null,
    } as unknown as ApiImportSession);
    expect(views).toHaveLength(1);
    expect(views[0].forbidden).toBe(true);
  });
});

/* ── §9 per-scan variation is neither agreement nor conflict ─────────────── */

describe('§9 · a value that differs by scan reads "Varies by Scan" — never a conflict', () => {
  const varying = candidate({
    candidate_id: 'ZZ_unit::detector_column',
    target_field_path: 'measurement.series[].channels[].name',
    proposed_value: null,
    proposable: false,
    not_proposable_reason: 'FAKE registry reason.',
    agreement: 'varies',
    review_status: 'needs_review',
    variation_basis: 'per_scan_item',
    variation_scans: 2,
    variation_total: 30,
    variation: [
      { scan: '1', item: 'column 0', source: null, value: 'I0', source_ids: ['S1'], locators: ['FAKE_001.dat · line 6'] },
      { scan: '2', item: 'column 0', source: null, value: 'I0b', source_ids: ['S2'], locators: ['FAKE_002.dat · line 6'] },
    ],
  } as never);

  it('shows a neutral Varies by Scan state, no conflict state, and the scan count', () => {
    const { container } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={varying} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    const meta = container.querySelector('.hi-cand-meta')!;
    // Several detector columns per scan: "Several per Scan", not "Varies by Scan" — the
    // columns differ from each other, not necessarily from scan to scan.
    expect(meta.textContent).toContain(C.stateLabels.severalPerScan);
    expect(meta.textContent).not.toContain(C.stateLabels.conflict);
    expect(meta.textContent).not.toContain(C.stateLabels.sourcesAgree);
    // Neutral tone, icon + word — never the conflict tone.
    const chip = [...meta.querySelectorAll('.semantic-status')].find((c) => c.textContent?.includes(C.stateLabels.severalPerScan))!;
    expect(chip.getAttribute('data-tone')).toBe('neutral');
    expect(chip.querySelector('svg')).not.toBeNull();
    expect(container.querySelector('.hi-cand-summary')?.textContent).toContain('30 values across 2 scans');
    // It is NOT offered the "No value has been selected." of an open conflict.
    expect(container.textContent).not.toContain(C.conflicts.noValue);
  });

  it('keeps every scan’s reading one press away, with where each came from and the true total', () => {
    const { container } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={varying} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    const rows = [...container.querySelectorAll('.hi-cand-variation .hi-cand-readings > li')].map((li) =>
      li.textContent?.replace(/\s+/g, ' ').trim(),
    );
    expect(rows).toEqual([
      'Scan 1 · column 0 I0FAKE_001.dat · line 6',
      'Scan 2 · column 0 I0bFAKE_002.dat · line 6',
    ]);
    expect(container.textContent).toContain('2 of 30 readings shown.');
    expect(container.textContent).toContain(C.variation.whyItem);
  });

  it('a per-scan value reads "Varies by Scan", one per scan', () => {
    const perScan = { ...varying, variation_basis: 'per_scan', variation_total: null } as never;
    const { container } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={perScan} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    expect(container.querySelector('.hi-cand-meta')?.textContent).toContain(C.stateLabels.variesByScan);
    expect(container.querySelector('.hi-cand-summary')?.textContent).toContain('one per scan · 2 scans');
    expect(container.textContent).toContain(C.variation.why);
  });

  it('writes a structured value as text, never [object Object] or a Python repr', () => {
    expect(normalizedText({ measurement_stem: 'ZZ_unit', scan_index: 1 })).toBe('ZZ_unit · scan 1');
    expect(normalizedText({ b: 2, a_b: 'x' })).toBe('a b x; b 2');
    expect(normalizedText([1, 2])).toBe('1, 2');
    expect(normalizedText(0.06)).toBe('0.06');
    expect(normalizedText(null)).toBe('');
  });
});
