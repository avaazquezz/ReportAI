export default defineNuxtRouteMiddleware(async () => {
  // Composables first: after an await there is no Nuxt context to resolve them in.
  const instance = useInstance()
  const { isInstanceAdmin } = useRole()
  await instance.load()
  if (!isInstanceAdmin.value) return navigateTo('/dashboard')
})
