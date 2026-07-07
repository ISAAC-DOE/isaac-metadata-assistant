# Security & data-incident policy

This is a **research prototype** built for a domain with real data-governance obligations
(SLAC/SSRL beamline metadata). The repository is public, but **public visibility does not grant
reuse rights** and there is no formal security-response team. The primary risk here is not a
software vulnerability but the **accidental exposure of real or sensitive experimental data**. This
policy is intentionally simple and appropriate for a prototype repo.

---

## Ground rules

- **Never commit secrets or private data.** No credentials, API keys, tokens, `.env` files,
  production dumps, or real experiment artifacts. See [`docs/data-governance.md`](docs/data-governance.md)
  for the full list and the `examples/` / `graphify-out/` policies.
- **No real data in issues, logs, screenshots, or PR descriptions.** Reproduce problems with the
  committed synthetic fixtures instead. If a bug only manifests on real data, describe it abstractly.
- **Be cautious with LLMs on real artifacts.** Sending real or private data to an LLM (including
  Claude) is not allowed by default and requires explicit approval. The deterministic core
  (`isaac validate` / `export` / `audit`) is LLM-free and can be used with no model involvement.

---

## Reporting a data or security issue

This is a research prototype with no formal security-response or public disclosure process. If you
discover exposed data, a leaked secret, or a security concern:

1. **Do not** open a public issue that contains or points to the sensitive content.
2. Notify the **project owner / mentor directly and privately**.
3. Preserve details needed to fix it, but keep any sensitive data out of written reports.

---

## If sensitive data is committed by accident

A file removed in a *later* commit still lives in git history. Deleting it is not enough.

1. **Stop.** Do not push (or, if already pushed, do not let others pull) until it is resolved.
2. **Notify the project owner immediately.**
3. **Rotate anything exposed** — any leaked credential, key, or token must be treated as compromised
   and rotated, regardless of how briefly it was committed.
4. **Rewrite history** to remove the data (e.g. `git filter-repo` or BFG), then force-update the
   branch **only** with the owner's coordination. If the commit was already pushed and pulled,
   assume the data is compromised and handle it as an incident, not just a git cleanup.
5. Add or tighten `.gitignore` so the same class of file cannot be re-added.

---

## Scope

This policy covers data governance and repository hygiene for the prototype. It does not constitute
a production security program; if this project ever handles real data or is deployed, a proper
security review is required first.
