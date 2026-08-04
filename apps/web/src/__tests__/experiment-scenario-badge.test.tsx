import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExperimentRow } from '../components/ExperimentRow';
import { toExperimentSummary } from '../lib/adapt';
import { CANONICAL_SCENARIO_LABELS, RESET_TITLE_BASE } from '../test/apiFixtures';
import type { ApiExperimentSummary, ExperimentSummary } from '../lib/types';

/*
 * The five canonical synthetic seeds share ONE scientific title once the
 * server's lifecycle suffix is stripped, so the row also renders the backend's
 * DERIVED `scenario` label as a quiet secondary line naming which seeded fixture
 * it is. These tests pin: all five render, the title is still the stripped base
 * title (never mutated), the label joins the accessible name, and a record
 * WITHOUT a scenario renders nothing at all — no empty shell, no "undefined".
 *
 * The server words each label as a PAST-TENSE statement about how the fixture was
 * materialised, so it cannot be falsified once the record advances. Non-duplication
 * against the live chip / group wording is checked below for ALL FIVE rows, not just
 * one: it was previously checked for the `in_review` row alone, and the row that
 * actually collided with a live chip was the exported one.
 */

const BASE_TITLE = 'XANES Example — CuO (Cu K-edge)';

/** The five rows exactly as `GET /api/experiments` serves them (title suffix +
 * derived scenario label + the live derived status each seed actually has). */
const CANONICAL_ROWS: ApiExperimentSummary[] = [
  {
    id: '01SYNTHXANESSEED0000000001',
    title: `${BASE_TITLE} · New Draft`,
    scenario: 'Example 1 · at setup: extraction only',
    status: 'needs_attention',
    created_utc: '2026-07-12T00:00:01Z',
    pending_count: 5,
    evidenced_field_count: 26,
    exported: false,
    record_id: null,
  },
  {
    id: '01SYNTHXANESSEED0000000002',
    title: `${BASE_TITLE} · Partially Completed`,
    scenario: 'Example 2 · at setup: some answers confirmed',
    status: 'needs_attention',
    created_utc: '2026-07-12T00:00:02Z',
    pending_count: 2,
    evidenced_field_count: 30,
    exported: false,
    record_id: null,
  },
  {
    id: '01SYNTHXANESSEED0000000003',
    title: `${BASE_TITLE} · Ready to Export`,
    scenario: 'Example 3 · at setup: all answers confirmed',
    status: 'ready_to_export',
    created_utc: '2026-07-12T00:00:03Z',
    pending_count: 0,
    evidenced_field_count: 33,
    exported: false,
    record_id: null,
  },
  {
    id: '01SYNTHXANESSEED0000000004',
    title: `${BASE_TITLE} · Export Review Required`,
    scenario: 'Example 4 · at setup: descriptor uncertainty omitted',
    status: 'in_review',
    created_utc: '2026-07-12T00:00:04Z',
    pending_count: 0,
    evidenced_field_count: 33,
    exported: false,
    record_id: null,
  },
  {
    id: '01SYNTHXANESSEED0000000005',
    title: `${BASE_TITLE} · Exported Record`,
    scenario: 'Example 5 · at setup: export run',
    status: 'done',
    created_utc: '2026-07-12T00:00:05Z',
    pending_count: 0,
    evidenced_field_count: 33,
    exported: true,
    record_id: '01SYNTHXANESSEED0000000005',
  },
];

function renderRow(exp: ExperimentSummary) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ExperimentRow exp={exp} />
    </MemoryRouter>,
  );
}

