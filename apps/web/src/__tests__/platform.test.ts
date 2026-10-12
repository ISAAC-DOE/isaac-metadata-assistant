import { afterEach, describe, expect, it, vi } from 'vitest';
import { isApplePlatform, searchShortcutHint } from '../lib/platform';

afterEach(() => vi.unstubAllGlobals());

const stubNavigator = (n: Record<string, unknown>) => vi.stubGlobal('navigator', n);

describe('which key the search shortcut is printed with (B-A17)', () => {
  it('Apple platforms get the Command key', () => {
    for (const platform of ['MacIntel', 'iPhone', 'iPad', 'MacARM']) {
      stubNavigator({ platform, userAgent: '' });
      expect(isApplePlatform(), platform).toBe(true);
      expect(searchShortcutHint()).toBe('⌘K');
    }
  });

  it('every other platform gets Ctrl', () => {
    for (const platform of ['Win32', 'Linux x86_64', 'Linux armv8l', 'CrOS']) {
      stubNavigator({ platform, userAgent: '' });
      expect(isApplePlatform(), platform).toBe(false);
      expect(searchShortcutHint()).toBe('Ctrl K');
    }
  });

  it('prefers the structured userAgentData platform over the legacy string', () => {
    stubNavigator({ userAgentData: { platform: 'macOS' }, platform: 'Win32', userAgent: '' });
    expect(isApplePlatform()).toBe(true);
    stubNavigator({ userAgentData: { platform: 'Windows' }, platform: 'MacIntel', userAgent: '' });
    expect(isApplePlatform()).toBe(false);
  });

  it('falls back to the user agent, and to Ctrl when nothing reports a platform', () => {
    stubNavigator({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' });
    expect(isApplePlatform()).toBe(true);
    stubNavigator({});
    expect(isApplePlatform()).toBe(false);
    vi.stubGlobal('navigator', undefined);
    expect(isApplePlatform()).toBe(false);
  });
});
