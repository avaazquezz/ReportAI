export function useApi() {
  const config = useRuntimeConfig()
  // In prod apiBase is the relative '/api', which has no origin during SSR —
  // server-side fetches use the container-internal backend URL instead.
  const baseURL =
    import.meta.server && config.apiBaseServer ? config.apiBaseServer : config.public.apiBase

  return $fetch.create({
    baseURL,
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
