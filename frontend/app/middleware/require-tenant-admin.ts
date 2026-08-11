export default defineNuxtRouteMiddleware(() => {
  const authStore = useAuthStore()

  // Deliberately exact-match, not "tenant_admin or super_admin" (the backend's
  // require_tenant_admin dependency is broader) — these pages resolve tenant_id from
  // the logged-in user, and a super_admin has none.
  if (authStore.user?.role !== 'tenant_admin') {
    return navigateTo('/dashboard')
  }
})
