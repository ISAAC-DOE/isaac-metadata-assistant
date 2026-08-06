import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axe from 'axe-core';

import {
  RecordVerification,
  useVerificationReport,
} from '../screens/statistics/RecordVerification';
import { MyStats } from '../screens/statistics/MyStats';
import {
  SAFEGUARD_LABELS,
  SAFEGUARD_STATE_LABELS,
  SUPPRESSED_ROW_LABEL,
  VERIFICATION_MODE_LABELS,
  VERIFICATION_MUTATION_KEYS,
  VERIFICATION_ORACLE_KEYS,
} from '../lib/verificationContract';
import {
  verificationErrorEnvelope,
  verificationFailureEnvelope,
  verificationFutureFormat,
  verificationRefusedEnvelope,
  verificationReportNoSuppression,
  verificationReportOk,
  verificationReportPrivateSample,
  verificationReportPrivateSampleShort,
  verificationReportSourceRecordsAltered,
  verificationReportWithheldButEmpty,
  verificationReportStale,
  verificationReportUnbalancedMutations,
  verificationReportUnknownMode,
  verificationReportWithFindings,
  verificationRunningEnvelope,
} from '../test/verificationFixtures';

/**
 * The Record Verification section, rendered.
 *
 * ── THE TWO RULES THIS FILE EXISTS FOR ─────────────────────────────────────
 *
 * 1. WHICH CORPUS RAN MUST NEVER BE MISSTATED. Two corpora produce this same
 *    report shape and they carry very different weight — the public upstream
 *    examples, and an authorized read of the records this application holds. A
 *    public result presented as if it came from the authorized sample would
 *    misattribute every figure on the screen at once, and nothing else would
 *    look wrong. The labelling tests come FIRST for that reason, and they assert
 *    in both directions: the right label present, AND the other label absent.
 *
 * 2. `not_applicable` MUST NEVER REACH THE SCREEN AS "VERIFIED". A
 *    read-only-transaction safeguard reading "Verified" when no database was
 *    contacted is a statement about an event that never happened — the exact
 *    class of false claim `CLAUDE.md` §15 records this project shipping and
 *    correcting more than once.
 *
 * Everything else here is the runtime-state matrix. The section owns its own
 * read, so every state below is driven through the injected `read` — including
 * the two a shared fetch hook cannot produce: a re-read that fails while a good
 * result is on screen, and that same failure happening twice in a row.
 */

/* ---- harness ------------------------------------------------------------ */

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/**
 * The section as the page mounts it: the read lives in `useVerificationReport`,
 * which `StatisticsPage` calls (so a tab switch cannot re-issue it), and the
 * section renders the state it is handed.
 */
function Section({ read }: { read: () => Promise<unknown> }) {
  const verification = useVerificationReport(read);
  return <RecordVerification verification={verification} />;
}

/** Wait until the section's own loading panel has gone. */
async function settled(): Promise<void> {
  await waitFor(() =>
    expect(document.querySelectorAll('.fetch-state[role="status"]')).toHaveLength(0),
  );
}

/** Render with a body that is already available. */
async function renderReport(body: unknown) {
  const view = render(<Section read={() => Promise.resolve(body)} />);
  await settled();
  return view;
}

const bodyText = (): string => document.body.textContent ?? '';

const liveRegion = (): HTMLElement => {
  const node = document.querySelector('.stats-verify-live[role="status"]');
  expect(node).not.toBeNull();
  return node as HTMLElement;
};

const refreshButton = (): HTMLElement =>
  screen.getByRole('button', { name: 'Refresh the verification report' });

/**
 * Flush pending microtasks (a settled `read`) inside `act`.
 *
 * `waitFor` is deliberately NOT used in the polling tests: it schedules its own
 * timers, so under fake timers it either hangs or advances the very clock the
 * assertion is about.
 */
async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

/**
 * Run `body` with fake timers installed BEFORE anything renders.
 *
 * THE ORDER IS THE WHOLE POINT, and getting it wrong is why the two polling
 * tests here were vacuous for a while: `vi.useFakeTimers()` called AFTER
 * `render()` leaves every timer registered during mount on the real clock, so
 * `advanceTimersByTime` moves a clock nothing is listening to. A genuine
 * `setInterval(… read() …, 30_000)` injected into the mount effect passed the
 * whole suite — 88 of 88 — with `read` still reported as called once.
 */
async function withFakeTimers(body: () => Promise<void>): Promise<void> {
  vi.useFakeTimers();
  try {
    await body();
  } finally {
    vi.useRealTimers();
  }
}

/* ============================================================ 1 · corpus == */

