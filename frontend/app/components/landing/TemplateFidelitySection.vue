<script setup lang="ts">
const { t } = useI18n()

// Real docxtpl syntax: the panel shows the client's .docx as the engine sees it,
// then does what the product does — each tag resolves into its value.
const TAGS = {
  date: ['{{', 'meeting_date', '}}'].join(' '),
  place: ['{{', 'location', '}}'].join(' '),
  attendees: '{% for a in attendees %}{{ a }}{% endfor %}',
  summary: ['{{', 'summary', '}}'].join(' ')
}

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.text', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
    .fromTo('.paper', { opacity: 0, y: 24, rotate: -1.5 }, { opacity: 1, y: 0, rotate: 0, duration: 0.6 }, '-=0.3')
    .fromTo('.line', { opacity: 0, x: -6 }, { opacity: 1, x: 0, duration: 0.4, stagger: 0.12 }, '-=0.2')
    .to('.tag', { opacity: 0, duration: 0.3, stagger: 0.22 }, '+=0.7')
    .to('.val', { opacity: 1, duration: 0.3, stagger: 0.22 }, '<')
    .fromTo('.check', { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4 }, '-=0.2')
})
</script>

<template>
  <section id="plantilla" ref="root" class="bg-surface-0 py-20 md:py-28">
    <div class="mx-auto grid max-w-[1200px] items-center gap-12 px-6 md:grid-cols-2 lg:gap-16">
      <div class="paper m-hide relative md:order-1">
        <div class="absolute -top-3 left-6 rounded-md bg-ink-900 px-2.5 py-1 font-mono text-[11px] text-white shadow-sm">
          {{ t('landing.templateFidelity.filename') }}
        </div>
        <div class="rounded-[3px] bg-surface-0 px-7 pb-10 pt-9 shadow-page ring-1 ring-ink-900/5 sm:px-9">
          <p class="font-body text-xl font-bold leading-none tracking-tight text-doc-700">{{ t('landing.templateFidelity.docTitle') }}</p>
          <div class="mt-3 h-px w-full bg-doc-700/15" />

          <p class="line m-hide mt-5 font-body text-[13px] leading-6 text-ink-900">
            <b class="font-semibold">{{ t('landing.templateFidelity.labels.date') }}</b>
            <span class="ml-1 inline-grid align-top">
              <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ TAGS.date }}</span>
              <span class="val col-start-1 row-start-1 opacity-0">{{ t('landing.templateFidelity.values.date') }}</span>
            </span>
          </p>
          <p class="line m-hide mt-1 font-body text-[13px] leading-6 text-ink-900">
            <b class="font-semibold">{{ t('landing.templateFidelity.labels.place') }}</b>
            <span class="ml-1 inline-grid align-top">
              <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ TAGS.place }}</span>
              <span class="val col-start-1 row-start-1 opacity-0">{{ t('landing.templateFidelity.values.place') }}</span>
            </span>
          </p>
          <p class="line m-hide mt-4 font-body text-sm font-semibold text-doc-700">{{ t('landing.templateFidelity.labels.attendees') }}</p>
          <p class="line m-hide mt-1 font-body text-[13px] leading-6 text-ink-900">
            <span class="inline-grid align-top">
              <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ TAGS.attendees }}</span>
              <span class="val col-start-1 row-start-1 opacity-0">{{ t('landing.templateFidelity.values.attendees') }}</span>
            </span>
          </p>
          <p class="line m-hide mt-4 font-body text-sm font-semibold text-doc-700">{{ t('landing.templateFidelity.labels.summary') }}</p>
          <p class="line m-hide mt-1 font-body text-[13px] leading-6 text-ink-900">
            <span class="inline-grid align-top">
              <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ TAGS.summary }}</span>
              <span class="val col-start-1 row-start-1 opacity-0">{{ t('landing.templateFidelity.values.summary') }}</span>
            </span>
          </p>
        </div>
      </div>

      <div class="md:order-2">
        <div class="text m-hide">
          <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900">
            {{ t('landing.templateFidelity.heading') }}
          </h2>
          <p class="mt-5 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.templateFidelity.paragraph') }}</p>
        </div>
        <p class="check m-hide mt-6 flex gap-3 rounded-lg border border-approved-600/30 bg-approved-100/60 px-4 py-3 font-body text-sm leading-relaxed text-ink-900/80">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mt-0.5 h-4 w-4 shrink-0 text-approved-600" aria-hidden="true">
            <path d="M4 10.5l4 4 8-9" />
          </svg>
          <span>{{ t('landing.templateFidelity.check') }}</span>
        </p>
      </div>
    </div>
  </section>
</template>
