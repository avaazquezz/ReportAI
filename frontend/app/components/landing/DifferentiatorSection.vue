<script setup lang="ts">
const { t } = useI18n()

// Every row is a "yes" for ReportAI and a "no" for call-based meeting bots: the table
// exists to make the category difference legible, not to score features.
const ROWS = ['noCall', 'afterVisit', 'ownTemplate', 'chat', 'approval'] as const

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.head', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.6 })
    .fromTo('.panel', { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.5 }, '-=0.3')
    .fromTo('.row', { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.35, stagger: 0.1 }, '-=0.2')
    .fromTo('.kicker', { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4 }, '-=0.1')
})
</script>

<template>
  <section id="diferencia" ref="root" class="bg-ink-900 py-20 text-white md:py-28">
    <div class="mx-auto grid max-w-[1200px] items-start gap-12 px-6 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
      <div>
        <div class="head m-hide">
          <h2 class="font-display text-[clamp(2.1rem,4.2vw,3.6rem)] font-bold leading-[1.02] tracking-[-0.025em] [text-wrap:balance]">
            {{ t('landing.differentiator.heading') }}
          </h2>
          <p class="mt-6 max-w-xl font-body text-lg leading-relaxed text-white/75">
            {{ t('landing.differentiator.paragraph') }}
          </p>
        </div>
        <p class="kicker m-hide mt-8 font-display text-xl font-bold text-capture-500">
          {{ t('landing.differentiator.kicker') }}
        </p>
      </div>

      <div class="panel m-hide overflow-hidden rounded-2xl bg-ink-800 ring-1 ring-white/10">
        <table class="w-full border-collapse font-body text-sm">
          <caption class="sr-only">{{ t('landing.differentiator.table.caption') }}</caption>
          <thead>
            <tr class="border-b border-white/10">
              <th scope="col" class="px-5 py-4 text-left text-xs font-medium text-white/50">
                {{ t('landing.differentiator.table.feature') }}
              </th>
              <th scope="col" class="w-[22%] px-3 py-4 text-center text-xs font-medium text-white/60">
                {{ t('landing.differentiator.table.bots') }}
                <span class="mt-0.5 block font-normal text-white/35">{{ t('landing.differentiator.table.botsSub') }}</span>
              </th>
              <th scope="col" class="w-[22%] bg-capture-500/10 px-3 py-4 text-center font-display text-sm font-bold text-capture-500">
                {{ t('landing.differentiator.table.reportai') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in ROWS" :key="key" class="row m-hide border-b border-white/10 last:border-b-0">
              <th scope="row" class="px-5 py-4 text-left font-medium text-white/90">
                {{ t(`landing.differentiator.table.rows.${key}`) }}
              </th>
              <td class="px-3 py-4 text-center text-white/35">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" class="mx-auto h-4 w-4" aria-hidden="true">
                  <path d="M5 5l10 10M15 5L5 15" />
                </svg>
                <span class="sr-only">{{ t('landing.differentiator.table.no') }}</span>
              </td>
              <td class="bg-capture-500/10 px-3 py-4 text-center text-capture-500">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" class="mx-auto h-4 w-4" aria-hidden="true">
                  <path d="M4 10.5l4 4 8-9" />
                </svg>
                <span class="sr-only">{{ t('landing.differentiator.table.yes') }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
