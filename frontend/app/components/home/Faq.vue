<script setup lang="ts">
// The objections the rest of the page doesn't settle, written for the buyer's worries. Native
// <details>: keyboard and screen readers get it for free; no JSON-LD (FAQ rich results are gone).
const { t } = useI18n()
const ITEMS = ['invent', 'data', 'template', 'offline', 'install', 'book', 'responsibility', 'selfhost', 'sale'] as const
</script>

<template>
  <section id="preguntas" class="space-l border-t border-ink-900/10" aria-labelledby="faq-title">
    <div class="home-grid gap-y-10">
      <h2 id="faq-title" class="t-section col-span-12 m-0 lg:sticky lg:top-28 lg:col-span-4 lg:self-start">{{ t('home.faq.heading') }}</h2>
      <div class="col-span-12 border-b border-ink-900/15 lg:col-span-7 lg:col-start-6">
        <details v-for="key in ITEMS" :key="key" class="faq group border-t border-ink-900/15">
          <summary class="flex cursor-pointer items-start justify-between gap-6 py-5 text-[1.1rem] font-semibold leading-snug">
            <span>{{ t(`home.faq.items.${key}.q`) }}</span>
            <svg viewBox="0 0 16 16" class="mt-1.5 h-4 w-4 shrink-0 transition-transform duration-200 group-open:rotate-45" aria-hidden="true">
              <path d="M8 2v12M2 8h12" stroke="currentColor" stroke-width="1.6" />
            </svg>
          </summary>
          <p class="t-body m-0 max-w-[40rem] pb-6 text-ink-900/75">{{ t(`home.faq.items.${key}.a`) }}</p>
        </details>
      </div>
    </div>
  </section>
</template>
