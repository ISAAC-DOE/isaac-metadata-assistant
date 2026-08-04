/*
 * Chart geometry — the PURE layer under `StatsCharts.tsx`.
 *
 * Everything here is a total function of its arguments: no React, no DOM, no
 * clock, no locale, no `Math.random`, no fetch. Every scale, tick set, mark
 * rectangle, polyline and accessible sentence a chart draws is computed here, so
 * the same data always produces the same picture and the picture can be tested
 * without rendering anything.
 *
 * THE HONESTY RULES THIS MODULE ENFORCES, because a chart is the easiest place
 * in an app to state something the data does not say:
 *
 *   · A SHARE IS NEVER INVENTED. `share()` returns `null` for a non-positive or
 *     non-finite denominator instead of `0%`, because "0% of nothing" is a claim
 *     and "we cannot express this as a share" is the truth.
 *   · A NON-FINITE VALUE IS NEVER DRAWN. `clampToDomain` maps NaN/Infinity to
 *     `null`, and every mark builder DROPS such a row rather than plotting it at
 *     zero — a zero-length bar reads as "measured, and it was zero".
 *   · NOTHING IS RESCALED PAST ITS DOMAIN. Bar lengths are clamped to the plot
 *     extent, so a caller whose counts exceed the domain they passed cannot
 *     overflow the plot and cannot make one bar silently mean "≥ max".
 *   · ZERO IS DRAWN AS ZERO. A finite `0` keeps its row, its visible label and
 *     its `0` — it is a measurement, unlike an absent value.
 *
 * Units: every function that returns geometry returns CSS PIXELS in a 1:1
 * coordinate space. `StatsCharts.tsx` measures its container and passes the real
 * pixel width, so an SVG's `viewBox` equals its rendered size, `stroke-width`
 * means pixels, a `4px` corner radius is 4px, and `<text>` is never scaled down
 * by `preserveAspectRatio`. That is the whole reason this module is in pixels
 * rather than in a normalized 0..1 space.
 */

/* ---- mark specs (fixed across every chart on this surface) ------------- */

/**
 * Bar/column thickness cap. The band's leftover is deliberately air rather than
 * a fatter mark — a bar that fills its slot reads as a block, not as data.
 */
export const MAX_BAR_THICKNESS = 24;

/** Minimum thickness before a bar stops reading as a bar. */
export const MIN_BAR_THICKNESS = 6;

/** Corner radius on the DATA END of a bar. The baseline end stays square. */
export const BAR_END_RADIUS = 4;

/** The surface-coloured gap that separates touching marks (stacked segments). */
export const SURFACE_GAP = 2;

/** Line stroke width, and the marker radius (>= 4 ⇒ >= 8px diameter). */
export const LINE_WIDTH = 2;
export const MARKER_RADIUS = 4;

/** Ring width in the surface colour, so a marker stays legible on the line. */
export const MARKER_RING = 2;

/** A pointer/focus hit target is never only the painted pixels. */
export const MIN_HIT_TARGET = 24;

/* ---- numbers ----------------------------------------------------------- */

/** A finite number, or `null`. Never a substituted 0. */
export function finiteOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * `value` as a share of `total`, rounded to whole percent — or `null` when no
 * share can honestly be expressed.
 *
 * `null` rather than `0` for a non-positive total is the point of this function.
 * A card that says "0% supported" over an empty field set has stated a
 * measurement nobody made; a card that omits the share has not.
 */
export function share(value: number, total: number): number | null {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return null;
  if (value < 0) return null;
  return Math.round((value / total) * 100);
}

/** `share()` as a display string, or `null`. Never `"0%"` for absent data. */
export function shareLabel(value: number, total: number): string | null {
  const pct = share(value, total);
  return pct === null ? null : `${pct}%`;
}

/**
 * Clamp a value into `[0, domainMax]`, or `null` if it cannot be placed.
 *
 * A non-finite value returns `null` so the caller DROPS the mark; a negative
 * value also returns `null`, because none of the quantities on this surface can
 * be negative (they are all counts) and drawing a negative count as zero would
 * hide a malformed body.
 */
