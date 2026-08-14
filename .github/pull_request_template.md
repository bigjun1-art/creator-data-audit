## What changed

Describe the smallest behavior change.

## Safety boundary

- [ ] Strict creator identity matching remains fail-closed.
- [ ] Platform access remains limited to the user's authorized logged-in session.
- [ ] No credentials, creator IDs, source tables, personal paths, screenshots, logs, HAR files, or business data are included.
- [ ] Checkpoint resume, count conservation, and Feishu readback still work.

## Verification

- [ ] `node scripts/validate-repository.mjs`
- [ ] No live platform write was used for CI or routine review.
