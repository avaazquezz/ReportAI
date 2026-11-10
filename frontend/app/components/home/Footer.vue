<script setup lang="ts">
const { t } = useI18n()
const { public: config } = useRuntimeConfig()

const REPO = 'https://github.com/avaazquezz/ReportAI'
const AUTHOR = 'https://www.vazquezdev.pro'

// Don't link a legal notice that would publish blanks: it appears once the deployment has
// configured the owner's identity (NUXT_PUBLIC_LEGAL_NAME / _ID / _ADDRESS).
const showLegalLink = computed(() => Boolean(config.legalName && config.legalId && config.legalAddress))

const PRODUCT = [
  { href: '/#como-funciona', key: 'how' },
  { href: '/#pruebalo', key: 'demo' },
  { href: '/#precios', key: 'pricing' },
  { href: '/#preguntas', key: 'faq' }
] as const
</script>

<template>
  <footer class="border-t border-ink-900/10">
    <div class="home-grid gap-y-10 py-14">
      <div class="col-span-12 md:col-span-5">
        <HomeMark />
        <p class="t-body mt-4 max-w-xs text-ink-900/70">{{ t('home.footer.tagline') }}</p>
      </div>

      <nav class="col-span-6 md:col-span-3" :aria-label="t('home.footer.product')">
        <p class="text-sm font-semibold">{{ t('home.footer.product') }}</p>
        <ul class="mt-4 space-y-2.5 p-0 text-[0.95rem] text-ink-900/75">
          <li v-for="item in PRODUCT" :key="item.href" class="list-none">
            <a :href="item.href" class="u-nav hover:text-ink-900">{{ t(`home.nav.${item.key}`) }}</a>
          </li>
        </ul>
      </nav>

      <nav class="col-span-6 md:col-span-4" :aria-label="t('home.footer.company')">
        <p class="text-sm font-semibold">{{ t('home.footer.company') }}</p>
        <ul class="mt-4 space-y-2.5 p-0 text-[0.95rem] text-ink-900/75">
          <li class="list-none"><NuxtLink to="/arquitectura" class="u-nav hover:text-ink-900">{{ t('home.footer.architecture') }}</NuxtLink></li>
          <li class="list-none"><a :href="REPO" target="_blank" rel="noopener" class="u-nav hover:text-ink-900">{{ t('home.footer.code') }}</a></li>
          <li class="list-none"><a :href="`mailto:${CONTACT_EMAIL}`" class="u-nav hover:text-ink-900">{{ t('home.footer.contact') }}</a></li>
          <li v-if="showLegalLink" class="list-none"><NuxtLink to="/aviso-legal" class="u-nav hover:text-ink-900">{{ t('home.footer.legal') }}</NuxtLink></li>
        </ul>
      </nav>

      <p class="col-span-12 m-0 border-t border-ink-900/10 pt-6 text-sm text-ink-900/60">
        {{ t('home.footer.madeBy') }}
        <a :href="AUTHOR" target="_blank" rel="noopener" class="u-field text-ink-900/80">Adrián Vázquez</a>
      </p>
    </div>
  </footer>
</template>
