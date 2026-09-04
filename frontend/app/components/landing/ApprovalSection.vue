<script setup lang="ts">
const { t } = useI18n()

// Static waveform for the voice-note bubble — the motion here is the
// conversation itself popping in, not the bars.
const WAVE_HEIGHTS = [6, 10, 14, 9, 16, 7, 12, 18, 8, 13, 10, 6]

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.text', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
    .fromTo('.phone', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.5 }, '-=0.3')
    .fromTo(
      '.bubble',
      { opacity: 0, y: 10, scale: 0.96 },
      { opacity: 1, y: 0, scale: 1, duration: 0.4, stagger: 0.45, ease: 'back.out(1.4)' },
      '-=0.1'
    )
})
</script>

<template>
  <section id="aprobacion" ref="root" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto grid max-w-[1200px] items-center gap-12 px-6 md:grid-cols-2 lg:gap-16">
      <div class="text m-hide">
        <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900">
          {{ t('landing.approval.heading') }}
        </h2>
        <p class="mt-5 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.approval.paragraph1') }}</p>
        <p class="mt-4 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.approval.paragraph2') }}</p>
        <div class="mt-8 flex flex-wrap items-center gap-3">
          <span class="rounded-full border border-capture-600 bg-surface-0 px-4 py-1.5 font-body text-sm font-semibold text-capture-600">
            {{ t('landing.approval.defaultChannelBadge') }}
          </span>
          <span class="rounded-full border border-ink-900/15 px-4 py-1.5 font-body text-sm text-ink-900/70">
            {{ t('landing.approval.otherChannelNote') }}
          </span>
        </div>
      </div>

      <div class="phone m-hide w-full max-w-sm justify-self-center overflow-hidden rounded-2xl bg-surface-0 shadow-float md:justify-self-end" aria-hidden="true">
        <div class="flex items-center gap-3 border-b border-paper-100 px-4 py-3">
          <span class="flex h-8 w-8 items-center justify-center rounded-full bg-ink-900 font-display text-xs font-bold text-capture-500">R</span>
          <div class="leading-tight">
            <p class="font-body text-sm font-semibold text-ink-900">ReportAI</p>
            <p class="font-body text-[11px] text-ink-900/50">{{ t('landing.approval.mockup.channel') }}</p>
          </div>
        </div>
        <div class="space-y-3 p-4">
          <div class="bubble m-hide ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-capture-600 px-4 py-3 text-white">
            <div class="flex items-center gap-2">
              <svg viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5 shrink-0">
                <path d="M6 4.5v11l9-5.5-9-5.5Z" />
              </svg>
              <span class="flex items-end gap-0.5">
                <span v-for="(h, i) in WAVE_HEIGHTS" :key="i" class="w-0.5 rounded-full bg-white/70" :style="{ height: `${h}px` }" />
              </span>
              <span class="font-mono text-xs text-white">0:47</span>
            </div>
          </div>

          <div class="bubble m-hide w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-paper-50 px-4 py-3">
            <p class="font-body text-sm font-medium text-ink-900">{{ t('landing.approval.mockup.draftReady') }}</p>
            <div class="mt-2 space-y-1 font-mono text-xs text-ink-900">
              <p><span class="text-ink-900/60">company_name:</span> {{ t('landing.approval.mockup.company') }}</p>
              <p><span class="text-ink-900/60">meeting_date:</span> {{ t('landing.approval.mockup.date') }}</p>
              <p><span class="text-ink-900/60">decisions:</span> 2</p>
            </div>
            <div class="mt-3 flex gap-2">
              <span class="rounded-md border border-approved-600 px-2.5 py-1 font-body text-xs font-medium text-approved-600">{{ t('landing.approval.mockup.approve') }}</span>
              <span class="rounded-md border border-ink-900/15 px-2.5 py-1 font-body text-xs text-ink-900/60">{{ t('landing.approval.mockup.correct') }}</span>
            </div>
          </div>

          <div class="bubble m-hide ml-auto w-fit rounded-2xl rounded-br-md bg-capture-600 px-4 py-2 font-body text-sm text-white">
            {{ t('landing.approval.mockup.approve') }}
          </div>

          <div class="bubble m-hide w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-paper-50 px-4 py-3">
            <div class="flex items-center gap-3">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ink-900 text-white">
                <svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4">
                  <path d="M4 2h8l4 4v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm7 1.5V7h3.5L11 3.5ZM6 10h8v1.2H6V10Zm0 3h8v1.2H6V13Z" />
                </svg>
              </span>
              <div>
                <p class="font-mono text-xs text-ink-900">{{ t('landing.approval.mockup.filename') }}</p>
                <p class="mt-0.5 font-body text-xs font-medium text-approved-600">{{ t('landing.approval.mockup.sentTo') }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
