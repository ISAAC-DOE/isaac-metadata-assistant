import './statistics.css';
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { LoadingPanel } from '../../components/FetchStates';
import {
  BAR_END_RADIUS,
  LINE_WIDTH,
  MARKER_RADIUS,
  MARKER_RING,
  axisTicks,
  bands,
  chartSummary,
  finiteOrNull,
  horizontalBars,
  linePoints,
  niceMax,
  polylinePoints,
  round,
  shareLabel,
  soleMaximumKey,
  stackSegments,
  verticalColumns,
} from './chartGeometry';

/**
 * Statistics — the chart primitives.
 *
 * Hand-written inline SVG. NO charting library and no new npm dependency: the
 * repo's own precedent is `screens/graph/GraphCanvas.tsx`, which draws a
 * 220-node graph in SVG it authors itself, and this file is the same bet for
 * quantitative marks.
 *
 * ── The three rules every chart here obeys ──────────────────────────────────
 *
 * 1. EVERY CHART HAS TWO TEXT EQUIVALENTS, not one. A `<p class="sr-only">`
 *    carries the whole distribution as one sentence (`chartSummary`), and a real
 *    `<table>` behind a disclosure carries every figure. The brief for this
 *    surface treats them as separate requirements because they do different
 *    jobs: the sentence gives the shape without walking a grid, the table gives
 *    the numbers. A screen-reader user therefore receives the same FACTS a
 *    sighted reader does, without either one being the only route.
 *
 * 2. THE SVG IS `aria-hidden`, DELIBERATELY. The alternative — `role="img"` with
 *    an `aria-label` — puts the sentence in an attribute, where it cannot be
 *    navigated, selected, translated by the browser, or read line by line; and
 *    marks inside a `role="img"` are presentational, so per-mark labels there
 *    would be silently dropped. A real `<p>` plus a real `<table>` beats both.
 *    Nothing is lost by hiding the picture, because the picture states nothing
 *    the sentence and the table do not.
 *
 * 3. COLOUR IS NEVER THE ONLY ENCODING. Every row-based chart renders its
 *    category name and its value as REAL HTML TEXT beside the mark; the stacked
 *    bar carries a legend whose entries pair a swatch with the class name, its
 *    count and its share, and 2px surface gaps separate its segments so the
 *    boundaries survive with all colour removed. Remove every fill and each
 *    chart is still readable.
 *
 * ── Why the container is measured ───────────────────────────────────────────
 *
 * Each chart measures its own plot column and renders SVG at REAL pixel size
 * (`viewBox` == rendered size). The tempting alternative — a fixed `viewBox`
 * with `width="100%"` — scales the whole drawing, which shrinks `<text>` and
 * `stroke-width` with it; `GraphCanvas.tsx` already documents fighting exactly
 * that ("the label scales with the viewBox and swallowed the glyphs at deep
 * zoom"). At 1:1 an axis tick is 11px at every container width, a hairline is
 * one pixel, and a 4px corner is 4px.
 *
 * There is no `ResizeObserver` anywhere else in this app, so its absence is
 * handled rather than assumed: {@link CHART_FALLBACK_WIDTH} is used when the API
 * is missing (jsdom) or before the first observation. That makes the unit tests
 * deterministic and means a browser without the API still gets a correctly
 * proportioned chart at a fixed width rather than a collapsed one.
 *
 * ── NO TEXT LIVES INSIDE AN SVG HERE ───────────────────────────────────────
 *
 * Axis ticks, the one direct value label and the in-segment shares are HTML
 * elements positioned over the plot, not `<text>` nodes. TWO reasons carry the
 * decision, and both are properties of the medium rather than of any one probe:
 *
 *   · real text is selectable, translatable by the browser, and honours a
 *     reader's own minimum-font-size — SVG `<text>` is none of those;
 *   · it keeps the SVG purely MARKS, which is what makes "the picture claims
 *     nothing" true of the element and not just of an attribute on it.
 *
 * A THIRD REASON USED TO BE RECORDED HERE AS "the one that forced it", and it
 * DOES NOT REPRODUCE. It claimed that `scrollWidth` on an SVG-namespaced element
 * reports the SVG VIEWPORT's width rather than the glyph's, so
 * `e2e/helpers/layout.ts`'s content-loss tier read a one-character tick as "7px
 * visible of 520px of content (1%)". Measured in this app's own headless Chromium
 * on a `<text>` reading `7` at 11px inside a 520px `<svg>`: `scrollWidth` 11,
 * `clientWidth` 11, client rect width 7 — the GLYPH box, three px of rounding
 * above the painted width. The `<svg>` element itself does report 520, so the
 * rule holds for the container and not for its children, and `layout.ts:86-89`
 * independently records the same small magnitude for the graph canvas ("20 vs
 * 25"). At 7-of-11 the tier's own 0.6 visible-fraction narrowing would not even
 * have fired.
 *
 * What IS true is that the content-loss tier reported these ticks on four
 * viewports and the ticks were perfectly legible. The mechanism was never
 * isolated, so it is recorded as an observation rather than as an explanation,
 * and it is not load-bearing: reasons one and two decide this on their own.
 *
 * ── Values, and the absence of them ────────────────────────────────────────
 *
 * These components format nothing scientific and derive nothing. A `number`
 * prop is a count the caller measured; a non-finite one is DROPPED from the
 * picture and reported as "not available" in the text, never drawn as zero. A
 * share is `null` — and simply absent — whenever the denominator cannot support
 * one. No primitive here substitutes a default, a dash, or a zero.
 */

/* ---- container measurement --------------------------------------------- */

/**
 * Plot width used before the first measurement, and wherever `ResizeObserver`
 * does not exist. Chosen as a plausible desktop plot column (the `wide` content
 * mode is 1200px, and a section card's plot column is roughly half of it) so a
 * non-observing environment still renders sensible proportions.
 */
