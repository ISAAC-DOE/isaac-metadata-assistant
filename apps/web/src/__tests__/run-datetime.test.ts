/**
 * THE ACQUISITION-TIMESTAMP PICKER, over the SAME stored string.
 *
 * The project owner, 2026-09-15: *"that acquisition start, acquisition end, no
 * idea, like why. Maybe that is the actual format it requires, so maybe that's
 * something separate."*
 *
 * WHAT THESE TESTS PROTECT — and the first is the contract, not a nicety:
 *
 *   1. THE STORED FORMAT DOES NOT CHANGE. Everything the picker produces is the
 *      string the text box always produced.
 *   2. A VALUE THE PICKER CANNOT REPRESENT IS `null`, NEVER A REINTERPRETATION.
 *      An offset, fractional seconds and a zone-less value each answer `null`,
 *      and the control then hands the field to the ISO text path rather than
 *      silently moving the instant or adding a `Z` nobody wrote.
 *   3. NO `Date` OBJECT IS INVOLVED, so no function here depends on the machine
 *      it runs on. The timezone case below is the one that would fail if one
 *      ever crept in.
 */
import { describe, expect, it } from 'vitest';

import {
  formatStoredDatetime,
  isoToPickerValue,
  pickerValueToIso,
} from '../lib/runDatetime';
import { RUN_FIELDS, parseRunField, runConditionsSummary } from '../lib/runFields';

const START = RUN_FIELDS.find((s) => s.path === 'timestamps.acquired_start_utc')!;

describe('the picker round-trips the official string exactly', () => {
  it('ISO → picker → ISO is the identity for a Z-suffixed value', () => {
    for (const iso of [
      '2026-01-31T09:00:00Z',
      '2026-01-31T09:00:37Z',
      '2026-12-31T23:59:59Z',
      '2026-01-01T00:00:00Z',
    ]) {
      const picker = isoToPickerValue(iso);
      expect(picker).not.toBeNull();
      expect(pickerValueToIso(picker as string)).toBe(iso);
    }
  });

  it('a minute-granularity entry becomes the seconds-bearing official string', () => {
    // Which is what a browser hands back when the control has no `step`, and
    // what `patchBodyAfterTyping` in `run-workspace.test.tsx` now enters.
    expect(pickerValueToIso('2026-01-31T11:30')).toBe('2026-01-31T11:30:00Z');
  });

  it('MUTATION-GUARDED: everything the picker produces passes the SAME format gate', () => {
    /*
     * MUTATION: dropping the `Z` in `pickerValueToIso`, or the `:00` fill,
     * makes this RED — and would have PATCHed a string the record has never
     * held. `parseRunField`'s gate is deliberately stricter than the downstream
     * stack (`official.py` installs no `FormatChecker`), so this is the only
     * thing standing between the picker and a value nothing else would refuse.
     */
    for (const entry of ['2026-01-31T11:30', '2026-01-31T11:30:45']) {
      const parsed = parseRunField(START, pickerValueToIso(entry));
      expect(parsed.ok).toBe(true);
      expect((parsed as { ok: true; value: unknown }).value).toBe(`${entry.length === 16 ? `${entry}:00` : entry}Z`);
    }
  });

  it('an emptied control clears the field, which is `null` on the wire', () => {
    expect(pickerValueToIso('')).toBe('');
    const parsed = parseRunField(START, '');
    expect(parsed).toEqual({ ok: true, value: null });
  });
});

describe('the picker refuses to represent what it would have to reinterpret', () => {
  it('MUTATION-GUARDED: an explicit offset is `null`, not a wall clock', () => {
    /*
     * MUTATION: returning the wall clock for `+02:00` makes this RED — and
     * ships the worst defect available here: the picker would show `09:00`,
     * and any edit would re-serialize it as `09:00Z`, moving the recorded
     * instant by two hours with nothing on screen saying so.
     */
    expect(isoToPickerValue('2026-01-31T09:00:00+02:00')).toBeNull();
    expect(isoToPickerValue('2026-01-31T09:00:00-07:00')).toBeNull();
  });

  it('MUTATION-GUARDED: a value with NO zone is `null`, so no `Z` is invented', () => {
    /* MUTATION: accepting it makes this RED. Re-serializing turns
       "unspecified" into a claim about UTC, and the field being NAMED `_utc` is
       still not this module's assertion to make on a scientist's behalf. */
    expect(isoToPickerValue('2026-01-31T09:00:00')).toBeNull();
    expect(isoToPickerValue('2026-01-31 09:00')).toBeNull();
  });

  it('fractional seconds are `null`, because no browser round-trips them', () => {
    expect(isoToPickerValue('2026-01-31T09:00:00.250Z')).toBeNull();
  });

  it('a half-typed or unreadable value is `null`, and an empty one is empty', () => {
    expect(isoToPickerValue('2026-01-3')).toBeNull();
    expect(isoToPickerValue('yesterday afternoon')).toBeNull();
    expect(isoToPickerValue('')).toBe('');
    expect(isoToPickerValue('   ')).toBe('');
  });
});

