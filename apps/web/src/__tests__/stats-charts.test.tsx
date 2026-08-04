import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import {
  CHART_FALLBACK_WIDTH,
  ChartAccessPending,
  ChartEmpty,
  ChartError,
  ChartLegend,
  ChartLoading,
  ChartSourceUnavailable,
  StatsBarChart,
  StatsColumnChart,
  StatsComparisonRows,
  StatsLineChart,
  StatsStackedBar,
  TechnicalDetails,
  estimateTextWidth,
} from '../screens/statistics/StatsCharts';

/**
 * The chart primitives, RENDERED.
 *
 * ── Why fixtures appear in this file and nowhere in the product ─────────────
 *
 * A chart with no data draws nothing, so the only way to check that a populated
 * chart is correct is to populate one. The rows below are obvious test fixtures
 * and they live ONLY here: `StatisticsPage.tsx` passes data derived from four
 * read-only GETs, and `MyStats.tsx` passes nothing at all because there is
 * nothing to pass. `StatsLineChart` in particular has NO production call site —
 * this suite is its only caller, which is the honest place for a chart whose real
 * series does not exist yet.
 *
 * ── What is asserted, and what deliberately is not ─────────────────────────
 *
 * Geometry is proved in `chart-geometry.test.ts` against the pure functions;
 * re-asserting pixel coordinates here would only re-test those. What this file
 * pins is everything BETWEEN the geometry and the reader:
 *
 *   · both text equivalents exist on every chart — the summary sentence AND the
 *     data table — and the summary is a real element rather than an attribute;
 *   · colour is never the only encoding: every category and every value survives
 *     the removal of all fill;
 *   · the SVG claims nothing (it is `aria-hidden`), so the text is authoritative;
 *   · a tooltip never GATES a value;
 *   · the five states are five different sentences, and access-pending is not
 *     empty and is not an error.
 *
 * jsdom has no `ResizeObserver`, so every chart here renders at
 * {@link CHART_FALLBACK_WIDTH}. That is a deliberate property of the hook, not an
 * accident of the test environment: a browser without the API gets a correctly
 * proportioned chart at a fixed width rather than a collapsed one.
 */

const WORKFLOW = [
  { key: 'load_record', label: 'Load Record', value: 0 },
  { key: 'complete_metadata', label: 'Complete Metadata', value: 1 },
  { key: 'export', label: 'Export', value: 3 },
];

const EVIDENCE = [
  { key: 'supported', label: 'Supported', value: 30 },
  { key: 'inferred_candidate', label: 'Inferred Candidate', value: 3 },
  { key: 'insufficient_evidence', label: 'Insufficient Evidence', value: 2 },
  { key: 'conflicting_evidence', label: 'Conflicting Evidence', value: 2 },
  { key: 'unknown', label: 'Unknown', value: 3 },
];

const METHODS = [
  { key: 'get', label: 'GET', value: 4 },
  { key: 'post', label: 'POST', value: 3 },
];

const figure = (caption: string): HTMLElement =>
  screen.getByText(caption, { selector: 'figcaption' }).closest('figure') as HTMLElement;

/**
 * The rendered text of a subtree with every `aria-hidden` subtree removed — i.e.
 * what is left when the whole drawn picture is taken away.
 *
 * Every text NODE is joined with a space, deliberately, rather than read off
 * `textContent`. `textContent` concatenates adjacent elements with no separator,
 * so `<span>B</span><span>Not Available</span>` becomes `BNot Available` and a
 * `label + value` assertion silently stops matching — the same trap
 * `statistics-page.test.tsx` documents on its own `textOf`.
 */
