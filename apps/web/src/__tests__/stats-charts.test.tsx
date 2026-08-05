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

/**
 * Every value `StatsCharts.tsx` exports that is NOT a chart form.
 *
 * ── Why this list exists ────────────────────────────────────────────────────
 *
 * The `it.each(ALL_FORMS)` block below used to claim that a sixth chart form
 * "cannot be added with only four of the five guarantees". `ALL_FORMS` is a
 * HAND-WRITTEN list, so it claimed nothing of the sort: an independent reviewer
 * added `StatsDonut` — no summary sentence, no data table, no `aria-hidden`, no
 * `focusable="false"`, and colour as its only encoding — mounted it in
 * production and gave it its own wrapper class, and all 2,667 frontend tests plus
 * all 93 browser tests passed. Omitting a form from a list is not a failure; it
 * is the default.
 *
 * So the guard is driven off the MODULE'S OWN EXPORTS instead. The export set
 * must be exactly `ALL_FORMS` plus this list, which means a new export cannot
 * ship until someone classifies it — and classifying it as a form puts it
 * through the five guarantees.
 *
 * The remaining hole, stated rather than papered over: a chart form could be
 * mis-filed HERE. `no chart form is mis-filed as a helper` below closes the
 * shape of it the reviewer actually used (a `Stats*`-named component), which is
 * this file's naming convention for a chart form; a chart form named
 * `PieChart` would still have to be caught by review.
 */
const NON_CHART_EXPORTS = [
  'CHART_FALLBACK_WIDTH',
  'CHART_MIN_WIDTH',
  'IN_SEGMENT_LABEL_SLOTS',
  'ChartAccessPending',
  'ChartEmpty',
  'ChartError',
  'ChartFrame',
  'ChartLegend',
  'ChartLoading',
  'ChartSourceUnavailable',
  'TechnicalDetails',
  'estimateTextWidth',
  'useChartWidth',
] as const;

describe('ALL_FORMS is driven by the module, not by convention', () => {
  it('accounts for every export — a new chart form cannot ship unlisted', async () => {
    const module = await import('../screens/statistics/StatsCharts');
    expect(Object.keys(module).sort()).toEqual(
      [...ALL_FORMS.map(([name]) => name), ...NON_CHART_EXPORTS].sort(),
    );
  });

  it('no chart form is mis-filed as a helper', () => {
    // `Stats*` is this module's naming convention for a chart form, so a
    // `Stats*` component parked in the helper list is the mis-classification
    // that would re-open the hole above.
    for (const name of NON_CHART_EXPORTS) {
      expect(name, `${name} is named like a chart form; it belongs in ALL_FORMS`).not.toMatch(
        /^Stats[A-Z]/,
      );
    }
    for (const [name] of ALL_FORMS) expect(name).toMatch(/^Stats[A-Z]/);
  });
});

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

// --- the domain: the largest value, never the total -------------------------

/**
 * THE SCALE RULE, PINNED.
 *
 * "The domain is a nice maximum over the LARGEST VALUE, not the total" is the
 * headline claim of this whole slice — it is what makes these bars a chart
 * rather than the row of progress bars `StageBars` drew, it is stated three
 * times in `StatsCharts.tsx` and, unlike the other two, it is PRINTED ON SCREEN:
 * `StatisticsPage.tsx` tells the reader "The scale runs to the largest bucket,
 * not to the total, so small differences stay visible."
 *
 * Nothing asserted it. Changing both call sites to `niceMax(total ?? …)` —
 * reinstating exactly the deleted behaviour and making that on-screen sentence
 * false — passed all 2,667 frontend tests.
 *
 * The fixture is chosen so the two domains cannot be confused: a maximum of 2
 * against a total of 40 gives ticks `0 · 1 · 2` under the rule and
 * `0 · 10 · 20 · 30 · 40 · 50` under the total. One assertion per scaled form.
 */
const SMALL_OF_MANY = [
  { key: 'a', label: 'Alpha', value: 1 },
  { key: 'b', label: 'Beta', value: 2 },
];
const BIG_TOTAL = 40;

const ticksOf = (caption: string, selector: string): string[] =>
  [...figure(caption).querySelectorAll(selector)].map((t) => t.textContent ?? '');

describe('the domain is the largest value, not the total', () => {
  it('StatsBarChart labels its shared axis 0 · 1 · 2 for a max of 2 out of 40', () => {
    render(
      <StatsBarChart
        caption="Records by workflow step"
        rows={SMALL_OF_MANY}
        unit="records"
        total={BIG_TOTAL}
        categoryHeader="Workflow Step"
      />,
    );
    expect(ticksOf('Records by workflow step', '.stats-chart-axis .stats-chart-tick')).toEqual([
      '0',
      '1',
      '2',
    ]);
    // …and the largest bar therefore spans the whole plot, which is the visible
    // consequence the on-screen sentence promises.
    const widest = Math.max(
      ...[...figure('Records by workflow step').querySelectorAll('.stats-chart-bar')].map((b) =>
        Number(b.getAttribute('width')),
      ),
    );
    expect(widest).toBe(CHART_FALLBACK_WIDTH);
  });

  it('StatsColumnChart labels its y axis 0 · 1 · 2 for a max of 2 out of 40', () => {
    render(
      <StatsColumnChart
        caption="Operations by method"
        rows={SMALL_OF_MANY}
        unit="operations"
        total={BIG_TOTAL}
        categoryHeader="HTTP Method"
      />,
    );
    expect(ticksOf('Operations by method', '.stats-chart-tick-y')).toEqual(['0', '1', '2']);
  });

  it('StatsComparisonRows gives the largest row the full track — it draws no axis', () => {
    render(
      <StatsComparisonRows
        caption="Operations by group"
        rows={SMALL_OF_MANY}
        unit="operations"
        total={BIG_TOTAL}
        categoryHeader="Group"
      />,
    );
    const fig = figure('Operations by group');
    // No tick strip at all on this form (see its own doc comment), so the domain
    // has to be read off the marks: 2-of-40 fills the track, 1-of-40 is half of
    // it. Against the TOTAL these would be 5% and 2.5% slivers.
    expect(ticksOf('Operations by group', '.stats-chart-tick')).toEqual([]);
    const widths = [...fig.querySelectorAll('.stats-chart-bar')].map((b) =>
      Number(b.getAttribute('width')),
    );
    expect(widths).toEqual([CHART_FALLBACK_WIDTH / 2, CHART_FALLBACK_WIDTH]);
  });

  it('StatsLineChart labels its y axis 0 · 1 · 2 for a max of 2', () => {
    render(
      <StatsLineChart
        caption="Exports per week"
        rows={SMALL_OF_MANY}
        unit="records"
        xAxisLabel="Week"
      />,
    );
    expect(ticksOf('Exports per week', '.stats-chart-tick-y')).toEqual(['0', '1', '2']);
  });
});

// --- the declared palette ---------------------------------------------------

