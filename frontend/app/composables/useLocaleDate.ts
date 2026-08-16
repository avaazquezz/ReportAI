const INTL_LOCALES: Record<string, string> = {
  es: 'es-ES',
  en: 'en-US'
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