function textWithoutHidden(root: HTMLElement): string {
  const clone = root.cloneNode(true) as HTMLElement;
  for (const node of clone.querySelectorAll('[aria-hidden="true"]')) node.remove();
  const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  while (walker.nextNode()) parts.push(walker.currentNode.textContent ?? '');
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

function tableOf(caption: string): [string, ...string[]][] {
  const table = figure(caption).querySelector('table.stats-chart-table');
  expect(table, `no data table under "${caption}"`).not.toBeNull();
  return [...table!.querySelectorAll('tbody tr')].map(
    (row) =>
      [
        row.querySelector('th')?.textContent?.trim() ?? '',
        ...[...row.querySelectorAll('td')].map((cell) => cell.textContent?.trim() ?? ''),
      ] as [string, ...string[]],
  );
}

function summaryOf(caption: string): string {
  return figure(caption).querySelector('.sr-only')?.textContent?.trim() ?? '';
}

// --- the invariant that applies to every form --------------------------------

/**
 * The contract every chart on this surface signs, checked against all five forms
 * by the same code.
 *
 * `it.each` over a render function rather than five near-identical tests: the
 * requirement is genuinely uniform, and writing it once means a SIXTH chart form
 * cannot be added with only four of the five guarantees.
 */
const ALL_FORMS: [string, string, () => void][] = [
  [
    'StatsBarChart',
    'Records by workflow step',
    () =>
      render(
        <StatsBarChart
          caption="Records by workflow step"
          rows={WORKFLOW}
          unit="records"
          total={4}
          categoryHeader="Workflow Step"
        />,
      ),
  ],
  [
    'StatsColumnChart',
    'Operations by method',
    () =>
      render(
        <StatsColumnChart
          caption="Operations by method"
          rows={METHODS}
          unit="operations"
          total={7}
          categoryHeader="HTTP Method"
        />,
      ),
  ],
  [
    'StatsStackedBar',
    'Share of fields by class',
    () =>
      render(
        <StatsStackedBar
          caption="Share of fields by class"
          rows={EVIDENCE}
          total={40}
          unit="fields"
          categoryHeader="Class"
        />,
      ),
  ],
  [
    'StatsComparisonRows',
    'Operations by group',
    () =>
      render(
        <StatsComparisonRows
          caption="Operations by group"
          rows={METHODS}
          unit="operations"
          total={7}
          categoryHeader="Group"
        />,
      ),
  ],
  [
    'StatsLineChart',
    'Exports per week',
    () =>
      render(
        <StatsLineChart
          caption="Exports per week"
          rows={[
            { key: 'w1', label: 'Week 1', value: 1 },
            { key: 'w2', label: 'Week 2', value: 4 },
          ]}
          unit="records"
          xAxisLabel="Week"
        />,
      ),
  ],
];

describe('every chart form carries BOTH text equivalents', () => {
  it.each(ALL_FORMS)('%s — an always-present summary sentence', (_name, caption, mount) => {
    mount();
    const summary = figure(caption).querySelector('p.sr-only');
    expect(summary, 'the summary must be a real element, not an attribute').not.toBeNull();
    expect(summary!.textContent?.trim().length).toBeGreaterThan(0);
    // NOT inside the collapsed disclosure: a closed <details> is hidden from
    // assistive technology too, so the sentence would vanish with it.
    expect(summary!.closest('details')).toBeNull();
  });

  it.each(ALL_FORMS)('%s — a real data table, with a header row', (_name, caption, mount) => {
    mount();
    const table = figure(caption).querySelector('table.stats-chart-table');
    expect(table).not.toBeNull();
    expect(table!.querySelectorAll('thead th').length).toBeGreaterThanOrEqual(2);
    expect(table!.querySelectorAll('tbody tr').length).toBeGreaterThan(0);
    // Row headers are `<th scope="row">`, so a screen reader announces the
    // category with every cell instead of reading a grid of bare numbers.
    for (const row of table!.querySelectorAll('tbody tr')) {
      expect(row.querySelector('th')?.getAttribute('scope')).toBe('row');
    }
  });

  it.each(ALL_FORMS)('%s — the drawn SVG claims nothing', (_name, caption, mount) => {
    mount();
    for (const svg of figure(caption).querySelectorAll('svg')) {
      expect(svg.getAttribute('aria-hidden')).toBe('true');
      expect(svg.getAttribute('focusable')).toBe('false');
      // No text equivalent hides in an attribute on the picture.
      expect(svg.getAttribute('aria-label')).toBeNull();
      expect(svg.getAttribute('role')).toBeNull();
    }
  });

  it.each(ALL_FORMS)('%s — no chart renders a fixed-height scroll trap', (_name, caption, mount) => {
    mount();
    // Every SVG's `height` attribute is a real number and its viewBox matches it,
    // so the container is sized to include the axis band rather than clipping it.
    for (const svg of figure(caption).querySelectorAll('svg')) {
      const height = Number(svg.getAttribute('height'));
      const width = Number(svg.getAttribute('width'));
      expect(Number.isFinite(height) && height > 0).toBe(true);
      expect(svg.getAttribute('viewBox')).toBe(`0 0 ${width} ${height}`);
    }
  });
});

// --- colour is never the only encoding ---------------------------------------

describe('colour is never the only encoding', () => {
  it('a bar chart states every category AND every value as real text', () => {
    render(
      <StatsBarChart
        caption="Records by workflow step"
        rows={WORKFLOW}
        unit="records"
        total={4}
        categoryHeader="Workflow Step"
      />,
    );
    const visible = textWithoutHidden(figure('Records by workflow step'));
    for (const row of WORKFLOW) {
      expect(visible).toContain(row.label);
      expect(new RegExp(`${row.label}\\s*${row.value}`).test(visible)).toBe(true);
    }
  });

  it('every bar in a one-series chart wears the SAME slot — no rainbow over nominal rows', () => {
    render(
      <StatsBarChart
        caption="Records by workflow step"
        rows={WORKFLOW}
        unit="records"
        total={4}
        categoryHeader="Workflow Step"
      />,
    );
    const slots = [...figure('Records by workflow step').querySelectorAll('.stats-chart-bar')].map(
      (bar) => bar.getAttribute('data-slot'),
    );
    expect(slots.length).toBe(WORKFLOW.length);
    expect(new Set(slots)).toEqual(new Set(['1']));
  });

  it('a stacked bar carries a legend pairing every ramp step with its class name', () => {
    render(
      <StatsStackedBar
        caption="Share of fields by class"
        rows={EVIDENCE}
        total={40}
        unit="fields"
        categoryHeader="Class"
      />,
    );
    const items = [...figure('Share of fields by class').querySelectorAll('.stats-chart-legend-item')];
    expect(items).toHaveLength(EVIDENCE.length);
    items.forEach((item, i) => {
      expect(item.textContent).toContain(EVIDENCE[i].label);
      // The swatch keys the step and is decorative — the NAME beside it is the
      // identity channel, so a reader never has to match a colour.
      const swatch = item.querySelector('.stats-chart-swatch');
      expect(swatch?.getAttribute('data-slot')).toBe(String(i + 1));
      expect(swatch?.getAttribute('aria-hidden')).toBe('true');
    });
  });

  it('each stacked segment takes the ramp step of its own row position', () => {
    render(
      <StatsStackedBar
        caption="Share of fields by class"
        rows={EVIDENCE}
        total={40}
        unit="fields"
        categoryHeader="Class"
      />,
    );
    expect(
      [...figure('Share of fields by class').querySelectorAll('.stats-chart-segment')].map((s) =>
        s.getAttribute('data-slot'),
      ),
    ).toEqual(['1', '2', '3', '4', '5']);
  });
});

// --- selective labelling -----------------------------------------------------

describe('labels are selective, and never clipped', () => {
  it('a column chart labels the SOLE maximum and nothing else', () => {
    render(
      <StatsColumnChart
        caption="Operations by method"
        rows={METHODS}
        unit="operations"
        total={7}
        categoryHeader="HTTP Method"
      />,
    );
    const labels = [...figure('Operations by method').querySelectorAll('.stats-chart-value')].map(
      (t) => t.textContent,
    );
    expect(labels).toEqual(['4']);
  });

  it('a TIE labels nothing rather than picking one of two equal columns', () => {
    render(
      <StatsColumnChart
        caption="Tied methods"
        rows={[
          { key: 'get', label: 'GET', value: 3 },
          { key: 'post', label: 'POST', value: 3 },
        ]}
        unit="operations"
        total={6}
        categoryHeader="HTTP Method"
      />,
    );
    expect(figure('Tied methods').querySelectorAll('.stats-chart-value')).toHaveLength(0);
    // …and the values are still reachable, in the table.
    expect(tableOf('Tied methods')).toEqual([
      ['GET', '3', '50%'],
      ['POST', '3', '50%'],
    ]);
  });

  /*
   * A LABEL THAT WOULD NOT FIT IS NOT DRAWN. The failure being prevented is an
   * in-segment percentage cropped by its own mark — worse than no label at all,
   * because half a number reads as a whole one. The share stays in the legend and
   * in the table either way, so nothing is gated by the decision.
   */
  it('an in-segment share is drawn only where it measurably fits', () => {
    render(
      <StatsStackedBar
        caption="Share of fields by class"
        rows={EVIDENCE}
        total={40}
        unit="fields"
        categoryHeader="Class"
      />,
    );
    const fig = figure('Share of fields by class');
    const drawn = [...fig.querySelectorAll('.stats-chart-inlabel')];
    /*
     * At the fallback width of 560px, three of the five segments are wide enough
     * to hold their own share with padding on both sides — `Supported` at 75%
     * (420px) and the two 8% segments (42px each) — and the two 5% segments
     * (28px) are not, so they are left unlabelled rather than cropped. The exact
     * set is asserted, not just its size, so a change to the fit rule shows up
     * here as a specific difference.
     */
    expect(drawn.map((t) => t.textContent)).toEqual(['75%', '8%', '8%']);

    for (const label of drawn) {
      const slot = label.getAttribute('data-slot');
      const segment = fig.querySelector(`.stats-chart-segment[data-slot="${slot}"]`);
      const width = Number(segment?.getAttribute('width'));
      expect(width).toBeGreaterThan(estimateTextWidth(label.textContent ?? ''));
    }

    // Every share, including the four that are not drawn, is in the table.
    expect(tableOf('Share of fields by class').map(([, , pct]) => pct)).toEqual([
      '75%',
      '8%',
      '5%',
      '5%',
      '8%',
    ]);
  });
});

// --- the hover layer ---------------------------------------------------------

describe('the hover readout enhances and never gates', () => {
  it('appears on a column, names the category and the value, and is aria-hidden', () => {
    render(
      <StatsColumnChart
        caption="Operations by method"
        rows={METHODS}
        unit="operations"
        total={7}
        categoryHeader="HTTP Method"
      />,
    );
    const fig = figure('Operations by method');
    expect(fig.querySelector('.stats-chart-tooltip')).toBeNull();

    fireEvent.pointerEnter(fig.querySelectorAll('.stats-chart-hit')[1]);
    const tip = fig.querySelector('.stats-chart-tooltip');
    expect(tip).not.toBeNull();
    expect(tip!.getAttribute('aria-hidden')).toBe('true');
    expect(tip!.textContent).toContain('POST');
    expect(tip!.textContent).toContain('3 operations');

    fireEvent.pointerLeave(fig.querySelector('svg')!);
    expect(fig.querySelector('.stats-chart-tooltip')).toBeNull();
  });

  it('uses the singular noun for a value of one', () => {
    render(
      <StatsColumnChart
        caption="One op"
        rows={[{ key: 'get', label: 'GET', value: 1 }]}
        unit="operations"
        total={1}
        categoryHeader="HTTP Method"
      />,
    );
    fireEvent.pointerEnter(figure('One op').querySelector('.stats-chart-hit')!);
    expect(figure('One op').querySelector('.stats-chart-tooltip')!.textContent).toContain(
      '1 operation',
    );
  });

  /*
   * NO READOUT WHERE EVERY VALUE IS ALREADY VISIBLE. A tooltip exists so an
   * undisplayed value can be read; on the row-based forms the value is real text
   * on its own row, so a readout would only repeat the page back to the reader.
   */
  it.each([
    [
      'StatsBarChart',
      'Records by workflow step',
      () =>
        render(
          <StatsBarChart
            caption="Records by workflow step"
            rows={WORKFLOW}
            unit="records"
            total={4}
            categoryHeader="Workflow Step"
          />,
        ),
    ],
    [
      'StatsComparisonRows',
      'Operations by group',
      () =>
        render(
          <StatsComparisonRows
            caption="Operations by group"
            rows={METHODS}
            unit="operations"
            total={7}
            categoryHeader="Group"
          />,
        ),
    ],
  ] as [string, string, () => void][])(
    '%s has no hover layer, because its values are already text',
    (_name, caption, mount) => {
      mount();
      const fig = figure(caption);
      expect(fig.querySelectorAll('.stats-chart-hit')).toHaveLength(0);
      expect(fig.querySelector('.stats-chart-tooltip')).toBeNull();
    },
  );

  it('a line marker carries a hit target far larger than the 8px mark', () => {
    render(
      <StatsLineChart
        caption="Exports per week"
        rows={[
          { key: 'w1', label: 'Week 1', value: 1 },
          { key: 'w2', label: 'Week 2', value: 4 },
        ]}
        unit="records"
        xAxisLabel="Week"
      />,
    );
    const fig = figure('Exports per week');
    const marker = fig.querySelector('.stats-chart-marker');
    const hit = fig.querySelector('circle.stats-chart-hit');
    expect(Number(hit?.getAttribute('r'))).toBeGreaterThan(Number(marker?.getAttribute('r')) * 2);
  });
});

// --- charts that hold a whole ------------------------------------------------

describe('a chart never re-normalizes a whole the caller did not claim', () => {
  it('a stacked bar whose parts fall short of the total leaves the remainder empty', () => {
    render(
      <StatsStackedBar
        caption="Truncated share"
        rows={[{ key: 'a', label: 'A', value: 5 }]}
        total={10}
        unit="fields"
        categoryHeader="Class"
      />,
    );
    expect(tableOf('Truncated share')).toEqual([['A', '5', '50%']]);
    const segment = figure('Truncated share').querySelector('.stats-chart-segment');
    expect(Number(segment?.getAttribute('width'))).toBeCloseTo(CHART_FALLBACK_WIDTH / 2, 0);
  });

  it('a summary with a null total names no denominator', () => {
    render(
      <StatsComparisonRows
        caption="Operations by group"
        rows={METHODS}
        unit="operations"
        total={null}
        categoryHeader="Group"
      />,
    );
    expect(summaryOf('Operations by group')).not.toMatch(/Total/);
    // …and its Share column says so explicitly rather than printing a percentage
    // it cannot compute.
    expect(tableOf('Operations by group')).toEqual([
      ['GET', '4', 'Not Available'],
      ['POST', '3', 'Not Available'],
    ]);
  });

  it('an unmeasurable value is "Not Available" in the table and dropped from the picture', () => {
    render(
      <StatsBarChart
        caption="Partly unmeasured"
        rows={[
          { key: 'a', label: 'A', value: 2 },
          { key: 'b', label: 'B', value: Number.NaN },
        ]}
        unit="records"
        total={2}
        categoryHeader="Workflow Step"
      />,
    );
    expect(tableOf('Partly unmeasured')).toEqual([
      ['A', '2', '100%'],
      ['B', 'Not Available', 'Not Available'],
    ]);
    // The row still exists, with its label and the honest literal…
    expect(textWithoutHidden(figure('Partly unmeasured'))).toContain('B Not Available');
    // …and no bar is drawn for it, which is not the same as a bar of length zero.
    expect(figure('Partly unmeasured').querySelectorAll('.stats-chart-bar')).toHaveLength(1);
    expect(summaryOf('Partly unmeasured')).toContain('B: not available');
  });
});

// --- the line chart's mandatory x-axis disclosure ----------------------------

describe('StatsLineChart states what its x positions are', () => {
  it('renders the required axis label as visible text and as the table row header', () => {
    render(
      <StatsLineChart
        caption="Exports per week"
        rows={[
          { key: 'w1', label: 'Week 1', value: 1 },
          { key: 'w2', label: 'Week 2', value: 4 },
        ]}
        unit="records"
        xAxisLabel="Week"
      />,
    );
    expect(figure('Exports per week').querySelector('.stats-chart-xlabel')?.textContent).toBe(
      'Week',
    );
    expect(
      figure('Exports per week').querySelector('thead th')?.textContent,
    ).toBe('Week');
  });

  it('draws a 2px line and a surface ring under every marker', () => {
    render(
      <StatsLineChart
        caption="Exports per week"
        rows={[
          { key: 'w1', label: 'Week 1', value: 1 },
          { key: 'w2', label: 'Week 2', value: 4 },
        ]}
        unit="records"
        xAxisLabel="Week"
      />,
    );
    const fig = figure('Exports per week');
    expect(fig.querySelector('.stats-chart-series')?.getAttribute('stroke-width')).toBe('2');
    expect(fig.querySelectorAll('.stats-chart-marker-ring')).toHaveLength(2);
    expect(fig.querySelectorAll('.stats-chart-marker')).toHaveLength(2);
  });
});

// --- the five states ---------------------------------------------------------

describe('the chart states are five different claims', () => {
  it('loading is the app-wide polite status — never a skeleton plot', () => {
    const { container } = render(<ChartLoading label="Loading the workflow distribution…" />);
    const panel = container.querySelector('[role="status"]');
    expect(panel).not.toBeNull();
    expect(panel).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('Loading the workflow distribution…')).toBeInTheDocument();
    // The selector the whole test suite waits on, so a chart's loading state can
    // never leave a round looking settled while it is still reading.
    expect(container.querySelector('.fetch-state[role="status"]')).not.toBeNull();
    // No plot, no axis, no placeholder rows.
    expect(container.querySelector('svg')).toBeNull();
  });

  it('empty says the source answered and there was nothing — with no axis drawn', () => {
    const { container } = render(
      <ChartEmpty title="No Records to Distribute">No records were returned.</ChartEmpty>,
    );
    expect(screen.getByText('No Records to Distribute')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('error offers the recourse as a real keyboard-operable button', () => {
    let retried = 0;
    render(<ChartError message="The records could not be read." onRetry={() => (retried += 1)} />);
    const button = screen.getByRole('button', { name: 'Retry' });
    expect(button.tagName).toBe('BUTTON');
    fireEvent.click(button);
    expect(retried).toBe(1);
  });

  /*
   * ACCESS-PENDING IS NOT EMPTY AND IS NOT AN ERROR, and the difference is the
   * whole point: empty means "we looked and found nothing", access-pending means
   * "we cannot attribute anything to you". Rendering the second as the first — as
   * a zero — would state a fact nobody established.
   */
  it('access-pending is neutral, states no zero, and raises no alarm', () => {
    const { container } = render(
      <ChartAccessPending title="Not Available in This Preview">
        Records here are not associated with an account.
      </ChartAccessPending>,
    );
    expect(container.querySelector('.stats-chart-state-pending')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(container.querySelector('svg')).toBeNull();
    expect(container.textContent).not.toMatch(/\b0\b/);
  });

  it('data-source-unavailable is a fifth, distinct state', () => {
    const { container } = render(
      <ChartSourceUnavailable title="Not Recorded">
        Nothing in this build measures it.
      </ChartSourceUnavailable>,
    );
    expect(screen.getByText('Not Recorded')).toBeInTheDocument();
    // Distinguishable from access-pending in the DOM, so the two cannot be
    // silently swapped for one another.
    expect(container.querySelector('.stats-chart-state-pending')).toBeNull();
    expect(container.querySelector('.stats-chart-state-block')).not.toBeNull();
  });
});

// --- the collapsible region --------------------------------------------------

describe('TechnicalDetails', () => {
  it('is a native disclosure, collapsed by default, with its heading inside', () => {
    const { container } = render(
      <TechnicalDetails id="tech" title="Technical Details" sub="Build internals.">
        <p>Inside.</p>
      </TechnicalDetails>,
    );
    const details = container.querySelector('details');
    expect(details).not.toBeNull();
    expect(details!.hasAttribute('open')).toBe(false);

    // The heading lives in the `<summary>`, so the outline is correct whether the
    // region is open or closed — a heading OUTSIDE a disclosure would point at
    // nothing while collapsed.
    const heading = screen.getByRole('heading', { level: 2, name: 'Technical Details' });
    expect(heading.closest('summary')).not.toBeNull();
    expect(heading.id).toBe('tech');
  });

  /*
   * `<summary>` takes phrasing content optionally intermixed with HEADING
   * content. A `<p>` is neither, so the supporting line must not be one.
   */
  it('renders its supporting line as a span, which is valid inside summary', () => {
    const { container } = render(
      <TechnicalDetails id="tech" title="Technical Details" sub="Build internals.">
        <p>Inside.</p>
      </TechnicalDetails>,
    );
    const summary = container.querySelector('summary')!;
    expect(summary.querySelector('p')).toBeNull();
    expect(summary.querySelector('span.stats-card-sub')?.textContent).toBe('Build internals.');
  });

  it('opens on click, keeping its children in the document either way', () => {
    const { container } = render(
      <TechnicalDetails id="tech" title="Technical Details">
        <p>Inside.</p>
      </TechnicalDetails>,
    );
    expect(screen.getByText('Inside.')).toBeInTheDocument();
    fireEvent.click(container.querySelector('summary')!);
    expect(container.querySelector('details')!.hasAttribute('open')).toBe(true);
  });
});

// --- legend ------------------------------------------------------------------

describe('ChartLegend', () => {
  it('renders nothing for an empty list rather than an empty box', () => {
    const { container } = render(<ChartLegend items={[]} />);
    expect(container.querySelector('ul')).toBeNull();
  });

  it('pairs each entry with its figures, and keeps the swatch decorative', () => {
    const { container } = render(
      <ChartLegend
        items={[{ key: 'a', label: 'Supported', slot: 1, detail: '30 fields · 75%' }]}
      />,
    );
    const item = container.querySelector('.stats-chart-legend-item')!;
    expect(within(item as HTMLElement).getByText('Supported')).toBeInTheDocument();
    expect(within(item as HTMLElement).getByText('30 fields · 75%')).toBeInTheDocument();
    expect(item.querySelector('.stats-chart-swatch')?.getAttribute('aria-hidden')).toBe('true');
  });
});
