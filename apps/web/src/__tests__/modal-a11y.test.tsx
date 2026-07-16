import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { exportedReadyRoutes, stubFetchRoutes } from '../test/apiFixtures';

/*
 * P22E — the artifact "View JSON" preview is a true modal dialog.
 *  - role="dialog" + aria-modal="true" + aria-labelledby wired to the title
 *  - focus moves into the dialog on open, and returns to the trigger on close
 *  - Escape, the Close button, and a backdrop click all close it
 *  - Tab / Shift+Tab are contained (hand-rolled, no dependency)
 *
 * A fresh load of an already-exported record (exportedReadyRoutes) makes the
 * View actions live from the /artifacts endpoint, so no export click is needed.
 */
function renderExport() {
  stubFetchRoutes(exportedReadyRoutes('demo'));
  return render(
    <MemoryRouter
      initialEntries={['/record/demo/export']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Open the record viewer via its trigger, focusing the trigger first (as a
 * keyboard/mouse activation would), so focus-return can be asserted. */
async function openRecordViewer(view: ReturnType<typeof renderExport>) {
  const { findByText } = view;
  await findByText('Valid against official ISAAC schema v1.05.');
  const trigger = (await findByText('View JSON')).closest('button')! as HTMLButtonElement;
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe('P22E · artifact preview modal — ARIA + focus semantics', () => {
  it('opens a dialog with role/aria-modal/aria-labelledby wired to its title', async () => {
    const view = renderExport();
    await openRecordViewer(view);

    const dialog = view.getByRole('dialog', { name: 'Official Record' });
    expect(dialog).toBeInTheDocument();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    // aria-labelledby resolves to the visible modal title (not a bare aria-label)
    const labelledby = dialog.getAttribute('aria-labelledby')!;
    expect(labelledby).toBeTruthy();
    // getElementById (not querySelector) — useId() emits colon-bearing ids.
    expect(document.getElementById(labelledby)!.textContent).toContain('Official Record');
  });

  it('moves focus into the dialog on open', async () => {
    const view = renderExport();
    await openRecordViewer(view);
    const dialog = view.getByRole('dialog');
    expect(document.activeElement).toBe(dialog);
  });

  it('closes on Escape and returns focus to the trigger', async () => {
    const view = renderExport();
    const trigger = await openRecordViewer(view);
    expect(view.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('closes via the Close button and returns focus to the trigger', async () => {
    const view = renderExport();
    const trigger = await openRecordViewer(view);

    fireEvent.click(view.getByRole('button', { name: 'Close' }));

    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('closes on backdrop click and returns focus to the trigger', async () => {
    const view = renderExport();
    const trigger = await openRecordViewer(view);

    const backdrop = view.container.querySelector('.artifact-modal-backdrop')!;
    fireEvent.click(backdrop);

    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('contains Tab at the boundary — Tab and Shift+Tab wrap onto the Close button', async () => {
    const view = renderExport();
    await openRecordViewer(view);

    const closeBtn = view.getByRole('button', { name: 'Close' }) as HTMLButtonElement;
    closeBtn.focus();
    expect(document.activeElement).toBe(closeBtn);

    // Close is the only (and therefore last) focusable: Tab is prevented and
    // focus wraps back onto it. fireEvent returns false when preventDefault ran.
    expect(fireEvent.keyDown(closeBtn, { key: 'Tab' })).toBe(false);
    expect(document.activeElement).toBe(closeBtn);

    // Shift+Tab at the first focusable wraps the same way.
    expect(fireEvent.keyDown(closeBtn, { key: 'Tab', shiftKey: true })).toBe(false);
    expect(document.activeElement).toBe(closeBtn);
  });

  it('the sidecar viewer opens its own labeled dialog (Evidence Trail)', async () => {
    const view = renderExport();
    await view.findByText('Valid against official ISAAC schema v1.05.');
    // the sidecar card uses the plain "View" action
    const sidecarView = view.getByText('View', { selector: 'button.btn' }).closest('button')!;
    sidecarView.focus();
    fireEvent.click(sidecarView);

    const dialog = await waitFor(() => view.getByRole('dialog', { name: /Evidence Trail/ }));
    expect(dialog.getAttribute('aria-modal')).toBe('true');

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(view.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(sidecarView);
  });
});
