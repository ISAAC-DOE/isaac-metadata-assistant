import './statistics.css';
import type { ReactNode } from 'react';

/**
 * Statistics — presentational primitives.
 *
 * Every export here is a PURE function of its props. Nothing in this file
 * fetches, derives, formats a number, computes a percentage of anything the
 * caller did not hand it, holds state, reads a clock, or imports a model. The
 * Statistics page's derivations live in `lib/statisticsModel.ts` and the
 * fetches live on the page; these components only render what they are given.
 *
 * One deliberate consequence of that: every numeric prop that is DISPLAYED is
 * typed `string`, not `number`. The caller decides the formatting, and can
 * therefore pass a word ("Synthetic-Only") or an explicit unavailable string in
 * the same slot. No primitive here substitutes a default, a dash, a zero, or a
 * "0" for a value it was not given — that would be inventing a figure.
 *
 * The QUANTITATIVE primitives — bar, column, stacked, comparison and line charts,
 * their legends, tooltips, text equivalents and states — live in
 * `StatsCharts.tsx`, which is where geometry, measurement and pointer state
 * belong. This file stays free of all four.
 *
 * Icons are accepted as `ReactNode` props rather than imported, so this file
 * needs no glyph from the `components/icons` barrel and a caller can pass any
 * already-formed node. Decorative icons are wrapped in an `aria-hidden="true"`
 * span here, so callers must NOT rely on an icon to convey meaning.
 */

/* ---- StatsSection ----------------------------------------------------- */

export interface StatsSectionProps {
  /** id for the heading; the section is `aria-labelledby` this value. */
  id: string;
  /** Title Case, per the app's casing convention. */
  title: string;
  /** Optional sentence-case supporting line. */
  sub?: string;
  /** Decorative only — rendered `aria-hidden`. */
  icon?: ReactNode;
  children: ReactNode;
  /** 2 by default. Use 3 only when nested inside another section's h2. */
  headingLevel?: 2 | 3;
}

/**
 * The card shell every Statistics region uses: the app's standard
 * `card placeholder-card` chrome, a heading the section is labelled by, and an
 * optional supporting line.
 */