describe('which corpus ran — the highest-stakes label on this screen', () => {
  it('names the public corpus as a preflight, and never as the authorized sample', async () => {
    await renderReport(verificationReportOk);

    expect(screen.getAllByText('Public reference preflight').length).toBeGreaterThan(0);
    // The wire token is carried too, verbatim — the label never replaces it.
    expect(bodyText()).toContain('public_reference');

    // THE ASSERTION THAT MATTERS: the other corpus is not named, in any form.
    expect(bodyText()).not.toContain('Authorized 30-record reference sample');
    expect(bodyText()).not.toContain('authorized_private_sample');
    expect(bodyText()).not.toMatch(/authorized/i);
  });

  it('names the private corpus as the authorized sample, and never as the public preflight', async () => {
    await renderReport(verificationReportPrivateSample);

    expect(screen.getAllByText('Authorized 30-record reference sample').length).toBeGreaterThan(0);
    expect(bodyText()).toContain('authorized_private_sample');

    expect(bodyText()).not.toContain('Public reference preflight');
    expect(bodyText()).not.toContain('public_reference');
  });

  it('pins both labels as literals, and pins what tells them apart', () => {
    // Duplicated from the module on purpose: a test that reads the constant it
    // is checking proves only that the constant equals itself.
    const publicLabel = 'Public reference preflight';
    const privateLabel = 'Authorized 30-record reference sample';
    expect(VERIFICATION_MODE_LABELS.public_reference).toBe(publicLabel);
    expect(VERIFICATION_MODE_LABELS.authorized_private_sample).toBe(privateLabel);

    // They DO share the word "reference", which is why the distinguishing test
    // is on the discriminating words rather than on disjointness: each label
    // carries a word the other cannot, and the labels differ from their FIRST
    // word — so a reading truncated anywhere past the first word still says
    // which corpus ran.
    expect(publicLabel.split(' ')[0]).toBe('Public');
    expect(privateLabel.split(' ')[0]).toBe('Authorized');
    expect(publicLabel).toMatch(/\bPublic\b/);
    expect(publicLabel).not.toMatch(/\bAuthorized\b/i);
    expect(privateLabel).toMatch(/\bAuthorized\b/);
    expect(privateLabel).not.toMatch(/\bPublic\b/i);
    // Neither is a prefix of the other, so neither can be produced by clipping.
    expect(publicLabel.startsWith(privateLabel)).toBe(false);
    expect(privateLabel.startsWith(publicLabel)).toBe(false);
  });

  it('shows an unrecognised mode verbatim, and maps it onto NEITHER shipped label', async () => {
    await renderReport(verificationReportUnknownMode);

    expect(bodyText()).toContain('some_future_corpus');
    expect(bodyText()).not.toContain('Public reference preflight');
    expect(bodyText()).not.toContain('Authorized 30-record reference sample');
    // …and it says plainly that the corpus cannot be named, rather than staying
    // silent and letting the figures read as if it had been.
    expect(bodyText()).toMatch(/no description for that corpus/i);
    expect(document.querySelector('.stats-verify-corpus')?.getAttribute('data-known')).toBe(
      'false',
    );
  });

  it('keeps the label and the token TOGETHER, inside the corpus block itself', async () => {
    /*
     * The guarantee is "label BESIDE token", and it was only pinned as "token
     * somewhere on the page" — which the About This Run row satisfies on its
     * own. Deleting the token from `CorpusBanner` left the whole suite green
     * while the prominent statement of which corpus ran became a product label
     * with nothing to check it against.
     */
    const { container } = await renderReport(verificationReportOk);
    const banner = container.querySelector('.stats-verify-corpus');
    expect(banner).not.toBeNull();
    expect(within(banner as HTMLElement).getByText('Public reference preflight')).toBeInTheDocument();
    expect(within(banner as HTMLElement).getByText('public_reference')).toBeInTheDocument();
    // …and the token is in the mono face, so it reads as a value rather than as
    // more prose.
    expect(banner!.querySelector('.mono')?.textContent).toBe('public_reference');
  });

  it('keeps the label and the token together for the private corpus too', async () => {
    const { container } = await renderReport(verificationReportPrivateSample);
    const banner = container.querySelector('.stats-verify-corpus') as HTMLElement;
    expect(within(banner).getByText('Authorized 30-record reference sample')).toBeInTheDocument();
    expect(within(banner).getByText('authorized_private_sample')).toBeInTheDocument();
  });

  it('keeps an UNRECOGNISED token in the corpus block, where the label would be', async () => {
    const { container } = await renderReport(verificationReportUnknownMode);
    const banner = container.querySelector('.stats-verify-corpus') as HTMLElement;
    // Twice: as its own label, and as the reported value.
    expect(within(banner).getAllByText('some_future_corpus').length).toBeGreaterThanOrEqual(2);
  });

  it('states the corpus BEFORE the first figure, because it qualifies all of them', async () => {
    const { container } = await renderReport(verificationReportOk);
    const corpus = container.querySelector('.stats-verify-corpus');
    const firstCard = container.querySelector('.stat-card');
    expect(corpus).not.toBeNull();
    expect(firstCard).not.toBeNull();
    expect(
      corpus!.compareDocumentPosition(firstCard!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('states BOTH numbers when the label’s figure and the measured size disagree', async () => {
    await renderReport(verificationReportPrivateSampleShort);
    // The label still says 30 — it is authored copy and is not rewritten…
    expect(bodyText()).toContain('Authorized 30-record reference sample');
    // …and the report's own measurement is stated beside it, with the
    // disagreement named rather than reconciled.
    expect(bodyText()).toMatch(/named for 30 records, and the report states that it evaluated 12/i);
    expect(bodyText()).toMatch(/neither has been adjusted/i);
  });

  it('states no size disagreement for the public corpus, which carries no figure in its name', async () => {
    await renderReport(verificationReportOk);
    expect(bodyText()).not.toMatch(/named for 30 records/i);
  });
});

/* ====================================================== 2 · runtime states = */

describe('runtime states', () => {
  it('LOADING — a labelled status, no figures, no zeros', () => {
    render(<Section read={() => new Promise(() => {})} />);
    expect(document.querySelector('.fetch-state[role="status"]')).not.toBeNull();
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0);
    expect(document.querySelectorAll('.stats-verify-state')).toHaveLength(0);
  });

  it('RUNNING — says a run is under way, and states no count in its place', async () => {
    await renderReport(verificationRunningEnvelope);
    expect(screen.getByText('Verification Run in Progress')).toBeInTheDocument();
    expect(bodyText()).toMatch(/no earlier result is shown in its place/i);
    // No figure, and pointedly no zero.
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0);
    expect(document.querySelectorAll('.stats-verify-state')).toHaveLength(0);
    expect(bodyText()).not.toMatch(/\b0 of 0\b/);
  });

  it('RUNNING — offers a control to look again, and does NOT poll on its own', async () => {
    // A run in progress is exactly the state a naive client would poll.
    const read = vi.fn().mockResolvedValue(verificationRunningEnvelope);
    await withFakeTimers(async () => {
      render(<Section read={read} />);
      await flush();
      expect(read).toHaveBeenCalledTimes(1);
      act(() => {
        vi.advanceTimersByTime(5 * 60 * 1000);
      });
      await flush();
      expect(read).toHaveBeenCalledTimes(1);
    });

    // …and the reader still has a way to ask again.
    expect(refreshButton()).toBeEnabled();
  });

  it('AVAILABLE — draws the report', async () => {
    await renderReport(verificationReportOk);
    expect(document.querySelectorAll('.stat-card')).toHaveLength(4);
    expect(document.querySelectorAll('.stats-verify-safeguard').length).toBeGreaterThan(0);
  });

  it('STALE — discloses that the result is past the age the API holds one for', async () => {
    await renderReport(verificationReportStale);
    expect(bodyText()).toMatch(/past the .* the API holds one for/i);
    expect(bodyText()).toMatch(/a newer run may already have replaced them/i);
    // Stale is not an error: the figures are still shown.
    expect(document.querySelectorAll('.stat-card')).toHaveLength(4);
  });

  it('FRESH — says nothing about staleness when the result is inside the window', async () => {
    await renderReport(verificationReportOk);
    expect(bodyText()).not.toMatch(/a newer run may already have replaced them/i);
  });

  it('REFRESHING — marks the control busy, keeps the figures, and announces', async () => {
    const pending = deferred<unknown>();
    const read = vi
      .fn()
      .mockResolvedValueOnce(verificationReportOk)
      .mockImplementationOnce(() => pending.promise);
    render(<Section read={read} />);
    await settled();

    fireEvent.click(refreshButton());

    await waitFor(() => expect(refreshButton()).toHaveAttribute('aria-busy', 'true'));
    expect(refreshButton()).toBeDisabled();
    expect(bodyText()).toMatch(/the results below are still the ones last read/i);
    expect(liveRegion().textContent).toBe('Re-reading the verification report.');
    // The figures never blank while a re-read is in flight.
    expect(document.querySelectorAll('.stat-card')).toHaveLength(4);

    await act(async () => {
      pending.resolve(verificationReportWithFindings);
      await pending.promise;
    });
    await waitFor(() =>
      expect(liveRegion().textContent).toBe('The verification report was re-read.'),
    );
    expect(refreshButton()).toBeEnabled();
    // …and the NEW body is what is drawn.
    expect(bodyText()).toMatch(/counted at least one statement/i);
  });

  it('FAILED REFRESH — keeps the last good result, says so, and announces it', async () => {
    const read = vi
      .fn()
      .mockResolvedValueOnce(verificationReportOk)
      .mockRejectedValueOnce(new Error('ECONNRESET at https://example.invalid/api'));
    render(<Section read={read} />);
    await settled();

    await act(async () => {
      fireEvent.click(refreshButton());
    });

    await waitFor(() =>
      expect(liveRegion().textContent).toMatch(/could not be re-read/i),
    );
    // THE POINT: the earlier reading is still on screen, and is not relabelled
    // as current.
    expect(document.querySelectorAll('.stat-card')).toHaveLength(4);
    expect(bodyText()).toMatch(/what is shown below is the result of the last read that did/i);
    expect(bodyText()).toMatch(/older than it says/i);
    // The rejection's own text never reaches the screen.
    expect(bodyText()).not.toContain('ECONNRESET');
    expect(bodyText()).not.toContain('example.invalid');
  });

  it('FAILED REFRESH TWICE — the second failure is announced too', async () => {
    // The regression this section's design exists for. A silent reload that only
    // records "the last refresh failed" as a boolean cannot report this: the
    // second failure writes the same value, React bails out, and the control is
    // left announcing a refresh that already ended.
    const read = vi
      .fn()
      .mockResolvedValueOnce(verificationReportOk)
      .mockRejectedValue(new Error('down'));
    render(<Section read={read} />);
    await settled();

    await act(async () => {
      fireEvent.click(refreshButton());
    });
    await waitFor(() => expect(refreshButton()).toBeEnabled());

    await act(async () => {
      fireEvent.click(refreshButton());
    });
    await waitFor(() => expect(refreshButton()).toBeEnabled());

    expect(read).toHaveBeenCalledTimes(3);
    expect(liveRegion().textContent).toMatch(/could not be re-read/i);
    expect(document.querySelectorAll('.stat-card')).toHaveLength(4);
  });

  it('UNAVAILABLE — names the causes the one status word covers, and asserts none of them', async () => {
    await renderReport(verificationFailureEnvelope);
    expect(screen.getByText('Verification Results Unavailable')).toBeInTheDocument();
    expect(bodyText()).toMatch(/does not say which of several causes applies/i);
    // A source that did not answer — the datastore case — is named as a
    // POSSIBILITY. Nothing here claims it happened, because the envelope carries
    // no metadata at all and cannot say.
    expect(bodyText()).toMatch(/a source it needed may not have answered/i);
    expect(bodyText()).toMatch(/a read may have timed out/i);
    expect(bodyText()).toMatch(/no count is assumed to be zero/i);
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0);
  });

  it('SAFE ERROR — reports the program’s own error status with no exception text', async () => {
    await renderReport(verificationErrorEnvelope);
    expect(bodyText()).toMatch(/reported an error and produced no result/i);
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0);
    expect(bodyText()).not.toMatch(/traceback|stack|exception|at .*\.py:/i);
  });

  it('REFUSED — states the refusal and infers nothing from it', async () => {
    await renderReport(verificationRefusedEnvelope);
    expect(screen.getByText('Verification Declined')).toBeInTheDocument();
    expect(bodyText()).toMatch(/nothing is inferred from the refusal/i);
  });

  it('TIMEOUT / UNREACHABLE — a read that never answers is a different state from a report that says nothing', async () => {
    const read = vi
      .fn()
      .mockRejectedValueOnce(new Error('timeout of 30000ms exceeded — GET /api/runtime/verification'));
    render(<Section read={read} />);
    await settled();

    expect(bodyText()).toMatch(/could not be read from the API/i);
    expect(bodyText()).toMatch(/no count is assumed to be zero/i);
    // The transport failure's text is never rendered.
    expect(bodyText()).not.toContain('30000ms');
    expect(bodyText()).not.toContain('/api/runtime/verification');
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0);
  });

  it('TIMEOUT — Retry re-reads, and a later success recovers the section', async () => {
    const read = vi
      .fn()
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(verificationReportOk);
    render(<Section read={read} />);
    await settled();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    });
    await settled();

    expect(read).toHaveBeenCalledTimes(2);
    expect(document.querySelectorAll('.stat-card')).toHaveLength(4);
  });

  it('UNREADABLE — refuses a format version it has not been checked against', async () => {
    await renderReport(verificationFutureFormat);
    expect(screen.getByText('Verification Results Not Shown')).toBeInTheDocument();
    expect(bodyText()).toMatch(/answered in format 3/i);
    expect(document.querySelectorAll('.stats-verify-state')).toHaveLength(0);
  });

  it('UNREADABLE — refuses a malformed body rather than partially drawing it', async () => {
    await renderReport({ status: 'ok', report_format_version: 2 });
    expect(bodyText()).toMatch(/cannot read as a verification report/i);
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0);
  });

  it('NEVER POLLS — an hour of clock changes nothing', async () => {
    const read = vi.fn().mockResolvedValue(verificationReportOk);
    await withFakeTimers(async () => {
      render(<Section read={read} />);
      await flush();
      expect(read).toHaveBeenCalledTimes(1);
      act(() => {
        vi.advanceTimersByTime(60 * 60 * 1000);
      });
      await flush();
      expect(read).toHaveBeenCalledTimes(1);
    });
  });

  it('NEVER POLLS — schedules no repeating timer during mount at all', async () => {
    /*
     * The SECOND, independent probe, and it needs no clock.
     *
     * Advancing timers proves a scheduled callback did not RE-READ; this proves
     * nothing was scheduled. They fail in different ways — a loop that polls a
     * different function, or one whose read is swallowed, escapes the first and
     * not the second — and the docstring in `RecordVerification.tsx` claims
     * "no interval, no timeout and no retry loop anywhere in this file", which
     * is a claim about the CODE, not about one observable consequence of it.
     *
     * `setInterval` only, and the SETTLE IS `flush()`, NOT `settled()`. The
     * first version of this test used `settled()` and failed with one recorded
     * call: `[Function checkRealTimersCallback], 50` — `waitFor` from
     * `@testing-library/dom` polls with its own `setInterval`. (An earlier
     * revision of this comment asserted the opposite, that testing-library uses
     * `setTimeout`; the test corrected it.) So the harness must not schedule
     * anything either, and `flush()` only awaits microtasks.
     *
     * `setTimeout` is deliberately NOT spied on: React's scheduler uses it, so
     * the assertion would need a stack filter, and a filter is a thing that
     * itself needs testing. Nothing else in this path touches `setInterval`,
     * which is what makes a bare "never called" meaningful.
     */
    const interval = vi.spyOn(globalThis, 'setInterval');
    try {
      const read = vi.fn().mockResolvedValue(verificationReportOk);
      render(<Section read={read} />);
      await flush();
      expect(read).toHaveBeenCalledTimes(1);
      expect(document.querySelectorAll('.stat-card')).toHaveLength(4);
      expect(interval).not.toHaveBeenCalled();
    } finally {
      interval.mockRestore();
    }
  });

  it('the live region is present from the first render, so its CHANGE is what announces', () => {
    render(<Section read={() => new Promise(() => {})} />);
    const live = liveRegion();
    expect(live).toHaveClass('sr-only');
    expect(live.textContent).toBe('');
  });

  it('the refresh control keeps ONE accessible name, busy or not', async () => {
    const pending = deferred<unknown>();
    const read = vi
      .fn()
      .mockResolvedValueOnce(verificationReportOk)
      .mockImplementationOnce(() => pending.promise);
    render(<Section read={read} />);
    await settled();

    fireEvent.click(refreshButton());
    // Still findable by the same name while busy — a control that renames itself
    // mid-press moves out from under the reader.
    await waitFor(() => expect(refreshButton()).toHaveAttribute('aria-busy', 'true'));

    await act(async () => {
      pending.resolve(verificationReportOk);
      await pending.promise;
    });
    expect(refreshButton()).toBeEnabled();
  });

  it('drops a finished announcement when the section is re-mounted', async () => {
    // The read state outlives the section (the General tab panel unmounts on a
    // switch to My Stats), so returning to the tab must not rebuild the live
    // region with the previous press's sentence already inside it.
    function Host({ read, mounted }: { read: () => Promise<unknown>; mounted: boolean }) {
      const verification = useVerificationReport(read);
      return mounted ? <RecordVerification verification={verification} /> : null;
    }
    const read = vi.fn().mockResolvedValue(verificationReportOk);
    const { rerender } = render(<Host read={read} mounted />);
    await settled();

    await act(async () => {
      fireEvent.click(refreshButton());
    });
    await waitFor(() =>
      expect(liveRegion().textContent).toBe('The verification report was re-read.'),
    );

    // Leave the tab…
    rerender(<Host read={read} mounted={false} />);
    // …and come back.
    rerender(<Host read={read} mounted />);
    await waitFor(() => expect(liveRegion().textContent).toBe(''));
    // Coming back re-read nothing: the state survived the unmount.
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('does not collide with the Statistics page’s own Refresh button name', async () => {
    await renderReport(verificationReportOk);
    // The page-level control is named exactly "Refresh"; this one must not be.
    expect(screen.queryByRole('button', { name: 'Refresh' })).toBeNull();
  });
});

