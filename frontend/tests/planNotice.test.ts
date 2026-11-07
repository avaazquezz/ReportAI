// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { PlanUsage } from '../app/types/index.ts'
import { planNotice } from '../app/composables/usePlan.ts'

const now = new Date('2026-11-06T12:00:00Z')
const base: PlanUsage = {
  plan: 'starter',
  status: 'active',
  period_start: '2026-11-01T00:00:00Z',
  period_end: '2026-12-01T00:00:00Z',
  reports_used: 10,
  reports_limit: 50
}

test('nothing to say on a healthy plan, or on self-host (no limit)', () => {
  assert.equal(planNotice(base, now), null)
  assert.equal(planNotice({ ...base, plan: 'unlimited', reports_limit: null, reports_used: 9999 }, now), null)
  assert.equal(planNotice(null, now), null)
})

test('the quota warns at 80 % and stops at 100 %', () => {
  assert.equal(planNotice({ ...base, reports_used: 40 }, now)?.key, 'admin.plan.notice.quotaNear')
  assert.deepEqual(planNotice({ ...base, reports_used: 50 }, now), {
    type: 'error',
    key: 'admin.plan.notice.quotaReached',
    params: { limit: 50 }
  })
})

test('a trial counts down its days and then ends', () => {
  const trial = { ...base, plan: 'trial' as const, status: 'trialing' as const, reports_limit: 30, reports_used: 0 }
  assert.deepEqual(planNotice({ ...trial, period_end: '2026-11-09T11:00:00Z' }, now)?.params, { days: 3 })
  assert.equal(planNotice({ ...trial, period_end: '2026-11-06T11:00:00Z' }, now)?.key, 'admin.plan.notice.trialEnded')
})

test('a canceled plan beats everything; payment due is a warning', () => {
  assert.equal(planNotice({ ...base, status: 'canceled', reports_used: 50 }, now)?.key, 'admin.plan.notice.inactive')
  assert.equal(planNotice({ ...base, status: 'past_due' }, now)?.type, 'warning')
})
