// How the panel picks its language. @nuxtjs/i18n's built-in detectBrowserLanguage only matches the
// exact configured codes (es/en): it has no notion of "Spain's co-official languages also mean
// Spanish", so the app decides itself (plugins/locale-detect.*).
export type AppLocale = 'es' | 'en'

// Written by LanguageSwitcher.vue: an explicit choice, which always wins.
export const LOCALE_COOKIE = 'i18n_redirected'

const SPANISH_LANGUAGE_PREFIXES = ['es', 'ca', 'eu', 'gl', 'oc']

function isAppLocale(value: string | null | undefined): value is AppLocale {
  return value === 'es' || value === 'en'
}

/** The person's choice if they made one; otherwise the first of their languages (an
 * Accept-Language header or navigator.language), bucketed into the two the app speaks. */
export function detectLocale(choice: string | null | undefined, languages: string): AppLocale {
  if (isAppLocale(choice)) return choice
  const primary = languages.split(',')[0]?.split('-')[0]?.trim().toLowerCase() ?? ''
  return SPANISH_LANGUAGE_PREFIXES.includes(primary) ? 'es' : 'en'
}
