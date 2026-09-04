export const CONTACT_EMAIL = 'adrian@vazquezdev.pro'

/** The landing's single conversion action: a pre-filled email to the founder. */
export function useContactHref() {
  const { t } = useI18n()
  return computed(() => `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(t('landing.cta.mailSubject'))}`)
}