export function clampToDomain(value: number, domainMax: number): number | null {
  if (!Number.isFinite(value) || value < 0) return null;
  if (!Number.isFinite(domainMax) || domainMax <= 0) return 0;
  return Math.min(value, domainMax);
}

/**
 * A "nice" axis maximum at or above `max`, on the 1 / 2 / 5 × 10^n ladder, so
 * tick labels are round numbers (0 · 2 · 4, never 0 · 1.7 · 3.4).
 *
 * `max <= 0` yields 1: an axis still needs a domain, and 1 is the smallest
 * honest one for a chart whose every value is zero. The bars are still drawn at
 * zero length, so nothing about the picture claims a value.
 */
export function niceMax(max: number): number {
  if (!Number.isFinite(max) || max <= 0) return 1;
  const exponent = Math.floor(Math.log10(max));
  const magnitude = Math.pow(10, exponent);
  const scaled = max / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}

/** Whether `value` sits on the 1 / 2 / 5 × 10^n ladder. */
function isLadderStep(value: number): boolean {
  if (!Number.isFinite(value) || value <= 0) return false;
  const scaled = value / Math.pow(10, Math.floor(Math.log10(value)));
  return [1, 2, 5].some((step) => Math.abs(scaled - step) < 1e-9);
}

/**
 * Tick values from 0 to {@link niceMax}, inclusive.
 *
 * The interval is chosen so it DIVIDES the axis maximum exactly and is itself on
 * the 1/2/5 ladder. Choosing the interval first and appending the maximum
 * afterwards — the obvious implementation — produces a crowded pair at the right
 * edge (`0 · 2 · 4 · 5`), which reads as data rather than as a scale.
 *
 * Every tick on this surface is a WHOLE NUMBER, because every quantity on it is
 * a count of records, fields or operations and "2.5 records" is not a thing. The
 * `n = 1` candidate always satisfies both conditions, so this always terminates.
 */
export function axisTicks(max: number): number[] {
  const top = niceMax(max);
  const divisions = [5, 4, 2, 1].find((n) => {
    const step = top / n;
    return Number.isInteger(step) && isLadderStep(step);
  });
  const step = top / (divisions ?? 1);
  const ticks: number[] = [];
  for (let t = 0; t <= top + step / 2; t += step) ticks.push(Number(t.toFixed(6)));
  return ticks;
}

/* ---- bands ------------------------------------------------------------- */

export interface Band {
  /** Start of the band along the cross axis, in px. */
  start: number;
  /** Full band size (mark + air), in px. */
  size: number;
  /** Where the mark sits inside the band, in px. */
  markStart: number;
  /** Mark thickness, capped by {@link MAX_BAR_THICKNESS}. */
  markThickness: number;
}

/**
 * Split `extent` px into `count` equal bands and centre a capped mark in each.
 *
 * The cap is what keeps a two-bar chart from drawing two 90px slabs. Below
 * {@link MIN_BAR_THICKNESS} the mark stops shrinking and the bands overlap
 * instead — the caller's container is then too small for the chart and should
 * scroll, which is a layout decision and not this function's to make silently.
 */
export function bands(count: number, extent: number): Band[] {
  if (count <= 0 || !Number.isFinite(extent) || extent <= 0) return [];
  const size = extent / count;
  const thickness = Math.max(MIN_BAR_THICKNESS, Math.min(MAX_BAR_THICKNESS, size * 0.62));
  return Array.from({ length: count }, (_, i) => {
    const start = size * i;
    return {
      start,
      size,
      markStart: start + (size - thickness) / 2,
      markThickness: thickness,
    };
  });
}

/* ---- horizontal bars --------------------------------------------------- */

export interface BarMark {
  /** The caller's row key, carried through so colour follows the ENTITY. */
  key: string;
  x: number;
  y: number;
  width: number;
  height: number;
  /** The value this mark encodes, for the label and the tooltip. */
  value: number;
}

