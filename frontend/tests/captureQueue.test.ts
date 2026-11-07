// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildCaptureForm, failureMessage, uploadOutcome } from '../app/utils/captureQueue.ts'

const typeId = '7d1c6f1e-2b8a-4c3e-9f41-0a6c5e2d8b10'
const file = (form: FormData, key: string) => form.get(key) as File

test('the form carries the document type, the text, the recording and every photo', () => {
  const form = buildCaptureForm({
    id: 'ignored',
    documentTypeId: typeId,
    text: 'Fuga en la sala de calderas',
    audio: new Blob(['voice'], { type: 'audio/webm;codecs=opus' }),
    photos: [new Blob(['a'], { type: 'image/jpeg' }), new Blob(['b'], { type: 'image/png' })]
  })
  assert.equal(form.get('document_type_id'), typeId)
  assert.equal(form.get('text'), 'Fuga en la sala de calderas')
  assert.equal(file(form, 'audio').name, 'recording.webm')
  assert.equal(file(form, 'audio').type, 'audio/webm;codecs=opus')
  assert.deepEqual(
    (form.getAll('photos') as File[]).map((photo) => photo.name),
    ['photo-1.jpg', 'photo-2.png']
  )
  assert.equal(form.has('id'), false) // the id travels as the Idempotency-Key header
})

test("the recording's extension follows the browser's format", () => {
  const name = (type: string) =>
    file(buildCaptureForm({ id: 'x', documentTypeId: typeId, text: null, audio: new Blob(['v'], { type }), photos: [] }), 'audio').name
  assert.equal(name('audio/mp4'), 'recording.m4a')
  assert.equal(name('audio/ogg;codecs=opus'), 'recording.ogg')
  assert.equal(name('audio/webm'), 'recording.webm')
})

test('nothing typed, nothing recorded: neither field is sent', () => {
  const form = buildCaptureForm({ id: 'x', documentTypeId: typeId, text: null, audio: null, photos: [] })
  assert.deepEqual([...form.keys()], ['document_type_id'])
})

test('no answer at all (offline, network error) is retried', () => {
  assert.equal(uploadOutcome(new TypeError('fetch failed')), 'retry')
  assert.equal(uploadOutcome({ response: undefined }), 'retry')
  assert.equal(uploadOutcome(undefined), 'retry')
})

test('server trouble, a timeout, throttling and an expired session are retried', () => {
  for (const status of [500, 502, 503, 504, 408, 429, 401]) {
    assert.equal(uploadOutcome({ response: new Response(null, { status }) }), 'retry', String(status))
  }
})

test('every other refusal fails, however the status is reported', () => {
  for (const status of [400, 402, 403, 404, 409, 422]) {
    assert.equal(uploadOutcome({ response: new Response(null, { status }) }), 'fail', String(status))
    assert.equal(uploadOutcome({ statusCode: status }), 'fail', `statusCode ${status}`)
    assert.equal(uploadOutcome({ status }), 'fail', `status ${status}`)
  }
  assert.equal(uploadOutcome({ statusCode: 503 }), 'retry')
})

test("the server's reason is shown only when it is a sentence", () => {
  assert.equal(failureMessage({ data: { detail: 'Your plan has no reports left this month' } }), 'Your plan has no reports left this month')
  assert.equal(failureMessage({ data: { detail: [{ loc: ['body', 'document_type_id'], msg: 'Field required' }] } }), null)
  assert.equal(failureMessage(new TypeError('fetch failed')), null)
  assert.equal(failureMessage(null), null)
})
