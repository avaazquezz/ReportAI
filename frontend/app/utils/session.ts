// What the panel can tell about its session without asking the API, for the paths that work with no
// coverage: whose session it is (read from its own token), whether a request got any answer, and
// which profile kept on the device may stand in for /auth/me. Pure, so tests/session.test.ts checks
// the rules on their own.
import type { User } from '~/types'

// How long the app waits for the API before it opens with what the device kept. On one bar of
// coverage a request can hang for minutes; a merely slow answer still arrives and replaces the copy.
export const DEVICE_COPY_AFTER_MS = 3000

/** The user id a session token is for: read, not verified (the server verifies every request). The
 * app only uses it to never mix one person's data kept on the device with someone else's session. */
export function tokenSubject(token: string | null | undefined): string | null {
  const payload = token?.split('.')[1]
  if (!payload) return null
  let claims: unknown
  try {
    claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
  } catch {
    return null // not a token this app issued: it belongs to nobody
  }
  const sub = (claims as { sub?: unknown } | null)?.sub
  return typeof sub === 'string' ? sub : null
}

/** A request that got no HTTP answer at all: no coverage, a dropped connection, or our own timeout.
 * Any answer, even a 502, means the server (or its proxy) is reachable and said something. */
export function isUnreachable(error: unknown): boolean {
  const err = error as { name?: unknown; response?: unknown } | null | undefined
  return err?.name === 'FetchError' && !err.response
}

/** The profile kept on the device, when it may open the app instead of /auth/me: only with no answer
 * from the API, and only if it is the profile of the person whose session this is. */
export function offlineProfile(error: unknown, kept: User | null, sessionUserId: string | null): User | null {
  if (!isUnreachable(error) || !kept || kept.id !== sessionUserId) return null
  return kept
}
