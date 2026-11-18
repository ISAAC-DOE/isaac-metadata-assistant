// Local development server: the same handlers Vercel runs, on localhost.
//
//   node dev-server.js [--port 5180] [--data <dir holding site-data.json>]
//
// Reads `.env.local` (or `.env.example` when there is none) for SITE_PASSWORD and QUESTION_SITE_DEV_STORE.
// Answers go to a JSON file. Nothing here is used by the deployed site.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

for (const file of ['.env.local', '.env.example']) {
  const p = path.join(here, file);
  if (!fs.existsSync(p)) continue;
  for (const line of fs.readFileSync(p, 'utf8').split('\n')) {
    const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
    if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2];
  }
  break;
}
const dataArg = arg('--data', null);
if (dataArg) process.env.QUESTION_SITE_DATA_DIR = path.resolve(dataArg);
if (!process.env.QUESTION_SITE_DATA_DIR && !fs.existsSync(path.join(here, 'data', 'site-data.json'))) {
  process.env.QUESTION_SITE_DATA_DIR = path.join(here, 'test', 'fixtures'); // made-up questions
}
if (process.env.QUESTION_SITE_DEV_STORE) {
  process.env.QUESTION_SITE_DEV_STORE = path.resolve(here, process.env.QUESTION_SITE_DEV_STORE);
}
process.chdir(here);

const vercel = JSON.parse(fs.readFileSync(path.join(here, 'vercel.json'), 'utf8'));
const siteHeaders = vercel.headers[0].headers.filter((h) => h.key !== 'Strict-Transport-Security');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.svg': 'image/svg+xml' };
const handlers = new Map();

async function api(name) {
  if (!/^[a-z]+$/.test(name)) return null;
  if (!handlers.has(name)) {
    const file = path.join(here, 'api', `${name}.js`);
    handlers.set(name, fs.existsSync(file) ? (await import(pathToFileURL(file).href)).default : null);
  }
  return handlers.get(name);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://local');
  for (const h of siteHeaders) res.setHeader(h.key, h.value);
  if (url.pathname.startsWith('/api/')) {
    const fn = await api(url.pathname.slice(5));
    if (!fn) {
      res.statusCode = 404;
      return res.end('Not found');
    }
    return fn(req, res);
  }
  let rel = url.pathname === '/' ? '/index.html' : url.pathname;
  if (!path.extname(rel)) rel += '.html';
  const file = path.join(here, 'public', path.normalize(rel));
  if (!file.startsWith(path.join(here, 'public') + path.sep) || !fs.existsSync(file)) {
    res.statusCode = 404;
    return res.end('Not found');
  }
  res.setHeader('Content-Type', TYPES[path.extname(file)] || 'application/octet-stream');
  res.setHeader('Cache-Control', 'no-store');
  return res.end(fs.readFileSync(file));
});

const port = Number(arg('--port', process.env.PORT || 5180));
server.listen(port, '127.0.0.1', () => {
  console.log(`question site: http://localhost:${port}  (data: ${process.env.QUESTION_SITE_DATA_DIR || 'data/'})`);
});
