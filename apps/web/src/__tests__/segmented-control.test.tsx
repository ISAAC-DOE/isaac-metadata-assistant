import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { useState } from 'react';

import { SegmentedControl, type SegmentOption } from '../components/SegmentedControl';

/**
 * SEGMENTED CONTROL — an APG radio group drawn as one track. Pinned: the visible label names the group, one
 * Tab stop (the checked segment, or the first when none is), arrows move and choose with wrap, Home / End,
 * "none chosen" is a real state that reports nothing until chosen, and disabled segments are skipped.
 */

const OPTIONS: SegmentOption[] = [
  { value: 'yes', label: 'Required' },
  { value: 'no', label: 'Optional' },
  { value: 'later', label: 'Later', disabled: true },
];

function Harness({ initial = null, onChange }: { initial?: string | null; onChange?: (v: string) => void }) {
  const [value, setValue] = useState<string | null>(initial);
  return (
    <SegmentedControl
      label="Must every record carry it?"
      options={OPTIONS}
      value={value}
      aria-required
      onChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
    />
  );
}

const group = () => screen.getByRole('radiogroup', { name: 'Must every record carry it?' });
const radio = (name: string) => within(group()).getByRole('radio', { name });

describe('SegmentedControl', () => {
  it('is a radiogroup named by its visible label, with nothing checked when the value is null', () => {
    render(<Harness />);
    expect(group()).toHaveAttribute('aria-required', 'true');
    expect(within(group()).getAllByRole('radio').map((r) => r.getAttribute('aria-checked'))).toEqual([
      'false',
      'false',
      'false',
    ]);
    // one Tab stop, on the first enabled segment
    expect(radio('Required')).toHaveAttribute('tabindex', '0');
    expect(radio('Optional')).toHaveAttribute('tabindex', '-1');
  });

  it('a click chooses, reports once, and moves the Tab stop to the chosen segment', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    fireEvent.click(radio('Optional'));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('no');
    expect(radio('Optional')).toHaveAttribute('aria-checked', 'true');
    expect(radio('Optional')).toHaveAttribute('tabindex', '0');
    expect(radio('Required')).toHaveAttribute('tabindex', '-1');
    fireEvent.click(radio('Optional'));
    expect(onChange).toHaveBeenCalledTimes(1); // the same value again is not a change
  });

  it('arrow keys move focus and choose, wrapping and skipping disabled segments; Home and End jump', () => {
    const onChange = vi.fn();
    render(<Harness initial="yes" onChange={onChange} />);
    radio('Required').focus();
    fireEvent.keyDown(radio('Required'), { key: 'ArrowRight' });
    expect(radio('Optional')).toHaveFocus();
    expect(radio('Optional')).toHaveAttribute('aria-checked', 'true');
    fireEvent.keyDown(radio('Optional'), { key: 'ArrowDown' });
    expect(radio('Required')).toHaveFocus(); // "Later" is disabled, so it wraps
    fireEvent.keyDown(radio('Required'), { key: 'ArrowLeft' });
    expect(radio('Optional')).toHaveFocus();
    fireEvent.keyDown(radio('Optional'), { key: 'Home' });
    expect(radio('Required')).toHaveAttribute('aria-checked', 'true');
    fireEvent.keyDown(radio('Required'), { key: 'End' });
    expect(radio('Optional')).toHaveAttribute('aria-checked', 'true');
    expect(onChange.mock.calls.map((c) => c[0])).toEqual(['no', 'yes', 'no', 'yes', 'no']);
  });

  it('Space chooses the focused segment when none is chosen yet', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    radio('Required').focus();
    fireEvent.keyDown(radio('Required'), { key: ' ' });
    expect(onChange).toHaveBeenCalledWith('yes');
  });

  it('a disabled segment cannot be chosen', () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    expect(radio('Later')).toBeDisabled();
    fireEvent.click(radio('Later'));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('can be named by a label already on the page instead of its own', () => {
    render(
      <>
        <h3 id="src">Source</h3>
        <SegmentedControl labelledBy="src" options={OPTIONS} value="yes" onChange={() => {}} />
      </>,
    );
    expect(screen.getByRole('radiogroup', { name: 'Source' })).toBeInTheDocument();
  });
});
