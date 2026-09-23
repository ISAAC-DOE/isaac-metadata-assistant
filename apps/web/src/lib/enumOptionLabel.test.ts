import { describe, expect, it } from 'vitest';
import { RUN_FIELDS, enumOptionLabel } from './runFields';

describe('enumOptionLabel (PR #277 review, minor) — casing and separators only', () => {
  it('reads each environment token as words, capitalised', () => {
    expect(enumOptionLabel('operando')).toBe('Operando');
    expect(enumOptionLabel('in_situ')).toBe('In situ');
    expect(enumOptionLabel('ex_situ')).toBe('Ex situ');
    expect(enumOptionLabel('in_silico')).toBe('In silico');
  });

  it('invents no meaning: every output word is an input word, for every enum option shipped', () => {
    for (const spec of RUN_FIELDS) {
      for (const option of spec.options ?? []) {
        const inWords = option.toLowerCase().split('_').filter(Boolean);
        const outWords = enumOptionLabel(option).toLowerCase().split(' ').filter(Boolean);
        expect(outWords).toEqual(inWords);
      }
    }
  });

  it('leaves a token with nothing to humanise unchanged', () => {
    expect(enumOptionLabel('_')).toBe('_');
  });
});
