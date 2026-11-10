/** Where the landing's one action leads: the free trial while self-signup is on (SIGNUP_ENABLED),
 * otherwise a prefilled email asking for access, so the button never opens a closed door. The
 * installation's status is loaded on the server by the global setup middleware. */
export function useTrialCta() {
  const { t } = useI18n()
  const { status } = useInstance()
  return computed(() =>
    status.value?.signup_enabled
      ? { href: '/signup', mail: false, label: t('home.cta.trial') }
      : {
          href: `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(t('home.cta.requestSubject'))}`,
          mail: true,
          label: t('home.cta.requestAccess')
        }
  )
}

/** A prefilled email to the founder for the landing's secondary actions (pilot, own server). */
export function mailtoHref(subject: string) {
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}`
}
