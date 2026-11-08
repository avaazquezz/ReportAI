// ReportAI's service worker, with one job: opening the app with no coverage. The build prepends
// VERSION and PRECACHE (modules/service-worker/index.ts). It never touches the API: a capture made
// offline waits in the page's own queue (composables/useCaptureQueue.ts), not here.
//
// Lifecycle: a new version installs next to the old one and waits until no page uses the old one,
// so the app never swaps its code under a recording. No skipWaiting() on purpose.
//
// If a released version ever breaks the app on phones: release one whose sw.js only calls
// self.registration.unregister() and deletes the reportai-* caches on activate (with skipWaiting()
// there). Browsers fetch /sw.js on every visit (no-cache), so it reaches them on their next one.
/* global VERSION, PRECACHE */

const CACHE = `reportai-${VERSION}`
const PRECACHED = new Set(PRECACHE)
// Rendered by the server with this installation's settings, but with no page in it: answered for
// any page asked for with no network, the app then draws that page on the phone.
const SHELL = '/app-shell'
// On weak coverage a page that takes longer than this opens from the phone instead, and the app
// then talks to the API by itself.
const NAVIGATION_TIMEOUT_MS = 4000

self.addEventListener('install', (event) => event.waitUntil(fill()))

// All or nothing: if one file can't be stored, this version isn't installed and the previous one
// keeps working.
async function fill() {
  const cache = await caches.open(CACHE)
  await Promise.all(PRECACHE.map((url) => keep(cache, url)))
  const shell = await fetch(SHELL, { cache: 'no-store' })
  if (!shell.ok) throw new Error(`${SHELL} answered ${shell.status}`)
  await cache.put(SHELL, shell)
}

async function keep(cache, url) {
  if (await cache.match(url)) return
  // The build names its files after their content: the copy a previous version keeps is the same
  // file, so it isn't downloaded again. Root files (icons, manifest) keep their name when they change.
  const hashed = url.startsWith('/_nuxt/')
  const held = hashed ? await caches.match(url) : undefined
  if (held) return cache.put(url, held)
  const response = await fetch(url, { cache: hashed ? 'default' : 'no-cache' })
  if (!response.ok) throw new Error(`${url} answered ${response.status}`)
  await cache.put(url, response)
}

self.addEventListener('activate', (event) => event.waitUntil(dropOldVersions()))

async function dropOldVersions() {
  const names = await caches.keys()
  await Promise.all(names.filter((name) => name.startsWith('reportai-') && name !== CACHE).map((name) => caches.delete(name)))
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  // The API (and the documents it serves) always goes to the network, whatever happens.
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  if (request.mode === 'navigate') event.respondWith(navigate(request))
  else if (PRECACHED.has(url.pathname)) event.respondWith(fromCache(request))
})

// The server's page whenever it answers in time, exactly as without a service worker; otherwise the
// app from the phone.
async function navigate(request) {
  const network = fetch(request)
  const answer = await Promise.race([network, timeout(NAVIGATION_TIMEOUT_MS)]).catch(() => null)
  if (answer) return answer
  const shell = await (await caches.open(CACHE)).match(SHELL)
  // Nothing kept yet (the first visit is still installing): the browser shows what it always shows.
  return shell ?? network
}

const timeout = (ms) => new Promise((resolve) => setTimeout(resolve, ms, null))

async function fromCache(request) {
  return (await (await caches.open(CACHE)).match(request)) ?? fetch(request)
}
