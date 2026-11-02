import './select.css';
import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { Check, ChevronDown } from './icons';

/**
 * SELECT — the app's themed picker, a WAI-ARIA APG "select-only combobox".
 *
 * A drop-in for a native `<select>` whose popup the browser draws in its own style:
 *   - the trigger is a real `<button>` with `role="combobox"`, so `<label htmlFor={id}>` names it and it takes
 *     focus, `disabled` and `aria-describedby` like any control;
 *   - the popup is a `role="listbox"` of `role="option"`s, optionally in `role="group"`s labelled by a visible
 *     group label (the `<optgroup>` equivalent);
 *   - focus never leaves the trigger. The active option is announced through `aria-activedescendant`, and the
 *     trigger keeps focus when the popup closes.
 *
 * Keyboard (APG): Enter / Space / ArrowDown / ArrowUp / Home / End open. While open: arrows, Home / End and
 * PageUp / PageDown move; Enter / Space choose and close; Escape closes without a change; Tab chooses the active
 * option and lets focus move on; typing jumps to the first option starting with the letters typed.
 *
 * `onChange` fires once per real change, never for re-choosing the current value. A value that matches no
 * option (for example `''` before anything is chosen) shows `placeholder`.
 */

export interface SelectOption {
  value: string;
  label: string;
  /** A second, quieter line under the label (its description, not part of its name). */
  detail?: string;
  /** Options with the same `group` are shown together under that group's label, in order of first appearance. */
  group?: string;
  disabled?: boolean;
}

export interface SelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly SelectOption[];
  /** Shown in the trigger while `value` matches no option. */
  placeholder?: string;
  /** When given, a hidden input of this name carries the value, so a native form submit sees it. */
  name?: string;
  disabled?: boolean;
  className?: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean | 'true' | 'false';
  'aria-required'?: boolean | 'true' | 'false';
  /** For a picker with no `<label htmlFor>`: its accessible name. */
  'aria-label'?: string;
  'aria-labelledby'?: string;
}

/** How long typed letters accumulate into one search, as the APG example does. */
const TYPEAHEAD_MS = 500;
const PAGE_STEP = 10;

