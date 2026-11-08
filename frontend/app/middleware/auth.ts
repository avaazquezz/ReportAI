import type { User } from '~/types'

export default defineNuxtRouteMiddleware(async () => {
  const authStore = useAuthStore()
  const { access, refresh } = useSessionCookies()

  if (!access.value && !refresh.value) {
    // A user left over from a session that has since ended must not keep the panel open (FE-3).
    authStore.user = null
    forgetOfflineCopies()
    return navigateTo('/login')
  }

  if (!authStore.isAuthenticated) {
    try {
      // A missing or expired access token is renewed with the refresh token inside useApi.
      await authStore.fetchMe()
    } catch (error) {
      // No answer at all (no coverage): the profile the API last confirmed on this device opens
      // the app, so a report can still be recorded and queued. Any answer means what it says.
      const unreachable = !(error as { response?: Response }).response
      const saved = unreachable ? readOfflineCopy<User>('profile') : null
      if (saved) {
        authStore.user = saved
        return
      }
      authStore.user = null
      return navigateTo('/login')
    }
  }
  // Kept on every navigation in the browser, wherever the profile came from (a server-rendered
  // page brings it in its payload, without fetchMe running here).
  keepOfflineCopy('profile', authStore.user)
})
