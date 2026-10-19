import './widget.css';
import {
  useState,
  type HTMLAttributes,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';

import { Disclosure } from './Disclosure';
import { Info } from './icons';

/**
 * WIDGET — one titled card that answers ONE question.
 *
 * Built for the Statistics redesign (owner direction, 2026-10-12: the page was
 * "a whole bunch of spam"; think of it as widgets, with the timelines and
 * breakdowns one click away INSIDE the widget) and written as a shared primitive
 * so the rest of the site can adopt it rather than re-deriving it.
 *
 * ── ANATOMY, IN DOCUMENT ORDER ────────────────────────────────────────────
 *
 *   header   icon · title (the region's accessible name) · optional one-line
 *            `sub` · tools on the right: an optional RANGE group and an
 *            optional INFO toggle
 *   info     the provenance / honesty prose, `hidden` until the toggle is
 *            pressed (it stays in the DOM, so every guard that reads the DOM
 *            still reaches it, and so `aria-controls` never dangles)
 *   lead     an optional qualifier that must be read BEFORE the headline
 *   headline the one figure or state the widget exists to state
 *   body     `children` — always visible (caveats that qualify the headline,
 *            loading / error states)
 *   views    an optional in-widget VIEW SWITCHER — a WAI-ARIA tablist of
 *            icon + label tabs that swaps the panel below it in place
 *   details  an optional expansion for the long list (the shared `Disclosure`)
 *   footer   links and the widget's own metadata
 *
 * ── WHAT EACH SLOT MAY HOLD, AND THE ONE RULE THAT DECIDES IT ──────────────
 *
 * THE INFO PANEL HOLDS PROSE AND NEVER A MEASUREMENT. It is closed by default,
 * a reader scanning the page skips it, and axe does not scan it while it is
 * closed — so a figure inside it would be a hidden figure. That is the rule the
 * Statistics page has enforced on its `<details>` disclosures since 2026-09-15,
 * carried over unchanged; `statistics-page.test.tsx` asserts it on every info
 * panel.
 *
 * A VIEW IS NOT A DISCLOSURE. Each view is a named, always-reachable alternative
 * presentation of the same figures — the breakdown beside the headline, not an
 * explanation of it — and the widget's headline stays visible whichever view is
 * selected. Inactive panels are `hidden`, NOT unmounted, so state inside one
 * survives a switch and every DOM-reading guard still reaches its text.
 *
 * A SENTENCE THAT QUALIFIES THE HEADLINE BELONGS IN `children`, visible, beside
 * the figure it qualifies. Moving a caveat into the info panel leaves the
 * visible figure reading as if it had none.
 *
 * ── ACCESSIBILITY ──────────────────────────────────────────────────────────
 *
 *   · The widget is a `<section aria-labelledby>` — a named `region` landmark.
 *   · The view switcher is the APG tabs pattern: automatic activation, roving
 *     tabindex, Arrow/Home/End, `aria-controls` on every tab (every panel is
 *     mounted), each panel `aria-labelledby` its tab. It is named
 *     "<title> Views" so it never collides with a page-level tablist.
 *   · The range group is a `radiogroup` of `role="radio"` buttons with the same
 *     roving keyboard model.
 *   · The info toggle is a real `<button>` with `aria-expanded` and
 *     `aria-controls`; its accessible name is "About <title>".
 *   · Icons are decorative (`aria-hidden`) everywhere; every control carries its
 *     meaning in text.
 *
 * It fetches nothing, formats no number and holds no state beyond which view is
 * shown and whether the info panel is open.
 */

export interface WidgetView {
  /** Stable id — becomes part of the tab and panel element ids. */
  id: string;
  /** Title Case, visible on the tab. */
  label: string;
  /** Decorative glyph beside the label. */
  icon?: ReactNode;
  content: ReactNode;
}

export interface WidgetRangeOption {
  value: string;
  /** Title Case, visible on the chip. */
  label: string;
}

export interface WidgetRange {
  /** The radiogroup's accessible name, e.g. "Time Range". */
  label: string;
  options: readonly WidgetRangeOption[];
  value: string;
  onChange: (value: string) => void;
}

export interface WidgetProps {
  /** Id of the heading; the section is `aria-labelledby` it. */
  id: string;
  /** Title Case. The region's accessible name. */
  title: string;
  /** Decorative glyph beside the title. */
  icon?: ReactNode;
  /** One sentence-case line under the title — the question the widget answers. */
  sub?: string;
  /**
   * A qualifier that must be READ BEFORE the headline — a truncation caveat, the
   * corpus a figure was measured over. Rendered visible, above the headline.
   */
  lead?: ReactNode;
  /** The headline figure or state. */
  headline?: ReactNode;
  /** Provenance / honesty PROSE, behind the info toggle. Never a measurement. */
  info?: ReactNode;
  /** Replaces the info toggle's accessible name ("About <title>"). */
  infoLabel?: string;
  /** In-widget views. One view renders without a switcher. */
  views?: readonly WidgetView[];
  /**
   * The initially selected view (uncontrolled). Defaults to the first. `null`
   * starts with no view open, and is honoured only with
   * `viewSwitcher="buttons"` + `collapsible`.
   */
  defaultView?: string | null;
  /** Controlled selection; pass with `onViewChange`. `null` = collapsed (see above). */
  view?: string | null;
  /** Called with the requested view id. */
  onViewChange?: (id: string) => void;
  /**
   * `'buttons'` + `collapsible` only: called when the reader collapses the
   * widget to no view. Kept separate from `onViewChange` so that callback's
   * `(id: string)` signature is unchanged for existing callers.
   */
  onViewCollapse?: () => void;
  /** An optional range selector in the header (e.g. 7 · 30 · 365 days). */
  range?: WidgetRange;
  /** The long list, behind a full-row disclosure. */
  details?: { summary: ReactNode; meta?: ReactNode; content: ReactNode };
  /** Links and widget metadata, at the foot. */
  footer?: ReactNode;
  /** `full` spans every column of a `.widget-grid`. */
  span?: 'full' | 'auto';
  /** 2 by default. 3 only when nested under another heading. */
  headingLevel?: 2 | 3;
  /**
   * Extra attributes for the HEADING element — e.g. `tabIndex={-1}` so a caller
   * can move focus to the widget's title after a navigation. `id` and
   * `className` are the widget's own and cannot be overridden here.
   * (Added 2026-10-18 for the Settings adoption; additive.)
   */
  headingProps?: Omit<HTMLAttributes<HTMLHeadingElement>, 'id' | 'className' | 'children'>;
  /**
   * HOW THE VIEWS ARE SWITCHED. `'tabs'` (the default) is the WAI-ARIA tablist
   * described above. `'buttons'` is a plain group of toggle buttons
   * (`aria-pressed` + `aria-controls`, every button in the Tab order, no arrow
   * keys) for a surface that must not nest a tablist inside a page-level one —
   * `settings-page.test.tsx` bans a nested tablist on Settings.
   * (Added 2026-10-18 for the Settings adoption; additive.)
   */
  viewSwitcher?: 'tabs' | 'buttons';
  /**
   * `'buttons'` only: pressing the SELECTED view's button again collapses the
   * widget to no view (every panel hidden), and the widget may start collapsed
   * with `defaultView={null}`. Ignored for `'tabs'`, where exactly one tab is
   * always selected by the pattern's own definition.
   */
  collapsible?: boolean;
  /** Always-visible body, after the headline. */
  children?: ReactNode;
  className?: string;
  /** `data-*` attributes are passed through to the `<section>`. */
  [dataAttribute: `data-${string}`]: string | number | boolean | undefined;
}

/** The element ids the widget derives — exported so a test or a caller can
 *  address one view without re-deriving the scheme. */
export const widgetIds = {
  info: (id: string) => `${id}-info`,
  views: (id: string) => `${id}-views`,
  tab: (id: string, view: string) => `${id}-tab-${view}`,
  panel: (id: string, view: string) => `${id}-panel-${view}`,
};

/**
 * The keyboard model shared by the view tablist and the range radiogroup:
 * Arrow keys wrap, Home and End jump, and selection follows focus.
 */
function rovingIndex(key: string, index: number, length: number): number | null {
  if (key === 'ArrowRight' || key === 'ArrowDown') return (index + 1) % length;
  if (key === 'ArrowLeft' || key === 'ArrowUp') return (index - 1 + length) % length;
  if (key === 'Home') return 0;
  if (key === 'End') return length - 1;
  return null;
}

export function Widget({
  id,
  title,
  icon,
  sub,
  lead,
  headline,
  info,
  infoLabel,
  views,
  defaultView,
  view: controlledView,
  onViewChange,
  onViewCollapse,
  range,
  details,
  footer,
  span = 'auto',
  headingLevel = 2,
  headingProps,
  viewSwitcher = 'tabs',
  collapsible = false,
  children,
  className,
  ...rest
}: WidgetProps) {
  const [infoOpen, setInfoOpen] = useState(false);
  const [uncontrolledView, setUncontrolledView] = useState<string | null | undefined>(
    defaultView,
  );
  const Heading: 'h2' | 'h3' = headingLevel === 3 ? 'h3' : 'h2';

  /* Only `data-*` keys survive into the section; anything else in `rest` is a
     caller error the types already refuse. */
  const dataAttributes = Object.fromEntries(
    Object.entries(rest).filter(([key]) => key.startsWith('data-')),
  );

  const viewList = views ?? [];
  const canCollapse = viewSwitcher === 'buttons' && collapsible;
  const requested = controlledView !== undefined ? controlledView : uncontrolledView;
  const activeView: string | undefined =
    requested === null && canCollapse
      ? undefined
      : (viewList.find((candidate) => candidate.id === requested)?.id ?? viewList[0]?.id);

  function selectView(next: string | null) {
    if (next === null) onViewCollapse?.();
    else onViewChange?.(next);
    if (controlledView === undefined) setUncontrolledView(next);
  }

  function pressViewButton(candidate: string) {
    selectView(canCollapse && candidate === activeView ? null : candidate);
  }

  function onTabKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    const next = rovingIndex(event.key, index, viewList.length);
    if (next === null) return;
    event.preventDefault();
    const target = viewList[next];
    selectView(target.id);
    (document.getElementById(widgetIds.tab(id, target.id)) as HTMLButtonElement | null)?.focus();
  }

  /* THE RANGE SITS WITH THE VIEWS when there are views: both choose WHAT the
     body below shows, so they read as one control bar beneath the headline.
     With no views it sits in the header beside the info toggle. */
  const rangeInBar = range !== undefined && viewList.length > 1;
  const hasTools = (range !== undefined && !rangeInBar) || info !== undefined;

  return (
    <section
      {...dataAttributes}
      className={`widget${className ? ` ${className}` : ''}`}
      aria-labelledby={id}
      data-span={span}
    >
      <header className="widget-head">
        {icon ? (
          <span className="widget-icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <div className="widget-titles">
          <Heading {...headingProps} className="widget-title" id={id}>
            {title}
          </Heading>
          {sub ? <p className="widget-sub">{sub}</p> : null}
        </div>
        {hasTools ? (
          <div className="widget-tools">
            {range && !rangeInBar ? <WidgetRangeGroup widgetId={id} range={range} /> : null}
            {info !== undefined ? (
              <button
                type="button"
                className="widget-info-toggle"
                aria-label={infoLabel ?? `About ${title}`}
                /* The same words as a hover tooltip: the control is an icon,
                   and a sighted pointer user otherwise gets no name for it. */
                title={infoLabel ?? `About ${title}`}
                aria-expanded={infoOpen}
                aria-controls={widgetIds.info(id)}
                onClick={() => setInfoOpen((open) => !open)}
              >
                <Info size={16} strokeWidth={2} aria-hidden="true" />
              </button>
            ) : null}
          </div>
        ) : null}
      </header>

      {info !== undefined ? (
        <div className="widget-info" id={widgetIds.info(id)} hidden={!infoOpen}>
          {info}
        </div>
      ) : null}

      {lead}

      {headline !== undefined && headline !== null ? (
        <div className="widget-headline">{headline}</div>
      ) : null}

      {children}

      {viewList.length > 1 && viewSwitcher === 'buttons' ? (
        <div className="widget-views-wrap" data-switcher="buttons">
          <div className="widget-bar">
            {/* A GROUP OF TOGGLE BUTTONS, not a tablist: each button is in the
                Tab order, says whether its view is shown (`aria-pressed`) and
                which panel it controls. No roving tabindex and no arrow keys —
                those belong to the tabs pattern this deliberately is not. */}
            <div className="widget-views" role="group" aria-label={`${title} Views`} id={widgetIds.views(id)}>
              {viewList.map((candidate) => {
                const pressed = candidate.id === activeView;
                return (
                  <button
                    key={candidate.id}
                    id={widgetIds.tab(id, candidate.id)}
                    type="button"
                    className="widget-view-tab"
                    aria-pressed={pressed}
                    aria-controls={widgetIds.panel(id, candidate.id)}
                    onClick={() => pressViewButton(candidate.id)}
                  >
                    {candidate.icon ? (
                      <span className="widget-view-icon" aria-hidden="true">
                        {candidate.icon}
                      </span>
                    ) : null}
                    <span>{candidate.label}</span>
                  </button>
                );
              })}
            </div>
            {rangeInBar && range ? <WidgetRangeGroup widgetId={id} range={range} /> : null}
          </div>
          {viewList.map((candidate) => (
            <div
              key={candidate.id}
              id={widgetIds.panel(id, candidate.id)}
              className="widget-view-panel"
              role="region"
              aria-labelledby={widgetIds.tab(id, candidate.id)}
              hidden={candidate.id !== activeView}
            >
              {candidate.content}
            </div>
          ))}
        </div>
      ) : viewList.length > 1 ? (
        <div className="widget-views-wrap">
          <div className="widget-bar">
            <div
              className="widget-views"
              role="tablist"
              aria-label={`${title} Views`}
              id={widgetIds.views(id)}
            >
              {viewList.map((candidate, index) => {
                const selected = candidate.id === activeView;
                return (
                  <button
                    key={candidate.id}
                    id={widgetIds.tab(id, candidate.id)}
                    type="button"
                    role="tab"
                    className="widget-view-tab"
                    aria-selected={selected}
                    aria-controls={widgetIds.panel(id, candidate.id)}
                    tabIndex={selected ? 0 : -1}
                    onClick={() => selectView(candidate.id)}
                    onKeyDown={(event) => onTabKeyDown(event, index)}
                  >
                    {candidate.icon ? (
                      <span className="widget-view-icon" aria-hidden="true">
                        {candidate.icon}
                      </span>
                    ) : null}
                    <span>{candidate.label}</span>
                  </button>
                );
              })}
            </div>
            {rangeInBar && range ? <WidgetRangeGroup widgetId={id} range={range} /> : null}
          </div>
          {viewList.map((candidate) => (
            <div
              key={candidate.id}
              id={widgetIds.panel(id, candidate.id)}
              className="widget-view-panel"
              role="tabpanel"
              aria-labelledby={widgetIds.tab(id, candidate.id)}
              /* APG: a tab panel is itself in the tab sequence, so a keyboard
                 user can reach a panel whose content holds no focusable
                 element (a figure list, a chart) right after the tablist. */
              tabIndex={0}
              hidden={candidate.id !== activeView}
            >
              {candidate.content}
            </div>
          ))}
        </div>
      ) : viewList.length === 1 ? (
        <div className="widget-view-panel">{viewList[0].content}</div>
      ) : null}

      {details ? (
        <Disclosure className="widget-details" summary={details.summary} meta={details.meta}>
          {details.content}
        </Disclosure>
      ) : null}

      {footer ? <footer className="widget-foot">{footer}</footer> : null}
    </section>
  );
}

/**
 * The range chips — a `radiogroup`, because exactly one range is in force and
 * choosing one is a selection, not a navigation.
 */
function WidgetRangeGroup({ widgetId, range }: { widgetId: string; range: WidgetRange }) {
  function onKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    const next = rovingIndex(event.key, index, range.options.length);
    if (next === null) return;
    event.preventDefault();
    const target = range.options[next];
    range.onChange(target.value);
    (
      document.getElementById(`${widgetId}-range-${target.value}`) as HTMLButtonElement | null
    )?.focus();
  }
  return (
    <div className="widget-range" role="radiogroup" aria-label={range.label}>
      {range.options.map((option, index) => {
        const checked = option.value === range.value;
        return (
          <button
            key={option.value}
            id={`${widgetId}-range-${option.value}`}
            type="button"
            role="radio"
            className="widget-range-option"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => range.onChange(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * A `.widget-grid` — the layout every widget surface uses. Columns are
 * auto-fitted from a minimum track, so a 955px column holds two widgets, a
 * 1,246px column holds two or three, and a phone holds one, with no media query
 * deciding it.
 */
export function WidgetGrid({ children, label }: { children: ReactNode; label?: string }) {
  /* A NAME NEEDS A ROLE: `aria-label` on a bare `<div>` is prohibited (it names
     nothing a screen reader announces), so a labelled grid is a `group`, and an
     unlabelled one carries neither. */
  return (
    <div
      className="widget-grid"
      role={label ? 'group' : undefined}
      aria-label={label}
    >
      {children}
    </div>
  );
}
