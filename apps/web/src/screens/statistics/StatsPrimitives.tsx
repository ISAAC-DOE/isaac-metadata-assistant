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
 * Two deliberate consequences of that:
 *
 *  - Every numeric prop that is DISPLAYED is typed `string`, not `number`.
 *    The caller decides the formatting, and can therefore pass a word
 *    ("Synthetic-Only") or an explicit unavailable string in the same slot. No
 *    primitive here substitutes a default, a dash, a zero, or a "0" for a
 *    value it was not given — that would be inventing a figure.
 *
 *  - `count` and `total` on `StageBars` are numbers because they are the only
 *    place a proportion is needed, and the proportion is computed from the
 *    caller's own two numbers with no rounding of the displayed count.
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

/* ---- StageBars -------------------------------------------------------- */

/** Number of page-scoped categorical colour slots declared in statistics.css. */
const CATEGORICAL_SLOTS = 6;

/**
 * Map a caller-supplied tone index onto one of the six `--stats-cat-*` slots.
 * Returns `undefined` for a missing or non-finite index, which leaves the bar
 * on the neutral default rather than picking a colour on the caller's behalf.
 */
function categorySlot(toneIndex: number | undefined): string | undefined {
  if (toneIndex === undefined || !Number.isFinite(toneIndex)) return undefined;
  return String((Math.trunc(Math.abs(toneIndex)) % CATEGORICAL_SLOTS) + 1);
}

/**
 * Bar width as a percentage of `total`. A non-positive `total` yields `0%` for
 * every row rather than dividing by zero, and the result is clamped to 100%
 * so a caller whose counts exceed their total cannot overflow the track.
 */
function barWidth(count: number, total: number): string {
  if (!Number.isFinite(count) || !Number.isFinite(total)) return '0%';
  if (total <= 0 || count <= 0) return '0%';
  return `${Math.min(100, (count / total) * 100).toFixed(3)}%`;
}

export interface StageBarRow {
  id: string;
  /** Title Case bucket name. Rendered as visible text on every row. */
  label: string;
  count: number;
  /** Optional categorical colour slot; omit for the neutral default. */
  toneIndex?: number;
}

export interface StageBarsProps {
  /** Sentence-case caption describing the distribution. */
  caption: string;
  rows: readonly StageBarRow[];
  /** Denominator for the bar widths. */
  total: number;
}

/**
 * A horizontal bar breakdown built from flex divs and `background` — the
 * repo's only bar precedent (`.progress` / `.progress-seg`). No chart library,
 * no SVG, and no coloured side border (which the no-vertical-rail gate
 * rejects).
 *
 * Accessibility: the bars are wrapped in a single `role="img"` whose
 * `aria-label` names every bucket, its count and the total, so a screen
 * reader receives the whole distribution as one string instead of walking a
 * pile of unlabelled divs. Every row ALSO renders its label and its count as
 * visible text, and a zero-count row still renders with a visible `0` and a
 * zero-width segment. There is no tooltip anywhere in this component, so no
 * information is hover-only.
 *
 * Renders nothing when `rows` is empty, for the same reason as `FigureList`.
 */
export function StageBars({ caption, rows, total }: StageBarsProps) {
  if (rows.length === 0) return null;
  const distribution = rows.map((row) => `${row.label}: ${row.count}`).join(', ');
  /* One sentence per clause regardless of whether the caller's caption already
     ends in punctuation — the label is read aloud verbatim. */
  const lead = caption.replace(/[.:;,\s]+$/, '');
  return (
    <figure className="stats-bars">
      <figcaption className="stats-bars-caption">{caption}</figcaption>
      <div
        className="stats-bars-body"
        role="img"
        aria-label={`${lead}. ${distribution}. Total ${total}.`}
      >
        {rows.map((row) => (
          <div className="stats-bar-row" key={row.id}>
            <span className="stats-bar-label">{row.label}</span>
            <span className="stats-bar-count mono">{row.count}</span>
            <span className="stats-bar-track">
              <span
                className="stats-bar-fill"
                data-cat={categorySlot(row.toneIndex)}
                style={{ width: barWidth(row.count, total) }}
              />
            </span>
          </div>
        ))}
      </div>
    </figure>
  );
}

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
