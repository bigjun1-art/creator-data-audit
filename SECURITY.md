# Security Policy

## Supported version

Only the latest commit on `main` is supported.

## Report a vulnerability

Use GitHub Private Vulnerability Reporting for credential exposure, cross-account data access, identity-matching bypass, unintended Feishu writes, command injection, unsafe browser execution, or leakage of creator/business data.

Do not publish secrets, creator identifiers, production URLs, source tables, HAR files, screenshots, logs, checkpoints, or exploit details in a public issue. Provide only a minimal sanitized reproduction, affected script, expected behavior, and impact.

## Credential and data model

This repository must never contain or request passwords, cookies, tokens, API keys, browser profile data, exported sessions, real creator lists, or customer data. Authentication remains in the user's local browser and supported CLI credential store. Generated run directories and evidence images are local artifacts and must not be committed.