export function StatsSection({
  id,
  title,
  sub,
  icon,
  children,
  headingLevel = 2,
}: StatsSectionProps) {
  const Heading: 'h2' | 'h3' = headingLevel === 3 ? 'h3' : 'h2';
  return (
    <section className="card placeholder-card stats-card" aria-labelledby={id}>
      <header className="stats-card-head">
        {icon ? (
          <span className="stats-card-icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <div className="stats-card-headings">
          <Heading id={id}>{title}</Heading>
          {sub ? <p className="stats-card-sub">{sub}</p> : null}
        </div>
      </header>
      {children}
    </section>
  );
}

/* ---- StatCard --------------------------------------------------------- */

export type StatTone = 'neutral' | 'good' | 'attention' | 'quiet';

export interface StatCardProps {
  /** Title Case label. Always states the meaning in words. */
  label: string;
  /**
   * Already-formatted display value. A string on purpose: the caller owns
   * formatting, and can pass a word or the literal unavailable text. This
   * component never formats, parses, rounds or defaults it.
   */
  value: string;
  /** Optional sentence-case clarifier beneath the value. */
  note?: string;
  /** Decorative only — rendered `aria-hidden`. */
  icon?: ReactNode;
  /**
   * Decoration, never the sole carrier of meaning: the label and value say it
   * in words, so the card is fully readable with all colour removed.
   * `quiet` is the neutral not-available treatment, not an error treatment.
   */
  tone?: StatTone;
}

/**
 * One at-a-glance metric, rendered as a single-group definition list — a
 * `<dt>` label followed by the `<dd>` value (and an optional `<dd>` note), per
 * the repo rule that figures must be a labelled `<dl>` and never bare divs of
 * numbers.
 */
export function StatCard({ label, value, note, icon, tone = 'neutral' }: StatCardProps) {
  return (
    <dl className="stat-card" data-tone={tone}>
      <dt className="stat-card-label">
        {icon ? (
          <span className="stat-card-icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <span>{label}</span>
      </dt>
      <dd className="stat-card-value mono">{value}</dd>
      {note ? <dd className="stat-card-note">{note}</dd> : null}
    </dl>
  );
}

/* ---- FigureList ------------------------------------------------------- */

export interface FigureRow {
  /** Title Case label. */
  label: string;
  /** Already-formatted display value — see `StatCardProps.value`. */
  value: string;
  /** Render the value in the mono/tabular face (ids, hashes, counts). */
  mono?: boolean;
}

export interface FigureListProps {
  rows: readonly FigureRow[];
}

/**
 * A grid of labelled figures as a definition list. Renders NOTHING when
 * `rows` is empty — an empty `<dl>` would be a labelled container with no
 * content, and inventing a placeholder row is exactly the guess this project
 * forbids. Use `UnavailableNote` when the absence itself needs stating.
 */
export function FigureList({ rows }: FigureListProps) {
  if (rows.length === 0) return null;
  return (
    <dl className="stats-figures">
      {rows.map((row) => (
        <div className="stats-figure" key={row.label}>
          <dt>{row.label}</dt>
          <dd className={row.mono ? 'mono' : undefined}>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/*
 * ---- StageBars: REMOVED, and this note is why -------------------------
 *
 * `StageBars` used to live here and drew all three of this page's
 * distributions. It scaled every bar against the TOTAL, drew no axis and no
 * tick labels, and offered no data table — so six workflow buckets over five
 * records read as six near-empty progress tracks, and a length could not be
 * read as a number. Its only text equivalent was one `aria-label`.
 *
 * It is SUPERSEDED, not merely unused, by `StatsCharts.tsx`:
 * `StatsBarChart` for a shared-axis comparison and `StatsComparisonRows` for
 * the compact case, both scaled to the largest value and both carrying a
 * summary sentence AND a data table.
 *
 * DELETED RATHER THAN LEFT IN PLACE on purpose. A progress-bar-shaped
 * "chart" primitive sitting in this file is exactly how the next slice
 * reintroduces the misleading visualization this one replaced.
 *
 * The six page-scoped `--stats-cat-*` categorical slots it used are gone from
 * `statistics.css` for the same reason: no chart on this surface encodes
 * identity by hue any more (one series takes one colour; the stacked bar takes
 * a validated ordinal ramp), so keeping six categorical slots would be an
 * invitation to paint a comparison in six hues that mean nothing.
 */

/* ---- MiniBreakdown ---------------------------------------------------- */

export interface MiniBreakdownItem {
  key: string;
  /** A formed chip node (e.g. `<StatusChip …/>`) carrying its own text. */
  chip: ReactNode;
  count: number;
  /** Singular/plural unit for screen readers, e.g. "fields" / "records". */
  noun: string;
}

export interface MiniBreakdownProps {
  /** Title Case label for the row. */
  label: string;
  items: readonly MiniBreakdownItem[];
}

/**
 * A chip + count-badge row, following the `.evclass-summary` precedent — chip,
 * numeric badge, and the unit noun in `.sr-only` so the badge is not a bare
 * number to a screen reader.
 *
 * Renders EVERY item, including zero counts, in exactly the order given: the
 * caller supplies severity order, and re-sorting here would silently change
 * what the row means. No `role="status"` — this is a static figure, not a live
 * region, so it must not announce itself on mount.
 */
export function MiniBreakdown({ label, items }: MiniBreakdownProps) {
  return (
    <div className="stats-mini">
      <p className="stats-mini-label">{label}</p>
      <div className="stats-mini-items">
        {items.map((item) => (
          <span className="stats-mini-item" key={item.key}>
            {item.chip}
            <span className="stats-mini-n mono">{item.count}</span>
            <span className="sr-only">{item.noun}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ---- UnavailableNote -------------------------------------------------- */

export interface UnavailableNoteProps {
  children: ReactNode;
}

/**
 * The honest-absence state, for a figure that genuinely is not available.
 *
 * Deliberately NOT error-styled: neutral `--cover-*` colours, no red, no
 * `role="alert"`, no live region, and no warning icon. An unavailable figure
 * is a fact about this workspace, not a fault, and dressing it as an error
 * would misinform the reader.
 */
export function UnavailableNote({ children }: UnavailableNoteProps) {
  return <div className="stats-unavailable">{children}</div>;
}
