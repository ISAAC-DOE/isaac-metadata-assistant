/*
 * Test helpers for the themed controls (`components/Select.tsx`, `components/SegmentedControl.tsx`), so a
 * test drives them the way a person does: open the picker, click the option.
 */
import { fireEvent, screen, within } from '@testing-library/react';

type Matcher = string | RegExp;

function matches(text: string, m: Matcher): boolean {
  return typeof m === 'string' ? text === m : m.test(text);
}

/** The `Select` named `label` (by its `<label htmlFor>` or aria-label), inside `root`. */
export function getSelect(label: Matcher, root: HTMLElement = document.body): HTMLElement {
  return within(root).getByRole('combobox', { name: label });
}

/** The current value of a `Select` (its trigger carries it as `data-value`). */
export function selectValue(select: HTMLElement): string {
  return select.getAttribute('data-value') ?? '';
}

/** The option labels a `Select` offers, grouped: `[{ group, options }]` (`group` null for ungrouped ones). */
export function selectGroups(select: HTMLElement): { group: string | null; options: string[] }[] {
  const listbox = document.getElementById(select.getAttribute('aria-controls') ?? '') as HTMLElement;
  const out: { group: string | null; options: string[] }[] = [];
  for (const child of Array.from(listbox.children)) {
    if (child.getAttribute('role') === 'group') {
      const labelId = child.getAttribute('aria-labelledby') ?? '';
      out.push({
        group: document.getElementById(labelId)?.textContent ?? null,
        options: Array.from(child.querySelectorAll('[role="option"]')).map(optionName),
      });
    } else if (child.getAttribute('role') === 'option') {
      const last = out[out.length - 1];
      if (last && last.group === null) last.options.push(optionName(child));
      else out.push({ group: null, options: [optionName(child)] });
    }
  }
  return out;
}

/** Every option label a `Select` offers, in display order. */
export function selectOptions(select: HTMLElement): string[] {
  return selectGroups(select).flatMap((g) => g.options);
}

function optionName(option: Element): string {
  return option.querySelector('.select-option-name')?.textContent ?? option.textContent ?? '';
}

/** Open the `Select` named `label` and click the option whose label is `optionText`. */
export function chooseOption(label: Matcher, optionText: Matcher, root: HTMLElement = document.body): void {
  const select = getSelect(label, root);
  chooseIn(select, optionText);
}

/** The same, on a `Select` already in hand. */
export function chooseIn(select: HTMLElement, optionText: Matcher): void {
  if (select.getAttribute('aria-expanded') !== 'true') fireEvent.click(select);
  const listbox = document.getElementById(select.getAttribute('aria-controls') ?? '') as HTMLElement;
  const option = Array.from(listbox.querySelectorAll<HTMLElement>('[role="option"]')).find((o) =>
    matches(optionName(o), optionText),
  );
  if (!option) {
    throw new Error(`no option ${String(optionText)} in ${select.id}: ${selectOptions(select).join(' | ')}`);
  }
  fireEvent.click(option);
}

/** Click the segment named `optionText` in the segmented control named `groupLabel`. */
export function chooseSegment(groupLabel: Matcher, optionText: Matcher, root: HTMLElement = document.body): void {
  const group = within(root).getByRole('radiogroup', { name: groupLabel });
  fireEvent.click(within(group).getByRole('radio', { name: optionText }));
}

export { screen };
