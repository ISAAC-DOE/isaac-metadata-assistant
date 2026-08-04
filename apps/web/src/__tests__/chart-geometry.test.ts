import { describe, it, expect } from 'vitest';

import {
  MAX_BAR_THICKNESS,
  MIN_BAR_THICKNESS,
  SURFACE_GAP,
  axisTicks,
  bands,
  chartSummary,
  clampToDomain,
  describeValue,
  finiteOrNull,
  horizontalBars,
  linePoints,
  niceMax,
  polylinePoints,
  round,
  share,
  shareLabel,
  soleMaximumKey,
  stackSegments,
  verticalColumns,
} from '../screens/statistics/chartGeometry';

/**
 * The PURE chart geometry.
 *
 * This suite is where the honesty rules of the visualization system are actually
 * enforced, because they are all decisions about what to do with a number the
 * caller could not supply — and a rendering test cannot distinguish "drew a
 * zero-length bar because the value is 0" from "drew a zero-length bar because
 * the value was NaN". Here it can.
 *
 * Four rules, each with its own group below:
 *
 *   1. A share is `null`, never `0%`, when no denominator supports one.
 *   2. A non-finite value is DROPPED, never plotted at zero.
 *   3. A finite `0` KEEPS its place — it is a measurement.
 *   4. Nothing is scaled past the domain it was given.
 */

describe('finiteOrNull / describeValue — absence is not zero', () => {
  it('accepts finite numbers, including zero and negatives', () => {
    expect(finiteOrNull(0)).toBe(0);
    expect(finiteOrNull(-3)).toBe(-3);
    expect(finiteOrNull(42)).toBe(42);
  });

  it('rejects every non-finite and non-numeric value — and never coerces to 0', () => {
    for (const value of [NaN, Infinity, -Infinity, null, undefined, '5', {}, []]) {
      expect(finiteOrNull(value), `${String(value)} must be null`).toBeNull();
    }
  });

  it('speaks a non-finite value as "not available", never as "0"', () => {
    expect(describeValue(0)).toBe('0');
    expect(describeValue(7)).toBe('7');
    expect(describeValue(NaN)).toBe('not available');
    expect(describeValue(Infinity)).toBe('not available');
  });
});

describe('share — no denominator, no percentage', () => {
  it('rounds to whole percent', () => {
    expect(share(1, 3)).toBe(33);
    expect(share(2, 3)).toBe(67);
    expect(share(40, 40)).toBe(100);
    expect(share(0, 40)).toBe(0); // a measured zero out of a real total IS 0%
  });

  it('returns null — not 0 — for a total that cannot carry a share', () => {
    expect(share(0, 0)).toBeNull();
    expect(share(5, 0)).toBeNull();
    expect(share(5, -1)).toBeNull();
    expect(share(5, NaN)).toBeNull();
    expect(share(NaN, 10)).toBeNull();
    expect(share(-1, 10)).toBeNull();
  });

  it('formats a share, or nothing at all', () => {
    expect(shareLabel(1, 4)).toBe('25%');
    expect(shareLabel(0, 4)).toBe('0%');
    expect(shareLabel(1, 0)).toBeNull();
  });
});