/**
 * THE PALETTE, PINNED — and pinned as a CSS FACT, because that is what it is.
 *
 * "COLOUR NEVER ENCODES IDENTITY. The six `--stats-cat-*` slots are gone" is the
 * second headline claim of the slice, and nothing asserted it either: an
 * independent reviewer re-declared all six `--stats-cat-1..6` and painted the
 * first three bars of every one-series chart with them — the exact anti-pattern
 * `StatsPrimitives.tsx`'s `StageBars` note says was eliminated — and all 2,667
 * frontend tests plus all 93 browser tests passed.
 *
 * A rendered-DOM assertion could not have caught it (jsdom applies no
 * stylesheet, and `data-slot` was unchanged), so the stylesheet is read as text.
 */
/** WCAG 2.x relative luminance and contrast ratio. Six lines, no dependency. */
const srgbOf = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const luminance = (hex: string) =>
  srgbOf(hex)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce((acc, c, i) => acc + [0.2126, 0.7152, 0.0722][i] * c, 0);
const contrastRatio = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

function declaredHex(name: string, from: string): string {
  const found = new RegExp(`${name}\\s*:\\s*(#[0-9a-fA-F]{6})`).exec(from);
  expect(found, `${name} must be declared as a 6-digit hex`).not.toBeNull();
  return found![1].toLowerCase();
}

/**
 * The 148 CSS named colours. Listed because `border-color: red` is a likelier debug
 * leftover than `border-color: #ff0000`, and a notation-only scan (`#hex` /
 * `rgb()` / `hsl()`) reads a named colour as no colour at all.
 *
 * Word-boundary anchored below, so `red` does not match inside `darkred` — and
 * `darkred` is on the list in its own right.
 */
const CSS_NAMED_COLOURS: readonly string[] =
  ('aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue ' +
    'blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk ' +
    'crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki ' +
    'darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen ' +
    'darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue ' +
    'dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite ' +
    'gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki ' +
    'lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan ' +
    'lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen ' +
    'lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen ' +
    'magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen ' +
    'mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream ' +
    'mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid ' +
    'palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum ' +
    'powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown ' +
    'seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen ' +
    'steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow ' +
    'yellowgreen').split(' ');

/**
 * Any literal colour, in any notation, plus every CSS named colour.
 *
 * AT MODULE SCOPE because BOTH colour guards need it: the stylesheet scan below and
 * the inline-style scan in `the components emit no inline colour`. Round 3 had two
 * different colour patterns in this file — the stylesheet one listed properties by
 * name, the inline one listed properties by name too, and each list was missing a
 * different member. Sharing the VALUE pattern is what stops them diverging again.
 *
 * Applied to a VALUE, never to a whole declaration: `white-space: nowrap` contains
 * `\bwhite\b` in its PROPERTY, and matching that would be a false positive.
 */
const LITERAL_COLOUR_ANYWHERE = new RegExp(
  `#[0-9a-fA-F]{3,8}|\\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix|device-cmyk)\\(` +
    `|\\b(?:${CSS_NAMED_COLOURS.join('|')})\\b`,
  'i',
);