describe('the one renderer for a stored timestamp', () => {
  it('re-spells a UTC value, and names the zone', () => {
    expect(formatStoredDatetime('2026-01-31T09:00:00Z')).toBe('Jan 31, 2026 · 09:00 UTC');
  });

  it('shows real seconds and hides `:00`', () => {
    expect(formatStoredDatetime('2026-01-31T09:00:37Z')).toBe('Jan 31, 2026 · 09:00:37 UTC');
  });

  it('carries an offset through verbatim rather than converting it', () => {
    /*
     * THE TEST THAT WOULD CATCH A `Date` CREEPING IN. `new Date(...)` resolves
     * this against the reader's zone, so a machine in Hamburg would print
     * `10:00` and one in Menlo Park `01:00` for the same record. Neither is
     * what the scientist wrote.
     */
    expect(formatStoredDatetime('2026-01-31T09:00:00+02:00')).toBe(
      'Jan 31, 2026 · 09:00 +02:00',
    );
  });

  it('claims no zone for a value that carries none', () => {
    expect(formatStoredDatetime('2026-01-31T09:00:00')).toBe('Jan 31, 2026 · 09:00');
  });

  it('MUTATION-GUARDED: an unreadable value is returned VERBATIM', () => {
    /* MUTATION: falling back to `new Date(raw).toDateString()` makes this RED
       with `Invalid Date` — a rendering that replaces information with a guess. */
    for (const raw of ['last Tuesday', '', '2026-13-40T99:99:99Z', 'null']) {
      expect(formatStoredDatetime(raw)).toBe(raw);
    }
  });

  it('a month number outside 1–12 falls through rather than indexing off the list', () => {
    expect(formatStoredDatetime('2026-00-31T09:00:00Z')).toBe('2026-00-31T09:00:00Z');
    expect(formatStoredDatetime('2026-13-31T09:00:00Z')).toBe('2026-13-31T09:00:00Z');
  });
});

/* --------------------------------------------------------------------------
 * ONE STORED VALUE, ONE SPELLING — across every site that shows it.
 * -------------------------------------------------------------------------- */

describe('the run conditions summary uses the SAME renderer as the Record Map', () => {
  /*
   * FOUND BY LOOKING AT THE SCREEN, not by a failing test, which is why this
   * guard exists now and did not before. Measured in Chrome on a run holding all
   * three values: the run card's summary line read
   * `in_situ · 45 K · 2026-01-31T09:00:00Z` while the Record Map beside it read
   * `Jan 31, 2026 · 09:00 UTC` — one stored value, two spellings, on one screen.
   *
   * `formatStoredDatetime`'s docstring claims "the Record Map row and the run
   * editor's read-back are the same function — so the two can never show one
   * stored value in two spellings". That was true of the two sites it NAMES. The
   * summary was a third, and it called `String(value)`.
   */
  const runWith = (fields: Record<string, unknown>) =>
    ({
      id: 'r1',
      label: 'Scan 0012',
      fields: Object.fromEntries(
        Object.entries(fields).map(([k, v]) => [k, { value: v, status: 'verified', evidence: [] }]),
      ),
    }) as unknown as Parameters<typeof runConditionsSummary>[0];

  it('renders a stored UTC timestamp the human way, exactly as the Record Map does', () => {
    const summary = runConditionsSummary(
      runWith({ 'timestamps.acquired_start_utc': '2026-01-31T09:00:00Z' }),
    );
    // THE SAME STRING THE OTHER TWO SITES PRODUCE — asserted by calling the
    // renderer, not by transcribing its output, so a change to the format moves
    // all three together or fails here.
    expect(summary).toBe(formatStoredDatetime('2026-01-31T09:00:00Z'));
    expect(summary).toBe('Jan 31, 2026 · 09:00 UTC');
    // MUTATION: reverting the summary to `String(value)` makes this RED.
    expect(summary).not.toContain('2026-01-31T09:00:00Z');
  });

  it('leaves the other kinds exactly as they were, units included', () => {
    /* A NEGATIVE CONTROL ON SCOPE. Routing everything through the datetime
       renderer would be the obvious over-fix; it returns its input verbatim for
       anything it cannot read, so the bug would be invisible here without this. */
    expect(
      runConditionsSummary(
        runWith({ 'context.environment': 'in_situ', 'context.temperature_K': 45 }),
      ),
    ).toBe('in_situ · 45 K');
  });

  it('shows an unreadable timestamp VERBATIM rather than guessing at it', () => {
    /* The renderer's own rule, relied on here: re-spelling something you could
       not read is how a surface shows a value nobody entered. A half-typed entry
       must still read back as exactly what the record holds. */
    const half = '2026-01-3';
    expect(runConditionsSummary(runWith({ 'timestamps.acquired_start_utc': half }))).toBe(half);
  });

  it('keeps the field ORDER and the separator the summary always had', () => {
    const summary = runConditionsSummary(
      runWith({
        'context.environment': 'in_situ',
        'context.temperature_K': 45,
        'timestamps.acquired_start_utc': '2026-01-31T09:00:00Z',
      }),
    );
    expect(summary).toBe('in_situ · 45 K · Jan 31, 2026 · 09:00 UTC');
  });
});
