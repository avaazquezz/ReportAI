export default defineNuxtRouteMiddleware(async () => {
  const authStore = useAuthStore()
  const { access, refresh } = useSessionCookies()

  if (!access.value && !refresh.value) {
    // A user left over from a session that has since ended must not keep the panel open (FE-3).
    authStore.user = null
    return navigateTo('/login')
  }

  if (!authStore.isAuthenticated) {
    try {
      // A missing or expired access token is renewed with the refresh token inside useApi.
      await authStore.fetchMe()
    } catch {
      authStore.user = null
      return navigateTo('/login')
    }
  }
})
