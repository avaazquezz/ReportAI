import type { TokenResponse, User } from '~/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null
  }),

  getters: {
    isAuthenticated: (state) => state.user !== null
  },

  actions: {
    async login(email: string, password: string) {
      const api = useApi()
      const tokens = await api<TokenResponse>('/auth/login', {
        method: 'POST',
        body: { email, password }
      })
      await this.applySession(tokens)
    },

    async demoLogin() {
      const api = useApi()
      const tokens = await api<TokenResponse>('/auth/demo-login', { method: 'POST' })
      await this.applySession(tokens)
    },

    async applySession(tokens: TokenResponse) {
      const { access, refresh } = useSessionCookies()
      access.value = tokens.access_token
      // Kept so the session outlives the one-hour access token (FE-1).
      refresh.value = tokens.refresh_token
      // useCookie() writes document.cookie via an async watcher (not synchronously on
      // assignment) — without this, fetchMe() below can read the cookie before that
      // write lands and send /auth/me with no Authorization header.
      await nextTick()
      await this.fetchMe()
    },

    async fetchMe() {
      const api = useApi()
      this.user = await api<User>('/auth/me')
    },

    async logout() {
      const api = useApi()
      const { access, refresh } = useSessionCookies()
      const refreshToken = refresh.value
      this.user = null
      access.value = null
      refresh.value = null
      if (refreshToken) {
        // Ends the session on the server too; signing out must not wait on (or fail with) it.
        api('/auth/logout', { method: 'POST', body: { refresh_token: refreshToken } }).catch(() => {})
      }
      await navigateTo('/')
    }
  }
})
