import type { NuxtApp } from '#app'
import type { FetchOptions } from 'ofetch'
import type { TokenResponse } from '~/types'

// A plain signature instead of $fetch's own: the API is the external backend, not Nitro routes,
// and comparing $fetch's generated route types made the type checker give up ("excessive stack
// depth") once enough pages called the API.
export type Api = <T = unknown>(url: string, options?: FetchOptions) => Promise<T>

export const ACCESS_COOKIE = 'reportai_token'
export const REFRESH_COOKIE = 'reportai_refresh'
// Matches the backend's REFRESH_TOKEN_EXPIRE_DAYS: the cookie lives as long as the token works.
const REFRESH_MAX_AGE = 7 * 24 * 60 * 60

// Endpoints whose 401 means "wrong credentials", not "the session expired".
const NO_RENEW = ['/auth/login', '/auth/demo-login', '/auth/refresh', '/auth/logout']

// One renewal at a time per app (per request during SSR): a refresh token works once, so the
// three requests a page fires when the access token expires must share a single refresh.
const renewals = new WeakMap<NuxtApp, Promise<boolean>>()

function createSessionCookies() {
  const secure = !import.meta.dev && useRuntimeConfig().public.secureCookies !== false
  const options = { sameSite: 'strict', secure } as const
  return {
    access: useCookie<string | null>(ACCESS_COOKIE, options),
    refresh: useCookie<string | null>(REFRESH_COOKIE, { ...options, maxAge: REFRESH_MAX_AGE })
  }
}

// One pair of cookie refs per app (per request during SSR). Each useCookie() call on the server
// reads the cookies the request came with, so after a renewal a second call would still see the
// expired token and spend the old refresh token again.
const sessions = new WeakMap<NuxtApp, ReturnType<typeof createSessionCookies>>()

export function useSessionCookies() {
  const nuxtApp = useNuxtApp()
  let cookies = sessions.get(nuxtApp)
  if (!cookies) {
    cookies = createSessionCookies()
    sessions.set(nuxtApp, cookies)
  }
  return cookies
}

export function useApi() {
  // Everything that needs the Nuxt context is resolved here, synchronously: inside a fetch hook,
  // after an await, there is no context and useCookie() throws NUXT_E1001 (FE-2).
  const nuxtApp = useNuxtApp()
  const config = useRuntimeConfig()
  const { access, refresh } = useSessionCookies()
  // In prod apiBase is the relative '/api', which has no origin during SSR —
  // server-side fetches use the container-internal backend URL instead.
  const baseURL =
    import.meta.server && config.apiBaseServer ? config.apiBaseServer : config.public.apiBase

  const request = $fetch.create({
    baseURL,
    onRequest({ options }) {
      if (access.value) {
        options.headers.set('Authorization', `Bearer ${access.value}`)
      }
    }
  }) as unknown as Api

  async function renew(): Promise<boolean> {
    const spent = refresh.value
    if (!spent) return false
    try {
      const tokens = await $fetch<TokenResponse>('/auth/refresh', {
        baseURL,
        method: 'POST',
        body: { refresh_token: spent }
      })
      access.value = tokens.access_token
      refresh.value = tokens.refresh_token
      return true
    } catch {
      if (import.meta.client) {
        // Another tab may have renewed first, spending the token this one sent.
        refreshCookie(ACCESS_COOKIE)
        refreshCookie(REFRESH_COOKIE)
      }
      return Boolean(refresh.value) && refresh.value !== spent
    }
  }

  function renewOnce(): Promise<boolean> {
    let pending = renewals.get(nuxtApp)
    if (!pending) {
      pending = renew().finally(() => renewals.delete(nuxtApp))
      renewals.set(nuxtApp, pending)
    }
    return pending
  }

  async function endSession() {
    access.value = null
    refresh.value = null
    await nuxtApp.runWithContext(() => {
      useAuthStore().user = null
      return navigateTo('/login')
    })
  }

  const api: Api = async <T>(url: string, options?: FetchOptions) => {
    try {
      return await request<T>(url, options)
    } catch (error) {
      const status = (error as { response?: Response }).response?.status
      // No cookies at all: a visitor, not an expired session — the caller handles it.
      if (status !== 401 || NO_RENEW.includes(url) || !(access.value || refresh.value)) throw error
      if (await renewOnce()) return await request<T>(url, options)
      await endSession()
      throw error
    }
  }

  return api
}
