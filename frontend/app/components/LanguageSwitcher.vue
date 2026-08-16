<script setup lang="ts">
const { locale, setLocale } = useI18n()

// setLocale() alone doesn't reliably persist the override for the next SSR
// request — write the same cookie server/middleware/locale-detect.ts and
// detectBrowserLanguage read (i18n_redirected) directly too.
const overrideCookie = useCookie('i18n_redirected', { path: '/', maxAge: 60 * 60 * 24 * 365 })

async function toggleLocale() {
  const next = locale.value === 'es' ? 'en' : 'es'
  overrideCookie.value = next
  await setLocale(next)
}
</script>

<template>
  <button
    type="button"
    class="rounded-md border border-slate-300 px-2.5 py-1 font-body text-xs font-semibold text-ink-900 hover:border-capture-500 hover:text-capture-500"
    :aria-label="locale === 'es' ? 'Switch to English' : 'Cambiar a español'"
    @click="toggleLocale"
  >
    {{ locale === 'es' ? 'EN' : 'ES' }}
  </button>
</template>
