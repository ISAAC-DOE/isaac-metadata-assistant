/**
 * A CHECK FINDING IS A STRUCTURED ROW — subject, state, the server's own
 * sentence, and a destination only when one exists.
 *
 * The project owner, 2026-09-15, looking at `Check Failed` on the Runs screen:
 * *"I don't even know what it's asking. What does it mean? I think you should
 * point to the specific field that it's talking about … it should be simple.
 * And if they want more information, then they can ask the agent — there could
 * be a button right next to it that points to the agent, and then the agent
 * will have the context."*
 *
 * WHAT THESE TESTS PROTECT, and every one of them is a claim this build could
 * get wrong in the direction of saying more than it knows:
 *
 *   1. A subject is READ, never inferred. `kind` is optional on the wire and
 *      `ApiRunCheckFinding`'s own docstring says so: "a reader groups by it
 *      when it is there and says nothing when it is not".
 *   2. The server's sentence is verbatim.
 *   3. A finding this build cannot describe is still COUNTED and still SHOWN —
 *      the behaviour that exists because it was got wrong once.
 *   4. `Go to field` appears only where the field is actually on screen.
 *   5. `Ask ISAAC` PRE-FILLS and never sends.
 */
import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';

import { FindingList } from '../components/RunFindingList';
import { AssistantAskContext } from '../lib/assistantAsk';

afterEach(cleanup);

const rows = () => Array.from(document.querySelectorAll('.run-check-item')) as HTMLElement[];

describe('a finding row says what it is about, and nothing more', () => {
  it('names the subject from the server’s own `kind`, through the ONE vocabulary', () => {
    render(
      <FindingList
        title="Blocking"
        state="Missing"
        findings={[
          { kind: 'series', message: 'Provide/point to the reduced spectrum.' },
          { kind: 'qc', message: 'What is the QC verdict for this measurement?' },
        ]}
      />,
    );
    // `adapt.KIND_LABEL`'s words, not a second copy of them.
    expect(within(rows()[0]).getByText('Reduced Spectrum')).toBeTruthy();
    expect(within(rows()[1]).getByText('QC Verdict')).toBeTruthy();
    // The state word the CALLER supplied, once per row.
    expect(rows()[0].querySelector('.run-check-item-state')?.textContent).toBe('Missing');
    // And the server's sentence, verbatim.
    expect(rows()[0].textContent).toContain('Provide/point to the reduced spectrum.');
  });

  it('MUTATION-GUARDED: a finding with NO kind gets no subject line at all', () => {
    /*
     * MUTATION: falling back to `titleCase(String(kind))` (which is what
     * `pendingItemToBlocker` correctly does for a form it is about to render)
     * makes this RED — and produces "Undefined" or, for `qc`, the measured
     * "Qc". A subject line is a claim about what a finding is ABOUT, so an
     * absent kind must produce silence rather than a guess.
     */
    render(
      <FindingList
        title="Blocking"
        state="Missing"
        findings={[{ message: 'A blocking question is open on this run.' }]}
      />,
    );
    expect(rows()).toHaveLength(1);
    expect(rows()[0].querySelector('.run-check-item-subject')).toBeNull();
    expect(rows()[0].textContent).toContain('A blocking question is open on this run.');
  });

  it('MUTATION-GUARDED: an unrecognised kind is not humanised into a subject', () => {
    /* MUTATION: `KIND_LABEL[kind] ?? titleCase(kind)` in `blockerKindLabel`
       makes this RED with "Spectrometer Drift" — a name no server ever sent. */
    render(
      <FindingList
        title="Blocking"
        state="Missing"
        findings={[{ kind: 'spectrometer_drift', message: 'Something new.' }]}
      />,
    );
    expect(rows()[0].querySelector('.run-check-item-subject')).toBeNull();
  });

  it('falls back to the official PATH, in mono, when there is no kind', () => {
    render(
      <FindingList
        title="Draft checks"
        state="Needs Review"
        findings={[{ path: 'context.temperature_K', message: 'no evidence' }]}
      />,
    );
    const subject = rows()[0].querySelector('.run-check-item-subject') as HTMLElement;
    expect(subject.textContent).toBe('context.temperature_K');
    // `UX-014` — a schema path is demoted, never removed, and never re-worded.
    expect(subject.className).toContain('mono');
  });

  it('does not print the path twice when the path IS the whole finding', () => {
    /* `runFindingText` falls back to `path` when there is no prose, so a subject
       line here would be the same six words stacked on themselves. */
    render(
      <FindingList title="Draft checks" state="Needs Review" findings={[{ path: 'descriptors' }]} />,
    );
    expect(rows()[0].querySelector('.run-check-item-subject')).toBeNull();
    expect(rows()[0].textContent).toContain('descriptors');
  });

  it('MUTATION-GUARDED: a finding it cannot describe is still counted and still shown', () => {
    /* The behaviour that exists because it was got wrong once: dropping it
       silently shrinks the number of things standing between this run and a
       valid record. MUTATION: filtering `text === null` makes this RED twice. */
    render(<FindingList title="Blocking" state="Missing" findings={[{ code: 'SOMETHING_NEW' }] as never} />);
    expect(screen.getByText('Blocking · 1')).toBeTruthy();
    expect(
      screen.getByText('The server reported a finding this build cannot describe.'),
    ).toBeTruthy();
  });
});

