// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { auditSummary } from '../app/utils/auditSummary.ts'

test('no details, nothing to show', () => {
  assert.equal(auditSummary(null), '')
  assert.equal(auditSummary({}), '')
})

test('changed field names are listed, changes read from → to', () => {
  assert.equal(auditSummary({ fields: ['brand_color', 'name'] }), 'brand_color, name')
  assert.equal(
    auditSummary({ email: 'ana@garcia.test', changes: { role: { from: 'approver', to: 'viewer' } } }),
    'email: ana@garcia.test · role: approver → viewer'
  )
  assert.equal(
    auditSummary({ plan: { from: 'unlimited', to: 'pro' }, plan_status: { from: 'active', to: 'active' } }),
    'plan: unlimited → pro · plan_status: active → active'
  )
})

test('plain values as they are', () => {
  assert.equal(auditSummary({ label: 'Ana', invite_email_sent: false }), 'label: Ana · invite_email_sent: false')
})
