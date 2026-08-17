<script setup lang="ts">
import gsap from 'gsap'

const { t, locale } = useI18n()
// Vue's own template tokenizer treats literal "{{"/"}}" inside a mustache
// expression as an unterminated nested interpolation — building the string in
// script and interpolating the result avoids that.
const eyebrowTag = computed(() => `{{ ${t('landing.approval.eyebrowTag')} }}`)

// Reuses the RealDemoSection story (same fictional client across the whole page).
const mockCompanyName = computed(() => (locale.value === 'es' ? 'Construcciones Marítimas' : 'Harbor Point Industrial'))
const mockMeetingDate = computed(() => (locale.value === 'es' ? '18/08/2025' : '08/18/2025'))

// Static waveform for the voice-note bubble — the motion here is the
// conversation itself popping in, not the bars.
const WAVE_HEIGHTS = [6, 10, 14, 9, 16, 7, 12, 18, 8, 13, 10, 6]

const root = ref<HTMLElement | null>(null)
const textCol = ref<HTMLElement | null>(null)
const bubbles = ref<HTMLElement[]>([])
const inView = useInView(root, 0.3)

function setBubbleRef(el: unknown, i: number) {
  if (el) bubbles.value[i] = el as HTMLElement
}

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set([textCol.value, ...bubbles.value], { opacity: 1, y: 0, scale: 1 })
    return
  }

  gsap
    .timeline()
    .fromTo(textCol.value, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' })
    .fromTo(
      bubbles.value,
      { opacity: 0, y: 12, scale: 0.97 },
      { opacity: 1, y: 0, scale: 1, duration: 0.45, stagger: 0.5, ease: 'back.out(1.4)' },
      '-=0.1'
    )
})
</script>

<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <div ref="root" class="grid items-center gap-12 md:grid-cols-2">
      <div ref="textCol" class="opacity-0">
        <p class="mb-2 font-mono text-xs uppercase tracking-wide text-capture-600">{{ eyebrowTag }}</p>
        <h2 class="font-display text-3xl font-bold text-ink-900 md:text-4xl">
          {{ t('landing.approval.heading') }}
        </h2>
        <p class="mt-6 font-body text-lg text-ink-900/80">
          {{ t('landing.approval.paragraph1') }}
        </p>
        <p class="mt-4 font-body text-lg text-ink-900/80">
          {{ t('landing.approval.paragraph2') }}
        </p>
        <div class="mt-8 flex flex-wrap items-center gap-3">
          <span
            class="rounded-full border border-capture-600 bg-surface-0 px-5 py-2 font-body text-sm font-semibold text-capture-600"
          >
            {{ t('landing.approval.defaultChannelBadge') }}
          </span>
          <span class="font-body text-sm text-ink-900/60">{{ t('landing.approval.otherChannelNote') }}</span>
        </div>
      </div>

      <div
        class="w-full max-w-sm justify-self-center overflow-hidden rounded-2xl bg-surface-0 shadow-xl md:justify-self-end"
      >
        <div class="flex items-center gap-3 border-b border-slate-300 px-4 py-3">
          <span class="flex h-8 w-8 items-center justify-center rounded-full bg-ink-900 font-display text-xs font-bold text-white">R</span>
          <div>
            <p class="font-body text-sm font-semibold text-ink-900">ReportAI</p>
            <p class="font-mono text-xs uppercase tracking-wide text-ink-900/70">Telegram</p>
          </div>
        </div>
        <div class="space-y-3 p-4">
          <div
            :ref="(el) => setBubbleRef(el, 0)"
            class="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-capture-600 px-4 py-3 text-white opacity-0"
          >
            <div class="flex items-center gap-2">
              <svg viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5 shrink-0">
                <path d="M6 4.5v11l9-5.5-9-5.5Z" />
              </svg>
              <span class="flex items-end gap-0.5" aria-hidden="true">
                <span
                  v-for="(h, i) in WAVE_HEIGHTS"
                  :key="i"
                  class="w-0.5 rounded-full bg-white/70"
                  :style="{ height: `${h}px` }"
                />
              </span>
              <span class="font-mono text-xs text-white">0:47</span>
            </div>
          </div>

          <div
            :ref="(el) => setBubbleRef(el, 1)"
            class="w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-paper-50 px-4 py-3 opacity-0"
          >
            <p class="font-body text-sm font-medium text-ink-900">{{ t('landing.approval.mockup.draftReady') }}</p>
            <div class="mt-2 space-y-1 font-mono text-xs text-ink-900">
              <p><span class="text-ink-900/70">company_name:</span> {{ mockCompanyName }}</p>
              <p><span class="text-ink-900/70">meeting_date:</span> {{ mockMeetingDate }}</p>
              <p><span class="text-ink-900/70">decisions:</span> 3</p>
            </div>
            <div class="mt-3 flex gap-2">
              <span class="rounded-md border border-approved-600 px-2.5 py-1 font-body text-xs font-medium text-approved-600">{{ t('landing.approval.mockup.approve') }}</span>
              <span class="rounded-md border border-slate-300 px-2.5 py-1 font-body text-xs text-ink-900/60">{{ t('landing.approval.mockup.correct') }}</span>
            </div>
          </div>

          <div
            :ref="(el) => setBubbleRef(el, 2)"
            class="ml-auto w-fit rounded-2xl rounded-br-md bg-capture-600 px-4 py-2 font-body text-sm text-white opacity-0"
          >
            {{ t('landing.approval.mockup.approve') }}
          </div>

          <div
            :ref="(el) => setBubbleRef(el, 3)"
            class="w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-paper-50 px-4 py-3 opacity-0"
          >
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
