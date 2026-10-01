# Installing ReportAI on your own server

One ReportAI installation serves one company, on a server it controls, with its own AI provider
account. This guide gets a technical person from an empty server to the first approved report.

## What you need

- A Linux server (2 vCPU, 4 GB RAM, 20 GB disk is plenty) with Docker 24+ and the Compose plugin.
  The installer offers to install Docker if it is missing.
- **Optional but recommended:** a domain or subdomain (`reportes.empresa.com`) pointing at the
  server, with ports 80 and 443 open. You get HTTPS with a free certificate, renewed on its own.
  Without a domain, the panel is served over plain HTTP on the server's IP: only acceptable on a
  private network or behind a VPN.
- An API key for the AI that reads the messages: Anthropic (recommended), OpenAI, DeepSeek or
  any OpenAI-compatible provider. Each report costs a few cents, billed to that account.
- **For voice notes:** an API key for a transcription service (Groq recommended: fast and cheap).
- **Optional:** an SMTP account to email reports, invitations and password resets.
- **For Telegram:** a bot, created in a minute with [@BotFather](https://t.me/BotFather).

## 1. Install

On the server, as root:

```sh
curl -fsSL https://raw.githubusercontent.com/avaazquezz/ReportAI/main/infra/install/install.sh | sudo bash
```

It asks for the domain (leave it empty to use the server's IP), then:

- writes everything to `/opt/reportai` — `docker-compose.yml`, `Caddyfile`, and `.env` with
  random secrets generated on the spot;
- installs the `reportai` command;
- starts ReportAI and waits until it answers;
- prints the panel's address and a **one-time setup code**.

Non-interactive: `… | sudo bash -s -- --domain reportes.empresa.com --yes`. Other options:
`--version X.Y.Z`, `--dir PATH`, `--http-port N`, `--https-port N` (see the top of `install.sh`).

Running the installer again keeps the existing settings and data.

## 2. Set it up in the browser

Open the address it printed. The setup wizard asks for:

1. **The setup code** from the terminal. Lost it, or it expired (24 h)? Run `reportai setup-code`.
2. **The company** (name, language, time zone) and **your administrator account**.
3. **The AI provider and its key**, and the **transcription service** — each with a *Test* button
   that makes one tiny real call, so a wrong key shows up now and not on the first report.
4. **Email** (optional) — with a *Send a test email* button.
5. **The Telegram bot token** (optional) — checked with Telegram before it is saved.

Keys and tokens are stored encrypted with the server's `ENCRYPTION_KEY`.

## 3. Before the first report

The dashboard's *First steps* list says what is left:

- **A template.** Under *Document types*, either start from a ready-made one (work order, site
  visit, incident report — with your logo and in your language) or create a type and upload a
  Word document you already fill in by hand: the template assistant proposes the fields and where
  each one goes, you correct it, preview it as a PDF and apply it.
- **People who send reports.** Under *Channels*, *Invite* creates a one-time link for each person
  (Telegram: opening it is all they do). Nobody copies chat ids.
- **Your team in the panel.** Under *Team*, invite admins, approvers (review, correct, approve,
  resend) and read-only viewers.
- **Your logo and colour**, under *Settings → Company*: used in emails and, through
  `{{ branding.logo }}` and `{{ branding.name }}`, in templates.

Then send the bot a voice note describing a job. The report comes back for confirmation, and
the PDF arrives in the chat and in the inboxes set on its document type.

## How it fits together

| Service | What it does |
| --- | --- |
| `caddy` | The only open ports (80/443). HTTPS for the domain; `/api/*` → backend, the rest → panel |
| `frontend` | The panel (Nuxt) |
| `backend` | The API (FastAPI) |
| `worker` | Runs the reports: transcription, the AI, rendering, delivery. Polls Telegram when there is no domain |
| `migrate` | Applies database migrations, then exits — on every start and every update |
| `postgres` | The data. Volume `reportai_database` |
| `gotenberg` | Word → PDF |

Uploaded templates, photos, audio and generated PDFs live in the volume `reportai_storage`.

**Telegram without a domain:** with no public address Telegram cannot call the server, so the
worker asks Telegram for new messages instead (long polling). Nothing has to be reachable from the
internet. With a domain, Telegram calls a webhook — faster and lighter.

## Uninstalling

```sh
cd /opt/reportai && docker compose down -v   # -v also deletes the data: only if you mean it
rm -rf /opt/reportai /usr/local/bin/reportai
```
