# Contributing

Keep changes small, reviewable, and safe by default.

1. Do not commit real creator names, account IDs, platform IDs, source sheets, Feishu tokens, URLs, screenshots, HAR files, logs, checkpoints, cookies, tokens, or personal absolute paths.
2. Preserve strict identity matching. Ambiguous accounts must remain unresolved rather than being guessed.
3. Keep platform reads parameterized, resumable, and limited to the user's authorized logged-in session.
4. Keep Feishu writes serial, explicitly targeted, count-checked, and followed by readback.
5. Add or update offline tests for parser, matching, checkpoint, evidence, or publishing changes.
6. Run `node scripts/validate-repository.mjs` before proposing a change.
7. Report vulnerabilities privately according to `SECURITY.md`.