export const CHART_FALLBACK_WIDTH = 560;

/**
 * The smallest plot width a chart will draw into: below this the measured width
 * is clamped and the SVG stops being re-laid-out at 1:1.
 *
 * What happens then is `max-width: 100%` on the four SVG rules in
 * `statistics.css` — the drawing SCALES DOWN uniformly to fit its column. It does
 * NOT scroll. This comment used to say "the plot column's own `overflow-x` takes
 * over", and there is no such rule: the only `overflow-x: auto` in the file is on
 * `.stats-scroll`, which wraps the chart DATA TABLES (see its own comment), and
 * `.stats-chart-plot` is a plain `display: flex` column with no overflow
 * declaration at all.
 */
export const CHART_MIN_WIDTH = 120;

/**
 * Measure an element's width. Returns a ref callback and the current width in CSS
 * pixels, {@link CHART_FALLBACK_WIDTH} until something is measured.
 *
 * TWO SOURCES OF MEASUREMENT, and the synchronous one is not belt-and-braces —
 * it is the fix for a defect the browser suite caught. A `ResizeObserver` alone
 * left the two charts inside the collapsed `Technical Details` region stuck at
 * the fallback width FOREVER, including after the reader opened it. Every claim
 * below is a headless-Chromium measurement on this app, re-taken 2026-08-04:
 *
 *   · A closed `<details>` does NOT hide its content with `display: none`.
 *     Chromium's UA stylesheet puts `content-visibility: hidden` on the
 *     `::details-content` pseudo-element — measured directly:
 *     `getComputedStyle(details, '::details-content').contentVisibility` is
 *     `hidden` while the plot INSIDE it computes `display: flex` and
 *     `content-visibility: visible` in its own right. A `content-visibility:
 *     hidden` subtree is SKIPPED by `ResizeObserver` (the spec says a skipped
 *     element gets no observation), so the callback never ran for those two
 *     plots — and, measured with the synchronous read removed, nothing fired when
 *     the region later opened either: both SVGs still carried `width="560"` a
 *     full 1.5s after the summary was clicked.
 *   · But the element still has a layout box, so a DIRECT read returns the real
 *     width. Measured: `getBoundingClientRect().width` is 918 with the region
 *     CLOSED, before any click, while the observer had reported nothing at all.
 *
 * So the ref callback reads the box itself, once, and the observer handles every
 * later change (a window resize, a breakpoint reflow). `getBoundingClientRect`
 * forces a synchronous layout, which is exactly what is wanted here and is paid
 * once per chart mount.
 *
 * A zero or absent measurement is IGNORED rather than applied, so a chart in a
 * genuinely unlaid-out container keeps the fallback and renders correctly
 * proportioned at a fixed size instead of collapsing to nothing. jsdom returns 0
 * from `getBoundingClientRect` and has no `ResizeObserver`, so the unit tests all
 * run at the fallback — deterministically, and by the same rule.
 */
export function useChartWidth(): [(node: HTMLElement | null) => void, number] {
  const [width, setWidth] = useState(CHART_FALLBACK_WIDTH);
  const observerRef = useRef<ResizeObserver | null>(null);

  useEffect(() => () => observerRef.current?.disconnect(), []);

  const apply = useCallback((measured: number | undefined) => {
    if (typeof measured !== 'number' || !Number.isFinite(measured) || measured <= 0) return;
    setWidth(Math.max(CHART_MIN_WIDTH, Math.round(measured)));
  }, []);

  const attach = useCallback(
    (node: HTMLElement | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      if (node === null) return;
      apply(node.getBoundingClientRect().width);
      if (typeof ResizeObserver === 'undefined') return; // jsdom: keep the fallback
      const observer = new ResizeObserver((entries) => apply(entries[0]?.contentRect.width));
      observer.observe(node);
      observerRef.current = observer;
    },
    [apply],
  );

  return [attach, width];
}

/* ---- the shared chart shell -------------------------------------------- */

export interface ChartTableRow {
  key: string;
  /** The row header cell — a category name. */
  label: string;
  /** Already-formatted cells, in the order of `columns`. */
  cells: readonly string[];
}

export interface ChartFrameProps {
  /** Sentence-case caption. Rendered as a visible `<figcaption>`. */
  caption: string;
  /** The one sentence a screen reader gets in place of the picture. */
  summary: string;
  /** Optional visible clarifier under the caption. */
  note?: string;
  /** The legend, for two or more series. Omitted for a single series. */
  legend?: ReactNode;
  /** Column headers for the data table, after the category column. */
  tableColumns: readonly string[];
  /** Header for the table's first (category) column. */
  tableRowHeader: string;
  tableRows: readonly ChartTableRow[];
  /** The drawn picture. */
  children: ReactNode;
}

/**
 * The shell every chart on this surface uses: a `<figure>` with a visible
 * caption, the picture, the screen-reader sentence, and the data table behind a
 * native `<details>` disclosure.
 *
 * The `<details>` is CLOSED by default and that is a considered trade, not an
 * oversight: a closed `<details>` is hidden from assistive technology too, which
 * is exactly why the summary sentence is a separate, always-present `<p>` rather
 * than something the table replaces. The table is the route to every individual
 * figure, for everyone, and it is one keystroke away.
 */
