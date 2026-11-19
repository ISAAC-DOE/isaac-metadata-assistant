# The question site

A small password-protected site where a scientist answers an ISAAC bundle's open questions a few at a time.
Most answers are one click (accept the suggestion, or pick an option), with a box for typing a different answer
and an "I don't know". Every answer saves as it is given, so ten questions today and fifteen next week both count.

It is the hosted companion to the `isaac-historical-import` skill:

1. `isaac bundle site export <bundle_dir> --out <dir>` writes the bundle's open questions as plain cards
   (`<dir>/data/site-data.json`, plus any curve images) and copies this folder beside them.
2. `<dir>` is deployed to Vercel. The scientist signs in with the site password and their name.
3. Anyone signed in can download `answers.json`. `isaac bundle site import <bundle_dir> answers.json --site-data
   <dir>/data/site-data.json` previews what the answers would record; `--apply` records them.

The two files are specified in [`docs/question-site-contract.md`](../../docs/question-site-contract.md).

## What goes online, and what protects it

The exported questions contain real beamtime details (sample names, logbook lines, curves). So:

- `data/` is never committed (it is gitignored here, and the export refuses to write inside a git tree).
- `data/` is never served as a static file. Every read goes through a signed-in route (`/api/state`,
  `/api/image`). An image is served only by its exported name and only if its bytes are that image type.
- Sign-in is one shared site password plus the name the person gives. The session is a signed, HttpOnly,
  Secure, SameSite=Strict cookie that lasts 30 days. Changing the password signs everyone out.
- An address gets ten sign-in tries in 15 minutes, right or wrong. After that every try is refused until the
  window ends, the right password included, so the refusal tells a guesser nothing.
- Every response says `noindex`, and `robots.txt` disallows everything. Images are never cached by the browser.
- The name is not verified. The import records each answer as "`<name>` (question site)".
- An answer is never overwritten unseen: if someone else answered a card while your page was open, the site shows
  you their answer instead of saving yours over it. Every save and every clear is also kept in a log.

## Run it locally

```bash
cd apps/question-site
node dev-server.js            # http://localhost:5180, made-up questions from test/fixtures
node dev-server.js --data /path/to/exported/dir/data
npm test
```

The local server reads `.env.local` (or `.env.example` when there is none) for the password and keeps answers in
a JSON file. There is nothing to install: the site uses only Node's standard library.

## Deploy it (once)

Run these from the exported folder (`<dir>` above), not from this repository.

1. Sign in to Vercel in a terminal: `npx vercel login`.
2. Create the project and a first deployment: `npx vercel deploy --prod`. Accept the defaults.
3. In the Vercel dashboard, open the project:
   - **Storage** → **Create** → **Upstash for Redis** → connect it to the project. Leave the "custom prefix" box
     empty, so the variables are named `KV_REST_API_URL` and `KV_REST_API_TOKEN`. Pick one region with no read
     replicas. Without the store the site refuses to save.
   - **Settings** → **Environment Variables** → add `SITE_PASSWORD`: at least 12 characters. Four random words is
     a good choice. This is the password you give the scientist.
   - Optional, same page: add `SESSION_SECRET`, a long random string (`openssl rand -hex 32`). Nobody types it;
     it makes a stolen cookie useless for guessing the password.
   - **Settings** → **Deployment Protection**: keep the default (Standard Protection). It leaves the production
     address open to the site's own sign-in and keeps old preview addresses behind Vercel's login.
   - **Firewall** → add a rate-limit rule on `/api/login` (for example 20 requests per minute per IP). The site
     limits tries per address itself; this rule stops a flood of tries from many addresses before it reaches
     the site or uses up the answer store's free quota.
4. Deploy again so the settings take effect: `npx vercel deploy --prod`.
5. Check it. Sign in, answer one question, open the site in a second browser to see the answer there, and use
   "Download all answers" to see it in the file. (The store's write runs as a small script inside Redis, which the
   tests can only imitate; this is its first real run.) Then, signed out: `/data/site-data.json` must answer 404 and `/api/state` must answer 401. Then sign in and
   check `/data/site-data.json` still answers 404 while the questions show on the page.

## Update the questions

Export again and redeploy the same folder (`npx vercel deploy --prod`). Answers are kept by card, so an answered
question that is still asked keeps its answer, and one the bundle no longer asks simply stops being shown.

## Files

| Path | What it is |
|---|---|
| `public/` | The page: `index.html`, `app.js` (views), `logic.js` (pure logic, tested), `styles.css` |
| `api/` | The routes: `login`, `logout`, `state`, `answer`, `answers` (download), `image` |
| `lib/` | Sign-in (`auth.js`), the answer store (`store.js`), answer checks (`answers.js`), data (`data.js`) |
| `test/` | `node --test` tests and a made-up question set (its image is kept as base64 text so the repo stays greppable) |
| `dev-server.js` | The local server |
| `vercel.json` | Security headers, and `data/**` bundled with the functions |
