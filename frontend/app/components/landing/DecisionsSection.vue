<script setup lang="ts">
const { t } = useI18n()

const ITEMS = ['graph', 'queue', 'hallucination', 'crash', 'providers', 'newdoc', 'limits'] as const

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
            name: t(`landing.decisions.items.${key}.q`),
            acceptedAnswer: { '@type': 'Answer', text: t(`landing.decisions.items.${key}.a`) }
          }))
        })
      )
    }
  ]
})
</script>

<template>
  <section id="decisiones" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto grid max-w-[1240px] gap-10 px-6 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
      <LandingSectionHeading class="lg:sticky lg:top-28 lg:self-start">{{ t('landing.decisions.heading') }}</LandingSectionHeading>

      <div class="divide-y divide-ink-900/15 border-y border-ink-900/15">
        <details v-for="key in ITEMS" :key="key" class="decision group py-5">
          <summary class="flex cursor-pointer items-center justify-between gap-6 font-plan text-[1.05rem] font-bold leading-snug tracking-[-0.01em] text-ink-900">
            {{ t(`landing.decisions.items.${key}.q`) }}
            <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-ink-900/20 text-ink-900 transition-transform duration-300 group-open:rotate-45" aria-hidden="true">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" class="h-3.5 w-3.5"><path d="M10 4v12M4 10h12" /></svg>
            </span>
          </summary>
          <p class="mb-0 mt-3 max-w-prose font-body text-base leading-relaxed text-ink-900/75">{{ t(`landing.decisions.items.${key}.a`) }}</p>
        </details>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* The answer eases in when its <details> opens; the plus rotates with it. */
.decision[open] > p {
  animation: decision-in 0.45s var(--ease-ra) both;
}
@keyframes decision-in {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
}
</style>
