import { defineI18nLocaleDetector } from '#i18n'
import { getHeaderLanguage, tryCookieLocale } from '@intlify/h3'

// Spain's Spanish + co-official regional languages all resolve to Spanish;
// everything else resolves to English. An explicit manual override (cookie,
// written by the language switcher) always wins over this detection.
const SPANISH_LANGUAGE_PREFIXES = ['es', 'ca', 'eu', 'gl', 'oc']

export default defineI18nLocaleDetector((event, config) => {
  const override = tryCookieLocale(event, { lang: config.defaultLocale })
  if (override) return override.toString()

  const primary = getHeaderLanguage(event).split('-')[0]?.toLowerCase() ?? ''
  return SPANISH_LANGUAGE_PREFIXES.includes(primary) ? 'es' : config.defaultLocale
})