/* ==================================================== 3 · headline cards === */

describe('the headline cards', () => {
  it('renders EXACTLY four, with exactly these four labels', async () => {
    const { container } = await renderReport(verificationReportOk);
    const labels = Array.from(container.querySelectorAll('.stat-card .stat-card-label')).map(
      (node) => node.textContent?.trim(),
    );
    expect(labels).toEqual([
      'Records Evaluated',
      'Official Validation',
      'Format Shadow',
      'Mutation Verification',
    ]);
  });

  it('states the corpus size it actually received', async () => {
    const { container } = await renderReport(verificationReportOk);
    const evaluated = container.querySelectorAll('.stat-card')[0];
    expect(within(evaluated as HTMLElement).getByText('10')).toBeInTheDocument();
  });

  it('glosses the jargon label so "Format Shadow" is not the only thing said', async () => {
    const { container } = await renderReport(verificationReportOk);
    const shadow = container.querySelectorAll('.stat-card')[2] as HTMLElement;
    expect(shadow.textContent).toMatch(/stricter second validator/i);
  });

  it('reports unexpected mutation outcomes when there are some', async () => {
    const { container } = await renderReport(verificationReportWithFindings);
    expect(verificationReportWithFindings.mutations.unexpected_outcomes).toBe(3);
    const mutation = container.querySelectorAll('.stat-card')[3] as HTMLElement;
    expect(mutation.textContent).toMatch(/3 behaved unexpectedly/);
    expect(mutation.getAttribute('data-tone')).toBe('attention');
  });

  it('draws the zero-unexpected case calmly, because zero is the good reading', async () => {
    const { container } = await renderReport(verificationReportOk);
    const mutation = container.querySelectorAll('.stat-card')[3] as HTMLElement;
    expect(mutation.getAttribute('data-tone')).toBe('good');
  });
});

