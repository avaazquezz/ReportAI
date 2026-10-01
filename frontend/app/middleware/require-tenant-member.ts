export default defineNuxtRouteMiddleware(() => {
  // Anyone in a company (admin, approver, read-only) reads its reports.
  if (!useRole().isMember.value) return navigateTo('/dashboard')
})