describe('scenario label — adapt layer', () => {
  it('passes the server label through verbatim for all five canonical rows', () => {
    expect(CANONICAL_ROWS.map((r) => toExperimentSummary(r).scenario)).toEqual([
      'Example 1 · at setup: extraction only',
      'Example 2 · at setup: some answers confirmed',
      'Example 3 · at setup: all answers confirmed',
      'Example 4 · at setup: descriptor uncertainty omitted',
      'Example 5 · at setup: export run',
    ]);
  });

  it('stays in lockstep with the shared API fixtures', () => {
    expect(CANONICAL_ROWS.map((r) => r.scenario)).toEqual(CANONICAL_SCENARIO_LABELS);
  });

  /*
   * ADDED because this file's OWN copy of the title base had drifted too, and nothing
   * checked it. `BASE_TITLE` read `'Synthetic XANES — CuO (Cu K-edge)'` while the
   * backend had been renamed to `'XANES Example — CuO (Cu K-edge)'` — the same drift
   * that `apiFixtures.ts` carried, and the reason a backend-side pin now exists
   * (`apps/api/tests/test_seed_fixture_parity.py`). That pin reads only
   * `apiFixtures.ts`, so this test is what ties THIS file's literal to it, giving the
   * pin transitive reach here.
   */
  it('uses the same title base as the shared API fixtures', () => {
    expect(BASE_TITLE).toBe(RESET_TITLE_BASE);
  });

  it('leaves the scientific title as the stripped base title (never mutated)', () => {
    for (const row of CANONICAL_ROWS) {
      expect(toExperimentSummary(row).title).toBe(BASE_TITLE);
    }
  });

  it('is undefined when the server sends null (non-canonical record)', () => {
    const row: ApiExperimentSummary = { ...CANONICAL_ROWS[0], scenario: null };
    expect(toExperimentSummary(row).scenario).toBeUndefined();
  });

  it('is undefined when the server omits the field entirely', () => {
    const { scenario: _drop, ...withoutScenario } = CANONICAL_ROWS[0];
    expect(toExperimentSummary(withoutScenario).scenario).toBeUndefined();
  });
});

