import { getCookie, getHeader } from 'h3'

// Sets the locale on every SSR request (utils/locale.ts says how it is picked).
//
// useI18n() only works inside a component's setup(), not a plugin — nuxtApp.$i18n is
// the same composer reached through the Nuxt app instance instead.
export default defineNuxtPlugin({
  name: 'locale-detect',
  // @nuxtjs/i18n's own plugin must install $i18n before this can use it.
  dependsOn: ['i18n:plugin'],
  async setup(nuxtApp) {
    const event = useRequestEvent()
    if (!event) return

    const i18n = nuxtApp.$i18n
    const detected = detectLocale(getCookie(event, LOCALE_COOKIE), getHeader(event, 'accept-language') ?? '')
    if (i18n.locale.value !== detected) await i18n.setLocale(detected)
  }
})
