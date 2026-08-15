// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  // Vuetify first so its base stylesheet loads before Tailwind's utilities —
  // Tailwind preflight is disabled (see tailwind.config.ts), so load order is
  // what keeps Vuetify's own component styles from being overridden.
  modules: ['vuetify-nuxt-module', '@nuxtjs/tailwindcss', '@pinia/nuxt', '@nuxt/eslint'],
  css: ['@mdi/font/css/materialdesignicons.css', '~/assets/css/main.css'],
  runtimeConfig: {
    // Server-side base for SSR fetches: inside Docker the public domain isn't
    // reachable from the container, so SSR talks to the backend service directly.
    // Empty means "use the public apiBase" (local dev).
    apiBaseServer: process.env.NUXT_API_BASE_SERVER || '',
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8000'
    }
  },
  vuetify: {
    vuetifyOptions: {
      icons: { defaultSet: 'mdi' },
      theme: {
        defaultTheme: 'reportai',
        themes: {
          reportai: {
            dark: false,
            colors: {
              background: '#EEF1F4',
              surface: '#FFFFFF',
              primary: '#FF6A45',
              success: '#1C8F6A',
              // Mirror tailwind.config.ts's semantic tokens so v-chip/v-btn `color`
              // props can use the same names as Tailwind classes — Vuetify's theme
              // and Tailwind's config are two separate systems that don't share values.
              approved: '#1C8F6A',
              pending: '#B8860B',
              failed: '#C0392B',
              'on-background': '#12151C',
              'on-surface': '#12151C'
            }
          }
        }
      }
    }
  }
})