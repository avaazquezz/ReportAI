export default defineNuxtRouteMiddleware(() => {
  const authStore = useAuthStore()

  if (authStore.user?.role !== 'super_admin') {
    return navigateTo('/dashboard')
  }
})
