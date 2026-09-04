<script setup lang="ts">
const { t } = useI18n()

const NAV = [
  { hash: '#ejemplo-real', key: 'realExample' },
  { hash: '#como-funciona', key: 'howItWorks' },
  { hash: '#diferencia', key: 'difference' },
  { hash: '#preguntas', key: 'faq' }
] as const
</script>

<template>
  <footer class="border-t border-paper-100 bg-cream-50">
    <div class="mx-auto max-w-[1200px] px-6 py-12">
      <div class="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <div class="flex items-center gap-2">
            <svg viewBox="0 0 100 100" class="h-7 w-7 shrink-0" aria-hidden="true">
              <rect width="100" height="100" rx="24" class="fill-ink-900" />
              <text
                x="50"
                y="70"
                font-size="60"
                text-anchor="middle"
                font-family="Arial, Helvetica, sans-serif"
                font-weight="700"
                class="fill-capture-500"
              >R</text>
            </svg>
            <span class="font-display text-lg font-bold text-ink-900">ReportAI</span>
          </div>
          <p class="mt-3 max-w-xs font-body text-sm text-ink-900/70">{{ t('landing.footer.tagline') }}</p>
        </div>

        <nav class="flex flex-col gap-2.5 font-body text-sm">
          <a
            v-for="item in NAV"
            :key="item.hash"
            :href="item.hash"
            class="w-fit text-ink-900/80 hover:text-capture-600"
          >
            {{ t(`landing.header.nav.${item.key}`) }}
          </a>
        </nav>

        <div class="flex flex-col gap-2.5 font-body text-sm">
          <a :href="`mailto:${CONTACT_EMAIL}`" class="w-fit text-ink-900/80 hover:text-capture-600">{{ CONTACT_EMAIL }}</a>
          <a
            href="https://www.vazquezdev.pro"
            target="_blank"
            rel="noopener noreferrer"
            class="w-fit text-ink-900/80 hover:text-capture-600"
          >
            www.vazquezdev.pro
          </a>
          <div class="mt-2">
            <LanguageSwitcher />
          </div>
        </div>
      </div>

      <div class="mt-10 flex flex-col gap-2 border-t border-ink-900/10 pt-6 font-body text-xs text-ink-900/60 sm:flex-row sm:justify-between">
        <span>© {{ new Date().getFullYear() }} ReportAI</span>
        <span>
          {{ t('landing.footer.madeBy') }}
          <a href="https://www.vazquezdev.pro" target="_blank" rel="noopener noreferrer" class="text-ink-900/80 hover:text-capture-600">vazquezdev.pro</a>
        </span>
      </div>
    </div>
  </footer>
</template>
