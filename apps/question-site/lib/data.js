// The exported questions (`data/site-data.json`, written by `isaac bundle site export`) and their images.
// The data folder is deployed beside the functions and is never served as a static file: every read goes through a
// signed-in route.

import fs from 'node:fs/promises';
import path from 'node:path';
import { HttpError } from './http.js';

export const FORMAT = 'isaac.question_site';
export const ANSWERS_FORMAT = 'isaac.question_site_answers';
export const FORMAT_VERSION = '1.0.0';

let cached = null;
let cachedDir = null;

export function dataDir() {
  return process.env.QUESTION_SITE_DATA_DIR || path.join(process.cwd(), 'data');
}

/** The site data, read once per instance. A missing or foreign file is a 503: the site is not set up. */
export async function siteData() {
  const dir = dataDir();
  if (cached && cachedDir === dir) return cached;
  let raw;
  try {
    raw = JSON.parse(await fs.readFile(path.join(dir, 'site-data.json'), 'utf8'));
  } catch {
    throw new HttpError(503, 'The site is not set up yet: its questions are missing.');
  }
  if (raw.format !== FORMAT || !Array.isArray(raw.cards) || typeof raw.bundle_id !== 'string') {
    throw new HttpError(503, 'The site is not set up yet: its questions are in a format it does not read.');
  }
  if (String(raw.format_version).split('.')[0] !== FORMAT_VERSION.split('.')[0]) {
    throw new HttpError(503, 'The site is not set up yet: its questions were exported for a different site version.');
  }
  const byId = new Map(raw.cards.map((c) => [c.card_id, c]));
  cached = { raw, byId };
  cachedDir = dir;
  return cached;
}

export function resetDataCache() {
  cached = null;
  cachedDir = null;
}

/** A card as the browser gets it: everything a person reads, and nothing about how an answer is recorded. */
export function publicCard(card) {
  const { covers, ...rest } = card; // eslint-disable-line no-unused-vars
  return rest;
}

const IMAGE = /^img\/([a-f0-9]{64})\.(png|jpg|jpeg)$/;
const TYPES = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg' };

function looksLike(ext, head) {
  if (ext === 'png') return head.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  return head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff;
}

/** One exported image by its contract name (`img/<sha256>.<ext>`). Anything else, or a file that is not that image type, is a 404. */
export async function readImage(name) {
  const m = IMAGE.exec(String(name || ''));
  if (!m) throw new HttpError(404, 'Not found.');
  const file = path.join(dataDir(), 'img', `${m[1]}.${m[2]}`);
  let body;
  try {
    body = await fs.readFile(file);
  } catch {
    throw new HttpError(404, 'Not found.');
  }
  if (!looksLike(m[2], body)) throw new HttpError(404, 'Not found.');
  return { body, type: TYPES[m[2]] };
}