describe('scenario label — ExperimentRow rendering', () => {
  it.each(CANONICAL_ROWS.map((r) => [r.scenario as string, r] as const))(
    'renders "%s" as a secondary line beneath the title',
    (label, row) => {
      const { container } = renderRow(toExperimentSummary(row));
      const line = container.querySelector('.exp-scenario');
      expect(line).not.toBeNull();
      expect(line?.textContent).toBe(label);
      // Secondary: it lives inside the main column, AFTER the title element.
      const main = container.querySelector('.exp-main');
      expect(main?.contains(line as Node)).toBe(true);
      const title = container.querySelector('.exp-title');
      expect(title).not.toBeNull();
      const position = (title as Element).compareDocumentPosition(line as Node);
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      // ...and the title itself never absorbs the label.
      expect(title?.textContent).toBe(BASE_TITLE);
    },
  );

  it('all five rows are visually distinguishable despite one shared title', () => {
    const rendered = CANONICAL_ROWS.map(
      (r) => renderRow(toExperimentSummary(r)).container.querySelector('.exp-scenario')?.textContent,
    );
    expect(new Set(rendered).size).toBe(5);
    expect(rendered.some((t) => t == null)).toBe(false);
  });

  it('pairs the label with an icon so meaning never rests on color alone', () => {
    const { container } = renderRow(toExperimentSummary(CANONICAL_ROWS[3]));
    const line = container.querySelector('.exp-scenario');
    const icon = line?.querySelector('svg');
    expect(icon).not.toBeNull();
    // decorative only — the text carries the meaning
    expect(icon?.getAttribute('aria-hidden')).toBe('true');
    expect(line?.textContent).toBe('Example 4 · at setup: descriptor uncertainty omitted');
  });

  it('renders NOTHING for a record without a scenario (no shell, no "undefined")', () => {
    const exp = toExperimentSummary({ ...CANONICAL_ROWS[0], scenario: null });
    const { container } = renderRow(exp);
    expect(container.querySelector('.exp-scenario')).toBeNull();
    expect(container.textContent).not.toContain('undefined');
    expect(container.textContent).not.toContain('at setup');
    // the rest of the row is untouched
    expect(container.querySelector('.exp-title')?.textContent).toBe(BASE_TITLE);
    expect(container.querySelector('.exp-sub')?.textContent).toContain('Draft');
  });

  it.each(CANONICAL_ROWS.map((r, i) => [r.scenario as string, r, i] as const))(
    'does not duplicate or contradict the status chip / group state: "%s"',
    (label, row, index) => {
      // Every row, not just one: the label names how the SEEDED FIXTURE was
      // materialised, not the live state, so it repeats neither the lifecycle chip
      // nor the group-state wording — including on the exported row, where the
      // earlier wording ("Scenario 5 · Exported") duplicated the chip verbatim.
      const { container } = renderRow(toExperimentSummary(row));
      const scenario = container.querySelector('.exp-scenario')?.textContent ?? '';
      expect(scenario).toBe(label);
      // Case-INSENSITIVE on both sides. The pre-Dean release review caught that a
      // case-sensitive comparison lets a differently-cased status word through — a
      // label reading "seeded: exported at setup" would have passed while still
      // restating the live chip. Lowercasing both sides is strictly stronger: every
      // string the old form rejected is still rejected, plus every casing variant.
      const scenarioLower = scenario.toLowerCase();
      for (const word of ['Draft', 'Exported', 'Needs Attention', 'In Review', 'Ready to Export', 'Done']) {
        expect(scenarioLower, `${label} restates the live word "${word}"`).not.toContain(
          word.toLowerCase(),
        );
      }
      // The live lifecycle chip is still rendered, and says the OTHER thing.
      const sub = container.querySelector('.exp-sub')?.textContent ?? '';
      expect(sub).toContain(row.exported ? 'Exported' : 'Draft');
      // ...and the label never states a field count that the live chip could contradict.
      expect(scenario.replace(`Example ${index + 1}`, '')).not.toMatch(/\d/);
      // ...and it is explicitly scoped to setup, so advancing the record — which
      // changes the chip and the group — cannot turn the label into a false claim.
      expect(scenario).toContain(`Example ${index + 1} · at setup: `);
    },
  );
});

describe('scenario label — accessible name', () => {
  it.each(CANONICAL_ROWS.map((r) => [r.scenario as string, r] as const))(
    'includes "%s" in the row accessible name',
    (label, row) => {
      const name =
        renderRow(toExperimentSummary(row)).getByRole('link').getAttribute('aria-label') ?? '';
      expect(name).toContain(label);
      expect(name).toContain(BASE_TITLE);
      expect(name).not.toContain('undefined');
    },
  );

  it('gives the five rows five DISTINCT accessible names', () => {
    // Container-scoped: the five renders share one document within this test.
    const names = CANONICAL_ROWS.map(
      (r) =>
        renderRow(toExperimentSummary(r)).container.querySelector('a')?.getAttribute('aria-label') ??
        '',
    );
    expect(new Set(names).size).toBe(5);
    expect(names.every((n) => n.length > 0)).toBe(true);
  });

  it('omits the label cleanly when there is none (no stray separator)', () => {
    const exp = toExperimentSummary({ ...CANONICAL_ROWS[0], scenario: null });
    const name = renderRow(exp).getByRole('link').getAttribute('aria-label') ?? '';
    expect(name).toBe(`${BASE_TITLE} — Draft, Needs Attention, 5 fields need you`);
    expect(name).not.toContain('undefined');
    expect(name).not.toContain(', ,');
  });

  it('keeps the existing lifecycle + group-state + count clauses alongside it', () => {
    const name =
      renderRow(toExperimentSummary(CANONICAL_ROWS[0])).getByRole('link').getAttribute('aria-label') ??
      '';
    expect(name).toBe(
      `${BASE_TITLE} — Example 1 · at setup: extraction only, Draft, Needs Attention, 5 fields need you`,
    );
  });
});