export function ChartFrame({
  caption,
  summary,
  note,
  legend,
  tableColumns,
  tableRowHeader,
  tableRows,
  children,
}: ChartFrameProps) {
  return (
    <figure className="stats-chart">
      <figcaption className="stats-chart-caption">{caption}</figcaption>
      {note ? <p className="stats-chart-note">{note}</p> : null}
      {/* The authoritative text equivalent. Present in the accessibility tree
          on every render — never inside the collapsed disclosure below. */}
      <p className="sr-only">{summary}</p>
      {children}
      {legend}
      {tableRows.length > 0 && (
        <details className="stats-chart-table-wrap">
          <summary className="stats-chart-table-toggle">Show the data table</summary>
          <div className="stats-scroll">
            <table className="stats-chart-table">
              <caption className="sr-only">{caption}</caption>
              <thead>
                <tr>
                  <th scope="col">{tableRowHeader}</th>
                  {tableColumns.map((column) => (
                    <th scope="col" key={column}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    {row.cells.map((cell, i) => (
                      <td className="mono" key={tableColumns[i] ?? i}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  );
}

/* ---- legend ------------------------------------------------------------ */

export interface ChartLegendItem {
  key: string;
  label: string;
  /** The ramp/series slot this entry keys, 1-based. */
  slot: number;
  /** Optional already-formatted figures shown after the label. */
  detail?: string;
}

/**
 * The identity channel for a multi-series chart. Present whenever two or more
 * series share one mark, so identity never depends on colour-matching alone —
 * and absent for a single series, where a one-swatch box would only restate the
 * caption.
 *
 * The swatch is `aria-hidden`: it carries no information the adjacent text does
 * not, and a screen reader announcing "image" five times would be noise.
 */
export function ChartLegend({ items }: { items: readonly ChartLegendItem[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="stats-chart-legend">
      {items.map((item) => (
        <li className="stats-chart-legend-item" key={item.key}>
          <span
            className="stats-chart-swatch"
            data-slot={String(item.slot)}
            aria-hidden="true"
          />
          <span className="stats-chart-legend-label">{item.label}</span>
          {item.detail ? (
            <span className="stats-chart-legend-detail mono">{item.detail}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/* ---- tooltip ----------------------------------------------------------- */

interface HoverState {
  key: string;
  /** Container-relative position of the readout's anchor, in px. */
  x: number;
  y: number;
  label: string;
  value: string;
  slot: number;
}

/**
 * The hover readout. Enhancement only: every value it shows is already in the
 * visible row text or the data table, so nothing is gated behind a pointer.
 *
 * `aria-hidden`, because the summary sentence and the table are the accessible
 * routes and a pointer-driven live region would announce on every mark crossed.
 * Values lead, labels follow — the reader already knows which mark they are on.
 */
function ChartTooltip({ hover }: { hover: HoverState | null }) {
  if (hover === null) return null;
  return (
    <div
      className="stats-chart-tooltip"
      style={{ left: `${hover.x}px`, top: `${hover.y}px` }}
      aria-hidden="true"
    >
      <span className="stats-chart-tooltip-value mono">{hover.value}</span>
      <span className="stats-chart-tooltip-key" data-slot={String(hover.slot)} />
      <span className="stats-chart-tooltip-label">{hover.label}</span>
    </div>
  );
}

/* ---- shared chart data shape ------------------------------------------- */

export interface ChartRow {
  /** Stable identity. Colour and legend order follow THIS, never the row index
   *  of a filtered view, so removing a row never repaints the survivors. */
  key: string;
  /** Title Case category name, rendered as visible text. */
  label: string;
  value: number;
}

/** Height of one row band in the row-based charts, in px. */
const ROW_BAND = 26;

/* ---- StatsBarChart (horizontal, shared axis) --------------------------- */

export interface StatsBarChartProps {
  caption: string;
  rows: readonly ChartRow[];
  /** The noun the values count — "records", "fields", "operations". */
  unit: string;
  /**
   * The denominator to state in the summary, or `null` for none. NOT the bar
   * domain: bars are scaled to a nice maximum derived from the largest value,
   * so a small count is legible instead of being a sliver of the total.
   */
  total: number | null;
  /** Header for the table's category column. */
  categoryHeader: string;
  note?: string;
}

/**
 * A horizontal bar chart over a SHARED value axis.
 *
 * FORM. Comparing magnitude across named categories whose labels are long is
 * the textbook horizontal-bar case: the labels get a full line of real HTML
 * text that wraps, and the bars share one axis so the eye compares lengths.
 *
 * AND IT IS NOT A ROW OF PROGRESS BARS, which is the specific regression this
 * surface has been warned about. Three things make the difference, and all
 * three are load-bearing:
 *
 *   · the domain is a nice maximum over the LARGEST VALUE, not the total, so the
 *     bars use the full width and small differences are visible;
 *   · a shared tick scale with hairline gridlines is drawn behind every row and
 *     labelled once beneath them, so a length can be READ as a number;
 *   · the figure carries the summary sentence and the data table.
 *
 * A progress bar answers "how far along is this one thing"; this answers "how do
 * these categories compare", which is a different question and a different mark.
 *
 * Colour is a SINGLE hue for every bar. The categories here are compared, not
 * identified, so per-bar hues would encode nothing the label does not already
 * say — and a value-ramp over nominal categories would double-encode length as
 * lightness. One series, one colour.
 *
 * NO HOVER READOUT, and that is the rule applied rather than skipped. A tooltip
 * exists so a value that is not directly labelled can still be read; every value
 * here IS directly labelled, as real text on its own row, so a readout would
 * repeat what is already on screen. The forms whose values are not all labelled —
 * {@link StatsColumnChart}, {@link StatsStackedBar}, {@link StatsLineChart} — do
 * carry one.
 */
export function StatsBarChart({
  caption,
  rows,
  unit,
  total,
  categoryHeader,
  note,
}: StatsBarChartProps) {
  const [attach, width] = useChartWidth();
  const domainMax = niceMax(Math.max(0, ...rows.map((r) => finiteOrNull(r.value) ?? 0)));
  const ticks = axisTicks(domainMax);
  const plotHeight = ROW_BAND;
  const summary = chartSummary(caption, rows, unit, total);

  return (
    <ChartFrame
      caption={caption}
      summary={summary}
      note={note}
      tableRowHeader={categoryHeader}
      tableColumns={[unit.replace(/^./, (c) => c.toUpperCase()), 'Share']}
      tableRows={rows.map((row) => ({
        key: row.key,
        label: row.label,
        cells: [
          finiteOrNull(row.value) === null ? 'Not Available' : String(row.value),
          total === null ? 'Not Available' : (shareLabel(row.value, total) ?? 'Not Available'),
        ],
      }))}
    >
      <div className="stats-chart-plot" ref={attach}>
        {rows.map((row) => {
          const marks = horizontalBars([row], domainMax, { width, height: plotHeight });
          const mark = marks[0];
          const value = finiteOrNull(row.value);
          return (
            <div className="stats-chart-row" key={row.key}>
              <span className="stats-chart-row-label">{row.label}</span>
              <span className="stats-chart-row-value mono">
                {value === null ? 'Not Available' : String(row.value)}
              </span>
              <svg
                className="stats-chart-track"
                width={width}
                height={plotHeight}
                viewBox={`0 0 ${width} ${plotHeight}`}
                aria-hidden="true"
                focusable="false"
              >
                {ticks.map((tick) => (
                  <line
                    key={tick}
                    className="stats-chart-grid"
                    x1={round((tick / domainMax) * width)}
                    x2={round((tick / domainMax) * width)}
                    y1={0}
                    y2={plotHeight}
                  />
                ))}
                {mark !== undefined && (
                  <rect
                    className="stats-chart-bar"
                    data-slot="1"
                    x={0}
                    y={round(mark.y)}
                    width={round(Math.max(0, mark.width))}
                    height={round(mark.height)}
                    rx={BAR_END_RADIUS}
                  />
                )}
              </svg>
            </div>
          );
        })}
        {/* The shared scale, labelled ONCE beneath the rows — this is what makes
            the group a bar chart rather than a stack of progress bars.
            `aria-hidden`, because the summary sentence and the data table are the
            accessible routes to every value and an axis read aloud tick by tick is
            noise. */}
        <div className="stats-chart-axis" aria-hidden="true">
          {ticks.map((tick) => (
            <span
              className="stats-chart-tick"
              key={tick}
              data-anchor={tickAnchor(tick, domainMax)}
              style={{ left: `${round((tick / domainMax) * 100)}%` }}
            >
              {tick}
            </span>
          ))}
        </div>
      </div>
    </ChartFrame>
  );
}

/**
 * How a tick label sits relative to its position on the scale.
 *
 * The first and last ticks are anchored INWARD so they stay inside the plot
 * instead of hanging half off each end — a `0` bleeding past the left edge of the
 * card is the classic axis defect. Everything between is centred. The CSS turns
 * these three values into a transform.
 */
function tickAnchor(tick: number, domainMax: number): 'start' | 'middle' | 'end' {
  if (tick === 0) return 'start';
  if (tick === domainMax) return 'end';
  return 'middle';
}

/** The singular of a plain count noun, for a tooltip reading "1 record". Only
 *  the trailing `s` is dropped, and only when there is one — this never invents
 *  an irregular plural, and a caller with one is free to pass the singular. */
function singular(unit: string): string {
  return unit.endsWith('s') ? unit.slice(0, -1) : unit;
}

/* ---- StatsColumnChart (vertical) --------------------------------------- */

export interface StatsColumnChartProps {
  caption: string;
  rows: readonly ChartRow[];
  unit: string;
  total: number | null;
  /** Header for the table's category column. */
  categoryHeader: string;
  note?: string;
}

/**
 * A vertical column chart.
 *
 * FORM. Few categories with SHORT names (HTTP methods) read best as columns: the
 * eye compares heights against a common baseline and the names sit under the
 * marks without wrapping, rotation or truncation. The moment the names get long
 * this is the wrong form and {@link StatsComparisonRows} is the right one.
 *
 * LABELLING IS SELECTIVE, per the rule that a number on every mark goes unread:
 * only the SOLE maximum is labelled on its cap, and only when there is a unique
 * one — a tie is deliberately left unlabelled rather than arbitrarily
 * highlighting one of two equal columns. The y-axis carries the rest
 * approximately and the data table carries every figure exactly.
 */
export function StatsColumnChart({
  caption,
  rows,
  unit,
  total,
  categoryHeader,
  note,
}: StatsColumnChartProps) {
  const [attach, width] = useChartWidth();
  const [hover, setHover] = useState<HoverState | null>(null);
  const domainMax = niceMax(Math.max(0, ...rows.map((r) => finiteOrNull(r.value) ?? 0)));
  const ticks = axisTicks(domainMax);
  const PLOT_HEIGHT = 132;
  const marks = verticalColumns(rows, domainMax, { width, height: PLOT_HEIGHT });
  const markFor = new Map(marks.map((m) => [m.key, m]));
  const peak = soleMaximumKey(rows);
  const layout = bands(rows.length, width);

  return (
    <ChartFrame
      caption={caption}
      summary={chartSummary(caption, rows, unit, total)}
      note={note}
      tableRowHeader={categoryHeader}
      tableColumns={[unit.replace(/^./, (c) => c.toUpperCase()), 'Share']}
      tableRows={rows.map((row) => ({
        key: row.key,
        label: row.label,
        cells: [
          finiteOrNull(row.value) === null ? 'Not Available' : String(row.value),
          total === null ? 'Not Available' : (shareLabel(row.value, total) ?? 'Not Available'),
        ],
      }))}
    >
      <div className="stats-chart-plot" ref={attach}>
        {/* The SVG is MARKS ONLY — gridlines, the baseline rule, the columns and
            their hit areas. Every glyph below it is HTML. */}
        <div className="stats-chart-band" style={{ height: `${PLOT_HEIGHT}px` }}>
          <svg
            className="stats-chart-columns"
            width={width}
            height={PLOT_HEIGHT}
            viewBox={`0 0 ${width} ${PLOT_HEIGHT}`}
            aria-hidden="true"
            focusable="false"
            onPointerLeave={() => setHover(null)}
          >
            {ticks.map((tick) => {
              const y = round(PLOT_HEIGHT - (tick / domainMax) * PLOT_HEIGHT);
              return (
                <line
                  key={tick}
                  className="stats-chart-grid"
                  x1={0}
                  x2={width}
                  y1={y}
                  y2={y}
                />
              );
            })}
            <line
              className="stats-chart-axis-rule"
              x1={0}
              x2={width}
              y1={PLOT_HEIGHT - 0.5}
              y2={PLOT_HEIGHT - 0.5}
            />
            {rows.map((row, i) => {
              const mark = markFor.get(row.key);
              const band = layout[i];
              if (mark === undefined || band === undefined) return null;
              return (
                <g key={row.key}>
                  <rect
                    className="stats-chart-bar"
                    data-slot="1"
                    x={round(mark.x)}
                    y={round(mark.y)}
                    width={round(mark.width)}
                    height={round(Math.max(0, mark.height))}
                    rx={BAR_END_RADIUS}
                    opacity={hover !== null && hover.key !== row.key ? 0.55 : 1}
                  />
                  <rect
                    className="stats-chart-hit"
                    x={round(band.start)}
                    y={0}
                    width={round(band.size)}
                    height={PLOT_HEIGHT}
                    onPointerEnter={() =>
                      setHover({
                        key: row.key,
                        x: round(band.start + band.size / 2),
                        y: round(Math.max(0, mark.y - 6)),
                        label: row.label,
                        value: `${row.value} ${row.value === 1 ? singular(unit) : unit}`,
                        slot: 1,
                      })
                    }
                  />
                </g>
              );
            })}
          </svg>
          {/* y-axis ticks, positioned on the same scale the gridlines use. */}
          {ticks.map((tick) => (
            <span
              className="stats-chart-tick stats-chart-tick-y"
              key={tick}
              aria-hidden="true"
              style={{ top: `${round(PLOT_HEIGHT - (tick / domainMax) * PLOT_HEIGHT)}px` }}
            >
              {tick}
            </span>
          ))}
          {/* The ONE direct label: the sole maximum's value, on its cap. */}
          {peak !== null &&
            (() => {
              const mark = markFor.get(peak);
              const row = rows.find((r) => r.key === peak);
              if (mark === undefined || row === undefined) return null;
              return (
                <span
                  className="stats-chart-value"
                  aria-hidden="true"
                  style={{
                    left: `${round(mark.x + mark.width / 2)}px`,
                    bottom: `${round(Math.max(0, PLOT_HEIGHT - mark.y) + 4)}px`,
                  }}
                >
                  {row.value}
                </span>
              );
            })()}
        </div>
        {/* Category names as real HTML, in the same band order as the columns —
            they wrap instead of being clipped or rotated. */}
        <div className="stats-chart-catrow">
          {rows.map((row) => (
            <span className="stats-chart-cat" key={row.key}>
              {row.label}
            </span>
          ))}
        </div>
        <ChartTooltip hover={hover} />
      </div>
    </ChartFrame>
  );
}

/* ---- StatsStackedBar --------------------------------------------------- */

export interface StatsStackedBarProps {
  caption: string;
  rows: readonly ChartRow[];
  /** The caller's OWN whole. Never re-derived from the segments. */
  total: number;
  unit: string;
  /** Header for the table's category column. */
  categoryHeader: string;
  note?: string;
}

/** Height of the stacked bar, in px. Thin by construction — a stack this tall
 *  reads as data rather than as a painted block. */
const STACK_HEIGHT = 22;

/**
 * A single horizontal stacked bar — the composition of ONE whole.
 *
 * FORM. Part-to-whole across mutually exclusive classes that sum to a known
 * total is the stacked bar's exact job, and horizontal is right here because the
 * class names are long. It answers "what is this workspace's evidence support
 * MADE OF", which is a different question from the per-class counts beside it
 * (those are a comparison, and they are already stated as text).
 *
 * COLOUR IS AN ORDINAL RAMP, and that choice is measured rather than taste.
 * The obvious alternative — the app's own five evidence-class status hues —
 * FAILS a colour-vision check as touching segments: `--needsyou-text` #8a6420
 * against `--fail-solid` #b23a30 is ΔE 0.9 under deuteranopia (OKLab ×100,
 * `dataviz/scripts/validate_palette.js`), i.e. indistinguishable. Those hues are
 * fine where this app uses them — on a `StatusChip`, which carries an icon and a
 * label — but a stacked segment has neither. One hue stepped by LIGHTNESS
 * survives every colour-vision deficiency, because lightness does; the ramp in
 * `statistics.css` passes the ordinal checks on both card surfaces.
 *
 * The ramp step encodes the class's POSITION in the caller's declared order.
 * It does not encode magnitude and it does not rank severity — the class name in
 * the legend and in the table carries the meaning, which is why the legend is
 * mandatory here and why every segment's figures are also plain text.
 */
export function StatsStackedBar({
  caption,
  rows,
  total,
  unit,
  categoryHeader,
  note,
}: StatsStackedBarProps) {
  const [attach, width] = useChartWidth();
  const [hover, setHover] = useState<HoverState | null>(null);
  const segments = stackSegments(rows, total, width);
  const segmentFor = new Map(segments.map((s) => [s.key, s]));

  return (
    <ChartFrame
      caption={caption}
      summary={chartSummary(caption, rows, unit, total)}
      note={note}
      legend={
        <ChartLegend
          items={rows.map((row, i) => ({
            key: row.key,
            label: row.label,
            slot: i + 1,
            detail: legendDetail(row.value, total, unit),
          }))}
        />
      }
      tableRowHeader={categoryHeader}
      tableColumns={[unit.replace(/^./, (c) => c.toUpperCase()), 'Share']}
      tableRows={rows.map((row) => ({
        key: row.key,
        label: row.label,
        cells: [
          finiteOrNull(row.value) === null ? 'Not Available' : String(row.value),
          shareLabel(row.value, total) ?? 'Not Available',
        ],
      }))}
    >
      <div className="stats-chart-plot" ref={attach}>
        <div className="stats-chart-band" style={{ height: `${STACK_HEIGHT}px` }}>
          <svg
            className="stats-chart-stack"
            width={width}
            height={STACK_HEIGHT}
            viewBox={`0 0 ${width} ${STACK_HEIGHT}`}
            aria-hidden="true"
            focusable="false"
            onPointerLeave={() => setHover(null)}
          >
            {rows.map((row, i) => {
              const segment = segmentFor.get(row.key);
              if (segment === undefined) return null;
              return (
                <g key={row.key}>
                  <rect
                    className="stats-chart-segment"
                    data-slot={String(i + 1)}
                    x={round(segment.x)}
                    y={0}
                    width={round(segment.width)}
                    height={STACK_HEIGHT}
                    opacity={hover !== null && hover.key !== row.key ? 0.55 : 1}
                  />
                  {segment.width > 0 && (
                    <rect
                      className="stats-chart-hit"
                      x={round(segment.x)}
                      y={0}
                      width={round(segment.width)}
                      height={STACK_HEIGHT}
                      onPointerEnter={() =>
                        setHover({
                          key: row.key,
                          x: round(segment.x),
                          y: 0,
                          label: row.label,
                          value: `${row.value} ${row.value === 1 ? singular(unit) : unit}`,
                          slot: i + 1,
                        })
                      }
                    />
                  )}
                </g>
              );
            })}
          </svg>
          {/* In-segment shares, as HTML over the bar. Drawn ONLY where the text
              measurably fits inside the segment with padding on both sides —
              never clipped, and never `overflow: hidden` over a cropped glyph —
              AND only on a ramp slot where a label colour clears 4.5:1 against
              the fill ({@link IN_SEGMENT_LABEL_SLOTS}). A share that is not drawn
              for either reason stays in the legend, the summary sentence and the
              table, so nothing is gated by the decision. */}
          {rows.map((row, i) => {
            const segment = segmentFor.get(row.key);
            if (segment === undefined || segment.sharePct === null) return null;
            if (!IN_SEGMENT_LABEL_SLOTS.includes(i + 1)) return null;
            const label = `${segment.sharePct}%`;
            if (segment.width < estimateTextWidth(label) + 12) return null;
            return (
              <span
                className="stats-chart-inlabel"
                key={row.key}
                data-slot={String(i + 1)}
                aria-hidden="true"
                style={{ left: `${round(segment.x + segment.width / 2)}px` }}
              >
                {label}
              </span>
            );
          })}
        </div>
        <ChartTooltip hover={hover} />
      </div>
    </ChartFrame>
  );
}

/** `12 fields · 40%`, dropping the share clause when none can be stated. */
function legendDetail(value: number, total: number, unit: string): string {
  const count = finiteOrNull(value);
  const head = count === null ? 'Not Available' : `${value} ${value === 1 ? singular(unit) : unit}`;
  const pct = shareLabel(value, total);
  return pct === null ? head : `${head} · ${pct}`;
}

/**
 * A conservative width estimate for a short numeric label at the in-segment
 * font size, used to decide whether it FITS before it is drawn. Deliberately
 * generous (over-estimates), because the failure it prevents — a clipped or
 * overflowing label — is worse than an unlabelled segment.
 */
export function estimateTextWidth(text: string): number {
  return text.length * 7.2;
}

/**
 * Ramp slots whose in-segment share label can be drawn AT ALL — i.e. the ones
 * where either `--surface` or `--text-heading` clears WCAG 1.4.3's 4.5:1 against
 * the ramp fill it would sit on.
 *
 * 11px semibold is NOT large text (that threshold is 18.66px bold / 24px
 * regular), so 4.5:1 applies rather than 3:1. Measured over the ramp declared in
 * `statistics.css` — the full table is in the `.stats-chart-inlabel` comment
 * there — the middle step #587ca7 gives 4.32:1 with white and 4.06:1 with ink.
 * NEITHER clears it, so slot 3 carries no label.
 *
 * WHY NOT RE-STEP THE RAMP INSTEAD, which would keep all five labelled: the dead
 * band is an intrinsic property of an evenly-stepped five-step ramp over this
 * range. White clears 4.5:1 only below relative luminance 0.1833 and ink only
 * above 0.2194, and the ramp's own steps sit at 0.118 / 0.193 / 0.297 in that
 * measure — the middle one lands inside the band. Nudging step 3 out of it breaks
 * the `dataviz` ordinal check the ramp currently PASSES: measured with
 * `dataviz/scripts/validate_palette.js --ordinal`, #50749f and #4d739f both fail
 * "Adjacent ΔL >= 0.06" against step 2 (0.060 and 0.056 in OKLab L). Re-stepping
 * all five to skip the band would make the ramp non-uniform and re-open a palette
 * that is currently validated on both card surfaces — a much larger change than
 * the defect, which is one unlabelled segment out of five.
 *
 * Nothing is gated: an unlabelled slot's share is still in the legend (name +
 * count + share, as text), in the summary sentence and in the data table — the
 * same relief the fit rule below already relies on.
 */
export const IN_SEGMENT_LABEL_SLOTS: readonly number[] = Object.freeze([1, 2, 4, 5]);

/* ---- StatsComparisonRows (compact horizontal comparison) --------------- */

export interface StatsComparisonRowsProps {
  caption: string;
  rows: readonly ChartRow[];
  unit: string;
  total: number | null;
  categoryHeader: string;
  note?: string;
}

/**
 * A compact horizontal comparison: label, value, and a short proportional
 * track, one row per category. No axis, no gridlines, no tick strip.
 *
 * FORM. This is the answer for MANY categories with LONG, caller-supplied names
 * in a narrow column — an OpenAPI document's own tag names, which can be
 * anything. A full bar chart's axis strip would cost vertical room per row it
 * cannot pay for, and a column chart would clip or rotate the names. So the
 * marks stay compact and the numbers stay as text.
 *
 * THE SCALE IS THE LARGEST VALUE, NOT THE TOTAL, and that is the difference
 * between a comparison and a row of progress bars: against the total, ten groups
 * of one operation each would be ten identical 10% slivers; against the largest,
 * they are ten equal FULL bars and the one group with four operations is
 * visibly four times any of them.
 */
export function StatsComparisonRows({
  caption,
  rows,
  unit,
  total,
  categoryHeader,
  note,
}: StatsComparisonRowsProps) {
  const [attach, width] = useChartWidth();
  const domainMax = niceMax(Math.max(0, ...rows.map((r) => finiteOrNull(r.value) ?? 0)));
  const COMPACT_BAND = 10;

  return (
    <ChartFrame
      caption={caption}
      summary={chartSummary(caption, rows, unit, total)}
      note={note}
      tableRowHeader={categoryHeader}
      tableColumns={[unit.replace(/^./, (c) => c.toUpperCase()), 'Share']}
      tableRows={rows.map((row) => ({
        key: row.key,
        label: row.label,
        cells: [
          finiteOrNull(row.value) === null ? 'Not Available' : String(row.value),
          total === null ? 'Not Available' : (shareLabel(row.value, total) ?? 'Not Available'),
        ],
      }))}
    >
      <div className="stats-chart-plot stats-chart-plot-compact" ref={attach}>
        {rows.map((row) => {
          const value = finiteOrNull(row.value);
          const marks = horizontalBars([row], domainMax, {
            width,
            height: COMPACT_BAND,
          });
          const mark = marks[0];
          return (
            <div className="stats-chart-comparerow" key={row.key}>
              <span className="stats-chart-row-label">{row.label}</span>
              <span className="stats-chart-row-value mono">
                {value === null ? 'Not Available' : String(row.value)}
              </span>
              <svg
                className="stats-chart-track stats-chart-track-compact"
                width={width}
                height={COMPACT_BAND}
                viewBox={`0 0 ${width} ${COMPACT_BAND}`}
                aria-hidden="true"
                focusable="false"
              >
                {mark !== undefined && (
                  <rect
                    className="stats-chart-bar"
                    data-slot="1"
                    x={0}
                    y={round(mark.y)}
                    width={round(Math.max(0, mark.width))}
                    height={round(mark.height)}
                    rx={BAR_END_RADIUS}
                  />
                )}
              </svg>
            </div>
          );
        })}
      </div>
    </ChartFrame>
  );
}

/* ---- StatsLineChart ---------------------------------------------------- */

export interface StatsLineChartProps {
  caption: string;
  /** Ordered observations, left to right. `label` names the position on x. */
  rows: readonly ChartRow[];
  unit: string;
  /** What the x positions ARE, in words. Mandatory — see the note below. */
  xAxisLabel: string;
  note?: string;
}

/**
 * A single-series line chart over an ORDERED sequence.
 *
 * FORM. A line is for change across an ordered dimension, and it earns the form
 * only when the order is real. `chartGeometry.linePoints` spaces the points
 * EVENLY BY INDEX and parses no dates, so this component cannot know whether the
 * gaps between observations are equal — which is why `xAxisLabel` is required:
 * the caption has to say what x is, so a reader is never left to assume a
 * uniform time axis that the data may not have.
 *
 * NOT MOUNTED ANYWHERE IN THE PRODUCT, on purpose. This build records no
 * time series: nothing counts requests, sessions, exports-per-day, or validation
 * outcomes over time, and `updated_utc` on a seeded record is the moment the
 * worked example was created, not activity. Plotting it would manufacture a
 * trend. The primitive exists so a real series — the readiness and
 * validation-over-time views in `lib/myStatsContract.ts` — can be dropped in
 * without inventing a chart at that moment; until then its only callers are
 * tests, which is the honest place for a fixture.
 */
export function StatsLineChart({
  caption,
  rows,
  unit,
  xAxisLabel,
  note,
}: StatsLineChartProps) {
  const [attach, width] = useChartWidth();
  const [hover, setHover] = useState<HoverState | null>(null);
  const domainMax = niceMax(Math.max(0, ...rows.map((r) => finiteOrNull(r.value) ?? 0)));
  const ticks = axisTicks(domainMax);
  const PLOT_HEIGHT = 140;
  const points = linePoints(rows, domainMax, { width, height: PLOT_HEIGHT });
  const clipId = useId();

  return (
    <ChartFrame
      caption={caption}
      summary={chartSummary(caption, rows, unit, null)}
      note={note}
      tableRowHeader={xAxisLabel}
      tableColumns={[unit.replace(/^./, (c) => c.toUpperCase())]}
      tableRows={rows.map((row) => ({
        key: row.key,
        label: row.label,
        cells: [finiteOrNull(row.value) === null ? 'Not Available' : String(row.value)],
      }))}
    >
      <div className="stats-chart-plot" ref={attach}>
        <div className="stats-chart-band" style={{ height: `${PLOT_HEIGHT}px` }}>
        <svg
          className="stats-chart-line"
          width={width}
          height={PLOT_HEIGHT}
          viewBox={`0 0 ${width} ${PLOT_HEIGHT}`}
          aria-hidden="true"
          focusable="false"
          onPointerLeave={() => setHover(null)}
        >
          <clipPath id={`stats-line-clip-${clipId}`}>
            <rect x={0} y={0} width={Math.max(0, width)} height={PLOT_HEIGHT} />
          </clipPath>
          {ticks.map((tick) => {
            const y = round(PLOT_HEIGHT - (tick / domainMax) * PLOT_HEIGHT);
            return (
              <line key={tick} className="stats-chart-grid" x1={0} x2={width} y1={y} y2={y} />
            );
          })}
          <line
            className="stats-chart-axis-rule"
            x1={0}
            x2={width}
            y1={PLOT_HEIGHT - 0.5}
            y2={PLOT_HEIGHT - 0.5}
          />
          {points.length > 1 && (
            <polyline
              className="stats-chart-series"
              data-slot="1"
              points={polylinePoints(points)}
              fill="none"
              strokeWidth={LINE_WIDTH}
              clipPath={`url(#stats-line-clip-${clipId})`}
            />
          )}
          {points.map((point) => (
            <g key={point.key}>
              {/* The 2px surface ring keeps a marker legible where it crosses
                  the line or another marker. */}
              <circle
                className="stats-chart-marker-ring"
                cx={round(point.x)}
                cy={round(point.y)}
                r={MARKER_RADIUS + MARKER_RING}
              />
              <circle
                className="stats-chart-marker"
                data-slot="1"
                cx={round(point.x)}
                cy={round(point.y)}
                r={MARKER_RADIUS}
              />
              {/* A hit target far larger than the 8px mark. */}
              <circle
                className="stats-chart-hit"
                cx={round(point.x)}
                cy={round(point.y)}
                r={14}
                onPointerEnter={() =>
                  setHover({
                    key: point.key,
                    x: round(point.x),
                    y: round(Math.max(0, point.y - 8)),
                    label: point.label,
                    value: `${point.value} ${point.value === 1 ? singular(unit) : unit}`,
                    slot: 1,
                  })
                }
              />
            </g>
          ))}
        </svg>
          {ticks.map((tick) => (
            <span
              className="stats-chart-tick stats-chart-tick-y"
              key={tick}
              aria-hidden="true"
              style={{ top: `${round(PLOT_HEIGHT - (tick / domainMax) * PLOT_HEIGHT)}px` }}
            >
              {tick}
            </span>
          ))}
        </div>
        <p className="stats-chart-xlabel">{xAxisLabel}</p>
        <ChartTooltip hover={hover} />
      </div>
    </ChartFrame>
  );
}

/* ---- chart states ------------------------------------------------------ */

/**
 * Loading — the app's existing `LoadingPanel`, REUSED rather than restyled.
 *
 * There is deliberately no chart skeleton here. A shimmering plot outline is the
 * standard treatment and it is the wrong one for this surface: it teaches the
 * reader to read a shape that was never data, and if a read never resolves the
 * fake plot is what stays on screen. A labelled polite status says the true
 * thing ("this is being read") and cannot be mistaken for a figure.
 *
 * This wrapper exists so a chart's loading branch has one obvious import
 * alongside its empty, error, access-pending and unavailable branches — and so
 * this decision is written down at the point someone would otherwise add the
 * skeleton. It delegates rather than duplicating, which also keeps every loading
 * state on the page inside the one `role="status"` selector the test suite waits
 * on.
 */
export function ChartLoading({ label }: { label: string }) {
  return <LoadingPanel label={label} />;
}

/**
 * Empty — the source answered, and there is nothing to draw. NO axes, NO zero
 * bars, NO placeholder rows: a row of zeros is a measurement claim.
 */
export function ChartEmpty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="stats-chart-state stats-chart-state-block">
      <p className="stats-chart-state-title">{title}</p>
      <p className="stats-note">{children}</p>
    </div>
  );
}

/** A localized read failure, with the recourse offered as a real button. */
export function ChartError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="stats-unavailable">
      <p>{message}</p>
      <div className="stats-retry">
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}

/**
 * Access pending — the view exists, the data is not this reader's to see yet.
 *
 * Distinct from {@link ChartEmpty} on purpose, and the distinction is the whole
 * point: empty means "we looked and there was nothing", access-pending means "we
 * cannot attribute anything to you". Rendering the second as the first — as
 * "0 records" — would state a fact nobody established.
 *
 * Neutral, not an error: no alert role, no warning glyph, no red. Nothing here
 * is broken.
 */
export function ChartAccessPending({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="stats-chart-state stats-chart-state-block stats-chart-state-pending">
      <p className="stats-chart-state-title">{title}</p>
      <p className="stats-note">{children}</p>
    </div>
  );
}

/**
 * Data-source-unavailable — the metric would need a signal this build does not
 * record. Also not an error, and pointedly not a zero.
 */
export function ChartSourceUnavailable({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="stats-chart-state stats-chart-state-block">
      <p className="stats-chart-state-title">{title}</p>
      <p className="stats-note">{children}</p>
    </div>
  );
}

/* ---- collapsible technical details ------------------------------------- */

export interface TechnicalDetailsProps {
  /** id for the region's own heading. */
  id: string;
  title: string;
  sub?: string;
  children: ReactNode;
}

/**
 * The collapsed-by-default region for build internals.
 *
 * A native `<details>`, so it is keyboard operable, announces its expanded
 * state, and works with no JavaScript state of its own. Its heading is inside
 * the `<summary>`, which keeps the document outline correct whether the region
 * is open or closed — the alternative (a heading outside a disclosure) leaves an
 * `h2` pointing at nothing when collapsed.
 */
export function TechnicalDetails({ id, title, sub, children }: TechnicalDetailsProps) {
  return (
    <details className="card placeholder-card stats-card stats-technical">
      {/* `<summary>` takes phrasing content optionally intermixed with HEADING
          content — so the `h2` is valid here and a `<p>` would not be. The
          supporting line is therefore a block-displayed `<span>`, not a
          paragraph, and it stays inside the summary so it is readable while the
          region is still closed. */}
      <summary className="stats-technical-summary">
        <h2 className="stats-technical-title" id={id}>
          {title}
        </h2>
        {sub ? <span className="stats-card-sub">{sub}</span> : null}
      </summary>
      <div className="stats-technical-body">{children}</div>
    </details>
  );
}
