import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import axe from 'axe-core';
import { useState } from 'react';

import { Widget, WidgetGrid, widgetIds } from '../components/Widget';

/**
 * `components/Widget.tsx` — the shared widget primitive (2026-10-12).
 *
 * The Statistics suites assert what each widget SAYS; this file asserts what
 * the primitive GUARANTEES to every surface that adopts it: a named region, an
 * info toggle that is a real disclosure, a view switcher that is the APG tabs
 * pattern, and a range group that is a real radiogroup. Each guarantee is
 * asserted through the control a reader uses, not through internal state.
 */

afterEach(cleanup);

function ThreeViews({ withRange = false }: { withRange?: boolean }) {
  const [range, setRange] = useState('7');
  return (
    <Widget
      id="w-test"
      title="Test Widget"
      sub="One question, answered."
      headline={<p>Headline 42</p>}
      info={<p>Provenance prose.</p>}
      views={[
        { id: 'a', label: 'Alpha', content: <p>Alpha body</p> },
        { id: 'b', label: 'Beta', content: <p>Beta body</p> },
        { id: 'c', label: 'Gamma', content: <p>Gamma body</p> },
      ]}
      range={
        withRange
          ? {
              label: 'Time Range',
              options: [
                { value: '7', label: '7 Days' },
                { value: '30', label: '30 Days' },
              ],
              value: range,
              onChange: setRange,
            }
          : undefined
      }
      footer={<a href="/x">Open X</a>}
    />
  );
}

