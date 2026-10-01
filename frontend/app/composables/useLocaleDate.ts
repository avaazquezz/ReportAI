const INTL_LOCALES: Record<string, string> = {
  es: 'es-ES',
  en: 'en-US'
}

/**
 * 'YYYY-MM-DD' as midnight on the viewer's own clock. `new Date('2026-09-30')` is midnight UTC,
 * which west of Greenwich is still the 29th — the day-off-by-one of FE-9.
 */
export function parseLocalDay(value: string, offsetDays = 0): Date {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year!, month! - 1, day! + offsetDays)
}

export function useLocaleDate() {
  const { locale } = useI18n()

  function formatDate(value: string | Date, options?: Intl.DateTimeFormatOptions) {
    return new Date(value).toLocaleDateString(INTL_LOCALES[locale.value], options)
  }

  function formatDateTime(value: string | Date, options?: Intl.DateTimeFormatOptions) {
    return new Date(value).toLocaleString(INTL_LOCALES[locale.value], options)
  }

  return { formatDate, formatDateTime }
}
