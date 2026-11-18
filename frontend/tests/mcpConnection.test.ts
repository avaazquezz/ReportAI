// Run from frontend/ with: npm test
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { claudeCodeCommand, mcpUrl } from '../app/utils/mcpConnection.ts'

test("a relative API base (production's /api) is resolved against the page's origin", () => {
  assert.equal(mcpUrl('/api', 'https://reportai.example'), 'https://reportai.example/api/mcp')
  assert.equal(mcpUrl('/api/', 'https://reportai.example'), 'https://reportai.example/api/mcp')
  assert.equal(mcpUrl('/api', 'http://192.168.1.20:8080'), 'http://192.168.1.20:8080/api/mcp')
})

test("an absolute API base is used as it is, whatever the page's origin", () => {
  assert.equal(mcpUrl('http://localhost:8000', 'http://127.0.0.1:3100'), 'http://localhost:8000/mcp')
  assert.equal(mcpUrl('https://api.example.com/api', 'https://panel.example.com'), 'https://api.example.com/api/mcp')
  assert.equal(mcpUrl('https://api.example.com/api//', 'https://panel.example.com'), 'https://api.example.com/api/mcp')
})

test('the Claude Code command carries the address and the key as a bearer header', () => {
  assert.equal(
    claudeCodeCommand('https://reportai.example/api/mcp', 'rpt_secret'),
    'claude mcp add --transport http reportai https://reportai.example/api/mcp --header "Authorization: Bearer rpt_secret"'
  )
})
