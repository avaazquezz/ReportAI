// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { oauthDocumentUrl } from '../server/utils/oauthDocuments.ts'

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
