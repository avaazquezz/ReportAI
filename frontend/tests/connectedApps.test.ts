// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { availabilityAfterFailure, disconnectOutcome } from '../app/utils/connectedApps.ts'

test('only a 404 from the list means OAuth is off', () => {
  assert.equal(availabilityAfterFailure(404), 'off')
})

test('any other failure of the list leaves it unknown, so no sign-in steps are shown', () => {
  for (const status of [500, 502, 401, 403, undefined]) assert.equal(availabilityAfterFailure(status), 'unknown')
})

test('disconnecting an app that is already gone counts as done', () => {
  assert.equal(disconnectOutcome(404), 'done')
})

test('the demo account is told it is read-only; anything else failed', () => {
  assert.equal(disconnectOutcome(403), 'readOnly')
  assert.equal(disconnectOutcome(500), 'failed')
  assert.equal(disconnectOutcome(undefined), 'failed')
})
