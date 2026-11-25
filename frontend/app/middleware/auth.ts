import type { User } from '~/types'

export default defineNuxtRouteMiddleware(async (to) => {
  const authStore = useAuthStore()
  const { access, refresh } = useSessionCookies()
  // Back to this page once signed in (the login page checks it is one of this site's: utils/safeNext.ts).
  const toLogin = { path: '/login', query: { next: to.fullPath } }

  if (!access.value && !refresh.value) {
    // A user left over from a session that has since ended must not keep the panel open (FE-3).
    authStore.user = null
    forgetOfflineCopies()
    return navigateTo(toLogin)
  }

  const sessionUserId = tokenSubject(refresh.value ?? access.value)
  // Another tab may have signed someone else in since this page loaded: the profile in memory must
  // be the one of the session the requests carry.
  if (authStore.user && authStore.user.id !== sessionUserId) authStore.user = null

  if (!authStore.isAuthenticated) {
    const kept = readOfflineCopy<User>('profile')
    const standIn = kept?.id === sessionUserId ? kept : null
    try {
      // A missing or expired access token is renewed with the refresh token inside useApi.
      const confirmed = authStore.fetchMe()
      if (standIn && !(await resolvesWithin(confirmed, DEVICE_COPY_AFTER_MS))) {
        // One bar of coverage: the app opens with the device's copy. The request isn't abandoned
        // (it may be spending the single-use refresh token): its answer replaces the profile, and
        // a 401 still ends the session (useApi).
        authStore.user = standIn
        return
      }
      await confirmed
    } catch (error) {
      // No answer at all (no coverage): the profile the API last confirmed for this session opens
      // the app, so a report can still be recorded and queued. Any answer means what it says.
      const profile = offlineProfile(error, kept, sessionUserId)
      if (profile) {
        authStore.user = profile
        return
      }
      authStore.user = null
      return navigateTo(toLogin)
    }
  }
  // Kept on every navigation in the browser, wherever the profile came from (a server-rendered
  // page brings it in its payload, without fetchMe running here).
  keepOfflineCopy('profile', authStore.user)
})

// true once the promise resolves, false if the time runs out first; a rejection in time is thrown.
function resolvesWithin(promise: Promise<unknown>, ms: number): Promise<boolean> {
  return Promise.race([promise.then(() => true), new Promise<boolean>((resolve) => setTimeout(resolve, ms, false))])
}
