// The hosted service's own pages: the commercial landing and the engineering case study. By route
// name, not path: the router also matches /architecture (the alias), a trailing slash and any case.
const MARKETING_PAGES = new Set(['index', 'arquitectura'])

export default defineNuxtRouteMiddleware(async (to) => {
  const instance = useInstance()
  if (!instance.status.value && !useNuxtApp().payload.serverRendered) {
    // Booted from the service worker's shell (no coverage, or one bar): an installation with a
    // service worker is already set up, and recording a report needs nothing from here, so the
    // answer isn't waited for. It is used from the next navigation on.
    void instance.load()
    return
  }
  const status = await instance.load()
  if (!status) return
  // A fresh installation: nothing else works until its company and admin exist.
  if (status.needs_setup) return to.path === '/setup' ? undefined : navigateTo('/setup')
  if (to.path === '/setup') return navigateTo('/login')
  // A company's own server has no marketing page: its address opens the panel.
  if (status.single_tenant && MARKETING_PAGES.has(String(to.name))) return navigateTo('/dashboard')
})
