/*
 * A Suggested Question picked while a Confirm is still in flight must not be lost, and the earlier
 * turn must not be archived twice (review of the B-03 rewrite: `appendAgentMessage` read the live turn
 * from the click-time closure). The live turn is read from a ref refreshed every render.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, cleanup, fireEvent, render, within } from '@testing-library/react';
import { AssistantPanel } from '../components/AssistantPanel';
import { clearAllSessions, loadSession } from '../lib/assistantSession';
import type { AgentContext, Proposal } from '../lib/assistantAgent';
import type { SuggestedPrompt } from '../lib/types';

const EXP = '01EXPERIMENTA0000000000000';
const CTX: AgentContext = {
  experimentId: EXP,
  recordRev: 5,
  version: 'gen.5',
  workflow: {
    current_step: 'complete_metadata',
    ordered_steps: [
      { id: 'complete_metadata', label: 'Complete Metadata', state: 'current', current: true, reopened: false, blocked: false, reason: null },
    ],
  },
  evidence: [],
  pending: [{ id: 'series', label: 'Reduced Series' }],
} as AgentContext;
const PROMPTS: SuggestedPrompt[] = [
  { text: 'Question A?', answeredFrom: 'workflow', answer: { text: 'Answer A.', answeredFrom: 'workflow' } },
  { text: 'Question B?', answeredFrom: 'workflow', answer: { text: 'Answer B.', answeredFrom: 'workflow' } },
];
const proposal: Proposal = {
  id: 'p1', experimentId: EXP, field: 'series', value: 'series-42', origin: 'user', sourceRev: 5, confirmationState: 'pending',
} as Proposal;

beforeEach(() => clearAllSessions());
afterEach(() => { cleanup(); clearAllSessions(); });

describe('reviewer repro: a pill clicked while Confirm is in flight', () => {
  it('does not lose the pill answer or duplicate the earlier turn', async () => {
    let release!: (v: unknown) => void;
    const pending = new Promise((r) => { release = r; });
    const confirmApi = {
      submitAnswer: () => pending,
      editField: () => pending,
    };
    const view = render(
      <AssistantPanel
        reply={{ text: '', answeredFrom: 'workflow' }}
        prompts={PROMPTS}
        experimentId={EXP}
        recordRev={5}
        agentContext={CTX}
        agentPrompts={[]}
        proposal={proposal}
        confirmApi={confirmApi as never}
        onRefresh={() => {}}
      />,
    );
    const openCatalog = () => fireEvent.click(within(view.container).getByRole('button', { name: /What Can I Ask/i }));
    openCatalog();
    fireEvent.click(view.getByRole('button', { name: /Question A\?/ }));
    expect(view.container.querySelector('.assistant-reply')?.textContent).toContain('Answer A.');
    fireEvent.click(view.getByRole('button', { name: /^confirm$/i }));
    openCatalog();
    fireEvent.click(view.getByRole('button', { name: /Question B\?/ }));
    expect(view.container.querySelector('.assistant-reply')?.textContent).toContain('Answer B.');
    await act(async () => { release({ invalidation: { changed: true }, pending: [] }); await pending; await Promise.resolve(); await Promise.resolve(); });
    const texts = loadSession(EXP).messages.map((m) => `${m.role}:${m.text}`);
    const bAnywhere = texts.some((t) => t.includes('Answer B.')) || (view.container.querySelector('.assistant-reply')?.textContent ?? '').includes('Answer B.');
    expect(texts.filter((t) => t.includes('Answer A.')).length).toBe(1);
    expect(bAnywhere).toBe(true);
  });
});
