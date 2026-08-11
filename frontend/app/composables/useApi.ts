export function useApi() {
  const config = useRuntimeConfig()

  return $fetch.create({
    baseURL: config.public.apiBase,
    onRequest({ options }) {
      const token = useCookie('reportai_token').value
      if (token) {
        options.headers.set('Authorization', `Bearer ${token}`)
      }
    }
  })
}
