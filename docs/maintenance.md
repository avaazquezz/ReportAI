# Maintaining a ReportAI installation

**Keeping an installation updated is the job of whoever installed it and maintains it** — the
company's own IT, or whoever it contracts for that. ReportAI does not update itself and nobody
updates it remotely: a security fix protects a company only once its installation runs it.

## Updates

The panel's *Settings → Version* (and a notice on the dashboard) says when a new release is out.
When a published security advisory affects the installed version, every page shows a red notice
to the installation's administrator until it is updated.

To update, on the server:

```sh
reportai update            # to the latest release
reportai update 1.4.2      # to a specific one
```

It saves a dump of the database to `/opt/reportai/backups/`, downloads the new version, applies
the database migrations and restarts, then checks that ReportAI answers. If the new version does
not start, it shows the logs and says how to go back: set the previous `REPORTAI_VERSION` in
`.env`, restore the dump, `reportai restart`. Going back a version is refused unless you pass
`--force`, because database migrations are not undone.

`--skip-backup` skips the dump (when you have just taken your own).

## Security advisories

Advisories are published as GitHub Security Advisories on the repository and listed in
[`security/advisories.json`](../security/advisories.json), with the versions they affect and the
one that fixes them. Installations check that file at most every 6 hours. See
[`SECURITY.md`](../SECURITY.md) to report a vulnerability.

Turn the check off with `UPDATE_CHECK_ENABLED=false` in `.env` (the server then never contacts
GitHub, and nobody is told about fixes: you have to watch the releases yourself).

## Backups

Backing up is the server's own job, not ReportAI's: the dump `reportai update` takes is a way back
from a bad update, not a backup. What to back up, off this server:

- the database (volume `reportai_database`, or `pg_dump` from the `postgres` service);
- the files (volume `reportai_storage`: templates, photos, audio, PDFs);
- `/opt/reportai/.env` — **without its `ENCRYPTION_KEY` the stored AI keys, mail password and bot
  tokens cannot be read**, and have to be entered again.

## Everyday commands

| Command | |
| --- | --- |
| `reportai status` | What is running, the version and the address |
| `reportai logs [service]` | Follow the logs (`backend`, `worker`, `frontend`, `caddy`…) |
| `reportai restart` / `reportai stop` | |
| `reportai setup-code` | A new code for the setup wizard (only before the first administrator exists) |
| `reportai password-link EMAIL` | A one-hour link to set a new password, for when email is not set up |

## Changing things later

- **AI provider, keys, mail server:** in the panel, *Settings → AI and voice / Email*. Values
  there win over `.env`.
- **Adding a domain later:** set `SITE_ADDRESS=reportes.empresa.com`,
  `FRONTEND_ORIGIN=https://reportes.empresa.com`, `PUBLIC_BASE_URL=https://reportes.empresa.com`
  and `SECURE_COOKIES=true` in `.env`, then `reportai restart`. Telegram bots switch to the
  webhook on their own when the worker starts.
- **Rotating `SECRET_KEY`** signs everybody out. **Changing `ENCRYPTION_KEY`** makes the stored
  keys unreadable: enter them again in the panel afterwards.

## Publishing a release (maintainers of ReportAI itself)

1. Tag the commit: `git tag v1.4.2 && git push origin v1.4.2`.
2. The *Publish images* workflow builds `ghcr.io/avaazquezz/reportai-backend:1.4.2` and
   `…/reportai-frontend:1.4.2` with the version baked in, and creates the GitHub release that
   installations compare themselves with.
3. For a security fix, also add the advisory to `security/advisories.json` on `main` and publish
   the GitHub Security Advisory.
