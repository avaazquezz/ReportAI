<script setup lang="ts">
// The drawing set's cover: what was built and by whom, the 60-second reading for anyone who stops
// here (a recruiter), and the index of sheets for anyone who goes on (a CTO). The headline paints
// from the first frame, with no motion: the cover argues with its content, not with a reveal.
const { t } = useI18n()
const contactHref = useContactHref()

const SUMMARY = ['what', 'hard', 'proof'] as const
const BLOCK = [
  { label: 'project', value: null },
  { label: 'author', value: 'authorValue' },
  { label: 'status', value: 'statusValue' },
  { label: 'rev', value: 'revValue' }
] as const
</script>

<template>
  <section class="grid-paper" aria-labelledby="cover-title">
    <div class="mx-auto max-w-[1240px] px-6 pb-14 pt-12 lg:pb-20 lg:pt-20">
      <div class="grid gap-12 lg:grid-cols-12 lg:gap-10">
        <div class="lg:col-span-7">
          <h1 id="cover-title" class="m-0 font-plan text-[clamp(2.3rem,1rem+3.6vw,4.25rem)] font-extrabold leading-[1.02] tracking-[-0.04em] text-ink-900">
            <span class="block">{{ t('landing.cover.line1') }}</span>
            <span class="mt-2 block text-plano-700">{{ t('landing.cover.line2') }}</span>
          </h1>
          <p class="mb-0 mt-8 max-w-[38rem] font-body text-[1.125rem] leading-relaxed text-ink-900/80">{{ t('landing.cover.lead') }}</p>

          <div class="mt-9 flex flex-wrap items-center gap-x-7 gap-y-4 font-body text-[15px]">
            <a :href="contactHref" class="rounded-md bg-capture-600 px-5 py-3 font-semibold text-white transition-colors hover:bg-ink-900">{{ t('landing.cta.talk') }}</a>
            <a href="https://github.com/avaazquezz/ReportAI" target="_blank" rel="noopener" class="cover-link">
              {{ t('landing.cta.seeCode') }}<span class="sr-only"> {{ t('landing.sheet.newTab') }}</span>
            </a>
            <NuxtLink to="/#pruebalo" class="cover-link">{{ t('landing.cta.demo') }}</NuxtLink>
            <a :href="t('landing.cta.cvHref')" target="_blank" rel="noopener" class="cover-link">
              {{ t('landing.cta.cv') }}<span class="sr-only"> {{ t('landing.sheet.newTab') }}</span>
            </a>
          </div>
        </div>

        <!-- The title block of the set: it carries the 60-second reading. -->
        <aside class="self-start border-2 border-ink-900 bg-surface-0 lg:col-span-5" aria-labelledby="summary-title">
          <h2 id="summary-title" class="m-0 border-b-2 border-ink-900 px-5 py-3 font-plan text-[1.15rem] font-extrabold tracking-[-0.02em] text-ink-900">
            {{ t('landing.cover.summaryTitle') }}
          </h2>
          <dl class="m-0">
            <div v-for="key in SUMMARY" :key="key" class="border-b border-ink-900/20 px-5 py-4 last:border-b-0">
              <dt class="font-body text-[13px] font-semibold text-capture-600">{{ t(`landing.cover.summary.${key}.label`) }}</dt>
              <dd class="m-0 mt-1 font-body text-[15px] leading-snug text-ink-900">{{ t(`landing.cover.summary.${key}.body`) }}</dd>
            </div>
          </dl>
          <dl class="m-0 grid grid-cols-2 border-t-2 border-ink-900 font-body text-[13px]">
            <div v-for="(row, i) in BLOCK" :key="row.label" class="px-5 py-2.5" :class="[i % 2 === 0 ? 'border-r border-ink-900/20' : '', i < 2 ? 'border-b border-ink-900/20' : '']">
              <dt class="font-mono text-[12px] text-ink-900/60">{{ t(`landing.cover.block.${row.label}`) }}</dt>
              <dd class="m-0 mt-0.5 font-medium text-ink-900">{{ row.value ? t(`landing.cover.block.${row.value}`) : 'ReportAI' }}</dd>
            </div>
          </dl>
        </aside>
      </div>

      <nav class="mt-14 border-t border-ink-900/25 pt-5 lg:mt-20" :aria-label="t('landing.cover.indexLabel')">
        <p class="m-0 font-body text-[13px] font-semibold text-ink-900/70" aria-hidden="true">{{ t('landing.cover.indexLabel') }}</p>
        <ol class="m-0 mt-4 grid list-none grid-cols-1 gap-x-6 gap-y-1 p-0 sm:grid-cols-2 lg:grid-cols-4">
          <li v-for="sheet in SHEETS" :key="sheet">
            <a :href="`#${SHEET_IDS[sheet]}`" class="group flex items-baseline gap-3 border-b border-ink-900/10 py-2.5 text-ink-900 transition-colors hover:text-capture-600">
              <span class="w-4 shrink-0 font-mono text-[12px] tabular-nums text-ink-900/70">{{ sheetNumber(sheet) }}</span>
              <span class="flex-1 font-body text-[15px] font-medium">{{ t(`landing.sheets.${sheet}.title`) }}</span>
              <span class="font-mono text-[12px] text-ink-900/80">{{ t(`landing.sheets.${sheet}.scale`) }}</span>
            </a>
          </li>
        </ol>
      </nav>
    </div>
  </section>
</template>

<style scoped>
.cover-link {
  color: rgb(18 21 28);
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: rgb(18 21 28 / 0.35);
  text-underline-offset: 0.3em;
  transition: text-decoration-color 0.2s var(--ease-ra);
}
.cover-link:hover {
  text-decoration-color: currentColor;
}
</style>
