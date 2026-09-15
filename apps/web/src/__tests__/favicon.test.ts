/*
 * The browser tab showed a generic document icon. The owner asked for the
 * ISAAC mark instead, explicit that it must REUSE the existing header logo
 * (`TopBar.tsx`'s `Brand()` / `.brand-tile` — the lucide-react
 * `AudioWaveform` glyph on an `--action` tile), not a new design.
 *
 * ── WHAT THIS FILE CANNOT SEE, STATED RATHER THAN IMPLIED ───────────────────
 *
 * jsdom computes no layout and loads no favicon — nothing here can see a
 * rendered browser tab. What IS mechanically checkable from source, and what
 * a future edit could silently break, is checked below: that the app links
 * to the mark's own SVG (not a generic default), that every icon href uses
 * Vite's `%BASE_URL%` build-time placeholder rather than a hardcoded
 * root-absolute path — the exact mistake that would 404 under the hosted
 * `/krish/` subpath while looking correct in local dev — and that the linked
 * SVG file actually reproduces the app's tile color and the same glyph path
 * lucide-react ships, rather than a redrawing.
 *
 * Browser/base-path verification actually performed (not claimed here):
 * `npx vite build` with and without `VITE_BASE_PATH=/krish/`, inspecting the
 * emitted `dist/index.html` — see the session report, not this file.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const INDEX_HTML = readFileSync(resolve(__dirname, '../../index.html'), 'utf-8');
const FAVICON_SVG = readFileSync(resolve(__dirname, '../../public/favicon.svg'), 'utf-8');

// The exact fill Brand()'s tile renders — apps/web/src/styles/tokens.css's
// `--action`. Hardcoded here (as a re-derivation, not a re-import) so a
// token-file edit that silently drifted the favicon's color would fail this
// test rather than only a human eye.
const ACTION_HEX = '#2c6ab0';

// Copied verbatim from node_modules/lucide-react/dist/esm/icons/audio-waveform.js —
// the same string scripts/render_favicons.py's own PATH_D constant carries.
const AUDIO_WAVEFORM_PATH_D =
  'M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0v-4a2 2 0 0 1 2-2';

describe('favicon — reuses the header mark, resolves under the deployed base path', () => {
  it('index.html links an SVG icon, not the browser default', () => {
    expect(INDEX_HTML).toMatch(/<link\s+rel="icon"\s+type="image\/svg\+xml"\s+href="[^"]+"\s*\/>/);
  });

  it('every icon href is BASE_URL-relative, never a hardcoded root-absolute path', () => {
    const hrefs = [...INDEX_HTML.matchAll(/<link[^>]*\brel="[^"]*icon[^"]*"[^>]*\bhref="([^"]+)"/g)].map(
      (m) => m[1],
    );
    // At least the four this slice wired: svg, png, ico, apple-touch-icon.
    expect(hrefs.length).toBeGreaterThanOrEqual(4);
    for (const href of hrefs) {
      expect(href.startsWith('%BASE_URL%'), `expected "${href}" to start with %BASE_URL%`).toBe(true);
      // The literal deploy subpath must never be hand-baked into source —
      // %BASE_URL% is what makes local dev (base "/") and the hosted build
      // (base "/krish/") both resolve without a code change.
      expect(href).not.toContain('/krish/');
    }
  });

  it('links a 32x32 PNG fallback, an .ico, and an apple-touch-icon', () => {
    expect(INDEX_HTML).toMatch(/<link\s+rel="icon"\s+type="image\/png"\s+sizes="32x32"\s+href="%BASE_URL%[^"]+"/);
    expect(INDEX_HTML).toMatch(/<link\s+rel="alternate icon"\s+href="%BASE_URL%[^"]+\.ico"/);
    expect(INDEX_HTML).toMatch(/<link\s+rel="apple-touch-icon"\s+href="%BASE_URL%[^"]+"/);
  });

  it('does not add a web-app manifest link (the app has none to point at)', () => {
    expect(INDEX_HTML).not.toMatch(/rel="manifest"/);
  });

  it('the linked favicon.svg fills the tile with --action, not an invented color', () => {
    expect(FAVICON_SVG.toLowerCase()).toContain(ACTION_HEX);
  });

  it('the linked favicon.svg draws the same lucide AudioWaveform path, not a redrawing', () => {
    expect(FAVICON_SVG).toContain(AUDIO_WAVEFORM_PATH_D);
  });

  it('the glyph is stroked white on the tile, matching Brand()s rendered contrast', () => {
    expect(FAVICON_SVG.toLowerCase()).toMatch(/stroke="#fff(fff)?"/);
  });
});
