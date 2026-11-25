// What the API's answers about apps connected by signing in (OAuth) mean for the /admin/api-keys
// page (tests/connectedApps.test.ts). The API decides; this only reads its status codes.

/** Whether this installation has OAuth sign-in on, as far as the page knows. */
export type OAuthAvailability = 'unknown' | 'on' | 'off'

/** The list of connected apps failed with `status`: a 404 means OAuth is off (its routes don't
 * exist); anything else (no coverage, a 500) says nothing either way. */
export function availabilityAfterFailure(status: number | undefined): OAuthAvailability {
  return status === 404 ? 'off' : 'unknown'
}

/** Disconnecting an app failed with `status`: a 404 means it is gone already (the app signed out,
 * or another tab got there first), which is what was asked for; a 403 is the read-only demo. */
export function disconnectOutcome(status: number | undefined): 'done' | 'readOnly' | 'failed' {
  if (status === 404) return 'done'
  return status === 403 ? 'readOnly' : 'failed'
}
