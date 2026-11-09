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
  type FocusEvent,
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
 *
 * THE POPUP IS FIXED-POSITIONED from the trigger's rect, not placed inside the wrapper, so a card, scroll box
 * or panel with `overflow: hidden | auto` around the picker cannot clip it. It stays in the wrapper's DOM (not
 * portalled), so it keeps working inside a modal `<dialog>`'s top layer, and its position is measured against
 * its real containing block, so a transformed ancestor (the assistant drawer slides in with `transform`) does
 * not offset it.
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
  /** Passed to the trigger, for forms that validate when a field is left. */
  onFocus?: (e: FocusEvent<HTMLButtonElement>) => void;
  onBlur?: (e: FocusEvent<HTMLButtonElement>) => void;
  /** `compact` is the toolbar and filter-row size: a 34px trigger in body-size text. */
  density?: 'regular' | 'compact';
  /** `data-*` attributes go on the trigger, where a caller's own lookups expect the control. */
  [dataAttribute: `data-${string}`]: string | undefined;
}

/** How long typed letters accumulate into one search, as the APG example does. */
const TYPEAHEAD_MS = 500;
/** The room the popup keeps from the viewport's edges (the page's own gutter at a phone width). */
const EDGE_GUTTER = 16;
/** The popup's widest, however much room there is. */
const POPUP_MAX = 512;
/** The popup's tallest (18rem), however much room there is. */
const POPUP_MAX_HEIGHT = 288;
/** The gap between the trigger and the popup. */
const POPUP_GAP = 4;
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
    onFocus,
    onBlur,
    density = 'regular',
    ...rest
  },
  ref,
) {
  /** Only `data-*` attributes pass through to the trigger; everything else is a named prop above. */
  const dataAttributes = Object.fromEntries(Object.entries(rest).filter(([k]) => k.startsWith('data-')));
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
      const start = order.indexOf(from);
      const rotated = [...order.slice(start + 1), ...order.slice(0, start + 1)];
      const match = (q: string) => rotated.find((i) => enabled(i) && options[i].label.toLowerCase().startsWith(q));
      return match(lower) ?? -1;
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
    // The same letter typed again, however fast, cycles through the options starting with it (APG): the search
    // is that one letter, starting after the current option.
    if (s.text.length > 1 && s.text.split('').every((c) => c === s.text[0])) return findByText(s.text[0], from);
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
        // Escape here belongs to the picker: a dialog or drawer around it must not close too.
        e.preventDefault();
        e.stopPropagation();
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

  // Placement. The popup is `position: fixed` at the trigger, so no clipping ancestor can cut it off. It opens
  // below, and flips above when there is no room below and more above; it is never taller than the room on the
  // side it opens, never wider than the room from the trigger's left edge to the viewport's right gutter (so an
  // indented trigger at a phone width cannot push the page sideways), and never narrower than the trigger.
  //
  // A fixed box is placed against its containing block, which is the viewport unless an ancestor has a
  // `transform`, `filter` or `contain` (the assistant drawer does). So the popup is first put at 0,0, where it
  // lands is read, and that offset is taken off. Measured again while open as the page scrolls or resizes; if
  // the trigger scrolls fully out of view, the popup closes rather than float over unrelated content.
  useLayoutEffect(() => {
    if (!open) return;
    function place(event?: Event) {
      const button = buttonRef.current;
      const list = listRef.current;
      if (!button || !list) return;
      if (event && event.target === list) return; // the popup scrolling its own options moves nothing
      const trigger = button.getBoundingClientRect();
      const viewW = window.innerWidth;
      const viewH = window.innerHeight;
      if (event && (trigger.bottom < 0 || trigger.top > viewH)) {
        close();
        return;
      }
      const style = list.style;
      style.top = '0px';
      style.left = '0px';
      style.minWidth = `${trigger.width}px`;
      style.maxWidth = `${Math.max(trigger.width, Math.min(POPUP_MAX, viewW - trigger.left - EDGE_GUTTER))}px`;
      const below = viewH - trigger.bottom - POPUP_GAP - EDGE_GUTTER / 2;
      const aboveRoom = trigger.top - POPUP_GAP - EDGE_GUTTER / 2;
      style.maxHeight = '';
      const wanted = Math.min(list.scrollHeight || list.offsetHeight, POPUP_MAX_HEIGHT);
      const flip = below < wanted && aboveRoom > below;
      const room = Math.max(0, Math.floor(flip ? aboveRoom : below));
      if (room < wanted) style.maxHeight = `${room}px`;
      const height = Math.min(list.offsetHeight || wanted, room < wanted ? room : wanted);
      const origin = list.getBoundingClientRect();
      const top = flip ? trigger.top - POPUP_GAP - height : trigger.bottom + POPUP_GAP;
      style.top = `${top - origin.top}px`;
      style.left = `${trigger.left - origin.left}px`;
      setAbove(flip);
    }
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, close, options]);

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
        // The value, for a lookup by value (an end-to-end test choosing a schema token, as `selectOption` did).
        data-value={option.value}
        aria-selected={isSelected}
        aria-disabled={option.disabled ? true : undefined}
        aria-labelledby={detailId ? `${optionId(index)}-name` : undefined}
        aria-describedby={detailId}
        className={`select-option${isActive ? ' is-active' : ''}${isSelected ? ' is-selected' : ''}`}
        onMouseEnter={() => !option.disabled && setActive(index)}
        onClick={() => {
          // A disabled option, or any option of a disabled picker (which never opens), chooses nothing.
          if (option.disabled || disabled) return;
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
    <div
      className={`select${density === 'compact' ? ' select-compact' : ''}${className ? ` ${className}` : ''}`}
      ref={wrapRef}
    >
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
        {...dataAttributes}
        data-value={value}
        disabled={disabled}
        onClick={() => (open ? close() : openWith(selectedIndex >= 0 ? selectedIndex : firstEnabled()))}
        onKeyDown={onKeyDown}
        onKeyUp={(e) => {
          // A button activates on Space at keyup (Firefox does so even when the keydown was prevented), which
          // would toggle the popup straight back. Space is handled at keydown, so its keyup does nothing here.
          if (e.key === ' ') e.preventDefault();
        }}
        onFocus={onFocus}
        onBlur={(e) => {
          if (open) close();
          onBlur?.(e);
        }}
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
