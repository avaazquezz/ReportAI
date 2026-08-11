interface User {
  id: string
  email: string
  full_name: string
  role: string
  tenant_id: string | null
}

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

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
