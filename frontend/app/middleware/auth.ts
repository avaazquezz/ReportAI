export default defineNuxtRouteMiddleware(async () => {
  const authStore = useAuthStore()

  if (!authStore.isAuthenticated) {
    const token = useCookie('reportai_token').value
    if (!token) return navigateTo('/login')

    try {
      await authStore.fetchMe()
    } catch {
      return navigateTo('/login')
    }
  }
})
