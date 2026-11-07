// Captures recorded in the app that the server hasn't accepted yet, kept in IndexedDB so a report
// recorded without coverage (or right before the battery dies) is never lost. Two tabs may send
// the same capture: harmless, its Idempotency-Key makes the server return the report it made.

export interface Capture {
  id: string
  documentTypeId: string
  text: string | null
  audio: Blob | null
  photos: Blob[]
}

export interface QueuedCapture extends Capture {
  createdAt: number
  attempts: number
  state: 'waiting' | 'sending' | 'failed'
  error: string | null
}

export type EnqueueResult = { state: 'sent' } | { state: 'queued' } | { state: 'failed'; error: string | null }

const STORE = 'captures'
// No answer within this is treated like no coverage (retried). It grows with the upload: 10 MB at
// ~50 KB/s (a weak 3G link) still fits, while a hung connection doesn't keep the queue forever.
const uploadTimeout = (item: Capture) =>
  60_000 + Math.ceil(((item.audio?.size ?? 0) + item.photos.reduce((sum, photo) => sum + photo.size, 0)) / 50)

let database: Promise<IDBDatabase> | null = null

function openDatabase(): Promise<IDBDatabase> {
  database ??= new Promise((resolve, reject) => {
    const request = indexedDB.open('reportai', 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'id' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  return database
}

// Resolves once the transaction has committed. 'strict' asks the browser to flush it to disk
// before saying so: a dead battery right after recording must not take the capture with it.
async function inStore<T>(mode: IDBTransactionMode, run: (captures: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDatabase()
  return await new Promise((resolve, reject) => {
    const transaction = db.transaction(STORE, mode, { durability: 'strict' })
    const request = run(transaction.objectStore(STORE))
    transaction.oncomplete = () => resolve(request.result)
    transaction.onabort = () => reject(transaction.error)
  })
}

const save = (item: QueuedCapture) => inStore('readwrite', (captures) => captures.put(item))
const remove = (id: string) => inStore('readwrite', (captures) => captures.delete(id))

// One queue per app. Plain objects swapped whole in a shallowRef: IndexedDB can't store a Vue proxy.
const items = shallowRef<QueuedCapture[]>([])
let api: Api | null = null
let ready: Promise<void> | null = null
let flushing: Promise<void> | null = null
let again = false
let persistAsked = false

const find = (id: string) => items.value.find((item) => item.id === id)

function replace(item: QueuedCapture) {
  items.value = items.value.map((other) => (other.id === item.id ? item : other))
}

async function load() {
  const stored = await inStore('readonly', (captures) => captures.getAll() as IDBRequest<QueuedCapture[]>)
  items.value = stored.sort((a, b) => a.createdAt - b.createdAt)
}

async function send(item: QueuedCapture) {
  const body = buildCaptureForm(item)
  // 'sending' lives only in memory: a tab closed mid-upload leaves the capture 'waiting' on disk.
  replace({ ...item, state: 'sending' })
  try {
    await api!('/capture', { method: 'POST', body, headers: { 'Idempotency-Key': item.id }, timeout: uploadTimeout(item) })
  } catch (error) {
    if (!find(item.id)) return // discarded while it was on its way
    const failed = uploadOutcome(error) === 'fail'
    const next: QueuedCapture = {
      ...item,
      attempts: item.attempts + 1,
      state: failed ? 'failed' : 'waiting',
      error: failed ? failureMessage(error) : null
    }
    replace(next)
    await save(next)
    return
  }
  items.value = items.value.filter((other) => other.id !== item.id)
  await remove(item.id)
}

// Every waiting capture once, oldest first; one that fails again waits for the next flush.
async function drain() {
  const tried = new Set<string>()
  for (;;) {
    const next = items.value.find((item) => item.state === 'waiting' && !tried.has(item.id))
    if (!next || !navigator.onLine) return
    tried.add(next.id)
    await send(next)
  }
}

function flush(): Promise<void> {
  // Asked again mid-flush (a capture just queued, a retry): one more pass once this one ends, so
  // nothing added after the pass last looked is left waiting.
  if (flushing) {
    again = true
    return flushing
  }
  flushing = (async () => {
    await ready
    do {
      again = false
      await drain()
    } while (again)
  })().finally(() => (flushing = null))
  return flushing
}

async function enqueue(capture: Capture): Promise<EnqueueResult> {
  await ready
  if (!persistAsked) {
    persistAsked = true
    // Best effort, so the browser is less likely to evict the stored recordings (Safari is the
    // strictest). Asked on the first capture, not on load: a browser that asks the person about it
    // asks right after they did something, not out of nowhere.
    void navigator.storage?.persist?.()
  }
  // photos copied: an array held in a ref() is a proxy, which IndexedDB can't store.
  const item: QueuedCapture = { ...capture, photos: [...capture.photos], createdAt: Date.now(), attempts: 0, state: 'waiting', error: null }
  await save(item)
  items.value = [...items.value, item]
  if (!navigator.onLine) return { state: 'queued' }
  await flush()
  const after = find(item.id)
  if (!after) return { state: 'sent' }
  return after.state === 'failed' ? { state: 'failed', error: after.error } : { state: 'queued' }
}

async function retry(id: string) {
  await ready
  const item = find(id)
  if (item?.state === 'failed') {
    const next: QueuedCapture = { ...item, state: 'waiting', error: null }
    replace(next)
    await save(next)
  }
  await flush()
}

async function discard(id: string) {
  await ready
  items.value = items.value.filter((item) => item.id !== id)
  await remove(id)
}

/** The app's offline queue of captures. On the server it stays empty and never loads or sends. */
export function useCaptureQueue() {
  if (import.meta.client && !api) {
    // Kept for good: useApi() needs the Nuxt context, which an 'online' event doesn't have.
    api = useApi()
    ready = load()
    void flush()
    window.addEventListener('online', () => void flush())
    // 'online' only fires when the network changes; weak coverage that never dropped doesn't fire
    // it. Coming back to the app is the other natural moment to try again.
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') void flush()
    })
  }
  return { items: items as Readonly<Ref<QueuedCapture[]>>, enqueue, flush, retry, discard }
}
