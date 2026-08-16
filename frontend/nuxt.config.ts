// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  // Vuetify first so its base stylesheet loads before Tailwind's utilities —
  // Tailwind preflight is disabled (see tailwind.config.ts), so load order is
  // what keeps Vuetify's own component styles from being overridden.
  modules: ['vuetify-nuxt-module', '@nuxtjs/tailwindcss', '@pinia/nuxt', '@nuxt/eslint', '@nuxtjs/i18n'],
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
  i18n: {
    locales: [
      // vuetify.json feeds vuetify-nuxt-module's auto-detected i18n adapter (it
      // reads Vuetify's own UI strings — pagination, "no data available", etc. —
      // from this same vue-i18n message tree under the `$vuetify` key).
      { code: 'es', language: 'es-ES', name: 'Español', files: ['es/vuetify.json', 'es/common.json', 'es/landing.json', 'es/auth.json', 'es/admin.json'] },
      { code: 'en', language: 'en-US', name: 'English', files: ['en/vuetify.json', 'en/common.json', 'en/landing.json', 'en/auth.json', 'en/admin.json'] }
    ],
    defaultLocale: 'en',
    // No /en/ /es/ URL prefixes — the landing nav's anchor links (e.g. #ejemplo-real)
    // must stay stable regardless of language.
    strategy: 'no_prefix',
    experimental: {
      // Runs server-side during SSR so the first HTML response is already in the
      // right language — see i18n/localeDetector.ts for the actual detection rule.
      localeDetector: 'localeDetector.ts'
    }
  },
  vuetify: {
    vuetifyOptions: {
      // vuetify-nuxt-module auto-detects @nuxtjs/i18n and replaces `locale` with
      // its own reactive vue-i18n adapter at runtime — nothing to configure here.
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