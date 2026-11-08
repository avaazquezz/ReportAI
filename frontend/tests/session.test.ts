// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { User } from '../app/types/index.ts'
import { isUnreachable, offlineProfile, tokenSubject } from '../app/utils/session.ts'

const base64url = (value: object) =>
  btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const token = (claims: object) => `${base64url({ alg: 'HS256' })}.${base64url(claims)}.signature`

const ana: User = { id: 'ana-id', email: 'ana@qa.test', full_name: 'Ana', role: 'technician', tenant_id: 't1', is_demo: false }
const noAnswer = Object.assign(new Error('fetch failed'), { name: 'FetchError', response: undefined })
const answered = (status: number) => Object.assign(new Error(String(status)), { name: 'FetchError', response: new Response(null, { status }) })

test("a session token's user is read from its claims", () => {
  assert.equal(tokenSubject(token({ sub: 'ana-id', type: 'refresh' })), 'ana-id')
  // base64url without padding, with the characters base64 writes as + and /
  assert.equal(tokenSubject(token({ sub: '>>>???', ver: 1 })), '>>>???')
})

test('no token, or one this app never issued, belongs to nobody', () => {
  assert.equal(tokenSubject(null), null)
  assert.equal(tokenSubject(undefined), null)
  assert.equal(tokenSubject('not-a-token'), null)
  assert.equal(tokenSubject('expired.bogus.token'), null)
  assert.equal(tokenSubject(token({ sub: 42 })), null)
})

test('only a request with no answer at all is unreachable', () => {
  assert.equal(isUnreachable(noAnswer), true)
  assert.equal(isUnreachable(answered(502)), false)
  assert.equal(isUnreachable(answered(401)), false)
  // A bug in our own code is not a lack of coverage.
  assert.equal(isUnreachable(new TypeError('x is undefined')), false)
  assert.equal(isUnreachable(undefined), false)
})

test("the device's profile stands in only with no answer, and only for its own session", () => {
  assert.deepEqual(offlineProfile(noAnswer, ana, 'ana-id'), ana)
  assert.equal(offlineProfile(answered(401), ana, 'ana-id'), null)
  assert.equal(offlineProfile(answered(502), ana, 'ana-id'), null)
  assert.equal(offlineProfile(noAnswer, ana, 'luis-id'), null)
  assert.equal(offlineProfile(noAnswer, ana, null), null)
  assert.equal(offlineProfile(noAnswer, null, 'ana-id'), null)
})
