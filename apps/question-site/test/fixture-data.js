// The made-up question set, materialised into a temporary folder.
//
// The fixture image is committed as base64 text (`fixtures/img/<sha256>.png.b64`), not as a binary: the repository
// keeps every tracked file greppable, and a PNG holds NUL bytes. This writes the real `.png` beside a copy of
// `site-data.json` so the site code reads it exactly as it reads an exported folder.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures');
let made = null;

export function fixtureDataDir() {
  if (made) return made;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'isaac-question-site-fixtures-'));
  fs.copyFileSync(path.join(SOURCE, 'site-data.json'), path.join(dir, 'site-data.json'));
  fs.mkdirSync(path.join(dir, 'img'));
  for (const name of fs.readdirSync(path.join(SOURCE, 'img'))) {
    if (!name.endsWith('.b64')) continue;
    const bytes = Buffer.from(fs.readFileSync(path.join(SOURCE, 'img', name), 'utf8'), 'base64');
    fs.writeFileSync(path.join(dir, 'img', name.slice(0, -4)), bytes);
  }
  made = dir;
  return dir;
}
