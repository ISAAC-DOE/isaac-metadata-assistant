import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { GraphStatusChip } from '../components/GraphStatusChip';

/*
 * P33 S3 (D7) — ONE accessible memory-availability state. The chip reads
 * "Memory Available" / "Memory Unavailable" (single Title-Case state, no
 * "Memory:" colon fragment), the redundant adjacent "memory plane" label is
 * removed, and the state is carried by text (never colour alone) plus a
 * per-state class hook the CSS greens only when genuinely available. Only the
 * two real backend states exist — no invented Updating/Not-Configured.
 */

describe('GraphStatusChip — P33 S3 (D7)', () => {
  it('available: single "Memory Available" state, no redundant "memory plane" label', () => {
    const { getByText, queryByText, container } = render(
      <GraphStatusChip availability="available" />,
    );
    expect(getByText('Memory Available')).toBeTruthy();
    expect(queryByText(/memory plane/i)).toBeNull();
    // text carries the state (not colour-only); a semantic hook lets CSS green it
    expect(container.querySelector('.graph-available')).toBeTruthy();
  });

  it('unavailable: single "Memory Unavailable" state with its own class hook', () => {
    const { getByText, queryByText, container } = render(
      <GraphStatusChip availability="unavailable" />,
    );
    expect(getByText('Memory Unavailable')).toBeTruthy();
    expect(queryByText(/memory plane/i)).toBeNull();
    expect(container.querySelector('.graph-unavailable')).toBeTruthy();
  });
});