export const Select = forwardRef<HTMLButtonElement, SelectProps>(function Select(
  {
    id: idProp,
    value,
    onChange,
    options,
    placeholder,
    name,
    disabled = false,
    className,
    'aria-describedby': describedBy,
    'aria-invalid': invalid,
    'aria-required': required,
    'aria-label': ariaLabel,
    'aria-labelledby': labelledBy,
  },
  ref,
) {
  const autoId = useId();
  const id = idProp ?? `select-${autoId}`;
  const listboxId = `${id}-listbox`;
  const optionId = (i: number) => `${id}-option-${i}`;
  const groupId = (i: number) => `${id}-group-${i}`;

  const buttonRef = useRef<HTMLButtonElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => buttonRef.current as HTMLButtonElement);

  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [above, setAbove] = useState(false);
  /** The popup's name: the trigger's label, read when it opens (a `<label htmlFor>` has no id to point at). */
  const [listName, setListName] = useState<string | undefined>(undefined);
  const search = useRef({ text: '', at: 0 });

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null;

  /** The options grouped for display, each keeping its index in `options` (what `active` counts). */
  const sections = useMemo(() => {
    const out: { group: string | null; items: { option: SelectOption; index: number }[] }[] = [];
    options.forEach((option, index) => {
      const group = option.group ?? null;
      let section = out.find((s) => s.group === group);
      if (!section) {
        section = { group, items: [] };
        out.push(section);
      }
      section.items.push({ option, index });
    });
    return out;
  }, [options]);
  /** Display order, so arrow keys move through what the eye sees (groups gather options together). */
  const order = useMemo(() => sections.flatMap((s) => s.items.map((it) => it.index)), [sections]);

  const enabled = useCallback((i: number) => i >= 0 && i < options.length && !options[i].disabled, [options]);

  /** The next enabled option from position `from` in display order, stepping by `step` (no wrap). */
  const move = useCallback(
    (from: number, step: number) => {
      const pos = order.indexOf(from);
      let p = pos === -1 ? (step > 0 ? -1 : order.length) : pos;
      let last = pos === -1 ? -1 : from;
      for (let n = 0; n < Math.abs(step); n++) {
        let q = p + Math.sign(step);
        while (q >= 0 && q < order.length && !enabled(order[q])) q += Math.sign(step);
        if (q < 0 || q >= order.length) break;
        p = q;
        last = order[q];
      }
      return last;
    },
    [order, enabled],
  );
  const firstEnabled = useCallback(() => order.find(enabled) ?? -1, [order, enabled]);
  const lastEnabled = useCallback(() => [...order].reverse().find(enabled) ?? -1, [order, enabled]);

  const openWith = useCallback(
    (index: number) => {
      if (disabled) return;
      const labelText =
        ariaLabel ?? buttonRef.current?.labels?.[0]?.textContent?.trim() ?? undefined;
      setListName(labelText || undefined);
      setActive(index);
      setOpen(true);
    },
    [disabled, ariaLabel],
  );

  const close = useCallback(() => {
    setOpen(false);
    setActive(-1);
    search.current = { text: '', at: 0 };
  }, []);

  const commit = useCallback(
    (index: number) => {
      if (enabled(index) && options[index].value !== value) onChange(options[index].value);
    },
    [enabled, options, value, onChange],
  );

  /** Type-ahead: the first enabled option whose label starts with what was typed, searching after `from`. */
  const findByText = useCallback(
    (text: string, from: number) => {
      const lower = text.toLowerCase();
      const allSame = lower.split('').every((c) => c === lower[0]);
      const start = order.indexOf(from);
      const rotated = [...order.slice(start + 1), ...order.slice(0, start + 1)];
      const match = (q: string) => rotated.find((i) => enabled(i) && options[i].label.toLowerCase().startsWith(q));
      // Typing one letter again cycles through the options starting with it.
      return match(lower) ?? (allSame ? match(lower[0]) : undefined) ?? -1;
    },
    [order, enabled, options],
  );

  function typeahead(char: string, from: number): number {
    const now = Date.now();
    const s = search.current;
    s.text = now - s.at > TYPEAHEAD_MS ? char : s.text + char;
    s.at = now;
    // A fresh one-letter search starts AFTER the current option, so the same letter moves on; a longer search
    // starts AT it (searching after the option before it), so "ca" can stay on "cathode" once "c" found it.
    const pos = order.indexOf(from);
    const base = s.text.length === 1 || pos < 0 ? from : order[(pos - 1 + order.length) % order.length];
    return findByText(s.text, base);
  }

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    const { key, altKey, ctrlKey, metaKey } = e;
    const printable = key.length === 1 && !ctrlKey && !metaKey && !altKey;
    const searching = Date.now() - search.current.at <= TYPEAHEAD_MS && search.current.text !== '';

    if (!open) {
      const start = selectedIndex >= 0 ? selectedIndex : firstEnabled();
      if (key === 'ArrowDown' || key === 'ArrowUp' || key === 'Enter' || key === ' ') {
        e.preventDefault();
        openWith(key === 'ArrowUp' && selectedIndex < 0 ? firstEnabled() : start);
      } else if (key === 'Home') {
        e.preventDefault();
        openWith(firstEnabled());
      } else if (key === 'End') {
        e.preventDefault();
        openWith(lastEnabled());
      } else if (printable) {
        e.preventDefault();
        const found = typeahead(key, selectedIndex >= 0 ? selectedIndex : -1);
        openWith(found >= 0 ? found : start);
      }
      return;
    }

    switch (key) {
      case 'ArrowDown':
        e.preventDefault();
        setActive((a) => move(a, 1));
        return;
      case 'ArrowUp':
        e.preventDefault();
        if (altKey) {
          commit(active);
          close();
        } else setActive((a) => move(a, -1));
        return;
      case 'PageDown':
        e.preventDefault();
        setActive((a) => move(a, PAGE_STEP));
        return;
      case 'PageUp':
        e.preventDefault();
        setActive((a) => move(a, -PAGE_STEP));
        return;
      case 'Home':
        e.preventDefault();
        setActive(firstEnabled());
        return;
      case 'End':
        e.preventDefault();
        setActive(lastEnabled());
        return;
      case 'Escape':
        e.preventDefault();
        close();
        return;
      case 'Enter':
        e.preventDefault();
        commit(active);
        close();
        return;
      case 'Tab':
        // Choose and let focus move on: no preventDefault.
        commit(active);
        close();
        return;
      case ' ':
        if (searching) break; // a space inside a type-ahead search is part of it
        e.preventDefault();
        commit(active);
        close();
        return;
      default:
        break;
    }
    if (printable) {
      e.preventDefault();
      const found = typeahead(key, active);
      if (found >= 0) setActive(found);
    }
  }

  // Click outside closes; so does focus leaving (the trigger keeps focus while open, so a blur means it left).
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) close();
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open, close]);

  // Open below; flip above when there is no room below and more above.
  useLayoutEffect(() => {
    if (!open) return;
    const trigger = buttonRef.current?.getBoundingClientRect();
    const list = listRef.current;
    if (!trigger || !list) return;
    const wanted = Math.min(list.scrollHeight, list.offsetHeight || list.scrollHeight) || 0;
    const below = window.innerHeight - trigger.bottom;
    setAbove(below < wanted + 8 && trigger.top > below);
  }, [open]);

  // Keep the active option in view as it moves.
  useEffect(() => {
    if (!open || active < 0) return;
    const el = document.getElementById(optionId(active));
    el?.scrollIntoView?.({ block: 'nearest' });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- optionId is derived from id
  }, [open, active, id]);

  let groupCount = 0;
  const renderOption = ({ option, index }: { option: SelectOption; index: number }): ReactNode => {
    const isSelected = index === selectedIndex;
    const isActive = index === active;
    const detailId = option.detail ? `${optionId(index)}-detail` : undefined;
    return (
      <div
        key={`${option.value}-${index}`}
        id={optionId(index)}
        role="option"
        aria-selected={isSelected}
        aria-disabled={option.disabled ? true : undefined}
        aria-labelledby={detailId ? `${optionId(index)}-name` : undefined}
        aria-describedby={detailId}
        className={`select-option${isActive ? ' is-active' : ''}${isSelected ? ' is-selected' : ''}`}
        onMouseEnter={() => !option.disabled && setActive(index)}
        onClick={() => {
          if (option.disabled) return;
          commit(index);
          close();
          buttonRef.current?.focus();
        }}
      >
        <Check className="select-check" size={14} strokeWidth={2.25} aria-hidden="true" />
        <span className="select-option-text">
          <span className="select-option-name" id={`${optionId(index)}-name`}>
            {option.label}
          </span>
          {option.detail && (
            <span className="select-option-detail" id={detailId}>
              {option.detail}
            </span>
          )}
        </span>
      </div>
    );
  };

  return (
    <div className={`select${className ? ` ${className}` : ''}`} ref={wrapRef}>
      <button
        ref={buttonRef}
        id={id}
        type="button"
        role="combobox"
        className={`select-trigger${selected ? '' : ' is-empty'}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        aria-describedby={describedBy}
        aria-invalid={invalid}
        aria-required={required}
        aria-label={ariaLabel}
        aria-labelledby={labelledBy}
        data-value={value}
        disabled={disabled}
        onClick={() => (open ? close() : openWith(selectedIndex >= 0 ? selectedIndex : firstEnabled()))}
        onKeyDown={onKeyDown}
        onBlur={() => open && close()}
      >
        <span className="select-value">{selected ? selected.label : (placeholder ?? '')}</span>
        <ChevronDown className="select-chevron" size={16} strokeWidth={2} aria-hidden="true" />
      </button>
      {name !== undefined && <input type="hidden" name={name} value={value} />}
      {/* Always in the page (so `aria-controls` points at something), shown only while open. */}
      <div
        ref={listRef}
        id={listboxId}
        role="listbox"
        // Named only while open: closed, it is hidden, and a name on it would make the label find it as well.
        aria-label={open ? listName : undefined}
        aria-labelledby={open && listName === undefined ? (labelledBy ?? id) : undefined}
        className={`select-popup${above ? ' is-above' : ''}`}
        hidden={!open}
        tabIndex={-1}
        // A press inside the popup must not take focus from the trigger.
        onMouseDown={(e) => e.preventDefault()}
      >
        {sections.map((section) => {
          if (section.group === null) return section.items.map(renderOption);
          const gid = groupId(groupCount++);
          return (
            <div role="group" aria-labelledby={gid} className="select-group" key={`g-${section.group}`}>
              <div role="presentation" id={gid} className="select-group-name">
                {section.group}
              </div>
              {section.items.map(renderOption)}
            </div>
          );
        })}
      </div>
    </div>
  );
});
