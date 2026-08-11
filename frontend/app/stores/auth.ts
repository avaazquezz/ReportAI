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
      useCookie('reportai_token', { sameSite: 'strict' }).value = tokens.access_token
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

    logout() {
      this.user = null
      useCookie('reportai_token').value = null
      navigateTo('/')
    }
  }
})
