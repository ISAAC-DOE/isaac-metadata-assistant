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
import { RUN_FIELDS, parseRunField } from '../lib/runFields';

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
