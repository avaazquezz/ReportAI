// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { consentFailure } from '../app/utils/consentFailure.ts'

test('a session that ended sends the person to sign in, not to a dead end', () => {
  assert.equal(consentFailure(401, true), 'signIn')
})

test('a 404 is an expired request while OAuth is on, and OAuth not offered while it is off', () => {
  assert.equal(consentFailure(404, true), 'expired')
  assert.equal(consentFailure(404, false), 'unavailable')
})

test('an altered or old request is expired, whatever OAuth is', () => {
  assert.equal(consentFailure(400, true), 'expired')
  assert.equal(consentFailure(422, true), 'expired')
})

test('the demo account, the cap on apps and anything else each say their own thing', () => {
  assert.equal(consentFailure(403, true), 'notAllowed')
  assert.equal(consentFailure(409, true), 'limit')
  assert.equal(consentFailure(500, true), 'generic')
  assert.equal(consentFailure(undefined, true), 'generic')
})
