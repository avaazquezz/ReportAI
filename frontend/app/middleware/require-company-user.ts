export default defineNuxtRouteMiddleware(() => {
  // Anyone in a company reads its reports; a technician only their own (the API filters them).
  const { isMember, isTechnician } = useRole()
  if (!isMember.value && !isTechnician.value) return navigateTo('/dashboard')
})