describe('niceMax / axisTicks — a scale a reader can read', () => {
  it('rounds the domain up onto the 1 / 2 / 5 ladder', () => {
    expect(niceMax(1)).toBe(1);
    expect(niceMax(3)).toBe(5);
    expect(niceMax(5)).toBe(5);
    expect(niceMax(6)).toBe(10);
    expect(niceMax(17)).toBe(20);
    expect(niceMax(41)).toBe(50);
    expect(niceMax(140)).toBe(200);
  });

  it('gives an all-zero chart a domain of 1 rather than dividing by zero', () => {
    expect(niceMax(0)).toBe(1);
    expect(niceMax(-4)).toBe(1);
    expect(niceMax(NaN)).toBe(1);
  });

  it('ticks start at 0, end exactly at the domain, and are evenly spaced', () => {
    for (const max of [1, 2, 3, 5, 7, 10, 17, 20, 41, 50, 99, 140, 500]) {
      const ticks = axisTicks(max);
      expect(ticks[0], `max=${max}`).toBe(0);
      expect(ticks[ticks.length - 1], `max=${max}`).toBe(niceMax(max));
      const step = ticks[1] - ticks[0];
      for (let i = 1; i < ticks.length; i++) {
        expect(ticks[i] - ticks[i - 1], `even spacing at max=${max}`).toBeCloseTo(step, 6);
      }
    }
  });

  /*
   * THE BUG THIS PINS. Choosing the interval first and appending the maximum
   * afterwards is the obvious implementation, and for max=3 it produces
   * `0 · 2 · 4 · 5` — a crowded pair at the right edge that reads as data rather
   * than as a scale. The interval must DIVIDE the domain.
   */
  it('never crowds a final tick against the one before it', () => {
    expect(axisTicks(3)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(axisTicks(20)).toEqual([0, 5, 10, 15, 20]);
    expect(axisTicks(200)).toEqual([0, 50, 100, 150, 200]);
  });

  it('emits only whole-number ticks, because every quantity here is a count', () => {
    for (const max of [1, 2, 3, 5, 7, 10, 17, 20, 41, 50, 99, 140, 500, 0]) {
      for (const tick of axisTicks(max)) {
        expect(Number.isInteger(tick), `max=${max} tick=${tick}`).toBe(true);
      }
    }
  });
});

describe('bands — a mark is capped, and the leftover is air', () => {
  it('splits the extent evenly and centres the mark', () => {
    const [first, second] = bands(2, 200);
    expect(first.start).toBe(0);
    expect(first.size).toBe(100);
    expect(second.start).toBe(100);
    expect(first.markStart).toBeCloseTo((100 - first.markThickness) / 2, 6);
  });

  it('caps thickness so two bars are not two slabs', () => {
    expect(bands(2, 400)[0].markThickness).toBe(MAX_BAR_THICKNESS);
    expect(bands(1, 1000)[0].markThickness).toBe(MAX_BAR_THICKNESS);
  });

  it('stops shrinking at the floor rather than drawing a hairline', () => {
    expect(bands(40, 100)[0].markThickness).toBe(MIN_BAR_THICKNESS);
  });

  it('is empty for a degenerate request rather than throwing', () => {
    expect(bands(0, 100)).toEqual([]);
    expect(bands(3, 0)).toEqual([]);
    expect(bands(3, NaN)).toEqual([]);
  });
});

describe('clampToDomain — nothing is scaled past its domain', () => {
  it('passes a value inside the domain through', () => {
    expect(clampToDomain(3, 10)).toBe(3);
    expect(clampToDomain(0, 10)).toBe(0);
  });

  it('clamps rather than overflowing when the caller exceeds their own domain', () => {
    expect(clampToDomain(30, 10)).toBe(10);
  });

  it('returns null for a value that cannot be placed', () => {
    expect(clampToDomain(NaN, 10)).toBeNull();
    expect(clampToDomain(Infinity, 10)).toBeNull();
    expect(clampToDomain(-1, 10)).toBeNull();
  });
});

describe('horizontalBars — drop the unmeasurable, keep the measured zero', () => {
  const plot = { width: 300, height: 90 };

  it('scales widths against the NICE maximum, not the raw one', () => {
    // max 3 → domain 5, so a 5 would be full width and a 3 is 60% of it.
    const marks = horizontalBars(
      [
        { key: 'a', value: 3 },
        { key: 'b', value: 1 },
        { key: 'c', value: 0 },
      ],
      3,
      plot,
    );
    expect(marks.map((m) => m.key)).toEqual(['a', 'b', 'c']);
    expect(marks[0].width).toBeCloseTo(180, 6);
    expect(marks[1].width).toBeCloseTo(60, 6);
    expect(marks[2].width).toBe(0);
  });

  it('KEEPS a zero row, with a zero-width mark', () => {
    const marks = horizontalBars([{ key: 'z', value: 0 }], 4, plot);
    expect(marks).toHaveLength(1);
    expect(marks[0].width).toBe(0);
    expect(marks[0].value).toBe(0);
  });

  it('DROPS a non-finite or negative row instead of drawing it at zero', () => {
    const marks = horizontalBars(
      [
        { key: 'ok', value: 2 },
        { key: 'nan', value: NaN },
        { key: 'neg', value: -5 },
      ],
      2,
      plot,
    );
    expect(marks.map((m) => m.key)).toEqual(['ok']);
  });

  it('never exceeds the plot width', () => {
    const marks = horizontalBars([{ key: 'over', value: 999 }], 2, plot);
    expect(marks[0].width).toBeLessThanOrEqual(plot.width);
  });
});

describe('verticalColumns — grown from one baseline', () => {
  const plot = { width: 200, height: 100 };

  it('puts every column base at the plot floor', () => {
    const marks = verticalColumns(
      [
        { key: 'a', value: 5 },
        { key: 'b', value: 1 },
      ],
      5,
      plot,
    );
    for (const mark of marks) {
      expect(mark.y + mark.height).toBeCloseTo(plot.height, 6);
    }
    expect(marks[0].height).toBeCloseTo(100, 6);
    expect(marks[1].height).toBeCloseTo(20, 6);
  });

  it('drops a non-finite column', () => {
    expect(verticalColumns([{ key: 'x', value: Infinity }], 4, plot)).toEqual([]);
  });
});

describe('stackSegments — the caller owns the whole', () => {
  it('uses the caller total as the denominator, never the sum of the parts', () => {
    // Parts sum to 5 but the caller says the whole is 10: half the bar stays empty.
    const segments = stackSegments(
      [
        { key: 'a', value: 3 },
        { key: 'b', value: 2 },
      ],
      10,
      100,
    );
    expect(segments[0].sharePct).toBe(30);
    expect(segments[1].sharePct).toBe(20);
    // a: 30px minus the 2px gap; b is last so it keeps its full 20px.
    expect(segments[0].width).toBeCloseTo(30 - SURFACE_GAP, 6);
    expect(segments[1].width).toBeCloseTo(20, 6);
    expect(segments[1].x).toBeCloseTo(30, 6);
  });

  it('leaves a surface gap between every pair of adjacent segments, and none after the last', () => {
    const segments = stackSegments(
      [
        { key: 'a', value: 1 },
        { key: 'b', value: 1 },
        { key: 'c', value: 2 },
      ],
      4,
      400,
    );
    // Each non-final segment ends SURFACE_GAP short of the next one's start.
    for (let i = 0; i < segments.length - 1; i++) {
      expect(segments[i + 1].x - (segments[i].x + segments[i].width)).toBeCloseTo(SURFACE_GAP, 6);
    }
    const last = segments[segments.length - 1];
    expect(last.x + last.width).toBeCloseTo(400, 6);
  });

  it('keeps a zero segment (with zero width) so its class is still accounted for', () => {
    const segments = stackSegments(
      [
        { key: 'a', value: 4 },
        { key: 'zero', value: 0 },
      ],
      4,
      200,
    );
    expect(segments.map((s) => s.key)).toEqual(['a', 'zero']);
    expect(segments[1].width).toBe(0);
    expect(segments[1].sharePct).toBe(0);
  });

  it('never lets a sliver go negative once its gap is taken out', () => {
    const segments = stackSegments(
      [
        { key: 'tiny', value: 1 },
        { key: 'rest', value: 999 },
      ],
      1000,
      100,
    );
    expect(segments[0].width).toBeGreaterThanOrEqual(0);
  });

  it('states no share at all when the whole is not a positive number', () => {
    const segments = stackSegments([{ key: 'a', value: 0 }], 0, 100);
    expect(segments[0].sharePct).toBeNull();
    expect(segments[0].width).toBe(0);
  });
});

describe('linePoints / polylinePoints — an index axis, never an inferred calendar', () => {
  const plot = { width: 300, height: 100 };
  const rows = [
    { key: 'w1', label: 'Week 1', value: 0 },
    { key: 'w2', label: 'Week 2', value: 5 },
    { key: 'w3', label: 'Week 3', value: 10 },
  ];

  it('spaces points evenly by index across the full width', () => {
    const points = linePoints(rows, 10, plot);
    expect(points.map((p) => round(p.x))).toEqual([0, 150, 300]);
    expect(points.map((p) => round(p.y))).toEqual([100, 50, 0]);
  });

  it('centres a single observation rather than pinning it to the left edge', () => {
    expect(round(linePoints([rows[0]], 10, plot)[0].x)).toBe(150);
  });

  it('DROPS a non-finite observation, leaving a real gap rather than a fake zero', () => {
    const points = linePoints(
      [rows[0], { key: 'bad', label: 'Week 2', value: NaN }, rows[2]],
      10,
      plot,
    );
    expect(points.map((p) => p.key)).toEqual(['w1', 'w3']);
    // ...and the surviving points keep their ORIGINAL index positions, so the gap
    // is visible instead of the series closing up over the missing period.
    expect(round(points[1].x)).toBe(300);
  });

  it('serializes to an SVG points attribute', () => {
    expect(polylinePoints(linePoints(rows, 10, plot))).toBe('0,100 150,50 300,0');
    expect(polylinePoints([])).toBe('');
  });
});

describe('chartSummary — the sentence a screen reader gets', () => {
  const rows = [
    { label: 'Load Record', value: 0 },
    { label: 'Export', value: 2 },
  ];

  it('names every category, its value, and the unit-qualified total', () => {
    expect(chartSummary('Records by step', rows, 'records', 5)).toBe(
      'Records by step. Load Record: 0, Export: 2. Total 5 records.',
    );
  });

  it('strips trailing punctuation from the caller caption so the sentence reads once', () => {
    expect(chartSummary('Records by step:', rows, 'records', 5)).toContain('Records by step. ');
  });

  it('omits the total clause rather than naming a denominator it was not given', () => {
    const summary = chartSummary('Operations by group', rows, 'operations', null);
    expect(summary).not.toMatch(/Total/);
    expect(summary).toContain('Load Record: 0');
  });

  it('says there is nothing to describe rather than describing nothing', () => {
    expect(chartSummary('Records by step', [], 'records', 0)).toBe(
      'Records by step. No records to describe.',
    );
  });

  it('speaks an unmeasurable value as not available, so the unit is never faked', () => {
    expect(chartSummary('X', [{ label: 'A', value: NaN }], 'fields', null)).toContain(
      'A: not available',
    );
  });
});

describe('soleMaximumKey — label selectively, and never arbitrarily', () => {
  it('names the single largest row', () => {
    expect(
      soleMaximumKey([
        { key: 'a', value: 1 },
        { key: 'b', value: 4 },
        { key: 'c', value: 2 },
      ]),
    ).toBe('b');
  });

  /*
   * A TIE LABELS NOTHING. Highlighting one of two equal maxima would assert a
   * difference that is not in the data — the exact class of small lie this whole
   * surface is arranged against.
   */
  it('returns null for a tie', () => {
    expect(
      soleMaximumKey([
        { key: 'a', value: 4 },
        { key: 'b', value: 4 },
      ]),
    ).toBeNull();
  });

  it('returns null when every value is zero, absent or unmeasurable', () => {
    expect(soleMaximumKey([])).toBeNull();
    expect(soleMaximumKey([{ key: 'a', value: 0 }])).toBeNull();
    expect(soleMaximumKey([{ key: 'a', value: NaN }])).toBeNull();
  });
});
