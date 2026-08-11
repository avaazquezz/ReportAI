export function useApi() {
  const config = useRuntimeConfig()

  return $fetch.create({
    baseURL: config.public.apiBase,
    onRequest({ options }) {
      const token = useCookie('reportai_token').value
      if (token) {
        options.headers.set('Authorization', `Bearer ${token}`)
      }
    },
    onResponseError({ response }) {
      // Only force a redirect for a session that WAS authenticated and got rejected
      // (expired/invalid token) — a fresh login attempt's own 401 has no cookie yet
      // and is handled by the caller (see login.vue's own error message).
      const tokenCookie = useCookie('reportai_token')
      if (response.status === 401 && tokenCookie.value) {
        tokenCookie.value = null
        navigateTo('/login')
      }
    }
  })
}
