// Sign-in: one shared site password plus the name the person gives. The name is who each answer is recorded as; it
// is not verified (the import records it as such).
//
// The session is a signed cookie, so the site needs no session storage: `payload.signature`, where the payload is
// the name and an expiry and the signature is HMAC-SHA256 under a key derived from the site password. Changing the
// password therefore signs everyone out.

import crypto from 'node:crypto';
import { HttpError } from './http.js';

export const COOKIE = 'qs_session';
const SESSION_DAYS = 30;
const NAME_MAX = 60;

export function sitePassword() {
  const pw = process.env.SITE_PASSWORD;
  if (!pw || pw.length < 8) {
    throw new HttpError(503, 'The site is not set up yet: its password is missing or shorter than 8 characters.');
  }
  return pw;
}

function key() {
  const secret = process.env.SESSION_SECRET || sitePassword();
  return crypto.createHmac('sha256', secret).update('isaac-question-site-session-v1').digest();
}

function b64(buf) {
  return Buffer.from(buf).toString('base64url');
}

function sign(payload) {
  return b64(crypto.createHmac('sha256', key()).update(payload).digest());
}

/** Constant-time comparison of two strings of any length. */
export function sameSecret(a, b) {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

/** The name as it will be recorded: trimmed, inner whitespace collapsed, control characters removed. */
export function cleanName(raw) {
  const name = String(raw ?? '')
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!name) throw new HttpError(400, 'Please give your name.');
  if (name.length > NAME_MAX) throw new HttpError(400, `Please keep the name under ${NAME_MAX} characters.`);
  return name;
}

export function makeSession(name, now = Date.now()) {
  const payload = b64(JSON.stringify({ n: name, e: now + SESSION_DAYS * 86400_000 }));
  return `${payload}.${sign(payload)}`;
}

export function readSession(token, now = Date.now()) {
  if (typeof token !== 'string' || token.length > 2048) return null;
  const dot = token.indexOf('.');
  if (dot < 1) return null;
  const payload = token.slice(0, dot);
  const given = token.slice(dot + 1);
  if (!sameSecret(given, sign(payload))) return null;
  try {
    const data = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    if (typeof data.n !== 'string' || typeof data.e !== 'number' || data.e < now) return null;
    return { name: data.n, expires: data.e };
  } catch {
    return null;
  }
}

export function parseCookies(req) {
  const out = {};
  for (const part of String(req.headers.cookie || '').split(';')) {
    const eq = part.indexOf('=');
    if (eq < 1) continue;
    out[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  return out;
}

function isLocal(req) {
  const host = String(req.headers.host || '').split(':')[0];
  return host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
}

export function sessionCookie(req, token) {
  const parts = [`${COOKIE}=${token}`, 'Path=/', 'HttpOnly', 'SameSite=Strict', `Max-Age=${SESSION_DAYS * 86400}`];
  if (!isLocal(req)) parts.push('Secure');
  return parts.join('; ');
}

export function clearCookie(req) {
  const parts = [`${COOKIE}=`, 'Path=/', 'HttpOnly', 'SameSite=Strict', 'Max-Age=0'];
  if (!isLocal(req)) parts.push('Secure');
  return parts.join('; ');
}

/** The signed-in person, or a 401. Every data route calls this first. */
export function requireSession(req) {
  sitePassword(); // an unconfigured site answers 503, never "signed in"
  const session = readSession(parseCookies(req)[COOKIE]);
  if (!session) throw new HttpError(401, 'Please sign in.');
  return session;
}
