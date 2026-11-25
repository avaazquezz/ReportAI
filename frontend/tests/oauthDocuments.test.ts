// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { createServer, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { test } from 'node:test'
import { fetchOAuthDocument, isMcpResourcePath, oauthDocumentUrl, RelayFailure } from '../server/utils/oauthDocuments.ts'

test("inside Docker the API's internal address is used, whatever the public base", () => {
  assert.equal(oauthDocumentUrl('http://backend:8000', '/api', '/oauth/metadata'), 'http://backend:8000/oauth/metadata')
  assert.equal(oauthDocumentUrl('http://backend:8000/', '/api', '/oauth/protected-resource'), 'http://backend:8000/oauth/protected-resource')
})

test('in development the public base is absolute and is used', () => {
  assert.equal(oauthDocumentUrl('', 'http://localhost:8000', '/oauth/metadata'), 'http://localhost:8000/oauth/metadata')
})

test('a relative public base with no internal one is a misconfiguration, not a guess', () => {
  assert.equal(oauthDocumentUrl('', '/api', '/oauth/metadata'), null)
})

test("the protected resource's document is at the MCP server's own path only", () => {
  // Behind the proxy the API, and so the MCP server, lives under /api.
  assert.equal(isMcpResourcePath('api/mcp', '/api'), true)
  assert.equal(isMcpResourcePath('api/mcp/', '/api/'), true)
  assert.equal(isMcpResourcePath('mcp', '/api'), false)
  assert.equal(isMcpResourcePath('api/other', '/api'), false)
  assert.equal(isMcpResourcePath('api/mcp/extra', '/api'), false)
  assert.equal(isMcpResourcePath('', '/api'), false)
  // In development the public base is the API's own address, at the root.
  assert.equal(isMcpResourcePath('mcp', 'http://localhost:8000'), true)
  assert.equal(isMcpResourcePath('api/mcp', 'http://localhost:8000'), false)
})

async function serving(handler: Parameters<typeof createServer>[1]): Promise<{ base: string; server: Server }> {
  const server = createServer(handler)
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  return { base: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, server }
}

async function failure(promise: Promise<unknown>): Promise<RelayFailure> {
  try {
    await promise
  } catch (error) {
    assert.ok(error instanceof RelayFailure, String(error))
    return error
  }
  assert.fail('the relay did not fail')
}

test("the API's answer is passed on as it is: status, type, caching and body", async () => {
  const { base, server } = await serving((_, response) => {
    response.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'max-age=60' }).end('<p>Not found</p>')
  })
  try {
    const relayed = await fetchOAuthDocument(base, '/api', '/oauth/metadata')

    assert.deepEqual(relayed, { status: 404, contentType: 'text/html; charset=utf-8', cacheControl: 'max-age=60', body: '<p>Not found</p>' })
  } finally {
    server.close()
  }
})

test('an API that never answers is a 502 at the deadline, logged with its address', async (t) => {
  const logged = t.mock.method(console, 'error', () => {})
  const { base, server } = await serving(() => {}) // takes the request, never answers
  try {
    const started = Date.now()
    const refused = await failure(fetchOAuthDocument(base, '/api', '/oauth/metadata', 100))

    assert.equal(refused.statusCode, 502)
    assert.ok(Date.now() - started < 2000)
    assert.equal(logged.mock.callCount(), 1)
    assert.match(String(logged.mock.calls[0]?.arguments[0]), new RegExp(`${base}/oauth/metadata`))
    assert.ok(logged.mock.calls[0]?.arguments[1] instanceof Error) // the cause
  } finally {
    server.closeAllConnections()
    server.close()
  }
})

test('an API that is down is a 502, logged', async (t) => {
  const logged = t.mock.method(console, 'error', () => {})
  const { base, server } = await serving(() => {})
  await new Promise((resolve) => server.close(resolve)) // nothing listens there any more

  const refused = await failure(fetchOAuthDocument(base, '/api', '/oauth/protected-resource'))

  assert.equal(refused.statusCode, 502)
  assert.match(String(logged.mock.calls[0]?.arguments[0]), /\/oauth\/protected-resource/)
})

test('no address to reach the API from is a 500, logged before it is answered', async (t) => {
  const logged = t.mock.method(console, 'error', () => {})

  const refused = await failure(fetchOAuthDocument('', '/api', '/oauth/metadata'))

  assert.equal(refused.statusCode, 500)
  assert.equal(logged.mock.callCount(), 1)
  assert.match(String(logged.mock.calls[0]?.arguments[0]), /NUXT_API_BASE_SERVER/)
})
