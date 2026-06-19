# Security

This is a personal, single-user project. It is published mainly to use free CI.

## Reporting

If you believe you have found a security issue (for example, a credential that
was accidentally committed), **do not open a public issue, pull request or
discussion that contains the secret value.** Public issues are world-readable
and would expose the secret further.

Instead, contact the maintainer privately and include only the minimum needed to
locate the problem (file path and line, never the full secret value).

## Secrets handling

- All credentials are read from environment variables / a local `.env` file.
- `.env` and any credential files are git-ignored and must never be committed.
- `.env.example` contains variable names only, never real values.
- CI uses repository **Secrets** (`Settings → Secrets and variables → Actions`);
  secrets are never written into workflow files or printed to logs.

## If a secret is ever exposed

1. **Rotate it immediately** at the provider (the old value is considered
   compromised the moment it touches a public repo — clones and caches persist).
2. Remove it from the working tree and history.
3. Replace the CI secret with the new value.
