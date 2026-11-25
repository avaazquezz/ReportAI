# 0002. The field app is the primary channel; chats are optional connectors

- **Status:** Accepted; supersedes the 2026-08-10 channel priority (Telegram, WhatsApp and email first)
- **Date:** 2026-11-06
- **Evidence:** `PROJECT_ROADMAP.md` §3 ("Field app (installable web app) as the primary channel;
  chat channels as optional connectors") and the 2026-11-06 log entry; commits `62a664a` (capture
  as a `web` channel, 2026-11-07) and `f08f000` (offline queue, 2026-11-08)

## Context

The first build (August 2026) took reports over Telegram, WhatsApp and inbound email, the channels
the audience already used. The roadmap records what that cost: the core flow depended on Meta or
Telegram, a report was reviewed in a chat instead of a form, a third-party platform held the voice
notes, and people had to install something to sign up.

## Decision

An installable web app is the primary way to capture and review reports. It enters the same
pipeline as any channel: one `web` connection per company (`backend/app/services/channels/web.py`),
captures through `POST /capture`, review in a form. Telegram, inbound email and WhatsApp
(experimental) remain as optional connectors.

## Alternatives considered

- **Chat-first, as in the first build.** Superseded for the reasons above.
- **A native app.** Out of scope (roadmap §6): only if recording on an iPhone stops with the screen
  locked and users suffer it.

## Consequences

- The app needs HTTPS (microphone, service worker), so a self-hosted server without a domain can't
  serve it.
- Captures are idempotent by a key made on the phone, and an offline queue keeps them
  ([field app offline](../how-it-works/field-app-offline.md)).
- In the app the form is the question: missing fields are highlighted instead of asked, and
  approval is a button that checks required fields ([report lifecycle](../how-it-works/lifecycle.md)).
- The `web` channel is exempt from "one active report per sender", so a technician can keep several
  drafts open.

## Revisit when

Users need something only a native app can do, such as reliable recording with the screen locked
on iOS.
