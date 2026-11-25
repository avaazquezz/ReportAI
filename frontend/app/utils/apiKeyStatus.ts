// Where a personal API key stands, for the panel's /admin/api-keys page (tests/apiKeyStatus.test.ts).
// The API decides whether a key works (backend/app/services/api_keys.py); this only labels it.

export type ApiKeyStatus = 'active' | 'expired' | 'revoked'

/**
 * Revoked wins over expired: someone ended it on purpose, and the panel shows when. A key with no
 * `expires_at` never expires; one whose `expires_at` is `now` or earlier no longer works.
 */
export function apiKeyStatus(
  key: { revoked_at: string | null; expires_at: string | null },
  now: Date = new Date()
): ApiKeyStatus {
  if (key.revoked_at) return 'revoked'
  return isPastExpiry(key, now) ? 'expired' : 'active'
}

/** Whether the key's expiry date has passed, revoked or not: what tense its expiry is told in. */
export function isPastExpiry(key: { expires_at: string | null }, now: Date = new Date()): boolean {
  return key.expires_at !== null && new Date(key.expires_at).getTime() <= now.getTime()
}
