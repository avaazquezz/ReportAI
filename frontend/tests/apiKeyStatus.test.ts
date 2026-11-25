// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { apiKeyStatus, isPastExpiry } from '../app/utils/apiKeyStatus.ts'

const now = new Date('2026-11-25T12:00:00Z')

test('a key with no expiry and not revoked is active', () => {
  assert.equal(apiKeyStatus({ revoked_at: null, expires_at: null }, now), 'active')
})

test('a key is active until its expiry and expired from that instant on', () => {
  assert.equal(apiKeyStatus({ revoked_at: null, expires_at: '2026-11-25T12:00:01Z' }, now), 'active')
  assert.equal(apiKeyStatus({ revoked_at: null, expires_at: '2026-11-25T12:00:00Z' }, now), 'expired')
  assert.equal(apiKeyStatus({ revoked_at: null, expires_at: '2026-08-27T09:30:00+02:00' }, now), 'expired')
})

test('a revoked key reads as revoked, expired or not', () => {
  assert.equal(apiKeyStatus({ revoked_at: '2026-11-01T10:00:00Z', expires_at: null }, now), 'revoked')
  assert.equal(apiKeyStatus({ revoked_at: '2026-11-01T10:00:00Z', expires_at: '2026-11-02T10:00:00Z' }, now), 'revoked')
  assert.equal(apiKeyStatus({ revoked_at: '2026-11-01T10:00:00Z', expires_at: '2027-11-02T10:00:00Z' }, now), 'revoked')
})

test('a revoked key whose date has passed is still past its expiry', () => {
  assert.equal(isPastExpiry({ expires_at: '2026-11-02T10:00:00Z' }, now), true)
  assert.equal(isPastExpiry({ expires_at: '2027-11-02T10:00:00Z' }, now), false)
  assert.equal(isPastExpiry({ expires_at: null }, now), false)
})
