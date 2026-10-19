import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { StrictMode } from 'react';

import { CHART_FALLBACK_WIDTH, StatsBarChart } from '../screens/statistics/StatsCharts';

/**
 * `useChartWidth` KEEPS A LIVE ResizeObserver UNDER <StrictMode> (2026-10-12).
 *
 * The defect this pins, measured in Chromium before it was fixed: the observer
 * was created in the ref callback and disconnected by a mount-only effect
 * cleanup. `main.tsx` renders under `<StrictMode>`, which in development runs
 * every effect's cleanup once and re-runs the effect — and React 18 does not
 * re-run the ref callback — so the simulated unmount killed the observer and
 * nothing ever made another. A chart mounted while hidden (a widget view that is
 * not selected) then stayed at the 560px fallback forever after being shown.
 *
 * jsdom has no ResizeObserver, so one is installed here that HONOURS
 * `disconnect()`: a callback is delivered only to observers still connected. The
 * negative control is the old shape — revert the hook and the first assertion
 * below fails, because the only observer was disconnected during mount.
 */

type Listener = (entries: { contentRect: { width: number } }[]) => void;

class FakeResizeObserver {
  static live = new Set<FakeResizeObserver>();
  constructor(private readonly listener: Listener) {}
  observe(): void {
    FakeResizeObserver.live.add(this);
  }
  unobserve(): void {
    FakeResizeObserver.live.delete(this);
  }
  disconnect(): void {
    FakeResizeObserver.live.delete(this);
  }
  static resizeAll(width: number): void {
    for (const observer of [...FakeResizeObserver.live]) {
      observer.listener([{ contentRect: { width } }]);
    }
  }
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  FakeResizeObserver.live.clear();
});

describe('useChartWidth under StrictMode', () => {
  it('keeps an observer connected through the double-invoked effects, and follows a resize', () => {
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    const { container } = render(
      <StrictMode>
        <StatsBarChart
          caption="A chart"
          rows={[{ key: 'a', label: 'Alpha', value: 3 }]}
          unit="records"
          total={3}
          categoryHeader="Thing"
        />
      </StrictMode>,
    );
    // jsdom measures 0, so the chart starts at the fallback, as documented.
    const svg = () => container.querySelector('svg.stats-chart-track') as SVGSVGElement;
    expect(svg().getAttribute('width')).toBe(String(CHART_FALLBACK_WIDTH));

    expect(FakeResizeObserver.live.size, 'no observer survived StrictMode').toBeGreaterThan(0);
    act(() => FakeResizeObserver.resizeAll(733));
    expect(svg().getAttribute('width')).toBe('733');
  });

  it('disconnects its observer on a real unmount', () => {
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
    const view = render(
      <StrictMode>
        <StatsBarChart
          caption="A chart"
          rows={[{ key: 'a', label: 'Alpha', value: 3 }]}
          unit="records"
          total={3}
          categoryHeader="Thing"
        />
      </StrictMode>,
    );
    expect(FakeResizeObserver.live.size).toBeGreaterThan(0);
    view.unmount();
    expect(FakeResizeObserver.live.size).toBe(0);
  });
});