describe('a control is offered only where its destination exists', () => {
  it('MUTATION-GUARDED: no Go to field button when the caller renders no inputs', () => {
    /*
     * `ValidateReview` is exactly this case — it shows a run's findings and
     * renders none of that run's inputs. MUTATION: rendering the button
     * unconditionally makes this RED, and ships a control that scrolls to
     * nothing or to another run's box.
     */
    render(
      <FindingList
        title="Draft checks"
        state="Needs Review"
        findings={[{ path: 'context.temperature_K', message: 'no evidence' }]}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Go to field' })).toBeNull();
  });

  it('offers Go to field for a run-level path, and calls back with that path', () => {
    const go = vi.fn();
    render(
      <FindingList
        title="Draft checks"
        state="Needs Review"
        findings={[{ path: 'context.temperature_K', message: 'no evidence' }]}
        onGoToField={go}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Go to field' }));
    expect(go).toHaveBeenCalledWith('context.temperature_K');
  });

  it('MUTATION-GUARDED: a path that is NOT one of the five offers nothing', () => {
    /*
     * MUTATION: matching by prefix — so `timestamps` resolves to
     * `timestamps.acquired_start_utc` — makes this RED. "The timestamps block
     * has a problem" and "this field has a problem" are different claims, and
     * only the server can tell them apart.
     */
    render(
      <FindingList
        title="Official schema"
        state="Invalid"
        findings={[
          { path: 'timestamps', message: "'acquired_start_utc' is required" },
          { path: 'descriptors', message: "'outputs' is a required property" },
        ]}
        onGoToField={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Go to field' })).toBeNull();
  });

  it('MUTATION-GUARDED: no Ask ISAAC control on a screen with no Assistant', () => {
    /* The context default is `null`, and a button that cannot reach a composer
       is a button that does nothing. MUTATION: rendering it regardless makes
       this RED. */
    render(
      <FindingList title="Blocking" state="Missing" findings={[{ kind: 'series', message: 'x' }]} />,
    );
    expect(screen.queryByRole('button', { name: /Ask ISAAC/ })).toBeNull();
  });
});

describe('Ask ISAAC composes the context and sends nothing', () => {
  const askWith = (findings: Parameters<typeof FindingList>[0]['findings']) => {
    const ask = vi.fn();
    render(
      <AssistantAskContext.Provider value={ask}>
        <FindingList
          title="Blocking"
          state="Missing"
          findings={findings}
          ask={{ experimentId: 'EXP1', runId: 'RUN7', runLabel: 'Run 7' }}
        />
      </AssistantAskContext.Provider>,
    );
    return ask;
  };

  it('carries the subject, the run, the record and the validator’s own words', () => {
    const ask = askWith([
      { kind: 'series', message: 'Provide/point to the reduced spectrum.' },
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'Ask ISAAC about Reduced Spectrum' }));
    expect(ask).toHaveBeenCalledTimes(1);
    const question = ask.mock.calls[0][0] as string;
    expect(question).toContain('Reduced Spectrum');
    expect(question).toContain('Run 7');
    expect(question).toContain('RUN7');
    expect(question).toContain('EXP1');
    // VERBATIM. The composed question quotes the validator; it never rewords it.
    expect(question).toContain('Provide/point to the reduced spectrum.');
  });

  it('MUTATION-GUARDED: it never invents a subject for an unnamed finding', () => {
    /* MUTATION: interpolating `finding.kind` unguarded puts "undefined" into a
       sentence a scientist is about to send. */
    const ask = askWith([{ message: 'A blocking question is open on this run.' }]);
    fireEvent.click(
      screen.getByRole('button', { name: 'Ask ISAAC about this missing finding' }),
    );
    const question = ask.mock.calls[0][0] as string;
    expect(question).not.toMatch(/undefined|null|\[object/i);
    expect(question).toContain('A blocking question is open on this run.');
  });

  it('each row’s control is distinguishable by name', () => {
    /* Six identical "Ask ISAAC" buttons in one list are six controls a
       screen-reader user cannot tell apart. */
    askWith([
      { kind: 'series', message: 'a' },
      { kind: 'descriptor', message: 'b' },
    ]);
    expect(screen.getByRole('button', { name: 'Ask ISAAC about Reduced Spectrum' })).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Ask ISAAC about Scientific Descriptor' }),
    ).toBeTruthy();
  });
});
