// Run from frontend/ after `npm run build`: npm run test:smoke
// Starts the built server and checks on real responses what tests/securityHeaders.test.ts can't:
// that every script Nuxt writes carries that response's own nonce, that the nonce changes on every
// response, and the headers around it (server/plugins/security-headers.ts).
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { after, before, test } from 'node:test'

const freePort = () =>
  new Promise((resolve, reject) => {
    const probe = createServer().listen(0, '127.0.0.1', () => {
      const { port } = probe.address()
      probe.close(() => resolve(port))
    })
    probe.on('error', reject)
  })

let server
let base

before(async () => {
  const port = await freePort()
  base = `http://127.0.0.1:${port}`
  server = spawn(process.execPath, ['.output/server/index.mjs'], {
    // The API on a closed port: server-side requests fail at once, and the pages render without it.
    env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', NUXT_PUBLIC_API_BASE: 'http://127.0.0.1:9' },
    stdio: 'inherit'
  })
  for (let tries = 0; ; tries++) {
    try {
      await fetch(`${base}/manifest.webmanifest`)
      return
    } catch (error) {
      if (tries === 100) throw error
      await new Promise((resolve) => setTimeout(resolve, 200))
    }
  }
})

after(() => server?.kill())

const page = async (path, headers = {}) => {
  const response = await fetch(base + path, { headers: { accept: 'text/html', ...headers }, redirect: 'manual' })
  const html = await response.text()
  const nonce = /'nonce-([^']+)'/.exec(response.headers.get('content-security-policy') ?? '')?.[1]
  return { response, html, nonce }
}

// The landing, a public page, the service worker's shell (never server-rendered) and the error page.
for (const path of ['/', '/login', '/app-shell', '/no-such-page']) {
  test(`${path}: every script tag carries the nonce its own policy names`, async () => {
    const { html, nonce } = await page(path)
    assert.ok(nonce, 'no nonce in the Content-Security-Policy')
    const scripts = html.match(/<script\b[^>]*>/gi) ?? []
    assert.ok(scripts.length > 0, 'no scripts at all: the page did not render')
    for (const tag of scripts) assert.ok(tag.includes(` nonce="${nonce}"`), `unsigned: ${tag.slice(0, 80)}`)
  })
}

test('the nonce changes on every response', async () => {
  const [first, second] = await Promise.all([page('/login'), page('/login')])
  assert.notEqual(first.nonce, second.nonce)
})

test('HSTS only when the proxy says the browser used HTTPS', async () => {
  assert.equal((await page('/login')).response.headers.get('strict-transport-security'), null)
  const secure = await page('/login', { 'x-forwarded-proto': 'https' })
  assert.equal(secure.response.headers.get('strict-transport-security'), 'max-age=31536000')
})

test('static files get the headers but no policy, and nothing names the framework', async () => {
  const asset = await fetch(`${base}/manifest.webmanifest`)
  assert.equal(asset.headers.get('x-content-type-options'), 'nosniff')
  assert.equal(asset.headers.get('x-frame-options'), 'DENY')
  assert.equal(asset.headers.get('content-security-policy'), null)
  assert.equal((await page('/login')).response.headers.get('x-powered-by'), null)
})
