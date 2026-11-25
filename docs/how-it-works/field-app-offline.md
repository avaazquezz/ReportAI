# Field app offline

How a technician records a report with one bar of signal, or none, and how the recording reaches
the server without being lost or sent twice. The field app is the panel's own Nuxt build, installable
on a phone's home screen; it needs HTTPS (browsers block the microphone and service workers over
plain HTTP).

Two independent pieces do the work:

| Piece | Job | Code |
|---|---|---|
| Capture queue | Keeps every recording in IndexedDB until the server accepts it | `frontend/app/composables/useCaptureQueue.ts`, `frontend/app/utils/captureQueue.ts` |
| Service worker | Opens the app with no network | `frontend/modules/service-worker/sw.js`, `frontend/modules/service-worker/index.ts` |

The service worker never touches the API, and the queue never depends on the service worker.

## The capture queue

### Saving

`enqueue` writes the capture to the `captures` store of the `reportai` IndexedDB database
**before** trying to upload it, in a transaction opened with `durability: 'strict'`, so the
browser flushes it to disk before saying it's done: a dead battery right after recording doesn't
take the capture with it. On the first capture it also asks the browser for persistent storage
(`navigator.storage.persist()`), best effort, so the stored recordings are less likely to be
evicted.

Each queued capture carries:

| Field | Meaning |
|---|---|
| `id` | A UUID made on the phone: the report's id and the upload's `Idempotency-Key` |
| `documentTypeId`, `text`, `audio`, `photos` | The capture itself; audio and photos as `Blob`s |
| `ownerId` | The user id of the session that recorded it |
| `state` | `waiting`, `sending` (in memory only) or `failed` |
| `attempts`, `error` | How many uploads failed, and the server's reason for a refusal |

### Sending

`flush` sends every waiting capture of the signed-in person once, oldest first. It runs when:

- the queue loads, and after each new capture (unless the phone is offline);
- the browser fires `online`;
- the page becomes visible again (weak coverage that never dropped doesn't fire `online`);
- a different person signs in (their waiting captures can go up now).

A flush asked for while one is running schedules one more pass, so nothing added mid-flush waits
for the next trigger.

Each upload is a multipart `POST /capture` (`buildCaptureForm`) with the header
`Idempotency-Key: <id>`, and a timeout of 60 seconds plus one millisecond per 50 bytes of audio and
photos: a 10 MB upload at about 50 KB/s still fits, and a hung connection doesn't hold the queue.

What a failed upload means (`uploadOutcome`):

| Answer | Outcome |
|---|---|
| No HTTP answer at all (offline, dropped, timed out) | `retry`: back to `waiting` |
| `5xx`, `401`, `408`, `429` | `retry` (a 401 after the session renewal failed: the recording waits for the person to sign in again) |
| Any other `4xx` (a switched-off type, a plan limit, a bad photo) | `fail`: kept as `failed` with the server's message, for the person to retry or discard |

A capture is removed from IndexedDB only after the server accepted it.

### Exactly one report per capture

The server makes the `Idempotency-Key` the report's primary key (`backend/app/api/capture.py`,
`capture_report`):

- A second upload of the same capture (the first answer was lost, or two tabs sent it) finds the
  existing report and returns it with the same `202` body.
- Two uploads arriving at the same instant race on the primary key; the loser returns the report
  the winner made, or a `409` asking to try again in a moment if it isn't committed yet.
- A key that belongs to another person's report answers `409`: a capture can only replay its own
  report.

### Whose captures

A shared phone or tablet may hold captures of several people. The queue sends and shows only the
captures whose `ownerId` matches the user id in the session's own token (`useSessionUserId`, read
from the cookies, which all tabs share), never the profile a tab happens to display. With nobody
signed in, nothing is sent (`nextToSend`).

## The service worker

Its one job is opening the app with no coverage (`frontend/modules/service-worker/sw.js`):

- **Install** stores the app shell (`/app-shell`, a page rendered with no content, so the app can
  draw any page on the phone) and the build's files. The list is written into `sw.js` at build time
  by `frontend/modules/service-worker/index.ts`, with a version that is a hash of the files. All or
  nothing: if one file can't be stored, this version isn't installed and the previous one keeps
  working.
- **Navigation** asks the network first; if there is no answer within 4 seconds, it serves the
  stored shell.
- **Static files** in the list come from the cache.
- **The API**, and anything on another origin, always goes to the network.
- **Updates** never swap code under a recording: a new version waits until no page uses the old
  one (no `skipWaiting()`). `/sw.js` is served with `cache-control: no-cache`, so a fix reaches
  phones on their next visit.

The comment at the top of `sw.js` describes the emergency procedure if a released version ever
breaks the app on phones.

### What the app keeps for opening offline

So the capture screen opens with no coverage, the app keeps the last profile and document types
the API returned in `localStorage` under the `reportai_offline:` prefix
(`frontend/app/utils/offlineCopy.ts`). They are read only when the API can't be reached and only
for the person whose session it is (`offlineProfile`, `frontend/app/utils/session.ts`); signing
out, or the server ending the session, wipes them. The server still decides who is signed in:
nothing goes up without a valid token. If the API doesn't answer within 3 seconds
(`DEVICE_COPY_AFTER_MS`), the app opens with what the device kept and replaces it when the answer
arrives.

## Known limits

- Recording with the screen locked is verified on Android only; iPhone is untested (roadmap,
  "Known risks").
- The shell keeps the public settings (`NUXT_PUBLIC_*`) of the build that installed it; a change of
  them reaches phones only with the next release (the `ponytail:` note in `sw.js`).

## Tests

- `frontend/tests/captureQueue.test.ts`: the upload form, the retry/fail rule, owner filtering.
- `frontend/tests/session.test.ts`: token subject, unreachable detection, the offline profile.
- `backend/tests/test_capture.py`: idempotent captures, replay rules, photo and audio validation.
- `frontend/tests/securityHeaders.smoke.mjs`: the built server's CSP nonce and security headers.
