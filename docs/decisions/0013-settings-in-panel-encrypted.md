# 0013. Settings entered in the panel, encrypted at rest

- **Status:** Accepted
- **Date:** 2026-10-01
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Secrets in environment variables or encrypted in the
  database, never committed"); commits `d491221` ("encrypt channel tokens at rest", 2026-10-01) and
  `c08e5e8` ("enter the AI provider, transcription and mail server in the panel, stored encrypted
  and tried before saving", 2026-10-01); the docstring of `backend/app/core/crypto.py`

## Context

A company installing ReportAI on its own server should not need a shell to change its AI key or
mail server, and its credentials must not be readable from a database dump or a backup.

## Decision

- The AI provider, transcription service, mail server and Telegram bot tokens are entered in the
  panel (the setup wizard, then *Settings*), each with a check that makes one real call, so a
  wrong key shows up when it is entered and not on the first report.
- Secrets are encrypted with Fernet under a key derived by HKDF from `ENCRYPTION_KEY` (or from
  `SECRET_KEY` on installations made before it existed). The key lives only in the server's
  environment.
- A value saved in the panel wins over the environment variable of the same name, so an
  installation configured through `.env` keeps working.

## Alternatives considered

- (Reconstructed.) **Environment variables only.** Every change would need shell access and a
  restart.
- (Reconstructed.) **Plaintext in the database.** A stolen dump would hand over every credential.

## Consequences

- Losing or changing `ENCRYPTION_KEY` makes stored secrets unreadable; decryption fails loud with
  `UndecryptableSecretError`, and they have to be entered again. Back up `.env` apart from the
  dumps ([Operations](../operations.md#backups-and-restore)).
- Sealed links (the MCP PDF link, the OAuth consent request) use a separate derived key, so a link
  token never opens a stored secret.

## Revisit when

An installation needs a key-management service or key rotation without re-entering secrets.
