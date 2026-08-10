# ChannelAdapter design note

`backend/app/services/channels/base.py` defines the contract every input
channel implements:

```python
class ChannelAdapter(ABC):
    channel_type: ClassVar[str]

    async def receive_message(self, payload: dict) -> IncomingMessage: ...
    async def send_message(self, message: OutgoingMessage) -> None: ...
    async def download_media(self, media_reference: str) -> bytes: ...
```

## Why this shape

- **`receive_message`** normalizes a channel's raw webhook/event payload into
  a single `IncomingMessage` shape the agent pipeline understands, regardless
  of whether it came from Telegram, WhatsApp, or an inbound email. The
  original payload is kept in `raw_payload` for debugging.
- **`download_media`** is separate from `receive_message` because a voice
  note's bytes usually need a second authenticated fetch (a Telegram
  `file_id`, a WhatsApp media URL, an email attachment) — `IncomingMessage`
  only carries an opaque `media_reference` until the pipeline actually needs
  the bytes.
- **`send_message`** is intentionally dumb — it just sends. *When* it fires
  (immediately after rendering, or only after a human approves the draft) is
  controlled entirely by the Phase 1 agent pipeline, not by the adapter. This
  interface doesn't decide whether a human-approval checkpoint sits before
  delivery — that's an explicit open question for Phase 1's own plan.

## Adding a channel

Each new channel (Telegram, WhatsApp Business Cloud API, email-in, and later
Slack/Microsoft Teams on demand — see `PROJECT_ROADMAP.md`) is one class
implementing these three methods, registered with its own `channel_type`.
Nothing in the agent core or the data model changes to add a channel — see
`channel_connections.channel_type`, a free-form string, not a DB enum.
