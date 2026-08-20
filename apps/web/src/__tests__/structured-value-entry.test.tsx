/**
 * Entering a spectrum and a descriptor — the last two questions a record made in this
 * application could not answer.
 *
 * WHAT WAS WRONG
 * ==============
 * `series` and `descriptor` render as "structured" blockers, and the only way to answer
 * one was to CONFIRM a worked-example value. A record a scientist created has no
 * example (`demo_answer` is null outside the walkthrough), so the screen said
 * "No example value is available for this field — leave it honestly missing" and
 * rendered no control at all. Both are required for an evidence record, so the record
 * could be taken to that screen and no further.
 *
 * WHAT THESE TESTS PIN, and each is a way the fix could be worse than the gap:
 *
 *   1. NOTHING IS PREFILLED OR PRESELECTED. A form that arrives with `kind: absolute`
 *      chosen is the app asserting something about somebody's measurement.
 *   2. AN INCOMPLETE OR MALFORMED VALUE IS REFUSED, not coerced into a plausible one.
 *   3. WHAT IS SUBMITTED IS THE SHAPE THE SERVER ACCEPTS — `complete.is_series_shaped`
 *      and `is_descriptor_shaped`, plus the official schema's required keys.
 *   4. THE WORKED-EXAMPLE FLOW IS UNTOUCHED. A walkthrough record must not start asking
 *      a reader to paste JSON.
 */

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import { GuidedPrompt } from '../components/GuidedPrompt';
import {
  descriptorIsComplete,
  descriptorPayload,
  EMPTY_DESCRIPTOR,
  seriesParseError,
  typedValue,
} from '../components/StructuredValueEntry';
import type { PendingBlocker } from '../lib/types';

const base = (kind: 'series' | 'descriptor'): PendingBlocker => ({
  id: kind,
  kind,
  question: kind === 'series' ? 'Provide the reduced spectrum.' : 'Provide a descriptor.',
  label: kind,
  path: kind === 'series' ? 'measurement.series' : 'descriptors',
  inputType: 'structured',
});

function renderEntry(kind: 'series' | 'descriptor', overrides: Partial<PendingBlocker> = {}) {
  const onConfirm = vi.fn();
  const onStagedChange = vi.fn();
  render(
    <GuidedPrompt
      blocker={{ ...base(kind), ...overrides }}
      index={0}
      total={1}
      onConfirm={onConfirm}
      onDontKnow={vi.fn()}
      onStagedChange={onStagedChange}
    />,
  );
  return { onConfirm, onStagedChange };
}

const confirmButton = () => screen.getByRole('button', { name: /confirm|save/i });

// ---------------------------------------------------------------------------
// The pure helpers
// ---------------------------------------------------------------------------

describe('typedValue records a number as a number and anything else as text', () => {
  it.each([
    ['9001.2', 9001.2],
    ['-3', -3],
    ['0', 0],
    ['  42  ', 42],
  ])('%s -> %s', (text, expected) => {
    expect(typedValue(text)).toBe(expected);
  });

  it.each(['Cu(II)', 'octahedral', 'NaN', 'Infinity', '1e400'])(
    'keeps %s as text',
    (text) => {
      // NaN and Infinity parse as JS numbers but are NOT representable in JSON, and
      // writing one wedges the record — `experiment.json` becomes invalid JSON and every
      // later export raises forever. `Number.isFinite` is what excludes them, and this
      // asserts it rather than trusting it.
      expect(typeof typedValue(text)).toBe('string');
    },
  );

  it('treats blank as absent rather than as zero', () => {
    expect(typedValue('   ')).toBeNull();
  });
});

describe('seriesParseError refuses what the server would refuse', () => {
  it('accepts a non-empty list of objects', () => {
    expect(seriesParseError('[{"series_id": "averaged_spectrum"}]')).toBeNull();
  });

  it.each([
    ['not json at all', /not valid JSON/],
    ['{"series_id": "s"}', /list of series objects/],
    ['[]', /empty list/],
    ['[1, 2, 3]', /series object/],
    ['[[]]', /series object/],
    ['null', /list of series objects/],
  ])('refuses %s', (text, pattern) => {
    expect(seriesParseError(text)).toMatch(pattern);
  });
});

