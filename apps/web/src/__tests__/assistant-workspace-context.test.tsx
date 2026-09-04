/**
 * PR-E — the Assistant panel's workspace-context lead sentence
 * ("You are on Runs."). Reuses `RECORD_WORKSPACES`' own label copy
 * (`components/RecordWorkspaceNav.tsx`) — no new backend intent, no new
 * copy. Passed only by `RecordWorkbench`; every other mount omits it.
 *
 * HONESTY ABOUT WHAT IS PROVEN HERE, matching this repository's own
 * convention for this file family: RENDERED DOM/props behaviour only — no
 * pixel measurement.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { clearAllSessions } from '../lib/assistantSession';
import type { AssistantMessage, SuggestedPrompt } from '../lib/types';

const REPLY: AssistantMessage = { text: '', answeredFrom: 'workflow' };
const PROMPTS: SuggestedPrompt[] = [];

afterEach(() => {
  cleanup();
  clearAllSessions();
});

describe("PR-E · AssistantPanel's workspace-context lead sentence", () => {
  it('renders nothing when omitted (every non-record mount is unaffected)', () => {
    const { container } = render(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId="exp-a" />,
    );
    expect(container.querySelector('.assistant-workspace-context')).toBeNull();
  });

  it('renders "You are on <label>." when passed, using the SAME label text passed in — no re-derivation', () => {
    const { container } = render(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId="exp-b" workspaceContext="Runs" />,
    );
    const el = container.querySelector('.assistant-workspace-context');
    expect(el).not.toBeNull();
    expect(el!.textContent).toBe('You are on Runs.');
    expect(el!.querySelector('strong')?.textContent).toBe('Runs');
  });

  it('re-renders the lead sentence on a workspace switch WITHOUT resetting the composer text (same mount, new prop)', () => {
    const { container, rerender, getByLabelText } = render(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId="exp-c" workspaceContext="Record Fields" />,
    );
    expect(container.querySelector('.assistant-workspace-context')!.textContent).toBe(
      'You are on Record Fields.',
    );

    const composer = getByLabelText('Ask the assistant a question') as HTMLInputElement;
    fireEvent.change(composer, { target: { value: 'Draft question in progress' } });
    expect(composer.value).toBe('Draft question in progress');

    rerender(
      <AssistantPanel reply={REPLY} prompts={PROMPTS} experimentId="exp-c" workspaceContext="Runs" />,
    );

    expect(container.querySelector('.assistant-workspace-context')!.textContent).toBe(
      'You are on Runs.',
    );
    // Same experimentId (same session key) across the switch — the conversation
    // session is keyed by experimentId, not by workspace, so switching
    // workspaces on the same record must not touch it. The composer element
    // itself stays the same node (no remount) with its typed value intact.
    const composerAfter = getByLabelText('Ask the assistant a question') as HTMLInputElement;
    expect(composerAfter).toBe(composer);
    expect(composerAfter.value).toBe('Draft question in progress');
  });

  /*
   * M-7 (independent review, 2026-09-03) — RETITLED AND GIVEN A REAL NEGATIVE
   * CONTROL. The previous version of this test was titled as a proof that
   * "no intent catalog lookup" happens, but its body only repeated the same
   * POSITIVE assertion the test above already makes (a real workspace label
   * renders as itself) — that cannot distinguish "the string is echoed
   * verbatim" from "the string happens to also be a valid catalog entry
   * that resolves to itself". The actual proof is a string NO catalog would
   * recognise: if `AssistantPanel` validated `workspaceContext` against
   * `RECORD_WORKSPACES` or any intent registry, an unrecognised value would
   * be dropped, replaced with a fallback, or would throw — not rendered
   * verbatim.
   */
  it('renders an UNRECOGNISED workspace-context string verbatim — proof there is no catalog lookup, not merely a repeated positive case', () => {
    const NOT_A_REAL_WORKSPACE = 'Not A Real Workspace Name — 🜂 test-only string';
    const { container } = render(
      <AssistantPanel
        reply={REPLY}
        prompts={PROMPTS}
        experimentId="exp-d"
        workspaceContext={NOT_A_REAL_WORKSPACE}
      />,
    );
    const el = container.querySelector('.assistant-workspace-context');
    expect(el).not.toBeNull();
    expect(el!.textContent).toBe(`You are on ${NOT_A_REAL_WORKSPACE}.`);
    expect(el!.querySelector('strong')?.textContent).toBe(NOT_A_REAL_WORKSPACE);
  });
});