/* ============================================ 4 · official vs shadow ======= */

describe('the official / shadow comparison', () => {
  it('draws a grouped chart, not a progress bar', async () => {
    const { container } = await renderReport(verificationReportOk);
    const groups = container.querySelectorAll('.stats-verify-chartgroup');
    expect(groups).toHaveLength(2);
    // A shared, labelled value axis is what makes it a chart rather than a row
    // of tracks.
    expect(container.querySelectorAll('.stats-chart-axis').length).toBeGreaterThan(0);
    // Four bars: two series in each of two groups.
    const bars = Array.from(groups).flatMap((group) =>
      Array.from(group.querySelectorAll('rect.stats-chart-bar')),
    );
    expect(bars).toHaveLength(4);
  });

  it('labels every bar with its series name and value as real text', async () => {
    const { container } = await renderReport(verificationReportOk);
    const groups = container.querySelectorAll('.stats-verify-chartgroup');
    const official = groups[0] as HTMLElement;
    const rows = official.querySelectorAll('.stats-chart-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]!.querySelector('.stats-chart-row-label')!.textContent).toMatch(/^Passing/);
    expect(rows[0]!.querySelector('.stats-chart-row-value')!.textContent).toBe('9');
    expect(rows[1]!.querySelector('.stats-chart-row-label')!.textContent).toMatch(/^Not Passing/);
    expect(rows[1]!.querySelector('.stats-chart-row-value')!.textContent).toBe('1');
  });

  it('carries an accessible legend pairing each swatch with a series NAME', async () => {
    const { container } = await renderReport(verificationReportOk);
    const legend = container.querySelector('.stats-chart-legend');
    expect(legend).not.toBeNull();
    const labels = Array.from(legend!.querySelectorAll('.stats-chart-legend-label')).map(
      (node) => node.textContent,
    );
    expect(labels).toEqual(['Passing', 'Not Passing']);
    // The swatch itself carries nothing a reader needs.
    legend!.querySelectorAll('.stats-chart-swatch').forEach((swatch) => {
      expect(swatch).toHaveAttribute('aria-hidden', 'true');
    });
  });

  it('carries a textual summary naming both denominators separately', async () => {
    await renderReport(verificationReportOk);
    const summaries = screen.getAllByText(
      /Official Validation: 9 of 10 records passing, 1 not passing; Format Shadow: 6 of 10 records passing, 4 not passing\./,
    );
    expect(summaries.length).toBeGreaterThan(0);
    expect(bodyText()).toMatch(/counted against its own total/i);
  });

  it('carries a data-table alternative with all four figures', async () => {
    const { container } = await renderReport(verificationReportOk);
    const table = Array.from(container.querySelectorAll('table.stats-chart-table')).find(
      (node) => node.querySelector('th[scope="row"]')?.textContent === 'Official Validation',
    );
    expect(table).toBeDefined();
    const headers = Array.from(table!.querySelectorAll('thead th')).map((n) => n.textContent);
    expect(headers).toEqual(['Validator', 'Passing', 'Not Passing', 'Records Counted']);
    const rows = Array.from(table!.querySelectorAll('tbody tr')).map((row) =>
      Array.from(row.querySelectorAll('th,td')).map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ['Official Validation', '9', '1', '10'],
      ['Format Shadow', '6', '4', '10'],
    ]);
  });

  it('never states a total spanning both validators', async () => {
    await renderReport(verificationReportOk);
    // 9 + 1 + 6 + 4 = 20 records would be the fabricated whole.
    expect(bodyText()).not.toMatch(/\b20 records\b/);
    expect(bodyText()).toMatch(/never added together/i);
  });

  it('says the shadow decides nothing, so its stricter verdict cannot read as validity', async () => {
    await renderReport(verificationReportOk);
    expect(bodyText()).toMatch(/never make a record invalid/i);
    expect(bodyText()).toMatch(/gates nothing/i);
  });
});

