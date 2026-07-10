import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('router-level smoke: each surface renders without error', () => {
  it('S1 · My Experiments (/experiments)', () => {
    const { getByText } = renderAt('/experiments');
    expect(getByText('Cu-foil reference — energy calibration')).toBeInTheDocument();
  });

  it('S2 · Load Materials (/load)', () => {
    const { getByText } = renderAt('/load');
    expect(getByText('Run the Synthetic Demo')).toBeInTheDocument();
  });

  it('S3 · Review Record (/record/:id)', () => {
    const { getByText } = renderAt('/record/demo');
    expect(getByText('5 Fields Need Your Confirmation')).toBeInTheDocument();
  });

  it('S4 · Complete Missing Fields (/record/:id/complete)', () => {
    const { getByText } = renderAt('/record/demo/complete');
    expect(getByText('Answer 5 Questions to Finish This Record')).toBeInTheDocument();
  });

  it('S5 · Evidence & File Preview (/record/:id/evidence)', () => {
    const { getByText } = renderAt('/record/demo/evidence');
    expect(getByText('Direct Fields')).toBeInTheDocument();
  });

  it('S6 · Ready to Export (/record/:id/export)', () => {
    const { getByText } = renderAt('/record/demo/export');
    expect(getByText('Valid against official ISAAC schema v1.05.')).toBeInTheDocument();
  });

  it('Project Memory (/memory) is a separate destination', () => {
    const { getByText } = renderAt('/memory');
    expect(getByText('Memory / Query Plane')).toBeInTheDocument();
  });

  it('the index route redirects into the queue', () => {
    const { getByText } = renderAt('/');
    expect(getByText('Cu-foil reference — energy calibration')).toBeInTheDocument();
  });
});
