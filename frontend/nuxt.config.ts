// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  // Vuetify first so its base stylesheet loads before Tailwind's utilities —
  // Tailwind preflight is disabled (see tailwind.config.ts), so load order is
  // what keeps Vuetify's own component styles from being overridden.
  modules: ['vuetify-nuxt-module', '@nuxtjs/tailwindcss', '@pinia/nuxt', '@nuxt/eslint', '@nuxtjs/i18n'],
  // The icon font's stylesheet (~420 KB, ~74% of the global CSS) is loaded by the panel's layouts
  // (app, auth), the only pages that draw icons: the public pages no longer wait for it.
  css: ['~/assets/css/fonts.css', '~/assets/css/main.css', '~/assets/css/home.css'],
  nitro: {
    // Every build file also ships pre-compressed (.br, .gz) and the server sends what the browser
    // accepts: the global stylesheet (Vuetify and the icon font included) is ~540 KB raw, and
    // uncompressed it held the landing's first paint for seconds on a mobile connection.
    compressPublicAssets: { gzip: true, brotli: true }
  },
  routeRules: {
    // The page the service worker keeps on the phone (modules/service-worker): rendered with nothing
    // in it, so the app can draw whichever page was asked for with no coverage.
    '/app-shell': { ssr: false },
    // Asked for on every visit, so a fixed service worker reaches the phones on their next one.
    '/sw.js': { headers: { 'cache-control': 'no-cache' } }
  },
  runtimeConfig: {
    // Server-side base for SSR fetches: inside Docker the public domain isn't
    // reachable from the container, so SSR talks to the backend service directly.
    // Empty means "use the public apiBase" (local dev).
    apiBaseServer: process.env.NUXT_API_BASE_SERVER || '',
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8000',
      // Session cookies are Secure (HTTPS only). An installation reached over plain HTTP — by its
      // IP on a private network, without a domain — sets NUXT_PUBLIC_SECURE_COOKIES=false, or the
      // browser would drop them and nobody could sign in.
      secureCookies: true,
      // Identity published on /aviso-legal (LSSI art. 10). Set per deployment through
      // NUXT_PUBLIC_LEGAL_NAME / _ID / _ADDRESS; the page flags whatever is missing.
      legalName: '',
      legalId: '',
      legalAddress: '',
      // Pilot places on the landing's pricing (NUXT_PUBLIC_PILOT_SPOTS / NUXT_PUBLIC_PILOTS_TAKEN).
      pilotSpots: 5,
      pilotsTaken: 3
    }
  },
  i18n: {
    locales: [
      // vuetify.json feeds vuetify-nuxt-module's auto-detected i18n adapter (it
      // reads Vuetify's own UI strings — pagination, "no data available", etc. —
      // from this same vue-i18n message tree under the `$vuetify` key).
      { code: 'es', language: 'es-ES', name: 'Español', files: ['es/vuetify.json', 'es/common.json', 'es/landing.json', 'es/auth.json', 'es/admin.json', 'es/home.json'] },
      { code: 'en', language: 'en-US', name: 'English', files: ['en/vuetify.json', 'en/common.json', 'en/landing.json', 'en/auth.json', 'en/admin.json', 'en/home.json'] }
    ],
    defaultLocale: 'en',
    // No /en/ /es/ URL prefixes — the landing nav's anchor links (e.g. #ejemplo-real)
    // must stay stable regardless of language.
    strategy: 'no_prefix',
    // The built-in detector only matches Accept-Language against the two codes above —
    // it has no notion of "Spain's co-official regional languages also mean Spanish".
    // app/plugins/locale-detect.server.ts does that bucketing itself on every SSR
    // request, so the built-in one is disabled rather than left running redundantly.
    detectBrowserLanguage: false,
    experimental: {
      // Writes each locale's messages as a static file in the build, which the service worker keeps
      // on the phone (modules/service-worker); served by a server route, the app would open with no
      // coverage showing translation keys instead of text.
      prerenderMessages: true
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
              // capture-600, not the brand's #FF6A45: white text on #FF6A45 is 2.84:1 (FE-10).
              primary: '#C0432A',
              success: '#136B4F',
              // Mirror tailwind.config.ts's semantic tokens so v-chip/v-btn `color`
              // props can use the same names as Tailwind classes — Vuetify's theme
              // and Tailwind's config are two separate systems that don't share values.
              // Darker than tailwind's approved/pending-600 so tonal chips reach 4.5:1 (FE-10).
              approved: '#136B4F',
              pending: '#7A5800',
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