describe('Widget · the region', () => {
  it('is a region named by its own title, with its question beneath', () => {
    render(<ThreeViews />);
    const region = screen.getByRole('region', { name: 'Test Widget' });
    expect(within(region).getByRole('heading', { level: 2, name: 'Test Widget' })).toHaveAttribute(
      'id',
      'w-test',
    );
    expect(within(region).getByText('One question, answered.')).toBeInTheDocument();
    expect(within(region).getByText('Headline 42')).toBeInTheDocument();
    expect(within(region).getByRole('link', { name: 'Open X' })).toBeInTheDocument();
  });

  it('honours headingLevel 3 and a full-span request', () => {
    render(<Widget id="w3" title="Nested" headingLevel={3} span="full" />);
    expect(screen.getByRole('heading', { level: 3, name: 'Nested' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Nested' })).toHaveAttribute('data-span', 'full');
  });
});

describe('Widget · the info toggle', () => {
  it('is a named button that discloses a panel it controls, closed on arrival', () => {
    render(<ThreeViews />);
    const toggle = screen.getByRole('button', { name: 'About Test Widget' });
    const panel = document.getElementById(widgetIds.info('w-test'))!;
    expect(toggle).toHaveAttribute('aria-controls', panel.id);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(panel).toHaveAttribute('hidden');
    // Closed but MOUNTED: every DOM-reading guard still reaches its prose.
    expect(panel.textContent).toBe('Provenance prose.');

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(panel).not.toHaveAttribute('hidden');
    fireEvent.click(toggle);
    expect(panel).toHaveAttribute('hidden');
  });

  it('accepts a replacement accessible name', () => {
    render(<Widget id="w4" title="Named" info={<p>x</p>} infoLabel="About These Figures" />);
    expect(screen.getByRole('button', { name: 'About These Figures' })).toBeInTheDocument();
  });

  it('names the icon for a pointer user too: a title tooltip matching its accessible name', () => {
    render(<ThreeViews />);
    expect(screen.getByRole('button', { name: 'About Test Widget' })).toHaveAttribute(
      'title',
      'About Test Widget',
    );
    cleanup();
    render(<Widget id="w4t" title="Named" info={<p>x</p>} infoLabel="About These Figures" />);
    expect(screen.getByRole('button', { name: 'About These Figures' })).toHaveAttribute(
      'title',
      'About These Figures',
    );
  });

  it('renders no toggle when there is nothing to disclose', () => {
    render(<Widget id="w5" title="Bare" />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('Widget · the view switcher is the APG tabs pattern', () => {
  it('names the tablist after the widget, selects the first view, and roves the tab stop', () => {
    render(<ThreeViews />);
    const tablist = screen.getByRole('tablist', { name: 'Test Widget Views' });
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['Alpha', 'Beta', 'Gamma']);
    expect(tabs.map((t) => t.getAttribute('aria-selected'))).toEqual(['true', 'false', 'false']);
    expect(tabs.map((t) => t.tabIndex)).toEqual([0, -1, -1]);
  });

  it('wires every tab to its own panel and back, and hides — not unmounts — the inactive ones', () => {
    render(<ThreeViews />);
    for (const id of ['a', 'b', 'c']) {
      const tab = document.getElementById(widgetIds.tab('w-test', id))!;
      const panel = document.getElementById(widgetIds.panel('w-test', id))!;
      expect(tab).toHaveAttribute('aria-controls', panel.id);
      expect(panel).toHaveAttribute('role', 'tabpanel');
      expect(panel).toHaveAttribute('aria-labelledby', tab.id);
    }
    expect(document.getElementById(widgetIds.panel('w-test', 'a'))).not.toHaveAttribute('hidden');
    expect(document.getElementById(widgetIds.panel('w-test', 'b'))).toHaveAttribute('hidden');
    // APG: every tab panel is in the tab sequence, so a panel holding nothing
    // focusable (a figure list, a chart) is still reachable after the tablist.
    for (const id of ['a', 'b', 'c']) {
      expect(document.getElementById(widgetIds.panel('w-test', id))).toHaveAttribute('tabindex', '0');
    }
    // Mounted while hidden: its text is still in the document.
    expect(screen.getByText('Beta body')).toBeInTheDocument();
    expect(screen.getByText('Beta body')).not.toBeVisible();
  });

  it('switches on click', () => {
    render(<ThreeViews />);
    fireEvent.click(screen.getByRole('tab', { name: 'Gamma' }));
    expect(screen.getByRole('tab', { name: 'Gamma' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Gamma body')).toBeVisible();
    expect(screen.getByText('Alpha body')).not.toBeVisible();
  });

  it('moves selection AND focus with Arrow keys, wrapping, and with Home / End', () => {
    render(<ThreeViews />);
    const tab = (name: string) => screen.getByRole('tab', { name });
    tab('Alpha').focus();
    fireEvent.keyDown(tab('Alpha'), { key: 'ArrowRight' });
    expect(tab('Beta')).toHaveAttribute('aria-selected', 'true');
    expect(tab('Beta')).toHaveFocus();
    fireEvent.keyDown(tab('Beta'), { key: 'End' });
    expect(tab('Gamma')).toHaveFocus();
    fireEvent.keyDown(tab('Gamma'), { key: 'ArrowRight' });
    expect(tab('Alpha')).toHaveFocus();
    expect(tab('Alpha')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(tab('Alpha'), { key: 'ArrowLeft' });
    expect(tab('Gamma')).toHaveFocus();
    fireEvent.keyDown(tab('Gamma'), { key: 'Home' });
    expect(tab('Alpha')).toHaveFocus();
  });

  it('a controlled selection reports the request and follows its prop', () => {
    function Controlled() {
      const [view, setView] = useState('b');
      return (
        <>
          <Widget
            id="wc"
            title="Controlled"
            view={view}
            onViewChange={setView}
            views={[
              { id: 'a', label: 'One', content: 'one' },
              { id: 'b', label: 'Two', content: 'two' },
            ]}
          />
          <output data-testid="view">{view}</output>
        </>
      );
    }
    render(<Controlled />);
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'One' }));
    expect(screen.getByTestId('view').textContent).toBe('a');
    expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute('aria-selected', 'true');
  });

  it('renders ONE view without a switcher, because a single choice is no choice', () => {
    render(<Widget id="w1" title="Single" views={[{ id: 'a', label: 'Only', content: 'only' }]} />);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.getByText('only')).toBeVisible();
  });
});

describe('Widget · the button switcher (viewSwitcher="buttons")', () => {
  const VIEWS = [
    { id: 'a', label: 'Alpha', content: 'alpha body' },
    { id: 'b', label: 'Beta', content: 'beta body' },
  ];

  it('renders a GROUP of toggle buttons, not a tablist, each in the Tab order', () => {
    render(<Widget id="wb" title="Buttons" viewSwitcher="buttons" views={VIEWS} />);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.queryByRole('tab')).toBeNull();
    const group = screen.getByRole('group', { name: 'Buttons Views' });
    const buttons = within(group).getAllByRole('button');
    expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false']);
    for (const b of buttons) {
      expect(b.tabIndex).toBe(0);
      expect(document.getElementById(b.getAttribute('aria-controls') ?? '')).not.toBeNull();
    }
    fireEvent.click(buttons[1]);
    expect(buttons[1]).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('beta body')).toBeVisible();
    expect(screen.getByText('alpha body')).not.toBeVisible();
  });

  it('collapses on a second press of the shown view when collapsible, and reports it', () => {
    let collapsed = 0;
    const changes: string[] = [];
    render(
      <Widget
        id="wc2"
        title="Collapsing"
        viewSwitcher="buttons"
        collapsible
        defaultView={null}
        views={VIEWS}
        onViewChange={(id) => changes.push(id)}
        onViewCollapse={() => (collapsed += 1)}
      />,
    );
    // Starts collapsed: no view pressed, no panel shown.
    const alpha = screen.getByRole('button', { name: 'Alpha' });
    expect(alpha).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('alpha body')).not.toBeVisible();
    fireEvent.click(alpha);
    expect(alpha).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('alpha body')).toBeVisible();
    fireEvent.click(alpha);
    expect(alpha).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('alpha body')).not.toBeVisible();
    expect(changes).toEqual(['a']);
    expect(collapsed).toBe(1);
  });

  it('does NOT collapse without `collapsible`, and `null` is ignored by the tabs pattern', () => {
    const { unmount } = render(<Widget id="wn" title="Fixed" viewSwitcher="buttons" views={VIEWS} />);
    const alpha = screen.getByRole('button', { name: 'Alpha' });
    fireEvent.click(alpha);
    expect(alpha).toHaveAttribute('aria-pressed', 'true');
    unmount();
    render(<Widget id="wt" title="Tabs" defaultView={null} collapsible views={VIEWS} />);
    expect(screen.getByRole('tab', { name: 'Alpha' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('Widget · heading props and data attributes', () => {
  it('passes headingProps to the heading without letting them replace its id', () => {
    render(<Widget id="wh" title="Focusable" headingProps={{ tabIndex: -1 }} />);
    const heading = screen.getByRole('heading', { name: 'Focusable' });
    expect(heading).toHaveAttribute('tabindex', '-1');
    expect(heading).toHaveAttribute('id', 'wh');
    expect(heading).toHaveClass('widget-title');
  });

  it('passes data-* attributes through to the section, and nothing else', () => {
    render(<Widget id="wd2" title="Tagged" data-surface="settings" data-order={3} />);
    const region = screen.getByRole('region', { name: 'Tagged' });
    expect(region).toHaveAttribute('data-surface', 'settings');
    expect(region).toHaveAttribute('data-order', '3');
    expect(region).toHaveAttribute('data-span', 'auto');
  });
});

describe('Widget · the range group is a radiogroup', () => {
  it('names the group, checks exactly one, roves the tab stop, and follows the arrows', () => {
    render(<ThreeViews withRange />);
    const group = screen.getByRole('radiogroup', { name: 'Time Range' });
    const radios = within(group).getAllByRole('radio');
    expect(radios.map((r) => r.getAttribute('aria-checked'))).toEqual(['true', 'false']);
    expect(radios.map((r) => r.tabIndex)).toEqual([0, -1]);
    radios[0].focus();
    fireEvent.keyDown(radios[0], { key: 'ArrowRight' });
    const thirty = within(group).getByRole('radio', { name: '30 Days' });
    expect(thirty).toHaveAttribute('aria-checked', 'true');
    expect(thirty).toHaveFocus();
  });

  it('sits in the view bar, beside the tabs, when the widget has views', () => {
    render(<ThreeViews withRange />);
    const group = screen.getByRole('radiogroup', { name: 'Time Range' });
    expect(group.closest('.widget-bar')).not.toBeNull();
    expect(group.closest('.widget-head')).toBeNull();
  });
});

describe('Widget · the details expansion', () => {
  it('is the shared full-row Disclosure, closed on arrival, with its body mounted', () => {
    render(
      <Widget
        id="wd"
        title="Long List"
        details={{ summary: 'Show All Items', content: <ul><li>item one</li></ul> }}
      />,
    );
    const trigger = screen.getByRole('button', { name: 'Show All Items' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('item one')).not.toBeVisible();
    fireEvent.click(trigger);
    expect(screen.getByText('item one')).toBeVisible();
  });
});

describe('Widget · structural accessibility', () => {
  it('reports no structural violation, with every control open and closed', async () => {
    const { container } = render(
      <WidgetGrid>
        <ThreeViews withRange />
        <Widget id="w2" title="Second" info={<p>More prose.</p>} />
      </WidgetGrid>,
    );
    const run = async () =>
      (
        await axe.run(container, {
          runOnly: {
            type: 'rule',
            values: [
              'button-name',
              'aria-required-children',
              'aria-required-parent',
              'aria-valid-attr-value',
              'aria-allowed-attr',
              'landmark-unique',
              'region',
            ],
          },
          resultTypes: ['violations'],
        })
      ).violations.map((v) => `${v.id} × ${v.nodes.length}`);
    expect(await run()).toEqual([]);
    fireEvent.click(screen.getByRole('button', { name: 'About Test Widget' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Beta' }));
    expect(await run()).toEqual([]);
  });

  it('every glyph it draws is decorative', () => {
    const { container } = render(<ThreeViews withRange />);
    for (const svg of container.querySelectorAll('svg')) {
      expect(svg.closest('[aria-hidden="true"]')).not.toBeNull();
    }
  });
});
