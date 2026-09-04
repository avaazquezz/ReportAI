<script setup lang="ts">
const { t } = useI18n()

const ITEMS = ['install', 'channels', 'errors', 'data', 'languages', 'documents', 'price'] as const

// Same questions and answers the page shows, exposed for search engines.
useHead({
  script: [
    {
      type: 'application/ld+json',
      innerHTML: computed(() =>
        JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'FAQPage',
          mainEntity: ITEMS.map((key) => ({
            '@type': 'Question',
            name: t(`landing.faq.items.${key}.q`),
            acceptedAnswer: { '@type': 'Answer', text: t(`landing.faq.items.${key}.a`) }
          }))
        })
      )
    }
  ]
})
</script>

<template>
  <section id="preguntas" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto grid max-w-[1200px] gap-10 px-6 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
      <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900 [text-wrap:balance] lg:sticky lg:top-28">
        {{ t('landing.faq.heading') }}
      </h2>

      <div class="divide-y divide-ink-900/10 border-y border-ink-900/10">
        <details v-for="key in ITEMS" :key="key" class="group py-5">
          <summary class="flex cursor-pointer items-center justify-between gap-6 font-display text-lg font-bold leading-snug text-ink-900">
            {{ t(`landing.faq.items.${key}.q`) }}
            <span
              class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-ink-900/20 text-ink-900 transition-transform duration-300 group-open:rotate-45"
              aria-hidden="true"
            >
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" class="h-3.5 w-3.5">
                <path d="M10 4v12M4 10h12" />
              </svg>
            </span>
          </summary>
          <p class="mt-3 max-w-prose font-body text-base leading-relaxed text-ink-900/75">{{ t(`landing.faq.items.${key}.a`) }}</p>
        </details>
      </div>
    </div>
  </section>
</template>
