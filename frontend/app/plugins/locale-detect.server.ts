import { getCookie, getHeader } from 'h3'

// @nuxtjs/i18n's built-in detectBrowserLanguage only matches Accept-Language against
// the exact configured locale codes (es/en) — it has no notion of "Spain's co-official
// regional languages also mean Spanish", so we set the locale ourselves on every SSR
// request instead. LanguageSwitcher.vue's cookie (an explicit manual choice) always
// wins; otherwise we bucket by the request's Accept-Language.
//
// useI18n() only works inside a component's setup(), not a plugin — nuxtApp.$i18n is
// the same composer reached through the Nuxt app instance instead.
type AppLocale = 'es' | 'en'

const SPANISH_LANGUAGE_PREFIXES = ['es', 'ca', 'eu', 'gl', 'oc']
const OVERRIDE_COOKIE = 'i18n_redirected'

function isAppLocale(value: string | undefined): value is AppLocale {
  return value === 'es' || value === 'en'
}

export default defineNuxtPlugin({
  name: 'locale-detect',
  // @nuxtjs/i18n's own plugin must install $i18n before this can use it.
  dependsOn: ['i18n:plugin'],
  async setup(nuxtApp) {
    const event = useRequestEvent()
    if (!event) return

    const i18n = nuxtApp.$i18n

    const override = getCookie(event, OVERRIDE_COOKIE)
    if (isAppLocale(override)) {
      if (i18n.locale.value !== override) await i18n.setLocale(override)
      return
    }

    const header = getHeader(event, 'accept-language') ?? ''
    const primary = header.split(',')[0]?.split('-')[0]?.trim().toLowerCase() ?? ''
    const detected: AppLocale = SPANISH_LANGUAGE_PREFIXES.includes(primary) ? 'es' : 'en'
    if (i18n.locale.value !== detected) await i18n.setLocale(detected)
  }
})
