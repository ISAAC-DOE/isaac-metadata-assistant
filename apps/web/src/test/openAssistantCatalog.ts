/**
 * Open the Assistant's "What Can I Ask?" popover inside a rendered panel.
 *
 * *** WHY EVERY PILL QUERY NOW GOES THROUGH HERE. *** On 2026-09-13 the
 * Suggested Questions and Agent Actions groups moved out of the Assistant rail
 * and into that popover, at the project owner's request. The cause was
 * measured in a real browser at the shipped width: the rail stacked ELEVEN
 * blocks, two of which were independently-scrolling regions that were BOTH
 * clipped — `.assistant-empty` hiding 85px and `.assistant-agent-actions`
 * hiding 65px. A reader met two half-lists, each with its own scrollbar.
 *
 * The controls themselves are unchanged: the same buttons, running the same
 * intents, in one scroll region instead of two. What changed is that reaching
 * them is an explicit act — for a reader, and therefore for a test.
 *
 * A HELPER RATHER THAN A LINE IN EACH TEST, because the alternative was 34
 * copies of the same click with 34 chances to write it slightly differently.
 * It returns the popover element so a caller can scope to it.
 */
import { fireEvent, waitFor, within } from '@testing-library/react';

export function openAssistantCatalog(scope: HTMLElement): HTMLElement {
  const trigger = within(scope).getByRole('button', { name: /What Can I Ask/i });
  // Idempotent: a test that opens it twice (or a helper called after a test
  // already opened it) must not toggle it shut.
  if (trigger.getAttribute('aria-expanded') !== 'true') fireEvent.click(trigger);
  const panel = scope.querySelector('.assistant-capabilities-panel');
  if (panel === null) {
    throw new Error(
      'the capabilities popover did not open. The suggested-question and agent-action ' +
        'pills live inside it since 2026-09-13; if it has moved again, update this helper ' +
        'rather than re-adding the pills to the rail.',
    );
  }
  return panel as HTMLElement;
}

/**
 * Wait for the Assistant panel to mount, then open its catalog.
 *
 * Screens that fetch a bundle render the panel only once data lands, so a test
 * cannot query `.assistant` immediately after `render`. The tests that used to
 * wait on a PILL now have nothing to wait on — the pills are behind the
 * popover — so the wait has to be on the panel itself.
 */
export async function openAssistantCatalogWhenReady(
  container: HTMLElement,
): Promise<HTMLElement> {
  let assistant: HTMLElement | null = null;
  await waitFor(() => {
    assistant = container.querySelector('.assistant');
    if (assistant === null) throw new Error('the Assistant panel has not mounted yet');
  });
  return openAssistantCatalog(assistant as unknown as HTMLElement);
}
