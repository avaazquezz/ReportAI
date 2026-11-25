# ChannelAdapter design note

`backend/app/services/channels/base.py` defines the contract every input
channel implements:

```python
class ChannelAdapter(ABC):
    channel_type: ClassVar[str]

    async def receive_message(self, payload: dict) -> IncomingMessage: ...
    async def send_message(self, message: OutgoingMessage) -> None: ...
    async def download_media(self, media_reference: str) -> bytes: ...
    async def acknowledge(self, callback_id: str) -> None: ...  # optional, a no-op by default
```

The implementations are `web` (the field app, `backend/app/services/channels/web.py`), `telegram`,
`email` (inbound through Mailgun, `backend/app/services/channels/email_inbound.py`) and `whatsapp`
(experimental).

## Why this shape

- **`receive_message`** normalizes a channel's raw webhook/event payload into
  a single `IncomingMessage` shape the agent pipeline understands, regardless
  of whether it came from Telegram, WhatsApp, or an inbound email. The
  original payload is kept in `raw_payload` for debugging. The `web` adapter
  doesn't implement it: the app sends its captures to `POST /capture`.
- **`download_media`** is separate from `receive_message` because a voice
  note's bytes usually need a second authenticated fetch (a Telegram
  `file_id`, a WhatsApp media URL, an email attachment) — `IncomingMessage`
  only carries an opaque `media_reference` until the pipeline actually needs
  the bytes. For `web`, the reference is the path of the uploaded file.
- **`send_message`** is intentionally dumb — it just sends. *When* it fires is
  decided by the agent pipeline, not by the adapter: nothing is delivered
  before the human-approval interrupt in the graph is resumed with a
  confirmation (see [report lifecycle](how-it-works/lifecycle.md)). For `web`
  it is a no-op: the person reads every answer in the app.
- **`acknowledge`** tells the channel a button press arrived (it stops
  Telegram's loading spinner); channels without buttons keep the default no-op.

## Adding a channel

Each new channel (later Slack or Microsoft Teams, on demand — see
`PROJECT_ROADMAP.md`) is:

1. one class implementing these methods, with its own `channel_type`;
2. a branch in `get_channel_adapter` (`backend/app/services/channels/factory.py`)
   that builds it from a `channel_connections` row;
3. a route that receives its webhooks, verifies them, and hands the parsed
   message to `ingest_message` (`backend/app/services/agent/ingestion.py`), as
   `backend/app/api/webhooks/` does for the existing ones.

The graph and the data model don't change: `channel_connections.channel_type`
is a free-form string, not a database enum.
