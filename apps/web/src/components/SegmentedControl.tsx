import './segmented-control.css';
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

/**
 * SEGMENTED CONTROL — a short, exclusive choice drawn as one themed track: a WAI-ARIA `radiogroup` of
 * `role="radio"` buttons.
 *
 * - **Label.** The visible `label` names the group (`aria-labelledby`). To use a heading or legend that is
 *   already on the page instead, pass `labelledBy` and no `label`.
 * - **Roving tab stop.** One Tab stop: the checked segment, or the first enabled one when none is checked.
 *   Arrow keys move AND choose (APG radio group), wrapping at the ends; Home and End jump; Space or Enter
 *   chooses the focused segment.
 * - **"None chosen" is a real state.** `value: null` checks nothing, and nothing is chosen until the person
 *   chooses. A form that must not default a choice (for example "Required?") sends nothing then.
 */

export interface SegmentOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

export interface SegmentedControlProps {
  /** The visible group label. Omit it only when `labelledBy` points at a label already on the page. */
  label?: ReactNode;
  labelledBy?: string;
  options: readonly SegmentOption[];
  value: string | null;
  onChange: (value: string) => void;
  id?: string;
  className?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean;
  'aria-required'?: boolean;
}

export function SegmentedControl({
  label,
  labelledBy,
  options,
  value,
  onChange,
  id,
  className,
  'aria-describedby': describedBy,
  'aria-invalid': invalid,
  'aria-required': required,
}: SegmentedControlProps) {
  const autoId = useId();
  const labelId = `${id ?? `segmented-${autoId}`}-label`;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const enabledIndexes = options.map((o, i) => (o.disabled ? -1 : i)).filter((i) => i >= 0);
  const checkedIndex = options.findIndex((o) => o.value === value);
  /** The one Tab stop. */
  const stop = checkedIndex >= 0 && !options[checkedIndex].disabled ? checkedIndex : (enabledIndexes[0] ?? -1);

  function choose(i: number) {
    const option = options[i];
    if (!option || option.disabled) return;
    refs.current[i]?.focus();
    if (option.value !== value) onChange(option.value);
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    if (enabledIndexes.length === 0) return;
    const pos = enabledIndexes.indexOf(i);
    let next: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = enabledIndexes[(pos + 1) % enabledIndexes.length];
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp')
      next = enabledIndexes[(pos - 1 + enabledIndexes.length) % enabledIndexes.length];
    else if (e.key === 'Home') next = enabledIndexes[0];
    else if (e.key === 'End') next = enabledIndexes[enabledIndexes.length - 1];
    else if (e.key === ' ' || e.key === 'Enter') next = i;
    if (next === null) return;
    e.preventDefault();
    choose(next);
  }

  return (
    <div className={`segmented${className ? ` ${className}` : ''}`} id={id}>
      {label !== undefined && (
        <span className="segmented-label" id={labelId}>
          {label}
        </span>
      )}
      <div
        role="radiogroup"
        className="segmented-track"
        aria-labelledby={label !== undefined ? labelId : labelledBy}
        aria-describedby={describedBy}
        aria-invalid={invalid ? true : undefined}
        aria-required={required ? true : undefined}
      >
        {options.map((o, i) => {
          const checked = i === checkedIndex;
          return (
            <button
              key={o.value}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={checked}
              disabled={o.disabled}
              tabIndex={i === stop ? 0 : -1}
              className={`segmented-option${checked ? ' is-checked' : ''}`}
              onClick={() => choose(i)}
              onKeyDown={(e) => onKeyDown(e, i)}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