export interface PlotBox {
  width: number;
  height: number;
}

/**
 * Horizontal bars: value on x, category on y, all bars from a single x=0
 * baseline.
 *
 * A row whose value is non-finite or negative is DROPPED (see
 * {@link clampToDomain}) rather than drawn at zero. A row whose value is a
 * finite `0` keeps a zero-WIDTH mark, so the axis still shows its band and the
 * caller's visible `0` label still sits beside it.
 */
export function horizontalBars(
  rows: readonly { key: string; value: number }[],
  domainMax: number,
  plot: PlotBox,
): BarMark[] {
  const top = niceMax(domainMax);
  const layout = bands(rows.length, plot.height);
  const marks: BarMark[] = [];
  rows.forEach((row, i) => {
    const band = layout[i];
    if (!band) return;
    const value = clampToDomain(row.value, top);
    if (value === null) return;
    marks.push({
      key: row.key,
      x: 0,
      y: band.markStart,
      width: plot.width > 0 ? (value / top) * plot.width : 0,
      height: band.markThickness,
      value: row.value,
    });
  });
  return marks;
}

/**
 * Vertical columns: category on x, value on y, all columns from a single
 * y=`plot.height` baseline. Same drop/zero rules as {@link horizontalBars}.
 */
export function verticalColumns(
  rows: readonly { key: string; value: number }[],
  domainMax: number,
  plot: PlotBox,
): BarMark[] {
  const top = niceMax(domainMax);
  const layout = bands(rows.length, plot.width);
  const marks: BarMark[] = [];
  rows.forEach((row, i) => {
    const band = layout[i];
    if (!band) return;
    const value = clampToDomain(row.value, top);
    if (value === null) return;
    const height = plot.height > 0 ? (value / top) * plot.height : 0;
    marks.push({
      key: row.key,
      x: band.markStart,
      y: plot.height - height,
      width: band.markThickness,
      height,
      value: row.value,
    });
  });
  return marks;
}

/* ---- stacked bar ------------------------------------------------------- */

export interface StackSegment {
  key: string;
  x: number;
  width: number;
  value: number;
  /** Whole-percent share of the stack total, or `null` if none can be stated. */
  sharePct: number | null;
}

/**
 * One horizontal stacked bar: the composition of a single whole.
 *
 * `total` is the caller's OWN denominator, never re-derived from the segments,
 * so a caller who knows the whole is bigger than the parts it can show (a
 * truncated body) cannot have this function quietly re-normalize the picture to
 * 100%.
 *
 * A {@link SURFACE_GAP} sits between adjacent segments, taken out of the
 * PRECEDING segment's width so the stack still ends exactly at `width` when the
 * segments sum to `total`. A segment too small to survive its own gap is
 * returned with `width: 0` — it keeps its legend entry, its table row and its
 * share, and only its (unreadable) sliver is dropped. Zero-value segments are
 * likewise kept at `width: 0` rather than removed, because a class with no
 * fields is a measurement.
 */
export function stackSegments(
  rows: readonly { key: string; value: number }[],
  total: number,
  width: number,
): StackSegment[] {
  const usable = Number.isFinite(width) && width > 0 ? width : 0;
  const denominator = Number.isFinite(total) && total > 0 ? total : 0;
  const drawn = rows.filter((r) => finiteOrNull(r.value) !== null && r.value >= 0);
  let cursor = 0;
  return drawn.map((row, i) => {
    const raw = denominator > 0 ? (row.value / denominator) * usable : 0;
    const isLast = i === drawn.length - 1;
    const gap = isLast ? 0 : SURFACE_GAP;
    const segment: StackSegment = {
      key: row.key,
      x: cursor,
      width: Math.max(0, Math.min(raw - gap, Math.max(0, usable - cursor))),
      value: row.value,
      sharePct: share(row.value, total),
    };
    cursor += raw;
    return segment;
  });
}

/* ---- line ------------------------------------------------------------- */

export interface LinePoint {
  key: string;
  x: number;
  y: number;
  value: number;
  /** The category/period label, carried for the tooltip and the table. */
  label: string;
}

