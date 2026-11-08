// The service worker's app shell (modules/service-worker) is never rendered by the server, so
// locale-detect.server.ts didn't run for it: the same choice is made here, from the same inputs.
export default defineNuxtPlugin({
  name: 'locale-detect-client',
  dependsOn: ['i18n:plugin'],
  async setup(nuxtApp) {
    if (nuxtApp.payload.serverRendered) return
    const i18n = nuxtApp.$i18n
    const detected = detectLocale(useCookie(LOCALE_COOKIE).value, navigator.language)
    if (i18n.locale.value !== detected) await i18n.setLocale(detected)
  }
})