/* ============================================== 5 · mutation accounting ==== */

describe('mutation verification', () => {
  it('shows every one of the seven mutation counts', async () => {
    await renderReport(verificationReportOk);
    const mutations = verificationReportOk.mutations;
    for (const key of VERIFICATION_MUTATION_KEYS) {
      expect(String(mutations[key]).length).toBeGreaterThan(0);
    }
    // Each figure appears under a plain-word label in a real definition list.
    for (const label of [
      'Change Types Defined',
      'Trials Attempted',
      'Trials That Applied',
      'Trials Skipped as Not Applicable',
      'Trials That Behaved as Designed',
      'Trials That Behaved Unexpectedly',
      'Trials Recorded Without an Expected Outcome',
    ]) {
      expect(screen.getByText(label).closest('dl')).not.toBeNull();
    }
  });

  it('shows all seven harness self-check counts', async () => {
    await renderReport(verificationReportOk);
    expect(VERIFICATION_ORACLE_KEYS).toHaveLength(7);
    for (const label of [
      'Source Records Altered by the Run',
      'Records Not Restored After a Trial',
      'Repeat Runs That Disagreed',
      'Results That Depended on Order',
      'No-Guessing Breaches',
      'Workflow Inconsistencies',
      'Validation Engine Disagreements',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('shows both accounting identities RECONCILING on screen', async () => {
    await renderReport(verificationReportOk);
    expect(
      screen.getByText('170 trials attempted = 134 trials that applied + 36 trials skipped as not applicable'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        '134 trials that applied = 128 trials that behaved as designed + 0 trials that behaved unexpectedly + 6 trials recorded without an expected outcome',
      ),
    ).toBeInTheDocument();
    expect(bodyText()).toMatch(/accounted for exactly once/i);
  });

  it('prints the BACKEND’S OWN field names beside the words, so the two cannot drift', async () => {
    await renderReport(verificationReportOk);
    expect(
      screen.getByText('trials_attempted = trials_applicable + trials_skipped_not_applicable'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'trials_applicable = expected_outcome_matches + unexpected_outcomes + observation_only_trials',
      ),
    ).toBeInTheDocument();
  });

  it('says so out loud when the counts do NOT add up, instead of drawing a tidy total', async () => {
    const { container } = await renderReport(verificationReportUnbalancedMutations);
    expect(bodyText()).toMatch(/do not account for every trial exactly once/i);
    expect(bodyText()).toMatch(/the parts total 137, and the report states 134 trials that applied/i);
    const broken = container.querySelector('.stats-verify-identity[data-balances="false"]');
    expect(broken).not.toBeNull();
    // The identity that DOES hold is not tarred with it.
    expect(container.querySelector('.stats-verify-identity[data-balances="true"]')).not.toBeNull();
  });

  it('keeps the balanced case free of any mismatch copy', async () => {
    const { container } = await renderReport(verificationReportOk);
    expect(container.querySelector('.stats-verify-identity[data-balances="false"]')).toBeNull();
    expect(bodyText()).not.toMatch(/do not account for every trial/i);
  });

  it('separates good news from bad news rather than listing seven alike counts', async () => {
    const { container } = await renderReport(verificationReportOk);
    const tones = Array.from(container.querySelectorAll('.stats-verify-group')).map((node) =>
      node.getAttribute('data-tone'),
    );
    // Neutral coverage, affirmative expected, affirmative-when-zero unexpected.
    expect(new Set(tones).size).toBeGreaterThan(1);
    expect(bodyText()).toMatch(/0 is the expected reading/i);
  });

  it('makes NO flat claim that the source records were left unchanged', async () => {
    /*
     * The copy read "The records themselves are never altered." — and this same
     * panel can say otherwise. With `source_mutation_failures: 5` and
     * `source_records_modified: 'unverified'`, all four of these rendered at
     * once: that sentence, "Source Records Altered by the Run → 5", "Source
     * Records Left Unchanged → Unverified", and "This check did not run, so
     * nothing here states that it holds."
     *
     * The design intent may be stated; the OUTCOME belongs to the measurement.
     */
    await renderReport(verificationReportSourceRecordsAltered);

    expect(bodyText()).not.toContain('The records themselves are never altered');
    expect(bodyText()).not.toMatch(/records[^.]{0,40}\bnever altered\b/i);
    expect(bodyText()).not.toMatch(/source records were (left )?unchanged\./i);

    // What IS said: the design, plus a pointer to the measurement.
    expect(bodyText()).toMatch(/each trial works on a copy of one record/i);
    expect(bodyText()).toMatch(/reported below rather than promised here/i);

    // …and the contradicting measurements are all still on screen.
    expect(screen.getByText('Source Records Altered by the Run')).toBeInTheDocument();
    const altered = screen
      .getByText('Source Records Altered by the Run')
      .closest('.stats-figure');
    expect(altered!.querySelector('dd')!.textContent).toBe('5');
    const safeguard = screen
      .getByText(SAFEGUARD_LABELS.source_records_modified)
      .closest('.stats-verify-safeguard');
    expect(safeguard!.querySelector('.stats-verify-state')!.textContent).toBe('Unverified');
  });

  it('makes no flat unchanged-claim in the CALM case either', async () => {
    // The sentence is scoped by construction, not switched on the data — a copy
    // that only tells the truth when the news is bad is still a copy that can
    // state a fact it did not measure.
    await renderReport(verificationReportOk);
    expect(bodyText()).not.toMatch(/\bnever altered\b/i);
    expect(bodyText()).toMatch(/reported below rather than promised here/i);
  });

  it('prints the wire field beside every mutation and self-check figure', async () => {
    // `operators_defined` is the one mutation count neither accounting identity
    // uses, so without this it was reachable on screen only as a renamed label.
    const { container } = await renderReport(verificationReportOk);
    const hints = Array.from(container.querySelectorAll('.stats-figure-hint')).map(
      (n) => n.textContent,
    );
    for (const key of VERIFICATION_MUTATION_KEYS) expect(hints).toContain(key);
    for (const key of VERIFICATION_ORACLE_KEYS) expect(hints).toContain(key);
    expect(hints).toContain('dml_statements');
    expect(hints).toContain('ddl_statements');
    // The plain-word label is still its own element, so it is what a reader —
    // and a query for it — actually gets.
    expect(screen.getByText('Change Types Defined')).toHaveClass('stats-figure-label');
  });

  it('flags a tripped self-check rather than folding it into the calm sentence', async () => {
    await renderReport(verificationReportWithFindings);
    expect(bodyText()).toMatch(/2 trials tripped a check on the run itself/i);
  });
});

/* ============================================ 6 · privacy distributions ==== */

describe('the privacy-protected distributions', () => {
  it('draws both breakdowns as horizontal bar charts', async () => {
    const { container } = await renderReport(verificationReportOk);
    const captions = Array.from(container.querySelectorAll('.stats-chart-caption')).map(
      (n) => n.textContent,
    );
    expect(captions).toContain('Format issues by check name');
    expect(captions).toContain('Format issues by position in the ISAAC schema');
  });

  it('draws the WITHHELD bucket as its own bar, carrying the withheld occurrences', async () => {
    const { container } = await renderReport(verificationReportOk);
    const labels = Array.from(container.querySelectorAll('.stats-chart-row-label')).map(
      (n) => n.textContent,
    );
    expect(labels).toContain(SUPPRESSED_ROW_LABEL);
    expect(SUPPRESSED_ROW_LABEL).toBe('Withheld (categories below the disclosure floor)');

    const withheldRow = Array.from(container.querySelectorAll('.stats-chart-row')).find(
      (row) => row.querySelector('.stats-chart-row-label')?.textContent === SUPPRESSED_ROW_LABEL,
    );
    expect(withheldRow).toBeDefined();
    // 7 occurrences in the error-code histogram.
    expect(withheldRow!.querySelector('.stats-chart-row-value')!.textContent).toBe('7');
  });

  it('discloses HOW MANY categories were withheld and why, in visible copy', async () => {
    await renderReport(verificationReportOk);
    expect(bodyText()).toMatch(
      /3 further categories are withheld, each occurring fewer than 5 times, accounting for 7 of the 28 occurrences counted/i,
    );
    expect(bodyText()).toMatch(/none of them is named here, because their names are not in the report/i);
  });

  it('never renders a withheld category NAME, because the payload has none', async () => {
    const { container } = await renderReport(verificationReportOk);
    const labels = Array.from(container.querySelectorAll('.stats-chart-row-label')).map(
      (n) => n.textContent ?? '',
    );
    // Every drawn label is either a category the report actually sent, or the
    // one aggregate bucket. Nothing else can appear.
    const sent = new Set<string>([
      ...verificationReportOk.format_shadow.failures_by_error_code.cells.map((c) => c.key),
      ...verificationReportOk.format_shadow.failures_by_schema_path.cells.map((c) => c.key),
      'Passing',
      'Not Passing',
      SUPPRESSED_ROW_LABEL,
    ]);
    for (const label of labels) {
      const bare = label.replace(/\s·\s\d+%$/, '');
      expect(sent.has(bare), `unexpected drawn label: ${label}`).toBe(true);
    }
    expect(bodyText()).not.toContain('suppressed_categories');
    expect(bodyText()).not.toContain('__withheld__');
  });

  it('draws the withheld bucket even when it accounts for NO occurrences', async () => {
    // The body the chart's empty branch and the row builder used to disagree
    // about. Omitting the row would say the three categories were never
    // withheld; the disclosure sentence states the categories separately.
    const { container } = await renderReport(verificationReportWithheldButEmpty);
    const chart = Array.from(container.querySelectorAll('figure.stats-chart')).find(
      (figure) =>
        figure.querySelector('.stats-chart-caption')?.textContent ===
        'Format issues by check name',
    );
    expect(chart).toBeDefined();
    const labels = Array.from(chart!.querySelectorAll('.stats-chart-row-label')).map(
      (n) => n.textContent,
    );
    expect(labels).toEqual([SUPPRESSED_ROW_LABEL]);
    expect(chart!.textContent).toMatch(/3 further categories are withheld/i);
  });

  it('draws no withheld bucket when nothing was withheld', async () => {
    const { container } = await renderReport(verificationReportNoSuppression);
    const errorCodeChart = Array.from(container.querySelectorAll('figure.stats-chart')).find(
      (figure) =>
        figure.querySelector('.stats-chart-caption')?.textContent ===
        'Format issues by check name',
    );
    expect(errorCodeChart).toBeDefined();
    const labels = Array.from(errorCodeChart!.querySelectorAll('.stats-chart-row-label')).map(
      (n) => n.textContent,
    );
    expect(labels).toEqual(['format']);
    expect(errorCodeChart!.textContent).not.toMatch(/withheld/i);
  });

  it('carries a textual summary and a data table for each distribution', async () => {
    const { container } = await renderReport(verificationReportOk);
    const figure = Array.from(container.querySelectorAll('figure.stats-chart')).find(
      (node) =>
        node.querySelector('.stats-chart-caption')?.textContent ===
        'Format issues by position in the ISAAC schema',
    );
    expect(figure).toBeDefined();
    expect(figure!.querySelector('p.sr-only')?.textContent).toMatch(/occurrences/);
    const table = figure!.querySelector('table.stats-chart-table');
    expect(table).not.toBeNull();
    const rowHeaders = Array.from(table!.querySelectorAll('tbody th')).map((n) => n.textContent);
    expect(rowHeaders).toEqual([
      'properties/dataset/properties/created',
      'properties/measurement/properties/uri',
      SUPPRESSED_ROW_LABEL,
    ]);
  });

  it('renders a long schema path whole, in a container that may wrap it', async () => {
    const { container } = await renderReport(verificationReportOk);
    const label = Array.from(container.querySelectorAll('.stats-chart-row-label')).find(
      (n) => n.textContent === 'properties/dataset/properties/created',
    );
    // Not truncated with an ellipsis, and not abbreviated: the whole path is the
    // text node, so a narrow column wraps it rather than hiding its tail.
    expect(label).toBeDefined();
    expect(label!.textContent).toBe('properties/dataset/properties/created');
    expect(label!.textContent).not.toMatch(/…|\.\.\./);
  });

  it('says the schema positions are places in the schema, not places in a record', async () => {
    await renderReport(verificationReportOk);
    expect(bodyText()).toMatch(/places in the ISAAC schema, not places inside any record/i);
  });
});

/* ================================================== 7 · safeguards ========= */

describe('the safeguards panel', () => {
  it('renders not_applicable with its own word, never as verified', async () => {
    await renderReport(verificationReportOk);

    const label = screen.getByText(SAFEGUARD_LABELS.transaction_read_only);
    const row = label.closest('.stats-verify-safeguard');
    expect(row).not.toBeNull();

    const state = row!.querySelector('.stats-verify-state');
    expect(state).not.toBeNull();
    expect(state!.getAttribute('data-state')).toBe('not_applicable');
    expect(state!.textContent).toBe(SAFEGUARD_STATE_LABELS.not_applicable);
    expect(state!.textContent).not.toMatch(/verified/i);
  });

  it('tones not_applicable NEUTRALLY — never with the affirmative treatment', async () => {
    await renderReport(verificationReportOk);
    const row = screen
      .getByText(SAFEGUARD_LABELS.transaction_read_only)
      .closest('.stats-verify-safeguard');
    expect(row!.getAttribute('data-tone')).toBe('neutral');
    expect(row!.getAttribute('data-tone')).not.toBe('good');
  });

  it('gives each of the three states a distinct word', () => {
    // Pinned as literals, not read back from the module under test.
    expect(SAFEGUARD_STATE_LABELS.verified).toBe('Verified');
    expect(SAFEGUARD_STATE_LABELS.not_applicable).toBe('Not applicable');
    expect(SAFEGUARD_STATE_LABELS.unverified).toBe('Unverified');
    const labels = Object.values(SAFEGUARD_STATE_LABELS);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it('renders all three words on one screen when the report carries all three', async () => {
    await renderReport(verificationReportWithFindings);
    const words = new Set(
      Array.from(document.querySelectorAll('.stats-verify-state')).map((n) => n.textContent),
    );
    expect(words.has('Verified')).toBe(true);
    expect(words.has('Not applicable')).toBe(true);
    expect(words.has('Unverified')).toBe(true);
  });

  it('does not carry meaning by colour alone', async () => {
    await renderReport(verificationReportOk);
    const states = document.querySelectorAll('.stats-verify-state');
    expect(states.length).toBe(6);
    states.forEach((node) => {
      expect(node.textContent?.trim()).not.toBe('');
    });
    // …and every row states its reason in a sentence as well.
    document.querySelectorAll('.stats-verify-safeguard').forEach((row) => {
      expect(row.querySelector('.stats-verify-safeguard-detail')?.textContent?.trim()).toBeTruthy();
    });
  });

  it('gives not_applicable a REASON, so "skipped" and "never arose" are not conflated', async () => {
    await renderReport(verificationReportOk);
    const row = screen
      .getByText(SAFEGUARD_LABELS.transaction_read_only)
      .closest('.stats-verify-safeguard');
    expect(row!.querySelector('.stats-verify-safeguard-detail')!.textContent).toBe(
      'Not applicable — this run did not open a database connection.',
    );
  });

  it('reads the database safeguards as verified in the mode that opens a connection', async () => {
    await renderReport(verificationReportPrivateSample);
    const row = screen
      .getByText(SAFEGUARD_LABELS.transaction_read_only)
      .closest('.stats-verify-safeguard');
    expect(row!.querySelector('.stats-verify-state')!.getAttribute('data-state')).toBe('verified');
  });

  it('carries no tick glyph anywhere, which is how "verified" gets read back in', async () => {
    const { container } = await renderReport(verificationReportOk);
    const panel = container.querySelector('.stats-verify-safeguards');
    expect(panel).not.toBeNull();
    expect(panel!.querySelectorAll('svg')).toHaveLength(0);
    expect(panel!.textContent).not.toMatch(/[✓✔☑]/);
  });

  it('surfaces a degraded safeguard instead of normalising it', async () => {
    await renderReport(verificationReportWithFindings);
    const states = Array.from(document.querySelectorAll('.stats-verify-state'));
    const degraded = states.filter((n) => n.getAttribute('data-state') === 'unverified');
    expect(degraded.length).toBeGreaterThan(0);
  });

  it('reports a nonzero DML count as attention rather than hiding it', async () => {
    await renderReport(verificationReportWithFindings);
    expect(screen.getByText(/counted at least one statement/i)).toBeTruthy();
  });

  it('says the run counted no data-changing statement when both counts are zero', async () => {
    await renderReport(verificationReportOk);
    expect(screen.getByText(/counted no statement/i)).toBeTruthy();
  });

  it('renders NO safeguard row for any state that is not a report', async () => {
    for (const envelope of [
      verificationRunningEnvelope,
      verificationFailureEnvelope,
      verificationRefusedEnvelope,
      verificationErrorEnvelope,
      verificationFutureFormat,
    ]) {
      const { unmount } = await renderReport(envelope);
      expect(document.querySelectorAll('.stats-verify-state')).toHaveLength(0);
      unmount();
    }
  });
});

/* ================================================ 8 · what must never appear */

describe('what must never appear', () => {
  it('renders no record identifier, title, hostname, credential or connection string', async () => {
    for (const body of [verificationReportOk, verificationReportPrivateSample]) {
      const { unmount } = await renderReport(body);
      const text = bodyText();
      for (const forbidden of [
        'record_id',
        'postgres://',
        'postgresql://',
        'PGHOST',
        'PGPASSWORD',
        'password',
        'localhost',
        'isaac-psql',
        'metadata_assistant',
        'metadata-assistant-db-app',
        '5432',
      ]) {
        expect(text, `${forbidden} must never be rendered`).not.toContain(forbidden);
      }
      unmount();
    }
  });

  it('states no per-record outcome, because the report carries none', async () => {
    await renderReport(verificationReportPrivateSample);
    expect(bodyText()).not.toMatch(/\brecord \d+\b/i);
    expect(bodyText()).not.toMatch(/\b01[0-9A-HJKMNP-TV-Z]{24}\b/); // a ULID
  });

  it('never substitutes a zero for a block that did not arrive', async () => {
    for (const envelope of [
      verificationRunningEnvelope,
      verificationFailureEnvelope,
      verificationRefusedEnvelope,
      verificationErrorEnvelope,
    ]) {
      const { unmount } = await renderReport(envelope);
      expect(document.querySelectorAll('.stat-card')).toHaveLength(0);
      expect(document.querySelectorAll('.stats-figure')).toHaveLength(0);
      expect(bodyText()).not.toMatch(/\b0 of 0\b/);
      unmount();
    }
  });

  it('never renders a CLI transcript or an exit code', async () => {
    await renderReport(verificationReportOk);
    // `VerdictCard` shipped `isaac validate --official · exit N` for a command
    // that was never run. No command is run here either.
    expect(bodyText()).not.toMatch(/exit \d/i);
    expect(bodyText()).not.toMatch(/isaac validate/i);
  });
});

/* ==================================================== 9 · My Stats ========= */

describe('My Stats stays truthfully empty', () => {
  function renderMine() {
    return render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyStats />
      </MemoryRouter>,
    );
  }

  it('states the one sentence that says what would fill it, and when', () => {
    renderMine();
    expect(
      screen.getByText(
        /Personal statistics will appear here once experiments are associated with your signed-in account\./,
      ),
    ).toBeInTheDocument();
  });

  it('renders no figure — no stat card, no chart, no data table', () => {
    const { container } = renderMine();
    expect(container.querySelectorAll('.stat-card')).toHaveLength(0);
    expect(container.querySelectorAll('figure.stats-chart')).toHaveLength(0);
    expect(container.querySelectorAll('table')).toHaveLength(0);
    expect(container.querySelectorAll('.stats-figures')).toHaveLength(0);
  });

  it('renders no fake zero, in digits or in words, and says absence is not zero', () => {
    const { container } = renderMine();
    expect(container.textContent).not.toMatch(/\b0\b/);
    expect(container.textContent).toMatch(/none of the figures below are zero — they are absent/i);
  });

  it('names no portal, database or cross-user metric', () => {
    const { container } = renderMine();
    const text = container.textContent ?? '';
    for (const forbidden of [/\bportal\b/i, /\bdatabase\b/i, /\bother users\b/i, /\bacross users\b/i]) {
      expect(text).not.toMatch(forbidden);
    }
  });

  it('displays no identity — no name, email, uid or group from any header', () => {
    const { container } = renderMine();
    const text = container.textContent ?? '';
    for (const forbidden of [/signed in as/i, /@[a-z0-9.-]+\.[a-z]{2,}/i, /X-authentik/i]) {
      expect(text).not.toMatch(forbidden);
    }
  });

  it('presents no workspace count as a personal one', () => {
    const { container } = renderMine();
    const text = container.textContent ?? '';
    // The workspace figures' own labels. A relabelled workspace count is the
    // cheapest possible false personal claim, so none of their names appears.
    //
    // NOT a ban on the word "export": one PLANNED view is named "Export
    // Readiness Over Time" and describes what it would count. That is a
    // description of an absent view, not a figure — the fake-zero test above is
    // what pins that nothing is being counted.
    for (const label of ['Total Records', 'Need Attention', 'Ready to Export', 'Stale Artifacts']) {
      expect(text, `${label} is a workspace figure and must not appear here`).not.toContain(label);
    }
  });
});

/* ================================================== 10 · accessibility ===== */

describe('accessibility of the rendered section', () => {
  /**
   * A STRUCTURAL scan, deliberately narrowed to the rules jsdom can decide.
   *
   * Colour-contrast is excluded because jsdom resolves no backgrounds — the
   * ratios for this surface are computed from the stylesheet and the token file
   * in `stats-charts.test.tsx`, which is the honest way to check them without a
   * browser. What is checked here is what this section actually authored:
   * whether every control has a name, whether the lists and definition lists it
   * builds are well-formed, and whether the tables it renders have headers.
   */
  async function structuralViolations(container: HTMLElement): Promise<string[]> {
    const results = await axe.run(container, {
      runOnly: {
        type: 'rule',
        values: [
          'button-name',
          'definition-list',
          'dlitem',
          'list',
          'listitem',
          'aria-required-children',
          'aria-required-parent',
          'aria-valid-attr-value',
          'td-headers-attr',
          'th-has-data-cells',
          'empty-table-header',
          'table-fake-caption',
        ],
      },
      resultTypes: ['violations'],
    });
    return results.violations.map((v) => `${v.id} × ${v.nodes.length}`);
  }

  it('the scanner is proven on a defect — an unnamed control fails it', async () => {
    // A guard nobody has watched fail is not a guard. jsdom is a limited
    // environment and an axe run that silently decides nothing would make every
    // assertion below vacuous.
    const { container } = render(
      <div>
        <button type="button" />
      </div>,
    );
    expect(await structuralViolations(container)).toEqual(['button-name × 1']);
  });

  it('reports no structural violation with a full report on screen', async () => {
    const { container } = await renderReport(verificationReportOk);
    expect(await structuralViolations(container)).toEqual([]);
  });

  it('reports no structural violation in the states that draw no figure', async () => {
    for (const envelope of [
      verificationRunningEnvelope,
      verificationFailureEnvelope,
      verificationFutureFormat,
    ]) {
      const { container, unmount } = await renderReport(envelope);
      expect(await structuralViolations(container)).toEqual([]);
      unmount();
    }
  });

  it('gives the transport-failure state a named control too', async () => {
    const { container } = render(
      <Section read={() => Promise.reject(new Error('down'))} />,
    );
    await settled();
    expect(await structuralViolations(container)).toEqual([]);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('hides every drawn mark from assistive technology, and states it in text instead', async () => {
    const { container } = await renderReport(verificationReportOk);
    container.querySelectorAll('svg').forEach((svg) => {
      expect(svg).toHaveAttribute('aria-hidden', 'true');
    });
    // …and every figure carries a real sentence AND a real table.
    const figures = container.querySelectorAll('figure.stats-chart');
    expect(figures.length).toBeGreaterThan(0);
    figures.forEach((figure) => {
      expect(figure.querySelector('figcaption')?.textContent?.trim()).toBeTruthy();
      expect(figure.querySelector('p.sr-only')?.textContent?.trim()).toBeTruthy();
      expect(figure.querySelector('table.stats-chart-table')).not.toBeNull();
    });
  });

  it('states every figure as a labelled definition list, never as bare numbers', async () => {
    const { container } = await renderReport(verificationReportOk);
    container.querySelectorAll('.stats-figure').forEach((row) => {
      expect(row.querySelector('dt')?.textContent?.trim()).toBeTruthy();
      expect(row.closest('dl')).not.toBeNull();
    });
  });

  it('animates nothing, so the reduced-motion rendering is the only rendering', async () => {
    const css = String((await import('../screens/statistics/statistics.css?raw')).default);
    const section = css.slice(css.indexOf('.statistics .stats-verify-corpus'));
    expect(section).not.toMatch(/\btransition\b/);
    expect(section).not.toMatch(/\banimation\b/);
    expect(section).not.toMatch(/@keyframes/);
  });

  it('lets long schema paths and long tokens wrap rather than overflow', async () => {
    const css = String((await import('../screens/statistics/statistics.css?raw')).default);
    for (const selector of [
      '.statistics .stats-verify-corpus-label',
      '.statistics .stats-verify-corpus-mode',
      '.statistics .stats-verify-identity-statement',
      '.statistics .stats-verify-identity-keys',
      '.statistics .stats-chart-row-label',
    ]) {
      const start = css.indexOf(selector);
      expect(start, `${selector} must be declared`).toBeGreaterThan(-1);
      const block = css.slice(start, css.indexOf('}', start));
      expect(block, `${selector} must wrap`).toMatch(/overflow-wrap:\s*anywhere/);
    }
  });

  it('collapses the safeguard grid to one column on a narrow viewport', async () => {
    const css = String((await import('../screens/statistics/statistics.css?raw')).default);
    expect(css).toMatch(
      /@media \(max-width: 900px\) \{\s*\.statistics \.stats-verify-safeguards \{\s*grid-template-columns: minmax\(0, 1fr\);/,
    );
  });

  it('lets the control row wrap, so the button and its status never collide', async () => {
    const css = String((await import('../screens/statistics/statistics.css?raw')).default);
    const start = css.indexOf('.statistics .stats-verify-controls-row');
    const block = css.slice(start, css.indexOf('}', start));
    expect(block).toMatch(/flex-wrap:\s*wrap/);
  });
});
