/*
 * `focusWhenPresent` — the cross-view focus hand-off, and the SLOW-MOUNT case that
 * PR #277's trusted suite failed on (2026-09-22).
 *
 * The defect: `RecordWorkbench` looked for "Review N Proposals"' destination heading
 * on ONE commit and gave up if it was not there. A destination that appears a frame
 * — or several — after the view switch lost the hand-off for good, and focus fell to
 * `<body>`. These tests pin the replacement's four behaviours: it waits for a late
 * target, it will not focus a target inside a hidden workspace, it gives up after a
 * bound (so nothing fires into whatever the reader is doing seconds later), and a
 * cancelled hand-off never focuses anything.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { focusWhenPresent } from '../lib/focusHandoff';

let frames: FrameRequestCallback[] = [];

beforeEach(() => {
  frames = [];
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    frames.push(cb);
    return frames.length;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    frames[id - 1] = () => undefined;
  });
  document.body.innerHTML = '';
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

/** Run the next queued frame (one "render later"). */
function tick(n = 1) {
  for (let i = 0; i < n; i += 1) {
    const queue = frames;
    frames = [];
    for (const cb of queue) cb(performance.now());
  }
}

function heading(): HTMLElement {
  const h = document.createElement('h2');
  h.id = 'dest';
  h.tabIndex = -1;
  return h;
}

describe('focusWhenPresent', () => {
  it('focuses at once when the destination is already there', () => {
    document.body.appendChild(heading());
    const done = vi.fn();
    focusWhenPresent(() => document.getElementById('dest'), done);
    expect(document.activeElement?.id).toBe('dest');
    expect(done).toHaveBeenCalledWith(true);
  });

  it('SLOW MOUNT: waits for a destination that appears several frames after the switch', () => {
    const done = vi.fn();
    focusWhenPresent(() => document.getElementById('dest'), done);
    // The first attempt found nothing — the old code returned here, for good.
    expect(document.activeElement).toBe(document.body);
    expect(done).not.toHaveBeenCalled();
    tick(2);
    expect(document.activeElement).toBe(document.body);
    // The workspace mounts three frames late …
    document.body.appendChild(heading());
    tick(1);
    // … and the hand-off still lands.
    expect(document.activeElement?.id).toBe('dest');
    expect(done).toHaveBeenCalledWith(true);
  });

  it('does not focus a destination inside a hidden workspace until it is shown', () => {
    const panel = document.createElement('section');
    panel.hidden = true;
    panel.appendChild(heading());
    document.body.appendChild(panel);
    const done = vi.fn();
    focusWhenPresent(() => document.getElementById('dest'), done);
    expect(document.activeElement).toBe(document.body);
    panel.hidden = false;
    tick(1);
    expect(document.activeElement?.id).toBe('dest');
  });

  it('gives up after its bound, and says so, rather than looping', () => {
    const done = vi.fn();
    // One immediate attempt plus up to 5 frames: the fifth retry is the last.
    // `minMs` 0 isolates the FRAME bound (since 2026-09-23 the hand-off also waits
    // out a time floor — pinned by its own test below).
    focusWhenPresent(() => document.getElementById('dest'), done, 5, 0);
    tick(4);
    expect(done).not.toHaveBeenCalled();
    tick(1);
    expect(done).toHaveBeenCalledWith(false);
    // Nothing is left scheduled, and a late arrival is NOT focused.
    expect(frames).toHaveLength(0);
    document.body.appendChild(heading());
    tick(3);
    expect(document.activeElement).toBe(document.body);
  });

  it('a cancelled hand-off never focuses, even if the destination then appears', () => {
    const done = vi.fn();
    const cancel = focusWhenPresent(() => document.getElementById('dest'), done);
    cancel();
    document.body.appendChild(heading());
    tick(3);
    expect(document.activeElement).toBe(document.body);
    expect(done).not.toHaveBeenCalled();
  });

  it('STALLED COMMIT (2026-09-23): frames spent but the time floor not reached — it keeps waiting, and lands', () => {
    let now = 1000;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const done = vi.fn();
    focusWhenPresent(() => document.getElementById('dest'), done, 5, 3000);
    // Every frame of the budget runs while the destination still has not rendered —
    // the full-parallel-run failure, where frames ran and the commit had not.
    tick(20);
    now += 1000;
    tick(5);
    expect(done).not.toHaveBeenCalled();
    // The commit finally lands, inside the time floor, and the hand-off still takes it.
    document.body.appendChild(heading());
    tick(1);
    expect(document.activeElement?.id).toBe('dest');
    expect(done).toHaveBeenCalledWith(true);
  });

  it('and once BOTH bounds have passed it gives up, so nothing fires later', () => {
    let now = 1000;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const done = vi.fn();
    focusWhenPresent(() => document.getElementById('dest'), done, 5, 3000);
    tick(10);
    expect(done).not.toHaveBeenCalled();
    now += 3000;
    tick(1);
    expect(done).toHaveBeenCalledWith(false);
    expect(frames).toHaveLength(0);
    document.body.appendChild(heading());
    tick(3);
    expect(document.activeElement).toBe(document.body);
  });
});
