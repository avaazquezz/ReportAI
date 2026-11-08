// What the offline queue (composables/useCaptureQueue.ts) uploads, and what a failed upload means.
// Pure, so it can be checked on its own (tests/captureQueue.test.ts).
import type { Capture, QueuedCapture } from '~/composables/useCaptureQueue'

// The rest follow the subtype (webm, ogg, png, webp...). The API reads the format from the part's
// content type; the file name only has to agree with it.
const EXTENSIONS: Record<string, string> = { 'audio/mp4': 'm4a', 'image/jpeg': 'jpg' }

function extension(type: string): string {
  const mime = type.split(';')[0]!.trim().toLowerCase() // Chrome says "audio/webm;codecs=opus"
  return EXTENSIONS[mime] ?? (mime.split('/')[1] || 'bin')
}

/** The multipart body of POST /capture. */
export function buildCaptureForm(capture: Capture): FormData {
  const form = new FormData()
  form.append('document_type_id', capture.documentTypeId)
  if (capture.text) form.append('text', capture.text)
  if (capture.audio) form.append('audio', capture.audio, `recording.${extension(capture.audio.type)}`)
  capture.photos.forEach((photo, index) => form.append('photos', photo, `photo-${index + 1}.${extension(photo.type)}`))
  return form
}

function statusOf(error: unknown): number | undefined {
  const err = error as { response?: Response; statusCode?: number; status?: number } | null | undefined
  return err?.response?.status ?? err?.statusCode ?? err?.status
}

// 401 too: useApi has already tried to renew the session, and a recording is never dropped for
// that. Once the person signs in again, the queue sends it.
const TRANSIENT = [401, 408, 429]

/** A failed upload with no answer (offline), or one the server may take later: try again. Any
 * other refusal stays in the queue as failed, for the person to retry or discard. */
export function uploadOutcome(error: unknown): 'retry' | 'fail' {
  const status = statusOf(error)
  return !status || status >= 500 || TRANSIENT.includes(status) ? 'retry' : 'fail'
}

/** The server's reason, when it gave one as a sentence (402 is already in the company's language). */
export function failureMessage(error: unknown): string | null {
  const detail = (error as { data?: { detail?: unknown } } | null | undefined)?.data?.detail
  return typeof detail === 'string' ? detail : null
}

/** The oldest waiting capture of this person that this pass hasn't tried yet. Never anyone else's:
 * with nobody signed in, nothing is sent. */
export function nextToSend(
  items: readonly QueuedCapture[],
  ownerId: string | null,
  tried: ReadonlySet<string>
): QueuedCapture | undefined {
  if (!ownerId) return undefined
  return items.find((item) => item.ownerId === ownerId && item.state === 'waiting' && !tried.has(item.id))
}
