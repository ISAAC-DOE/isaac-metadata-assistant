import { afterEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { useState } from 'react';

import { Select, type SelectOption } from '../components/Select';
import { chooseOption, chooseValue, optionValues, selectGroups, selectValue } from '../test/controls';

/**
 * SELECT — the APG select-only combobox. What is pinned is the contract a native `<select>` user relies on:
 * the label names it, the keys a person uses work, a choice is reported once, Escape changes nothing, focus
 * never leaves the trigger, and groups are exposed as groups.
 */

const FRUIT: SelectOption[] = [
  { value: 'apple', label: 'Apple' },
  { value: 'apricot', label: 'Apricot' },
  { value: 'banana', label: 'Banana', detail: 'Yellow, curved' },
  { value: 'blueberry', label: 'Blueberry', disabled: true },
  { value: 'cherry', label: 'Cherry' },
];

function Harness({
  initial = '',
  options = FRUIT,
  onChange,
  placeholder = 'Choose a fruit…',
}: {
  initial?: string;
  options?: SelectOption[];
  onChange?: (v: string) => void;
  placeholder?: string;
}) {
  const [value, setValue] = useState(initial);
  return (
    <div>
      <label htmlFor="fruit">Fruit</label>
      <Select
        id="fruit"
        value={value}
        options={options}
        placeholder={placeholder}
        aria-describedby="fruit-hint"
        onChange={(v) => {
          setValue(v);
          onChange?.(v);
        }}
      />
      <p id="fruit-hint">Pick one.</p>
      <button type="button">After</button>
    </div>
  );
}

const combo = () => screen.getByRole('combobox', { name: 'Fruit' });
const key = (k: string, opts: Partial<KeyboardEventInit> = {}) => fireEvent.keyDown(combo(), { key: k, ...opts });
const activeText = () => {
  const id = combo().getAttribute('aria-activedescendant');
  return id ? document.getElementById(id)?.querySelector('.select-option-name')?.textContent : null;
};

describe('Select', () => {
  it('is a combobox named by its <label>, described, showing the placeholder until something is chosen', () => {
    render(<Harness />);
    const c = combo();
    expect(c.tagName).toBe('BUTTON');
    expect(c).toHaveAttribute('aria-haspopup', 'listbox');
    expect(c).toHaveAttribute('aria-expanded', 'false');
    expect(c).toHaveAccessibleDescription('Pick one.');
    expect(c).toHaveTextContent('Choose a fruit…');
    expect(screen.getByLabelText('Fruit')).toBe(c);
    expect(document.getElementById(c.getAttribute('aria-controls')!)).toHaveAttribute('role', 'listbox');
    expect(screen.queryByRole('listbox')).toBeNull(); // hidden while closed
  });

  it('opens on Enter, Space, ArrowDown and ArrowUp, and a click toggles it', () => {
    render(<Harness />);
    for (const k of ['Enter', ' ', 'ArrowDown', 'ArrowUp']) {
      key(k);
      expect(combo()).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('listbox', { name: 'Fruit' })).toBeInTheDocument();
      key('Escape');
      expect(combo()).toHaveAttribute('aria-expanded', 'false');
    }
    fireEvent.click(combo());
    expect(combo()).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(combo());
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
  });

  it('moves with the arrows (skipping disabled options, not wrapping), Home and End; aria-activedescendant follows', () => {
    render(<Harness />);
    key('ArrowDown');
    expect(activeText()).toBe('Apple');
    key('ArrowDown');
    expect(activeText()).toBe('Apricot');
    key('ArrowDown');
    key('ArrowDown');
    expect(activeText()).toBe('Cherry'); // Blueberry is disabled
    key('ArrowDown');
    expect(activeText()).toBe('Cherry'); // no wrap
    key('Home');
    expect(activeText()).toBe('Apple');
    key('ArrowUp');
    expect(activeText()).toBe('Apple');
    key('End');
    expect(activeText()).toBe('Cherry');
    const activeId = combo().getAttribute('aria-activedescendant')!;
    expect(document.getElementById(activeId)).toHaveAttribute('role', 'option');
    key('Escape');
    expect(combo()).not.toHaveAttribute('aria-activedescendant');
  });

  it('opens on the chosen option, which is marked aria-selected', () => {
    render(<Harness initial="banana" />);
    expect(combo()).toHaveTextContent('Banana');
    key('ArrowDown');
    expect(activeText()).toBe('Banana');
    const selected = screen.getAllByRole('option').filter((o) => o.getAttribute('aria-selected') === 'true');
    expect(selected.map((o) => o.querySelector('.select-option-name')?.textContent)).toEqual(['Banana']);
    // the detail line is the option's description, not part of its name
    const banana = screen.getByRole('option', { name: 'Banana' });
    expect(banana).toHaveAccessibleDescription('Yellow, curved');
  });

  it('jumps by type-ahead: letters typed together, and one letter again cycles', () => {
    vi.useFakeTimers();
    try {
      render(<Harness />);
      key('ArrowDown');
      key('c');
      expect(activeText()).toBe('Cherry');
      act(() => void vi.advanceTimersByTime(600));
      key('a');
      expect(activeText()).toBe('Apple');
      key('p');
      expect(activeText()).toBe('Apple'); // "ap" still Apple
      key('r');
      expect(activeText()).toBe('Apricot'); // "apr"
      act(() => void vi.advanceTimersByTime(600));
      key('a');
      expect(activeText()).toBe('Apple'); // a fresh "a" moves on from Apricot and wraps to Apple
      act(() => void vi.advanceTimersByTime(600));
      key('a');
      expect(activeText()).toBe('Apricot');
      // typing on the closed picker opens it on the match
      key('Escape');
      act(() => void vi.advanceTimersByTime(600));
      key('b');
      expect(combo()).toHaveAttribute('aria-expanded', 'true');
      expect(activeText()).toBe('Banana');
    } finally {
      vi.useRealTimers();
    }
  });

  it('one letter typed again quickly cycles through the options starting with it', () => {
    vi.useFakeTimers();
    try {
      render(<Harness />);
      key('ArrowDown');
      key('a');
      expect(activeText()).toBe('Apricot'); // starts after Apple, the active option
      act(() => void vi.advanceTimersByTime(100));
      key('a');
      expect(activeText()).toBe('Apple'); // "aa" within the window: cycles on, wrapping
      act(() => void vi.advanceTimersByTime(100));
      key('a');
      expect(activeText()).toBe('Apricot');
    } finally {
      vi.useRealTimers();
    }
  });

  it('Escape closing the picker does not reach a dialog around it; closed, Escape passes through', () => {
    const outer = vi.fn();
    render(
      <div onKeyDown={(e) => outer(e.key)}>
        <Harness />
      </div>,
    );
    key('ArrowDown');
    key('Escape');
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
    expect(outer).not.toHaveBeenCalledWith('Escape');
    key('Escape'); // closed: the picker has nothing to close, so the dialog may
    expect(outer).toHaveBeenCalledWith('Escape');
  });

  it('Space is handled on keydown only: its keyup is prevented, so a browser cannot toggle it back', () => {
    render(<Harness />);
    key(' ');
    expect(combo()).toHaveAttribute('aria-expanded', 'true');
    const up = fireEvent.keyUp(combo(), { key: ' ' });
    expect(up).toBe(false); // default prevented
    expect(combo()).toHaveAttribute('aria-expanded', 'true');
    key(' '); // chooses and closes
    expect(fireEvent.keyUp(combo(), { key: ' ' })).toBe(false);
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
    // other keys' keyup is left alone
    expect(fireEvent.keyUp(combo(), { key: 'Enter' })).toBe(true);
  });

  it('passes focus and blur through to the trigger', () => {
    const onFocus = vi.fn();
    const onBlur = vi.fn();
    render(
      <>
        <label htmlFor="f">F</label>
        <Select id="f" value="" options={FRUIT} onChange={() => {}} onFocus={onFocus} onBlur={onBlur} />
      </>,
    );
    const c = screen.getByRole('combobox', { name: 'F' });
    fireEvent.focus(c);
    fireEvent.blur(c);
    expect(onFocus).toHaveBeenCalledTimes(1);
    expect(onBlur).toHaveBeenCalledTimes(1);
  });

  it('Escape closes and keeps the value', () => {
    const onChange = vi.fn();
    render(<Harness initial="apple" onChange={onChange} />);
    key('ArrowDown');
    key('ArrowDown');
    key('Escape');
    expect(onChange).not.toHaveBeenCalled();
    expect(selectValue(combo())).toBe('apple');
    expect(combo()).toHaveTextContent('Apple');
  });

  it('Enter commits the active option, fires onChange once, closes and keeps focus on the trigger', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    combo().focus();
    key('ArrowDown');
    key('ArrowDown');
    key('Enter');
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('apricot');
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
    expect(combo()).toHaveFocus();
    expect(selectValue(combo())).toBe('apricot');
    // choosing the same value again is not a change
    key('ArrowDown');
    key('Enter');
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('Space commits too, and Alt+ArrowUp chooses and closes', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    key('ArrowDown');
    key('ArrowDown');
    key(' ');
    expect(onChange).toHaveBeenLastCalledWith('apricot');
    key('ArrowDown');
    key('ArrowDown');
    key('ArrowUp', { altKey: true });
    expect(onChange).toHaveBeenLastCalledWith('banana');
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
  });

  it('Tab commits the active option and closes, without holding focus back', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    key('ArrowDown');
    key('End');
    const tab = fireEvent.keyDown(combo(), { key: 'Tab' });
    expect(tab).toBe(true); // not prevented: focus is free to move on
    expect(onChange).toHaveBeenCalledWith('cherry');
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
  });

  it('a click on an option chooses it and returns focus to the trigger; disabled ones do nothing', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.click(combo());
    fireEvent.click(screen.getByRole('option', { name: 'Blueberry' }));
    expect(onChange).not.toHaveBeenCalled();
    expect(combo()).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('option', { name: 'Cherry' }));
    expect(onChange).toHaveBeenCalledWith('cherry');
    expect(combo()).toHaveFocus();
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
  });

  it('a press outside closes it without a change', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.click(combo());
    fireEvent.mouseDown(screen.getByRole('button', { name: 'After' }));
    expect(combo()).toHaveAttribute('aria-expanded', 'false');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('exposes groups as role="group", each named by its visible label', () => {
    const grouped: SelectOption[] = [
      { value: 'a', label: 'record_type', group: 'Record Info' },
      { value: 'b', label: 'system.technique', group: 'System' },
      { value: 'c', label: 'system.domain', group: 'System' },
    ];
    render(<Harness options={grouped} />);
    fireEvent.click(combo());
    const groups = within(screen.getByRole('listbox')).getAllByRole('group');
    expect(groups.map((g) => g.getAttribute('aria-labelledby') && document.getElementById(g.getAttribute('aria-labelledby')!)?.textContent)).toEqual([
      'Record Info',
      'System',
    ]);
    expect(within(groups[1]).getAllByRole('option').map((o) => o.textContent)).toEqual(['system.technique', 'system.domain']);
    expect(selectGroups(combo())).toEqual([
      { group: 'Record Info', options: ['record_type'] },
      { group: 'System', options: ['system.technique', 'system.domain'] },
    ]);
    // arrows move in display order across groups
    key('Home');
    key('ArrowDown');
    expect(activeText()).toBe('system.technique');
  });

  it('a disabled picker does not open, and none of its options chooses', () => {
    const onChange = vi.fn();
    render(
      <>
        <label htmlFor="x">X</label>
        <Select id="x" value="" options={FRUIT} onChange={onChange} disabled placeholder="Choose…" />
      </>,
    );
    const c = screen.getByRole('combobox', { name: 'X' });
    expect(c).toBeDisabled();
    fireEvent.keyDown(c, { key: 'ArrowDown' });
    expect(c).toHaveAttribute('aria-expanded', 'false');
    // Its options stay in the page (hidden) so `aria-controls` resolves; a click reaching one — a script, a
    // test helper — still changes nothing.
    chooseValue(c, 'apple');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('chooses by value with the chooseValue helper, as fireEvent.change did on a native select', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    expect(optionValues(combo())).toEqual(FRUIT.map((f) => f.value));
    chooseValue(combo(), 'banana');
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(selectValue(combo())).toBe('banana');
    // A disabled option is clicked like any other and, as in the app, changes nothing.
    chooseValue(combo(), 'blueberry');
    expect(selectValue(combo())).toBe('banana');
    expect(() => chooseValue(combo(), 'durian')).toThrow(/no option of value "durian"/);
  });

  it('works with the chooseOption test helper, and renders no hidden input unless named', () => {
    const { container } = render(
      <form>
        <Harness />
      </form>,
    );
    chooseOption('Fruit', 'Cherry');
    expect(selectValue(combo())).toBe('cherry');
    expect(container.querySelector('input[type="hidden"]')).toBeNull();
  });

  it('carries its value in a hidden input when given a name, for a native form submit', () => {
    const { container } = render(
      <form>
        <label htmlFor="n">Named</label>
        <Select id="n" name="fruit" value="banana" options={FRUIT} onChange={() => {}} />
      </form>,
    );
    expect(container.querySelector('input[type="hidden"][name="fruit"]')).toHaveValue('banana');
  });

  it('passes data-* attributes to the trigger, and a compact density marks the wrapper', () => {
    render(
      <>
        <label htmlFor="d">Dense</label>
        <Select
          id="d"
          density="compact"
          data-run-field-path="a.b"
          value="apple"
          options={FRUIT}
          onChange={() => {}}
        />
      </>,
    );
    const c = screen.getByRole('combobox', { name: 'Dense' });
    expect(c).toHaveAttribute('data-run-field-path', 'a.b');
    expect(c.closest('.select')).toHaveClass('select-compact');
    expect(c).toHaveAttribute('data-value', 'apple');
    // Each option carries its value too, so a browser test can choose by value (as `selectOption` did).
    const listbox = document.getElementById(c.getAttribute('aria-controls')!)!;
    expect(
      Array.from(listbox.querySelectorAll('[role="option"]')).map((o) => o.getAttribute('data-value')),
    ).toEqual(FRUIT.map((f) => f.value));
  });

  /*
   * NOT CLIPPED BY ITS CONTAINER. The popup is fixed-positioned from the trigger's rect, so a card with
   * `overflow: hidden` around it (a run card, a screen card, the drawer's scroll body) cannot cut it off.
   * jsdom does no layout, so the rects are stubbed: the trigger sits at (40, 100), 200 wide and 40 tall, in a
   * 1000 x 800 viewport, inside a clipping box.
   */
  describe('placement', () => {
    const { innerWidth: W, innerHeight: H } = window;
    afterEach(() => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: W });
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: H });
      vi.restoreAllMocks();
    });
    function stubRect(el: Element, r: { top: number; left: number; width: number; height: number }) {
      vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
        ...r,
        x: r.left,
        y: r.top,
        right: r.left + r.width,
        bottom: r.top + r.height,
        toJSON: () => ({}),
      } as DOMRect);
    }
    function renderClipped() {
      render(
        <div style={{ overflow: 'hidden', height: 60 }}>
          <Harness />
        </div>,
      );
      const c = combo();
      const list = document.getElementById(c.getAttribute('aria-controls')!)!;
      stubRect(c, { top: 100, left: 40, width: 200, height: 40 });
      return { c, list };
    }

    it('is fixed at the trigger, below it, at least as wide as it and never past the right gutter', () => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1000 });
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });
      const { c, list } = renderClipped();
      fireEvent.click(c);
      expect(getComputedStyle(list).position).toBe('fixed');
      expect(list.style.top).toBe('144px'); // trigger bottom (140) + the 4px gap
      expect(list.style.left).toBe('40px');
      expect(list.style.minWidth).toBe('200px');
      expect(list.style.maxWidth).toBe('512px');
      expect(list).not.toHaveClass('is-above');
    });

    it('takes off the offset of a transformed ancestor (its containing block), as in the drawer', () => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1000 });
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });
      const { c, list } = renderClipped();
      // Put at 0,0, the popup lands at the containing block's origin: here a drawer at (600, 20).
      stubRect(list, { top: 20, left: 600, width: 200, height: 120 });
      fireEvent.click(c);
      expect(list.style.top).toBe(`${144 - 20}px`);
      expect(list.style.left).toBe(`${40 - 600}px`);
    });

    it('flips above when there is no room below, and caps its height to the room it has', () => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1000 });
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: 160 });
      const { c, list } = renderClipped();
      Object.defineProperty(list, 'scrollHeight', { configurable: true, value: 120 });
      Object.defineProperty(list, 'offsetHeight', { configurable: true, value: 88 });
      fireEvent.click(c);
      // Below: 160 - 140 - 4 - 8 = 8px. Above: 100 - 4 - 8 = 88px, so it opens above, capped at 88px.
      expect(list).toHaveClass('is-above');
      expect(list.style.maxHeight).toBe('88px');
      expect(list.style.top).toBe(`${100 - 4 - 88}px`);
    });

    it('closes when the page scrolls the trigger out of view, and ignores its own scrolling', () => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1000 });
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });
      const { c, list } = renderClipped();
      fireEvent.click(c);
      // The trigger is OUT of view while the popup scrolls its own options: the popup's own scroll is
      // ignored, so it stays open (without the guard, this scroll would close it).
      stubRect(c, { top: -200, left: 40, width: 200, height: 40 });
      fireEvent.scroll(list);
      expect(c).toHaveAttribute('aria-expanded', 'true');
      // The page scrolling it out of view does close it.
      act(() => {
        window.dispatchEvent(new Event('scroll'));
      });
      expect(c).toHaveAttribute('aria-expanded', 'false');
    });

    it('re-places on resize while open, and removes its listeners when it closes', () => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1000 });
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 });
      const { c, list } = renderClipped();
      const removed = vi.spyOn(window, 'removeEventListener');
      fireEvent.click(c);
      expect(list.style.top).toBe('144px');
      stubRect(c, { top: 300, left: 60, width: 200, height: 40 });
      act(() => {
        window.dispatchEvent(new Event('resize'));
      });
      expect(list.style.top).toBe('344px');
      expect(list.style.left).toBe('60px');
      removed.mockClear();
      fireEvent.keyDown(c, { key: 'Escape' });
      expect(c).toHaveAttribute('aria-expanded', 'false');
      const types = removed.mock.calls.map(([type]) => type);
      expect(types).toEqual(expect.arrayContaining(['resize', 'scroll']));
    });
  });
});
