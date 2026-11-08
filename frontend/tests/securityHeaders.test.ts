// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { SECURITY_HEADERS, contentSecurityPolicy, signScripts } from '../server/utils/securityHeaders.ts'

const directive = (policy: string, name: string) =>
  policy.split('; ').find((part) => part.split(' ')[0] === name)

test('every script tag the renderer wrote carries the nonce', () => {
  const head =
    '<script type="importmap">{"imports":{}}</script><script>window.__NUXT__={}</script>' +
    '<script type="module" src="/_nuxt/entry.js" crossorigin></script><SCRIPT>x</SCRIPT>'
  assert.equal(
    signScripts(head, 'abc'),
    '<script nonce="abc" type="importmap">{"imports":{}}</script><script nonce="abc">window.__NUXT__={}</script>' +
      '<script nonce="abc" type="module" src="/_nuxt/entry.js" crossorigin></script><script nonce="abc">x</SCRIPT>'
  )
})

test('nothing but script tags is touched, and a signed tag is not signed twice', () => {
  const html = '<style>a{}</style><noscript><style>b{}</style></noscript><scripts></scripts><script nonce="old">y</script>'
  assert.equal(signScripts(html, 'abc'), html)
})

test('scripts run only from this origin or with this response\'s nonce, never from eval or inline markup', () => {
  const scripts = directive(contentSecurityPolicy('n0nce+/=', '/api'), 'script-src')
  assert.equal(scripts, "script-src 'self' 'nonce-n0nce+/='")
})

test('a relative API base is this origin; an absolute one adds its origin, without the path', () => {
  assert.equal(directive(contentSecurityPolicy('n', '/api'), 'connect-src'), "connect-src 'self'")
  assert.equal(
    directive(contentSecurityPolicy('n', 'http://localhost:8000'), 'connect-src'),
    "connect-src 'self' http://localhost:8000"
  )
  assert.equal(
    directive(contentSecurityPolicy('n', 'https://api.example.com/v1/'), 'connect-src'),
    "connect-src 'self' https://api.example.com"
  )
})

test('the panel can never be framed, and plugins and <base> stay out', () => {
  const policy = contentSecurityPolicy('n', '/api')
  assert.equal(directive(policy, 'frame-ancestors'), "frame-ancestors 'none'")
  assert.equal(directive(policy, 'object-src'), "object-src 'none'")
  assert.equal(directive(policy, 'base-uri'), "base-uri 'self'")
})

test('what the field app needs is allowed: recordings, photos, PDF previews, the service worker, the microphone', () => {
  const policy = contentSecurityPolicy('n', '/api')
  assert.match(directive(policy, 'media-src')!, /blob:/)
  assert.match(directive(policy, 'img-src')!, /blob:/)
  assert.match(directive(policy, 'frame-src')!, /blob:/)
  assert.equal(directive(policy, 'worker-src'), "worker-src 'self'")
  assert.match(SECURITY_HEADERS['Permissions-Policy']!, /microphone=\(self\)/)
})
