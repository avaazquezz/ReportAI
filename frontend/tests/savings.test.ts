// Run from frontend/ with: node_modules/.bin/jiti tests/savings.test.ts (the system Node has no TypeScript support)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { computeSavings, SAVINGS_DEFAULTS } from '../app/utils/savings.ts'

test('defaults: 3 technicians × 6 reports × 46 weeks', () => {
  const r = computeSavings(SAVINGS_DEFAULTS)
  assert.equal(r.reportsMonth, 69)
  // 69 reports × (35 − 8) min = 1863 min = 31.05 h
  assert.ok(Math.abs(r.hoursSavedMonth - 31.05) < 1e-9)
  // 31.05 h × 28 €/h − (69 × 0.03 € + 9 €)
  assert.ok(Math.abs(r.netMonth - (31.05 * 28 - (69 * 0.03 + 9))) < 1e-9)
  assert.ok(Math.abs(r.netYear - r.netMonth * 12) < 1e-9)
})

test('the new way is never counted as slower than the old one', () => {
  const r = computeSavings({ ...SAVINGS_DEFAULTS, minutesBefore: 10, minutesAfter: 30 })
  assert.equal(r.hoursSavedMonth, 0)
  assert.equal(r.afterShare, 1)
})

test('a field mid-edit (NaN) counts as zero instead of poisoning the result', () => {
  const r = computeSavings({ ...SAVINGS_DEFAULTS, technicians: Number.NaN })
  assert.equal(r.reportsMonth, 0)
  assert.equal(r.hoursSavedMonth, 0)
  assert.ok(Number.isFinite(r.netYear))
  assert.equal(r.afterShare, 0)
})
