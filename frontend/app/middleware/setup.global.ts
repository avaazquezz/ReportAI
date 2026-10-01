export default defineNuxtRouteMiddleware(async (to) => {
  const status = await useInstance().load()
  if (!status) return
  // A fresh installation: nothing else works until its company and admin exist.
  if (status.needs_setup) return to.path === '/setup' ? undefined : navigateTo('/setup')
  if (to.path === '/setup') return navigateTo('/login')
  // A company's own server has no marketing page: its address opens the panel.
  if (status.single_tenant && to.path === '/') return navigateTo('/dashboard')
})