/**
 * An ordered series as pixel points, left to right in the order given.
 *
 * The x positions are the INDEX order, evenly spaced — this module never parses
 * a date and never infers a time interval, so a caller with unevenly spaced
 * observations must not present the result as a time axis. `StatsLineChart`'s
 * caption is the place that has to say what x is.
 *
 * A point whose value is non-finite is DROPPED, which leaves a genuine gap in
 * the polyline rather than a fabricated interpolation through zero.
 */
export function linePoints(
  rows: readonly { key: string; label: string; value: number }[],
  domainMax: number,
  plot: PlotBox,
): LinePoint[] {
  const top = niceMax(domainMax);
  const steps = Math.max(1, rows.length - 1);
  const points: LinePoint[] = [];
  rows.forEach((row, i) => {
    const value = clampToDomain(row.value, top);
    if (value === null) return;
    points.push({
      key: row.key,
      label: row.label,
      value: row.value,
      x: rows.length === 1 ? plot.width / 2 : (i / steps) * plot.width,
      y: plot.height - (value / top) * plot.height,
    });
  });
  return points;
}

/** `linePoints` as an SVG `points` attribute. Empty string for no points. */
export function polylinePoints(points: readonly LinePoint[]): string {
  return points.map((p) => `${round(p.x)},${round(p.y)}`).join(' ');
}

/** 3 decimals is below a device pixel at any plausible zoom and keeps the
 *  serialized attribute short enough to read in a test failure. */
export function round(value: number): number {
  return Number(value.toFixed(3));
}

/* ---- the accessible textual summary ----------------------------------- */

export interface SummaryRow {
  label: string;
  value: number;
}

/**
 * The ONE sentence a screen reader gets in place of the picture.
 *
 * Every chart on this surface carries this AND a data table — the brief for
 * this surface treats them as two requirements, not alternatives, because a
 * sentence gives the shape at a glance while the table gives every figure.
 *
 * `unit` is the caller's noun (records / fields / operations). It is mandatory:
 * the single worst thing a chart summary can do here is state "3" when the
 * quantity is FIELDS and the reader assumes RECORDS — the same conflation
 * `EvidenceTotals.recordsCounted` exists to prevent.
 *
 * The total clause is omitted when `total` is `null`, because a summary must not
 * name a denominator the caller could not supply.
 */
export function chartSummary(
  caption: string,
  rows: readonly SummaryRow[],
  unit: string,
  total: number | null,
): string {
  const lead = caption.replace(/[.:;,\s]+$/, '');
  if (rows.length === 0) {
    return `${lead}. No ${unit} to describe.`;
  }
  const parts = rows.map((row) => `${row.label}: ${describeValue(row.value)}`);
  const totalClause =
    total === null || !Number.isFinite(total) ? '' : ` Total ${total} ${unit}.`;
  return `${lead}. ${parts.join(', ')}.${totalClause}`;
}

/**
 * How a single value is spoken. A non-finite value is "not available" rather
 * than "0" — the same rule the rest of this surface follows for absence.
 */
export function describeValue(value: number): string {
  return Number.isFinite(value) ? String(value) : 'not available';
}

/**
 * The extreme a chart may DIRECTLY label, per the "label selectively" rule —
 * never a number on every mark.
 *
 * Returns the key of the single largest row, or `null` when there is no unique
 * largest (a tie, an empty set, or every value zero). `null` means "label
 * nothing", which is the honest answer: highlighting one of two equal maxima
 * would assert a difference that is not there.
 */
export function soleMaximumKey(rows: readonly { key: string; value: number }[]): string | null {
  let best: { key: string; value: number } | null = null;
  let tied = false;
  for (const row of rows) {
    const value = finiteOrNull(row.value);
    if (value === null || value <= 0) continue;
    if (best === null || value > best.value) {
      best = { key: row.key, value };
      tied = false;
    } else if (value === best.value) {
      tied = true;
    }
  }
  return best === null || tied ? null : best.key;
}