describe('the chart palette declared on .statistics', () => {
  /**
   * The stylesheet with every `/* … *\/` comment removed.
   *
   * Stripped for the same reason `my-stats.test.tsx`'s trap 1 matches against
   * import statements rather than whole text: this file's own header NAMES the
   * six slots in order to explain that they are gone, so a raw-text scan would
   * be satisfied by deleting the explanation. What must be absent is the CODE.
   */
  async function statisticsCss(): Promise<string> {
    const raw = String((await import('../screens/statistics/statistics.css?raw')).default);
    return raw.replace(/\/\*[\s\S]*?\*\//g, '');
  }

  it('declares and references no categorical slots anywhere', async () => {
    const css = await statisticsCss();
    // Not scoped to the `.statistics` block: a `--stats-cat-*` slot re-declared
    // under any selector, or referenced by any rule, is the same regression.
    expect(css).not.toMatch(/--stats-cat-/);
    // …and the explanation of their removal is still in the file, so this test
    // cannot be made to pass by deleting the reasoning.
    const raw = String((await import('../screens/statistics/statistics.css?raw')).default);
    expect(raw, 'the removed slots are still named in the file').toMatch(/--stats-cat-/);
    expect(raw, 'and the reason they were removed is still stated').toMatch(/slots are gone/i);
  });

  /** The six chart colours this surface is allowed to declare, and no more. */
  const CHART_COLOUR_TOKENS = [
    '--stats-ramp-1',
    '--stats-ramp-2',
    '--stats-ramp-3',
    '--stats-ramp-4',
    '--stats-ramp-5',
    '--stats-series',
  ] as const;

  it('declares exactly one series colour and a five-step ordinal ramp, and nothing else', async () => {
    const css = await statisticsCss();
    const block = /^\.statistics\s*\{([\s\S]*?)^\}/m.exec(css);
    expect(block, 'the .statistics page-root block must exist').not.toBeNull();
    const declared = [...block![1].matchAll(/^\s*(--[a-z0-9-]+)\s*:/gm)].map((m) => m[1]);
    expect(declared.sort()).toEqual([...CHART_COLOUR_TOKENS]);

    /*
     * …AND NOWHERE ELSE IN THE FILE. The assertion above is scoped to the
     * page-root block, so a custom property declared under ANY descendant
     * selector was invisible to it — which is the round-1 categorical-slot
     * regression coming back under a new name. Measured, an independent reviewer
     * shipped this and passed 2697 tests:
     *
     *     .statistics .stats-chart-plot { --ident-a: #b0522c; … }
     *     .statistics .stats-chart-bar[data-slot='1'] { fill: var(--ident-a); }
     *
     * Declarations only — `var(--surface)` and friends are REFERENCES to tokens
     * this file does not own, and there are 33 of those, all of which are fine.
     * What must not exist is a seventh colour declared here.
     */
    const declaredAnywhere = [...css.matchAll(/(?:^|[{;\s])(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]);
    expect(
      [...new Set(declaredAnywhere)].sort(),
      'a custom property is declared outside the page-root block',
    ).toEqual([...CHART_COLOUR_TOKENS]);
  });

  /**
   * THE IN-SEGMENT LABEL RULE, COMPUTED rather than trusted.
   *
   * `statistics.css` used to put `--surface` (white) on ramp slots 1–3 and
   * justify slot 3 as "4.06:1 clears the 3:1 that applies to an 11px semibold
   * label as large-ish text". Three things were wrong: the ratio is 4.32:1, 11px
   * semibold is not WCAG large text, and the applicable threshold is 4.5:1 —
   * which 4.32:1 fails. It was unexercised at the fallback width and lands in
   * axe's `incomplete` bucket in a browser, so no ratchet would ever have seen it.
   *
   * This test recomputes the whole table from the stylesheet and the token file
   * every run, so re-stepping the ramp or repainting a label re-derives the
   * answer instead of leaving a stale sentence behind.
   */
  it('draws an in-segment label only where its colour clears 4.5:1 on the fill', async () => {
    const css = await statisticsCss();
    const tokens = String((await import('../styles/tokens.css?raw')).default);

    const hexOf = declaredHex;
    const contrast = contrastRatio;

    const ramp = [1, 2, 3, 4, 5].map((n) => hexOf(`--stats-ramp-${n}`, css));
    // The two colours the rule may choose between, read from the token file so a
    // token change is picked up rather than re-hard-coded here.
    const candidates = {
      '--surface': hexOf('--surface', tokens),
      '--text-heading': hexOf('--text-heading', tokens),
    };

    /** Which slots the stylesheet actually paints a label on, and with what. */
    const painted = new Map<number, string>();
    for (const [, selectors, decl] of css.matchAll(
      /((?:\.statistics \.stats-chart-inlabel\[data-slot='\d'\],?\s*)+)\{([^}]*)\}/g,
    )) {
      const colour = /color\s*:\s*var\((--[a-z-]+)\)/.exec(decl)?.[1];
      expect(colour, 'an in-segment label must wear a token, not a literal').toBeTruthy();
      for (const [, slot] of selectors.matchAll(/data-slot='(\d)'/g)) {
        painted.set(Number(slot), colour!);
      }
    }

    const { IN_SEGMENT_LABEL_SLOTS } = await import('../screens/statistics/StatsCharts');

    for (let slot = 1; slot <= ramp.length; slot++) {
      const fill = ramp[slot - 1];
      const best = Math.max(...Object.values(candidates).map((c) => contrast(c, fill)));
      const legible = best >= 4.5;

      // The component's list and the measured answer must agree, in both
      // directions: a legible slot must be labelled, an illegible one must not.
      expect(
        IN_SEGMENT_LABEL_SLOTS.includes(slot),
        `slot ${slot} (${fill}): best available label contrast is ${best.toFixed(2)}:1, so it ` +
          `${legible ? 'MUST' : 'must NOT'} be in IN_SEGMENT_LABEL_SLOTS`,
      ).toBe(legible);

      if (!legible) {
        expect(painted.has(slot), `slot ${slot} must have no label colour rule`).toBe(false);
        continue;
      }
      const token = painted.get(slot);
      expect(token, `slot ${slot} is labelled and needs a colour rule`).toBeTruthy();
      const ratio = contrast(candidates[token as keyof typeof candidates], fill);
      expect(
        ratio,
        `slot ${slot}: ${token} on ${fill} is ${ratio.toFixed(2)}:1, below the 4.5:1 that applies ` +
          `to an 11px semibold label (WCAG large text starts at 18.66px bold)`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  /**
   * EVERY PIECE OF CHART TEXT CLEARS AA ON BOTH CARD SURFACES.
   *
   * The axis ticks shipped at `--text-tertiary` #78838f — 3.86:1 on #ffffff,
   * 3.76:1 on #fbfcfd, at 10.5px, against a 4.5:1 requirement. A brand-new WCAG
   * 1.4.3 failure on markup this slice authored, and the automated ratchet was
   * close to blind to it: axe reported ONE of the y-ticks as a violation, put
   * five more in `incomplete` (the SVG behind them defeats background
   * resolution) and never saw the three x-axis ticks, which sit in the
   * uncollapsed main flow. A count-based baseline cannot protect a defect it
   * cannot see, so this computes the ratio instead of counting nodes.
   *
   * `.stats-chart-inlabel` is excluded because it sits on a ramp fill, not on a
   * card surface — the test above covers it against the fill it actually has.
   *
   * SCOPED TO `.stats-chart-*` on purpose. `.stat-card-note` still uses
   * `--text-tertiary` at 11.5px and still fails; that is PRE-EXISTING, app-wide
   * debt recorded in `e2e/a11y-baseline.ts` (four instances on
   * `statistics-example` alone), and fixing that token moves counts on many
   * surfaces at once. Widening this test to the whole file would therefore fail
   * today — which is exactly why the limit is stated rather than assumed.
   */
  it('every chart text token clears 4.5:1 on both card surfaces', async () => {
    const css = await statisticsCss();
    const tokens = String((await import('../styles/tokens.css?raw')).default);
    const surfaces = ['--surface', '--surface-subtle'].map((t) => declaredHex(t, tokens));

    const seen: string[] = [];
    for (const [, selectors, decl] of css.matchAll(
      /((?:\.statistics \.stats-chart-[a-z-]*(?:\[[^\]]*\])?,?\s*)+)\{([^}]*)\}/g,
    )) {
      if (selectors.includes('inlabel')) continue; // sits on a fill; see above
      const token = /(?:^|[\s;])color\s*:\s*var\((--[a-z-]+)\)/.exec(decl)?.[1];
      if (token === undefined) continue;
      const fg = declaredHex(token, tokens);
      seen.push(token);
      for (const bg of surfaces) {
        const ratio = contrastRatio(fg, bg);
        expect(
          ratio,
          `${selectors.trim().split('\n')[0]} uses ${token} ${fg}, which is ${ratio.toFixed(2)}:1 ` +
            `on ${bg} — below the 4.5:1 WCAG 1.4.3 requires for text under 18.66px bold`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
    // Vacuity guard: the regex above must actually be finding rules.
    expect(seen.length, 'no chart text rule was inspected — the scan is broken').toBeGreaterThanOrEqual(8);
    expect(seen, 'the axis ticks in particular must be covered').toContain('--text-muted');
  });

  /*
   * ── THE COLOUR POLICY, BOUND PER SELECTOR ─────────────────────────────────
   *
   * TWO GENERATIONS OF THIS TEST OVERSTATED WHAT IT CHECKED, in different ways,
   * and both are recorded because the second was introduced while fixing the first.
   *
   * ROUND 1 — TITLE OVER BODY. It read "every mark rule draws from those six slots
   * and no other colour" while the body only rejected a literal `#hex` / `rgb()` /
   * `hsl()`. It never inspected the var NAME, so `fill: var(--anything)` passed —
   * and a reviewer declared three identity hues on a descendant selector and
   * painted three slots with them through 2697 passing tests.
   *
   * ROUND 2 — A UNION THAT ENFORCED NO DIRECTION. The fix resolved the name against
   * `[...DATA_INK, ...CHROME]` and the comment claimed the two were "listed
   * separately so a ramp colour cannot be smuggled in as chrome or vice versa".
   * One union membership test cannot say that. Negative control, measured at
   * 4b86f7e: `--stats-ramp-3` on `.stats-chart-grid` AND `--border` on
   * `.stats-chart-segment[data-slot='3']`, both at once — 59 of 59 tests passed.
   * The gridline became a data colour and the middle of the ramp became a hairline,
   * and nothing in this file objected.
   *
   * ROUND 2 ALSO SCANNED TOO FEW PROPERTIES. It extracted `fill|stroke` only, so a
   * literal colour in `background` or `color` was unguarded — including on
   * `.stats-chart-swatch` and `.stats-chart-tooltip-key`, which are the legend and
   * readout keys that BIND a legend entry to a segment, i.e. exactly where a
   * categorical identity hue would be reintroduced. Negative control, measured at
   * 4b86f7e: three identity hues as literal hex on swatches 1–3 — 59 of 59 passed.
   *
   * ROUND 3 SCANNED TOO FEW PROPERTIES AGAIN — including the LONGHAND of the very
   * property round 2 added. The pattern was
   *
   *     /(?:^|[;{\s])(fill|stroke|background|color)\s*:\s*([^;]+)/g
   *
   * `background` required a `:` immediately after it, and `color` required a
   * `[;{\s]` immediately before it, so `background-color:` matched NEITHER
   * alternative — and nor did `border-color`, `outline` or `box-shadow`. Negative
   * control, measured at 134eac2 — four literal identity hues appended to
   * `statistics.css`:
   *
   *     .stats-chart-swatch[data-slot='1'] { box-shadow: inset 0 0 0 99px #b0522c; }
   *     .stats-chart-swatch[data-slot='2'] { background-color: #7a4fa3; }
   *     .stats-chart-grid { border-color: #2f8f6b; outline: 1px solid #d94f4f; }
   *
   * 66 of 66 tests in this file passed, and 2774 of 2774 across the whole frontend
   * suite. `box-shadow: inset 0 0 0 99px` repaints a legend swatch entirely, and
   * `background-color` repaints swatch 2 outright.
   *
   * SO THE SCAN NOW FAILS CLOSED. It matches EVERY declaration and skips a closed
   * list of properties known not to carry a colour ({@link NON_COLOUR_PROPERTIES}),
   * rather than allow-listing the colour ones — because three rounds running, the
   * hole was a property nobody had listed. Two tiers:
   *
   *   · {@link PURE_COLOUR_PROPERTIES} — the whole value is a colour, so the strict
   *     rule applies: one plain `var()` or a listed keyword, and the selector's own
   *     class must be allowed to wear that token.
   *   · everything else that is scanned (today: `border`, `border-top`,
   *     `border-bottom`, `outline`, `box-shadow` — shorthands whose value is mostly
   *     geometry) — checked for a LITERAL colour only, since a token check would
   *     have to parse a shorthand. The ramp-as-chrome direction is covered for
   *     these by `a data-ink token is referenced ONLY by a class allowed to encode
   *     a value` below, which reads every property.
   *
   * WHAT IS STILL NOT READ, stated rather than implied: the declarations of the 39
   * properties listed in `NON_COLOUR_PROPERTIES`. That list is a documentation
   * device more than a filter — MEASURED today, it withholds 160 declarations and
   * NOT ONE of their values would trip the literal-colour scan, so deleting the
   * list would change no result. It exists so that the claim "these cannot carry a
   * colour" is written down and reviewable, and so that a genuine false positive
   * (a `font-family` containing the word `tan`, say) has a named home instead of
   * prompting somebody to narrow the scan again.
   *
   * SO THE POLICY IS PER SELECTOR. Every colour-bearing declaration under a
   * `.stats-chart-*` rule is looked up by its own class, and each class names the
   * exact value set it may carry. The table is closed: a class that declares a
   * colour and is not in it fails, so a new chart class cannot ship unclassified.
   */

  /** Data ink: the only colours that may encode a value. */
  const DATA_INK: readonly string[] = [...CHART_COLOUR_TOKENS];
  /** Text tokens. Chart text may wear these and nothing else. */
  const TEXT_INK: readonly string[] = [
    '--text-heading',
    '--text-strong',
    '--text-secondary',
    '--text-muted',
    '--text-slate',
    '--text-primary',
    '--action',
  ];
  /** Non-colour keywords a declaration may legally carry. */
  const KEYWORDS: readonly string[] = ['transparent', 'none', 'currentColor'];

  /**
   * Properties whose ENTIRE value is a colour, so the strict rule can apply to it
   * without parsing a shorthand. Longhands are spelled out: `background-color` is
   * here because its absence is exactly what round 3 shipped.
   */
  const PURE_COLOUR_PROPERTIES: readonly string[] = [
    'accent-color',
    'background',
    'background-color',
    'border-bottom-color',
    'border-color',
    'border-left-color',
    'border-right-color',
    'border-top-color',
    'caret-color',
    'color',
    'column-rule-color',
    'fill',
    'flood-color',
    'lighting-color',
    'outline-color',
    'stop-color',
    'stroke',
    'text-decoration-color',
  ];

  /**
   * Properties this surface declares that cannot carry a colour. CLOSED, and the
   * direction is the point: a property in NEITHER this list nor
   * `PURE_COLOUR_PROPERTIES` is still scanned for a literal colour, so the next
   * property nobody thought of is covered by default rather than skipped.
   *
   * Every entry is a property `statistics.css` actually declares under a chart
   * rule — measured, 39 of them — so the list documents a real decision instead of
   * pre-authorising a guess.
   */
  const NON_COLOUR_PROPERTIES: readonly string[] = [
    'align-items',
    'border-collapse',
    'border-radius',
    'display',
    'flex',
    'flex-direction',
    'flex-wrap',
    'font-size',
    'font-variant-numeric',
    'font-weight',
    'gap',
    'grid-column',
    'grid-template-columns',
    'height',
    'left',
    'line-height',
    'list-style',
    'margin',
    'margin-top',
    'max-width',
    'min-width',
    'outline-offset',
    'overflow',
    'overflow-wrap',
    'padding',
    'padding-bottom',
    'pointer-events',
    'position',
    'stroke-linecap',
    'stroke-linejoin',
    'stroke-width',
    'text-align',
    'text-overflow',
    'top',
    'transform',
    'vertical-align',
    'white-space',
    'width',
    'z-index',
  ];

  /** Any literal colour, in any notation, plus every CSS named colour. */
  const LITERAL_COLOUR = LITERAL_COLOUR_ANYWHERE;

  /**
   * The ONE literal colour this surface declares, enumerated so it cannot widen.
   *
   * A neutral drop shadow on the tooltip — no design token exists for a shadow
   * colour, and it encodes nothing. Keyed by normalised selector, property AND
   * exact value, so changing the colour fails and adding a second entry lands in
   * the diff next to whatever it excuses.
   */
  const LITERAL_COLOUR_EXCEPTIONS: readonly string[] = [
    '.statistics .stats-chart-tooltip box-shadow 0 2px 8px rgb(17 26 36 / 12%)',
  ];

  /**
   * What each `.stats-chart-*` class may paint with. Closed: an unlisted class that
   * declares a colour fails.
   *
   * The three groups are the point of the table. Only the first may name a ramp
   * step or the series colour; the chrome entries name ONE token each, spelled out,
   * so "it is chrome" cannot be used to admit an arbitrary token; text may only
   * wear text tokens.
   */
  const COLOUR_POLICY: Readonly<Record<string, readonly string[]>> = {
    // ── data ink · the marks that encode a value, plus the two keys that BIND a
    //    legend or readout entry to one. Nothing else may name a ramp step.
    'stats-chart-bar': DATA_INK,
    'stats-chart-marker': DATA_INK,
    'stats-chart-series': DATA_INK,
    'stats-chart-segment': DATA_INK,
    // The unslotted swatch is a fallback for a key with no slot, hence the one
    // chrome token beside the ramp.
    'stats-chart-swatch': [...DATA_INK, '--border-strong'],
    'stats-chart-tooltip-key': DATA_INK,
    // ── chrome · geometry and surfaces. One token each.
    'stats-chart-marker-ring': ['--surface'],
    'stats-chart-grid': ['--border-faint'],
    'stats-chart-axis-rule': ['--border'],
    'stats-chart-hit': ['transparent'],
    'stats-chart-tooltip': ['--surface'],
    'stats-chart-state-block': ['--surface-subtle'],
    // `--cover-border` became visible only when the scan started reading
    // `border-color`; it is the pending block's own hairline, declared beside the
    // cover background it belongs to.
    'stats-chart-state-pending': ['--cover-bg', '--cover-border'],
    // ── text · the contrast test above computes the RATIOS these have to clear;
    //    this only keeps them out of the data set and the data set out of them.
    'stats-chart-caption': TEXT_INK,
    'stats-chart-note': TEXT_INK,
    'stats-chart-row-label': TEXT_INK,
    'stats-chart-row-value': TEXT_INK,
    'stats-chart-tick': TEXT_INK,
    'stats-chart-value': TEXT_INK,
    'stats-chart-cat': TEXT_INK,
    'stats-chart-xlabel': TEXT_INK,
    'stats-chart-legend-label': TEXT_INK,
    'stats-chart-legend-detail': TEXT_INK,
    'stats-chart-tooltip-value': TEXT_INK,
    'stats-chart-tooltip-label': TEXT_INK,
    'stats-chart-table-toggle': TEXT_INK,
    'stats-chart-table': TEXT_INK,
    'stats-chart-state': TEXT_INK,
    'stats-chart-state-title': TEXT_INK,
    'stats-chart-state-label': TEXT_INK,
    // ── the one deliberate crossing: text set INSIDE a coloured fill, which is
    //    why `--surface` (white on the two dark ramp steps) is legal here.
    'stats-chart-inlabel': ['--surface', '--text-heading'],
  };

  /** The classes the table permits to name a data-ink token. */
  const dataMarkClasses = Object.entries(COLOUR_POLICY)
    .filter(([, allowed]) => allowed.includes('--stats-ramp-3'))
    .map(([cls]) => cls)
    .sort();

  /** The last `.stats-chart-*` class in one comma-separated selector part. */
  function chartClassOf(selectorPart: string): string | null {
    const classes = [...selectorPart.matchAll(/\.(stats-chart-[a-z0-9-]*)/g)].map((m) => m[1]);
    return classes.length === 0 ? null : classes[classes.length - 1];
  }

  /**
   * The stylesheet with every at-rule WRAPPER removed and its body hoisted to the
   * top level, recursively.
   *
   * ROUND 3 DEFECT, MEASURED. `rulesOf`'s `\{([^}]*)\}` cannot cross a `}`, so on
   * `@media (…) { .stats-chart-x { … } }` the first match came back with
   * `selector = "@media (…)"` and the nested rule sitting INSIDE `declarations` —
   * and the `/\.stats-chart-/` selector filter then discarded the whole thing.
   * Measured at 134eac2: a literal hue in the FIRST rule inside an `@media` block
   * passed 66 of 66 tests in this file; the SAME rule placed SECOND was caught,
   * because by then the scan had resynchronised on the inner braces.
   * `statistics.css` has four `@media` blocks and none of them contains a chart
   * rule, so the exposure was latent rather than live.
   *
   * Excluding `@` from the selector pattern does NOT fix it: the engine simply
   * starts the match one character later and reports `selector = "media (…)"`,
   * with the nested rule still buried in the declarations. The wrapper has to go.
   *
   * `@keyframes` and `@font-face` bodies are hoisted too. That is harmless: a
   * keyframe step (`0% { … }`) becomes a rule with no chart class and is filtered
   * out, and a hoisted `@font-face` body carries no `{`, so `rulesOf` never sees
   * it as a rule at all.
   *
   * NATIVE CSS NESTING IS NOT HANDLED, and this is the one place a reader will be
   * looking, so it is recorded here rather than left to be rediscovered. Flattening
   * an at-rule wrapper is possible because the wrapper is recognisable by its `@`;
   * a nested rule is not, and `rulesOf`'s `[^{}]+` selector pattern cannot express
   * one. So `.statistics { & .stats-chart-bar { fill: #b0522c } }` yields
   * `selector = ".statistics"`, the `.stats-chart-` filter discards it, and — worse
   * than a miss — `scanned.length` stays put, so the count pin does not fire either.
   * It fails SILENTLY, not closed.
   *
   * Left unhandled rather than solved because nesting has no precedent in this
   * repo: every `&` in all 24 stylesheets under `apps/web/src` is inside a comment.
   * Note the asymmetry that limits the damage — CONVERTING an existing rule to
   * nesting IS caught, because `scanned` drops; only ADDING a nested rule is
   * invisible. If nesting is ever adopted, reject it outright after flattening
   * (`expect(css).not.toMatch(/\{[^{}]*\{/)`) rather than trying to parse it.
   */
  function withoutAtRuleWrappers(css: string): string {
    let out = '';
    let index = 0;
    while (index < css.length) {
      const at = css.indexOf('@', index);
      if (at === -1) {
        out += css.slice(index);
        break;
      }
      out += css.slice(index, at);
      const brace = css.indexOf('{', at);
      const semicolon = css.indexOf(';', at);
      // A statement at-rule (`@import …;`, `@charset …;`) has no block to hoist.
      if (brace === -1 || (semicolon !== -1 && semicolon < brace)) {
        index = semicolon === -1 ? css.length : semicolon + 1;
        continue;
      }
      let depth = 1;
      let end = brace + 1;
      while (end < css.length && depth > 0) {
        if (css[end] === '{') depth += 1;
        else if (css[end] === '}') depth -= 1;
        end += 1;
      }
      // Separated by spaces so a hoisted body cannot weld onto its neighbour, and
      // recursive so an at-rule nested inside an at-rule also goes.
      out += ` ${withoutAtRuleWrappers(css.slice(brace + 1, end - 1))} `;
      index = end;
    }
    return out;
  }

  /** Every `selector { … }` rule of the comment-stripped, at-rule-flattened sheet. */
  function rulesOf(css: string): { selector: string; declarations: string }[] {
    return [...withoutAtRuleWrappers(css).matchAll(/([^{}]+)\{([^}]*)\}/g)].map((m) => ({
      selector: m[1],
      declarations: m[2],
    }));
  }

  it('the data-mark classes are exactly the six the policy names', () => {
    // Derived from the table, then pinned: widening the table is what this test
    // makes visible, since the table is also what the scan below trusts.
    expect(dataMarkClasses).toEqual([
      'stats-chart-bar',
      'stats-chart-marker',
      'stats-chart-segment',
      'stats-chart-series',
      'stats-chart-swatch',
      'stats-chart-tooltip-key',
    ]);
  });

  it('every chart colour declaration is literal-free, and every pure-colour one wears a token its OWN selector is allowed', async () => {
    const css = await statisticsCss();

    const seen: string[] = [];
    const scanned: string[] = [];
    for (const { selector, declarations } of rulesOf(css)) {
      if (!/\.stats-chart-/.test(selector)) continue;
      const where = selector.replace(/\s+/g, ' ').trim();
      // EVERY declaration, not a list of colour properties — see the round-3 note
      // above. `[a-z-]+` also catches a custom property, which is correct: a
      // `--ident: #b0522c` under a chart rule is the round-1 regression by hand.
      for (const [, property, rawValue] of declarations.matchAll(
        /(?:^|[;{\s])([a-z-]+)\s*:\s*([^;]+)/g,
      )) {
        const value = rawValue.trim();
        if (NON_COLOUR_PROPERTIES.includes(property)) continue;
        scanned.push(`${where} ${property} ${value}`);

        // 1 · no literal colour, in ANY notation, in ANY scanned property —
        //     including the shorthands (`border`, `outline`, `box-shadow`) the
        //     strict tier below cannot parse. This is the tier that catches the
        //     four hues round 3 shipped past.
        if (!LITERAL_COLOUR_EXCEPTIONS.includes(`${where} ${property} ${value}`)) {
          expect(
            value,
            `${where} { ${property}: ${value} } carries a literal colour. A colour this ` +
              `stylesheet does not name as a token is a colour no policy governs — put it in a ` +
              `token, or enumerate it in LITERAL_COLOUR_EXCEPTIONS with a reason.`,
          ).not.toMatch(LITERAL_COLOUR);
        }

        if (!PURE_COLOUR_PROPERTIES.includes(property)) continue;

        // 2 · one plain `var()` or a listed keyword — no fallback colour hiding in
        //     a second argument, no space-separated list.
        const named = KEYWORDS.includes(value)
          ? value
          : (/^var\(\s*(--[a-z0-9-]+)\s*\)$/.exec(value)?.[1] ?? null);
        expect(named, `must be one plain var() or a listed keyword: "${value}"`).not.toBeNull();

        // 3 · and its own selector must be allowed to wear it. Per PART, so a
        //     comma-grouped rule has to be legal for every selector in the group.
        let classesInRule = 0;
        for (const part of selector.split(',')) {
          const cls = chartClassOf(part);
          if (cls === null) continue;
          classesInRule += 1;
          const allowed = COLOUR_POLICY[cls];
          expect(
            allowed,
            `.${cls} declares ${property} and has no COLOUR_POLICY entry — classify it as ` +
              `data ink, chrome or text rather than leaving it unchecked`,
          ).toBeDefined();
          expect(
            allowed,
            `.${cls} { ${property}: ${value} } is not permitted for that selector. A ramp step ` +
              `outside the mark classes is a data colour used as chrome; a chrome or text token ` +
              `on a mark is a value drawn in the wrong ink.`,
          ).toContain(named);
          seen.push(`${cls} ${property} ${value}`);
        }
        expect(classesInRule, `no chart class found in selector "${selector.trim()}"`).toBeGreaterThan(0);
      }
    }

    /*
     * Vacuity guards, both MEASURED today.
     *
     * · 51 checked (selector-part, property) pairs in the strict tier, over 48
     *   pure-colour declarations. The three extra are the comma-grouped rules,
     *   each checked once per class in the group —
     *   `.stats-chart-bar`/`.stats-chart-marker` and the two
     *   `.stats-chart-inlabel` slot pairs. Round 2's `fill|stroke` scan saw 11 of
     *   those 48; round 3's `fill|stroke|background|color` saw 47.
     * · 54 declarations reach the literal-colour tier — the 48 above plus the six
     *   shorthands (`border` ×2, `border-top`, `border-bottom`, `outline`,
     *   `box-shadow`), which round 3 read not at all.
     */
    expect(seen.length, 'the colour scan found almost nothing — it is broken').toBe(51);
    expect(scanned.length, 'the literal-colour tier read almost nothing — it is broken').toBe(54);
    expect(LITERAL_COLOUR_EXCEPTIONS, 'the exception list has grown').toHaveLength(1);
    expect(seen, 'the ramp fills must be covered').toContain(
      'stats-chart-segment fill var(--stats-ramp-3)',
    );
    expect(seen, 'and the legend swatch backgrounds, which fill|stroke could not see').toContain(
      'stats-chart-swatch background var(--stats-ramp-3)',
    );
    expect(seen, 'and chart text colour').toContain('stats-chart-tick color var(--text-muted)');
    expect(
      seen,
      'and border-color, which round 3 matched as neither `background` nor `color`',
    ).toContain('stats-chart-state-pending border-color var(--cover-border)');
    expect(
      scanned,
      'and the shorthands the strict tier cannot parse must still be read for a literal',
    ).toContain('.statistics .stats-chart-tooltip border 1px solid var(--border-strong)');
  });

  /*
   * THE SCAN'S OWN COVERAGE, PINNED. Round 3's hole was invisible because nothing
   * asserted WHICH properties were read — the vacuity guard counted declarations,
   * and a narrower pattern simply counted fewer of them and was re-pinned. So the
   * property set is asserted directly, and the four names round 3 missed are named.
   */
  it('reads every colour-capable property this stylesheet declares', async () => {
    const css = await statisticsCss();
    const properties = new Set<string>();
    for (const { selector, declarations } of rulesOf(css)) {
      if (!/\.stats-chart-/.test(selector)) continue;
      for (const [, property] of declarations.matchAll(/(?:^|[;{\s])([a-z-]+)\s*:\s*([^;]+)/g)) {
        if (!NON_COLOUR_PROPERTIES.includes(property)) properties.add(property);
      }
    }
    expect(
      [...properties].sort(),
      'the set of colour-capable properties under a chart rule changed. If a new one is ' +
        'intended, add it here — and to PURE_COLOUR_PROPERTIES if its whole value is a colour — ' +
        'in the same commit. If it cannot carry a colour, list it in NON_COLOUR_PROPERTIES.',
    ).toEqual([
      'background',
      'border',
      'border-bottom',
      'border-color',
      'border-top',
      'box-shadow',
      'color',
      'fill',
      'outline',
      'stroke',
    ]);
    // The four round 3 could not see, called out by name so a future narrowing of
    // the pattern fails here rather than silently lowering a count.
    for (const property of ['background-color', 'border-color', 'outline', 'box-shadow']) {
      expect(
        NON_COLOUR_PROPERTIES,
        `${property} must never be treated as unable to carry a colour`,
      ).not.toContain(property);
    }
  });

  /*
   * THE OTHER DIRECTION, over EVERY property with no skip list at all — including
   * the ones `NON_COLOUR_PROPERTIES` withholds from the scan above. A data colour
   * must appear only where a value is encoded, so `--stats-ramp-3` in a `border`, a
   * `box-shadow`, an `outline`, a `border-radius` or a property nobody has thought
   * of yet is caught here. This is the tier that covers the token direction for the
   * shorthands, which the strict tier above deliberately does not parse.
   */
  it('a data-ink token is referenced ONLY by a class allowed to encode a value', async () => {
    const css = await statisticsCss();
    const references: string[] = [];
    for (const { selector, declarations } of rulesOf(css)) {
      for (const [, token] of declarations.matchAll(/var\((--stats-(?:ramp-\d|series))\)/g)) {
        for (const part of selector.split(',')) {
          const cls = chartClassOf(part);
          references.push(`${cls ?? '(no chart class)'} ${token}`);
          expect(
            dataMarkClasses,
            `${token} is referenced by "${part.trim()}", which is not a data-mark class — a ` +
              `value colour is being used as chrome or as text`,
          ).toContain(cls);
        }
      }
    }
    // Vacuity guard: 19 (selector-part, reference) pairs measured — 5 segment
    // fills, 5 swatch backgrounds, 5 tooltip-key backgrounds, the series colour on
    // the line rule and on the unslotted tooltip key, and the bar/marker rule,
    // which is one declaration counted once per class in its group.
    expect(references.length, 'no data-ink reference was inspected').toBe(19);
  });
});

/*
 * M2 — AN INLINE PRESENTATION ATTRIBUTE WOULD BYPASS EVERY TEST ABOVE, because
 * all of them read the stylesheet as text.
 *
 * MEASURED, in two parts. At 4b86f7e an inline `fill="#b0522c"` on
 * `.stats-chart-segment` passed all 59 tests in this file. And in headless Chromium
 * on the worked-example surface, with that attribute on every segment, all five
 * slots still COMPUTE their ramp step — slot 1: attribute `#b0522c`, computed
 * `rgb(28, 74, 122)`; slots 2–5 likewise — because a presentation attribute ranks
 * below any author declaration and `statistics.css` declares `fill` for slots 1–5.
 *
 * So today it is inert, BY ACCIDENT OF COVERAGE, and the accident is narrow: a
 * sixth slot or any mark class with no CSS `fill` has no author declaration for the
 * attribute to lose to. That half is the cascade rule applied, NOT an observation —
 * there is no sixth slot to measure. `.stats-chart-hit`'s `fill: transparent` is
 * the same exposure in the other direction, and the hit area is what makes the
 * tooltip work.
 *
 * So it is GUARDED rather than recorded as a residual. Every form is rendered and
 * the presentation attributes actually present are pinned: `fill="none"` on the
 * line chart's path (a geometry keyword, not a colour) and nothing else, plus no
 * inline `style` carrying a colour. jsdom applies no stylesheet, which is exactly
 * right here — what is being checked is what the COMPONENT emits.
 *
 * ROUND 3'S INLINE GUARD MISSED BOTH IDIOMATIC REACT ROUTES, by making the same
 * mistake as the stylesheet scan: it matched PROPERTY NAMES.
 *
 *     /(?:^|[;\s])(?:fill|stroke|background|color|border-color|box-shadow)\s*:/i
 *
 * It spelled out hyphenated `border-color` and not `background-color`, and it knew
 * nothing about custom properties. Negative control, measured at 134eac2 — one line
 * on `ChartLegend`'s swatch:
 *
 *     style={{ backgroundColor: '#b0522c', ['--stats-ramp-1' as never]: '#7a4fa3' }}
 *
 * which React serialises as `background-color: rgb(176, 82, 44); --stats-ramp-1:
 * #7a4fa3;` — 67 of 67 tests in this file passed. Non-vacuous: `StatsStackedBar` is
 * in `ALL_FORMS` and renders `ChartLegend`, so the guard did visit that element.
 *
 * The second half is the worse one. An inline custom property REDEFINES
 * `--stats-ramp-1` for that subtree, so every mark reading slot 1 changes colour
 * with no declaration any stylesheet scan can see.
 *
 * SO THE GUARD READS VALUES, NOT PROPERTY NAMES — the same `LITERAL_COLOUR_ANYWHERE`
 * the stylesheet scan uses — and rejects an inline custom property outright. No
 * component has a reason to set one: measured, the nine inline styles these forms
 * emit are `left`, `top` and `height`, all geometry.
 */
describe('the components emit no inline colour', () => {
  /**
   * Everything wrong with one element's inline style: a literal colour in a VALUE,
   * a chart token named inline, or a custom property redefined for the subtree.
   *
   * Per DECLARATION, and the value is taken from after the first `:` — the whole
   * attribute string cannot be matched against a colour pattern, because
   * `white-space: nowrap` carries `\bwhite\b` in its property name.
   */
  function inlineStyleFaults(element: Element): string[] {
    const style = element.getAttribute('style');
    if (style === null) return [];
    const faults: string[] = [];
    for (const declaration of style.split(';')) {
      const colon = declaration.indexOf(':');
      if (colon === -1) continue;
      const property = declaration.slice(0, colon).trim();
      const value = declaration.slice(colon + 1).trim();
      const where = `<${element.tagName.toLowerCase()}> style ${property}: ${value}`;
      if (property.startsWith('--')) {
        faults.push(`${where} — an inline custom property REDEFINES a token for this subtree`);
      }
      if (LITERAL_COLOUR_ANYWHERE.test(value)) {
        faults.push(`${where} — a literal colour no stylesheet scan can govern`);
      }
      if (/var\(\s*--stats-/i.test(value)) {
        faults.push(`${where} — a chart token applied inline, outside the per-selector policy`);
      }
    }
    return faults;
  }

  /**
   * How many elements of each form carry an inline `style`, MEASURED. The point of
   * pinning it is that the scan below is only meaningful where it entered the
   * branch, and one form never does — see the comment on the assertion.
   */
  const INLINE_STYLE_COUNTS: Readonly<Record<string, number>> = {
    'Records by workflow step': 6,
    'Operations by method': 8,
    'Share of fields by class': 4,
    'Exports per week': 7,
    'Operations by group': 0,
  };

  it.each(ALL_FORMS)('%s emits no colour attribute and no colour in style', (_name, caption, mount) => {
    mount();
    const fig = figure(caption);

    const attributes: string[] = [];
    const faults: string[] = [];
    let inlineStyles = 0;
    for (const element of [fig, ...fig.querySelectorAll('*')]) {
      for (const attribute of ['fill', 'stroke', 'color', 'stop-color', 'flood-color']) {
        const value = element.getAttribute(attribute);
        if (value !== null) attributes.push(`${attribute}="${value}"`);
      }
      if (element.getAttribute('style') !== null) inlineStyles += 1;
      faults.push(...inlineStyleFaults(element));
    }
    expect(faults).toEqual([]);
    /*
     * …and how many inline styles the branch actually saw, PINNED PER FORM rather
     * than asserted to be non-zero — because measured, `StatsComparisonRows` emits
     * NONE, so "every form emits at least one" would have been a false claim
     * written to make a vacuity guard pass. The four charts that place marks by
     * geometry emit `left` / `top` / `height`; the comparison rows are laid out
     * entirely in CSS.
     */
    expect(inlineStyles, `${caption}: the inline-style count changed`).toBe(
      INLINE_STYLE_COUNTS[caption],
    );

    // `fill="none"` is a geometry keyword on the line chart's path — a stroked
    // polyline must not be filled — and is the ONLY presentation attribute any
    // form emits. Any other value is a colour the stylesheet cannot govern.
    expect([...new Set(attributes)].sort()).toEqual(
      caption === 'Exports per week' ? ['fill="none"'] : [],
    );
  });

  /*
   * THE GUARD BITES, on the reviewer's exact control. Round 3's version passed this
   * line, so the line is kept as a fixture rather than described in a comment.
   */
  it('reports the reviewer control: an inline background-color AND a redefined ramp token', () => {
    render(
      <StatsStackedBar
        caption="Share of fields by class"
        rows={EVIDENCE}
        total={40}
        unit="fields"
        categoryHeader="Class"
      />,
    );
    const swatch = figure('Share of fields by class').querySelector(
      '.stats-chart-swatch',
    ) as HTMLElement;
    expect(swatch, 'the legend swatch must exist for the control to be planted on').not.toBeNull();
    swatch.setAttribute('style', 'background-color: rgb(176, 82, 44); --stats-ramp-1: #7a4fa3;');

    expect(inlineStyleFaults(swatch)).toEqual([
      '<span> style background-color: rgb(176, 82, 44) — a literal colour no stylesheet scan can govern',
      '<span> style --stats-ramp-1: #7a4fa3 — an inline custom property REDEFINES a token for this subtree',
      '<span> style --stats-ramp-1: #7a4fa3 — a literal colour no stylesheet scan can govern',
    ]);
  });

  /* …and each of the three fault kinds on its own, so none of them is carried by
   * the others in the combined control above. */
  it.each([
    ['a named colour, which a #hex-shaped scan misses', 'border-color: rebeccapurple'],
    ['a chart token applied inline', 'fill: var(--stats-ramp-2)'],
    ['a custom property with no colour in it at all', '--stats-series: var(--border)'],
    ['a longhand round 3 could not see', 'background-color: #b0522c'],
  ])('reports %s', (_why, declaration) => {
    render(
      <StatsStackedBar
        caption="Share of fields by class"
        rows={EVIDENCE}
        total={40}
        unit="fields"
        categoryHeader="Class"
      />,
    );
    const swatch = figure('Share of fields by class').querySelector(
      '.stats-chart-swatch',
    ) as HTMLElement;
    swatch.setAttribute('style', declaration);
    expect(inlineStyleFaults(swatch).length, declaration).toBeGreaterThan(0);
  });

  /* …and the geometry these forms really do emit is NOT reported, so the guard is
   * not simply flagging every inline style. */
  it.each(['left: 42px', 'top: 50%', 'height: 300px', 'white-space: nowrap'])(
    'leaves the geometry alone: %s',
    (declaration) => {
      const span = document.createElement('span');
      span.setAttribute('style', declaration);
      expect(inlineStyleFaults(span)).toEqual([]);
    },
  );
});

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

  /*
   * THE CONTRAST RULE IS HONOURED BY THE COMPONENT, not merely declared next to it.
   *
   * `IN_SEGMENT_LABEL_SLOTS` is checked against measured contrast above, and
   * `statistics.css` is checked for painting only legible slots. NEITHER of those
   * asserts that the renderer consults the list — and an independent reviewer
   * replaced the one line that does
   *
   *     if (!IN_SEGMENT_LABEL_SLOTS.includes(i + 1)) return null;
   *
   * with a comment and passed 2697 vitest tests and 30 browser tests. Deleting it
   * silently restores a 4.32:1 white-on-#587ca7 label in any workspace with a
   * flatter distribution than the seeded one.
   *
   * Both existing exercises are blind to it for the same reason: NEITHER FIXTURE
   * REACHES THE RULE. The `EVIDENCE` fixture makes slot 3 a 5% segment — 28px at
   * the fallback width, which fails the FIT rule anyway — and the seeded browser
   * distribution is 99%/1%, where the reviewer's probe found only one label at all.
   * So the discriminating fixture is FIVE EQUAL ROWS: measured here, every segment
   * is 110–112px wide, comfortably past `estimateTextWidth('20%') + 12` = 33.6, so
   * the fit rule excludes nothing and the drawn set is decided by the slot list
   * alone.
   *
   * Measured with the line present: slots 1, 2, 4, 5 at 20% each. Measured with the
   * line removed: slot 3 joins them.
   */
  it('honours IN_SEGMENT_LABEL_SLOTS where the FIT rule excludes nothing', async () => {
    const equal = [
      { key: 'a', label: 'A', value: 8 },
      { key: 'b', label: 'B', value: 8 },
      { key: 'c', label: 'C', value: 8 },
      { key: 'd', label: 'D', value: 8 },
      { key: 'e', label: 'E', value: 8 },
    ];
    render(
      <StatsStackedBar
        caption="Five equal classes"
        rows={equal}
        total={40}
        unit="fields"
        categoryHeader="Class"
      />,
    );
    const fig = figure('Five equal classes');

    // Every segment is wide enough for its own label — so nothing below is
    // explained by the fit rule.
    const widths = [...fig.querySelectorAll('.stats-chart-segment')].map((s) =>
      Number(s.getAttribute('width')),
    );
    expect(widths).toHaveLength(5);
    for (const w of widths) {
      expect(w, 'the fit rule must exclude nothing in this fixture').toBeGreaterThan(
        estimateTextWidth('20%') + 12,
      );
    }

    // …so the DRAWN set is exactly the slot list, in order, and slot 3 — the one
    // step of the ramp no label colour clears 4.5:1 on — carries no label.
    const drawn = [...fig.querySelectorAll('.stats-chart-inlabel')].map((n) => [
      n.getAttribute('data-slot'),
      n.textContent,
    ]);
    expect(drawn).toEqual([
      ['1', '20%'],
      ['2', '20%'],
      ['4', '20%'],
      ['5', '20%'],
    ]);

    const { IN_SEGMENT_LABEL_SLOTS } = await import('../screens/statistics/StatsCharts');
    expect(drawn.map(([slot]) => Number(slot))).toEqual([...IN_SEGMENT_LABEL_SLOTS]);

    // …and slot 3's share is still reachable, as text, in the table.
    expect(tableOf('Five equal classes')[2]).toEqual(['C', '8', '20%']);
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