describe('descriptorPayload builds the schema shape and omits what was left blank', () => {
  it('carries the four required keys plus uncertainty', () => {
    const payload = descriptorPayload({
      ...EMPTY_DESCRIPTOR,
      name: 'inflection_point_energy',
      kind: 'absolute',
      source: 'manual',
      value: '9001.2',
      unit: 'eV',
      sigma: '0.01',
      sigmaUnit: 'eV',
      basis: 'reported',
    });
    expect(payload).toEqual({
      name: 'inflection_point_energy',
      kind: 'absolute',
      source: 'manual',
      value: 9001.2,
      unit: 'eV',
      uncertainty: { sigma: 0.01, unit: 'eV', basis: 'reported' },
    });
  });

  it('records an unreported sigma as null rather than omitting uncertainty', () => {
    // "no uncertainty was reported" and "this descriptor has none" are different claims.
    const payload = descriptorPayload({
      ...EMPTY_DESCRIPTOR,
      name: 'oxidation_state',
      kind: 'categorical',
      source: 'manual',
      value: 'Cu(II)',
    });
    expect(payload.uncertainty).toEqual({ sigma: null });
    expect(payload).not.toHaveProperty('unit');
    expect(payload.value).toBe('Cu(II)');
  });

  it('is incomplete until every required field is present', () => {
    expect(descriptorIsComplete(EMPTY_DESCRIPTOR)).toBe(false);
    const nearly = {
      ...EMPTY_DESCRIPTOR,
      name: 'edge_position',
      kind: 'absolute',
      source: 'manual',
    };
    expect(descriptorIsComplete(nearly)).toBe(false); // no value
    expect(descriptorIsComplete({ ...nearly, value: '  ' })).toBe(false); // whitespace
    expect(descriptorIsComplete({ ...nearly, value: '8979' })).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// The rendered controls
// ---------------------------------------------------------------------------

describe('the descriptor form', () => {
  it('preselects nothing and prefills nothing', () => {
    renderEntry('descriptor');
    for (const select of screen.getAllByRole('combobox')) {
      expect(select).toHaveValue('');
    }
    for (const box of screen.getAllByRole('textbox')) {
      expect(box).toHaveValue('');
    }
    expect(confirmButton()).toBeDisabled();
  });

  it('offers the vocabulary as suggestions a scientist may ignore', () => {
    // The vocabulary file calls itself "an extraction/authoring aid only" and the schema
    // constrains `name` by PATTERN, not by enumeration — so the control must accept a
    // name outside the list. A `<datalist>` does; a `<select>` would not.
    renderEntry('descriptor');
    const name = screen.getByLabelText(/^name/i);
    expect(name.tagName).toBe('INPUT');
    expect(name).toHaveAttribute('list');
    fireEvent.change(name, { target: { value: 'something_the_wiki_has_not_heard_of' } });
    expect(name).toHaveValue('something_the_wiki_has_not_heard_of');
  });

  it('submits the schema shape once every required field is filled', () => {
    const { onConfirm } = renderEntry('descriptor');
    fireEvent.change(screen.getByLabelText(/^name/i), {
      target: { value: 'inflection_point_energy' },
    });
    fireEvent.change(screen.getByLabelText(/^kind/i), { target: { value: 'absolute' } });
    fireEvent.change(screen.getByLabelText(/^source/i), { target: { value: 'manual' } });
    fireEvent.change(screen.getByLabelText(/^value/i), { target: { value: '9001.2' } });
    fireEvent.change(screen.getByLabelText(/^unit/i), { target: { value: 'eV' } });

    expect(confirmButton()).toBeEnabled();
    fireEvent.click(confirmButton());

    expect(onConfirm).toHaveBeenCalledWith({
      name: 'inflection_point_energy',
      kind: 'absolute',
      source: 'manual',
      value: 9001.2,
      unit: 'eV',
      uncertainty: { sigma: null },
    });
  });

  it('reports every edit upward so a Refresh cannot destroy the form', () => {
    const { onStagedChange } = renderEntry('descriptor');
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: 'edge_shift' } });
    expect(onStagedChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ name: 'edge_shift' }),
    );
  });
});

describe('the series entry', () => {
  it('refuses to submit until the JSON parses AND has the right shape', () => {
    const { onConfirm } = renderEntry('series');
    const box = screen.getByLabelText(/series json/i);

    expect(confirmButton()).toBeDisabled();

    fireEvent.change(box, { target: { value: '{not json' } });
    expect(confirmButton()).toBeDisabled();
    expect(screen.getByText(/not valid JSON/i)).toBeInTheDocument();

    fireEvent.change(box, { target: { value: '[]' } });
    expect(confirmButton()).toBeDisabled();
    expect(screen.getByText(/empty list/i)).toBeInTheDocument();

    fireEvent.change(box, { target: { value: '[{"series_id": "s"}]' } });
    expect(confirmButton()).toBeEnabled();
    fireEvent.click(confirmButton());
    expect(onConfirm).toHaveBeenCalledWith([{ series_id: 's' }]);
  });

  it('never shows the parser its own error message', () => {
    // A `SyntaxError` names character offsets in a blob with no visible line numbers and
    // reads as a failure of the app rather than of the paste.
    renderEntry('series');
    fireEvent.change(screen.getByLabelText(/series json/i), { target: { value: '{' } });
    expect(screen.queryByText(/JSON\.parse|position \d+|Unexpected token/i)).toBeNull();
  });

  it('does not claim the values are checked, only the shape', () => {
    renderEntry('series');
    expect(screen.getByText(/never inspected or altered/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// NEGATIVE CONTROL — the worked-example flow is untouched
// ---------------------------------------------------------------------------

describe('a blocker that HAS a worked example still confirms it', () => {
  it('offers Use This Value and no entry control', () => {
    renderEntry('series', {
      demo_answer: { value: [{ series_id: 'averaged_spectrum' }], label: 'Example answer' },
    });
    expect(screen.getByRole('button', { name: /use this value/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/series json/i)).toBeNull();
  });

  it('offers Use This Value and no form for a descriptor', () => {
    renderEntry('descriptor', {
      demo_answer: { value: { name: 'x' }, label: 'Example answer' },
    });
    expect(screen.getByRole('button', { name: /use this value/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/^kind/i)).toBeNull();
  });
});

describe('accessibility of the entry controls', () => {
  it('every field has a real label and the required ones say so', () => {
    renderEntry('descriptor');
    for (const label of ['name', 'kind', 'source', 'value']) {
      const field = screen.getByLabelText(new RegExp(`^${label}`, 'i'));
      expect(field).toBeInTheDocument();
      const required = within(field.closest('label') as HTMLElement).queryByTitle('required');
      expect(required, `${label} is required and must say so`).not.toBeNull();
    }
  });

  it('the series status message is tied to the textarea and announced when it errors', () => {
    renderEntry('series');
    const box = screen.getByLabelText(/series json/i);
    const describedBy = box.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    fireEvent.blur(box);
    fireEvent.change(box, { target: { value: 'nope' } });
    expect(document.getElementById(describedBy as string)).toHaveAttribute('role', 'alert');
  });
});
