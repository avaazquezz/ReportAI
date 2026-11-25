// What a failed request of the OAuth consent page means for the person (tests/consentFailure.test.ts):
// pages/oauth/consent.vue turns it into a message, or into a sign-in that comes back to the page.

export type ConsentFailure = 'signIn' | 'unavailable' | 'expired' | 'notAllowed' | 'limit' | 'generic'

/**
 * `status` is what the consent request answered; `oauthOn` whether this installation has OAuth on,
 * which only matters for a 404: every OAuth route is a 404 while it is off, and so is a request for
 * an app that is gone.
 */
export function consentFailure(status: number | undefined, oauthOn: boolean): ConsentFailure {
  // The session ended while the page was open: sign in again and come back, request and all.
  if (status === 401) return 'signIn'
  if (status === 404) return oauthOn ? 'expired' : 'unavailable'
  // Older than 10 minutes or altered (400), or not a request at all (422).
  if (status === 400 || status === 422) return 'expired'
  // The read-only demo account, or one outside any company.
  if (status === 403) return 'notAllowed'
  // Approving answers 409 for one reason only: the person's cap on connected apps.
  if (status === 409) return 'limit'
  return 'generic'
}
