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
  descriptorDraftFrom,
  descriptorIsComplete,
  descriptorPayload,
  EMPTY_DESCRIPTOR,
  seriesParseError,
  seriesTextFrom,
  typedValue,
} from '../components/StructuredValueEntry';
import { pendingItemToBlocker } from '../lib/adapt';
import type { PendingBlocker } from '../lib/types';

const base = (kind: 'series' | 'descriptor'): PendingBlocker => ({
  id: kind,
  key: kind,
  kind,
  question: kind === 'series' ? 'Provide the reduced spectrum.' : 'Provide a descriptor.',
  label: kind,
  path: kind === 'series' ? 'measurement.series' : 'descriptors',
  inputType: 'structured',
});

/* `props` was added for the I4 tests at the foot of this file: an EDIT opens the same
   component with the confirmed value handed back through `initialValue`, and there was
   no way to express that here — which is part of why the editor shipped opening blank.
   Optional and spread last, so every existing call is unchanged. */
function renderEntry(
  kind: 'series' | 'descriptor',
  overrides: Partial<PendingBlocker> = {},
  props: { initialValue?: unknown; initialStaged?: boolean } = {},
) {
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
      {...props}
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

describe('per-question state is keyed by the unique key, not by the kind', () => {
  it('two runs needing the same thing are two distinct questions', () => {
    // CRITICAL REGRESSION TEST for a collision an independent review measured. `id` is
    // the blocker KIND — three runs needing a spectrum all carry `id: "series"` — and the
    // completion screen keyed staged input, the skipped set, its React keys and its
    // "was this applied?" test off `id`. The consequences it measured: answering one
    // run's verdict was reported as NOT APPLIED (another run's identical entry was still
    // in the list), one typed value was shared by every run's question, and skipping one
    // skipped all of them.
    //
    // `blocker_key` is the identity key and `id` stays the ANSWER key, because `id` is
    // what goes in the request body. This asserts the adapter produces distinct keys for
    // two runs and the SAME `id`, which is the pairing the fix depends on.
    const first = pendingItemToBlocker({
      id: 'series',
      kind: 'series',
      question: 'Provide the reduced spectrum.',
      run_id: '01RUNAAAAAAAAAAAAAAAAAAAA0',
      run_label: '300 K',
      blocker_key: '01RUNAAAAAAAAAAAAAAAAAAAA0:series',
    });
    const second = pendingItemToBlocker({
      id: 'series',
      kind: 'series',
      question: 'Provide the reduced spectrum.',
      run_id: '01RUNBBBBBBBBBBBBBBBBBBBB0',
      run_label: '400 K',
      blocker_key: '01RUNBBBBBBBBBBBBBBBBBBBB0:series',
    });

    expect(first.id).toBe(second.id);
    expect(first.key).not.toBe(second.key);
    expect(first.runLabel).toBe('300 K');
    expect(second.runLabel).toBe('400 K');
  });

  it('falls back to the id when the server sends no key', () => {
    // Correct for a record with no runs — the two are equal there by construction — and
    // it degrades to the pre-existing collision only where the server itself did not
    // distinguish the owners.
    const only = pendingItemToBlocker({ id: 'qc', kind: 'qc', question: 'q' });
    expect(only.key).toBe('qc');
    expect(only.runId).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// I4 — the inverses, and the editor that had none
// ---------------------------------------------------------------------------

/**
 * A CONFIRMED STRUCTURED VALUE COULD NOT BE EDITED, AND THE SCREEN SAID IT COULD.
 *
 * `GuidedCompletion` renders a confirmed answer read-only with an Edit button and its
 * own comment promises the editor opens "prefilled with the current value". For a
 * `series` or `descriptor` on a record with NO worked example — every record a
 * scientist creates, which is the only case in which these controls render — the value
 * was never passed down, and `initialStaged` does not cover it: `entering` is
 * `structured && demo === undefined`, and on that branch `canConfirm` is `entryReady`,
 * computed from the form and never from `staged`. Measured:
 *
 *     SERIES     editor value = ""                          SAVE DISABLED = true
 *     DESCRIPTOR Name="" Kind="" Source="" Value="" Unit="" SAVE DISABLED = true
 *
 * So one wrong digit in a descriptor cost the whole value, with a dead Save button and
 * nothing on screen saying why.
 */
describe('descriptorDraftFrom is the inverse descriptorPayload never had', () => {
  it('round-trips a payload back through the form unchanged', () => {
    const draft = {
      ...EMPTY_DESCRIPTOR,
      name: 'inflection_point_energy',
      kind: 'absolute',
      source: 'manual',
      value: '9001.2',
      unit: 'eV',
      sigma: '0.01',
      sigmaUnit: 'eV',
      basis: 'reported',
    };
    // payload -> draft -> payload is the identity, which is the property that makes it
    // safe to hand a confirmed value back to the control that produced it.
    expect(descriptorDraftFrom(descriptorPayload(draft))).toEqual(draft);
    expect(descriptorPayload(descriptorDraftFrom(descriptorPayload(draft)))).toEqual(
      descriptorPayload(draft),
    );
  });

  it('does NOT throw on the payload shape — the trap a cast would have fallen into', () => {
    /*
     * `rawValue` for a descriptor is `descriptorPayload(...)`: `value` is a NUMBER when
     * the text read as one, there is no `sigma` key, and σ is nested under
     * `uncertainty`. `GuidedPrompt` used to cast `initialValue as DescriptorDraft` on
     * `'name' in initialValue`, so simply passing the confirmed value down would have
     * put a number where `descriptorIsComplete` calls `.trim()` and `undefined` where
     * it reads `d.sigma` — turning a blank form into a crash on open, which is worse.
     */
    const payload = { name: 'edge', kind: 'absolute', source: 'auto', value: 8979, uncertainty: { sigma: null } };
    const draft = descriptorDraftFrom(payload);
    expect(() => descriptorIsComplete(draft)).not.toThrow();
    expect(draft.value).toBe('8979'); // the text that produced the number
    expect(draft.sigma).toBe(''); // `sigma: null` means none was REPORTED
    expect(descriptorIsComplete(draft)).toBe(true);
  });

  it('degrades to a blank form rather than to a half-populated one', () => {
    // A blank field the reader must fill is honest. A field silently holding the wrong
    // thing is not — and this control's whole purpose is that nothing is filled in for
    // you unless you put it there.
    for (const notADescriptor of [undefined, null, 'text', 42, [], {}, { status: 'valid' }]) {
      expect(descriptorDraftFrom(notADescriptor)).toEqual(EMPTY_DESCRIPTOR);
    }
    // A nested object where a scalar belongs has no text form `typedValue` would turn
    // back into it, so the field is left blank rather than stringified.
    expect(descriptorDraftFrom({ name: 'x', value: { a: 1 } }).value).toBe('');
  });

  it('reads a mid-edit DRAFT as well as a confirmed PAYLOAD', () => {
    // `onStagedChange` reports the DRAFT shape — flat `sigma`, every field a string —
    // and that is what survives a Refresh. Both shapes satisfy `'name' in value`, which
    // is exactly why a cast could not tell them apart.
    const inFlight = { ...EMPTY_DESCRIPTOR, name: 'edge', sigma: '0.5', sigmaUnit: 'eV' };
    expect(descriptorDraftFrom(inFlight)).toEqual(inFlight);
  });
});

describe('seriesTextFrom returns the spectrum to the box that produced it', () => {
  it('re-serialises a confirmed (parsed) array', () => {
    const value = [{ series_id: 'averaged_spectrum', channels: [1, 2] }];
    expect(JSON.parse(seriesTextFrom(value))).toEqual(value);
    // Pretty-printed, because a scientist has to read and correct it.
    expect(seriesTextFrom(value)).toContain('\n');
  });

  it('returns RAW TEXT untouched, half-written JSON included', () => {
    // A staged series survives as text on purpose: half-written JSON is still the
    // reader's work, and reparsing it to restore it would lose exactly the state a
    // Refresh most needs to preserve.
    expect(seriesTextFrom('[{"series_id": "half')).toBe('[{"series_id": "half');
  });

  it('gives an empty box rather than a wrong one for anything else', () => {
    for (const notASeries of [undefined, null, 42, { series_id: 'x' }]) {
      expect(seriesTextFrom(notASeries)).toBe('');
    }
  });
});

describe('the entry editor opens on the value it is editing', () => {
  it('a descriptor payload prefills every field and arms Confirm', () => {
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
    const { onConfirm } = renderEntry('descriptor', {}, { initialValue: payload });

    expect((screen.getByLabelText(/^Name/) as HTMLInputElement).value).toBe(
      'inflection_point_energy',
    );
    expect((screen.getByLabelText(/^Kind/) as HTMLSelectElement).value).toBe('absolute');
    expect((screen.getByLabelText(/^Source/) as HTMLSelectElement).value).toBe('manual');
    expect((screen.getByLabelText(/^Value/) as HTMLInputElement).value).toBe('9001.2');
    expect((screen.getByLabelText(/^Unit/) as HTMLInputElement).value).toBe('eV');
    expect((screen.getByLabelText(/Uncertainty \(σ\)/) as HTMLInputElement).value).toBe('0.01');

    // ARMED — the half a prefill alone would not fix, because `canConfirm` reads the
    // form on this branch and a blank form is a dead button.
    expect(confirmButton()).not.toBeDisabled();
    // And confirming without touching anything returns the SAME value, not a
    // reconstruction of it.
    fireEvent.click(confirmButton());
    expect(onConfirm).toHaveBeenCalledWith(payload);
  });

  it('a confirmed series prefills the box and arms Confirm', () => {
    const value = [{ series_id: 'averaged_spectrum', channels: [1, 2] }];
    const { onConfirm } = renderEntry('series', {}, { initialValue: value });

    const box = screen.getByLabelText(/series json/i) as HTMLTextAreaElement;
    expect(JSON.parse(box.value)).toEqual(value);
    expect(confirmButton()).not.toBeDisabled();
    fireEvent.click(confirmButton());
    expect(onConfirm).toHaveBeenCalledWith(value);
  });

  it('NEGATIVE CONTROL — no initial value still opens blank, with Confirm dead', () => {
    /*
     * The fix passes a value down unconditionally, and getting that wrong would
     * recreate the worst defect this screen has shipped: one run's scientific value
     * pre-filled into another run's identical question, one click from being confirmed.
     */
    renderEntry('descriptor');
    expect((screen.getByLabelText(/^Name/) as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText(/^Value/) as HTMLInputElement).value).toBe('');
    expect(confirmButton()).toBeDisabled();
  });
});
