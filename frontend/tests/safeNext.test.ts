// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { safeNext, withNext } from '../app/utils/safeNext.ts'

test('a path of this site is where the login page goes next', () => {
  assert.equal(safeNext('/dashboard'), '/dashboard')
  assert.equal(safeNext('/oauth/consent?request=gAAAAAB-x_y%3D'), '/oauth/consent?request=gAAAAAB-x_y%3D')
  assert.equal(safeNext('/admin/reports/1#top'), '/admin/reports/1#top')
})

test('anything that would leave the site is refused', () => {
  for (const next of [
    'https://evil.example/',
    '//evil.example/path',
    '/\\evil.example',
    '\\\\evil.example',
    '/\t/evil.example',
    '/\n/evil.example',
    'javascript:alert(1)',
    'evil.example',
    '',
    ' /dashboard'
  ]) {
    assert.equal(safeNext(next), null, JSON.stringify(next))
  }
})

test('a missing or repeated parameter is no destination', () => {
  assert.equal(safeNext(undefined), null)
  assert.equal(safeNext(null), null)
  assert.equal(safeNext(['/dashboard', '/admin']), null)
})

test("the technicians' sign-in carries a destination of this site on, and nothing else", () => {
  const consent = '/oauth/consent?request=gAAAAAB-x_y%3D&b=1'
  assert.equal(withNext('/magic', consent), `/magic?next=${encodeURIComponent(consent)}`)
  assert.equal(new URLSearchParams(withNext('/magic', consent).split('?')[1]).get('next'), consent) // read back intact
  assert.equal(withNext('/magic', '//evil.example/path'), '/magic')
  assert.equal(withNext('/magic', undefined), '/magic')
})
