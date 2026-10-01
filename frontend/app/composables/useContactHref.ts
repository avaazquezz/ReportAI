export const CONTACT_EMAIL = 'adrian@vazquezdev.pro'

/** The landing's conversion action: a pre-filled email to the founder. */
export function useContactHref(subjectKey = 'landing.cta.mailSubject') {
  const { t } = useI18n()
  return computed(() => `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(t(subjectKey))}`)
}
