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
- Wrong passwords are slowed down (10 per address per 15 minutes).
- Every response says `noindex`, and `robots.txt` disallows everything.
- The name is not verified. The import records each answer as "`<name>` (question site)".

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
   - **Storage** → **Create** → **Upstash for Redis** → connect it to the project. This sets
     `KV_REST_API_URL` and `KV_REST_API_TOKEN`. Without it the site refuses to save.
   - **Settings** → **Environment Variables** → add `SITE_PASSWORD` (at least 8 characters). This is the password
     you give the scientist.
   - **Settings** → **Deployment Protection** → turn Vercel Authentication off for Production, or the scientist
     meets Vercel's own login before the site's.
4. Deploy again so the settings take effect: `npx vercel deploy --prod`.
5. Check it: `/data/site-data.json` must answer 404, `/api/state` must answer 401 until you sign in.

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
