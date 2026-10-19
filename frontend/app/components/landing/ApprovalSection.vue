<script setup lang="ts">
import gsap from 'gsap'

const { t } = useI18n()

// Static waveform for the voice-note bubble — the motion here is the conversation itself
// arriving, one message after another.
const WAVE_HEIGHTS = [6, 10, 14, 9, 16, 7, 12, 18, 8, 13, 10, 6]

const root = ref<HTMLElement | null>(null)
useMotionScope(root, (c) => {
  if (!c.motion) return
  gsap.from('.ap-text', { opacity: 0, y: 14, duration: MOTION.reveal, stagger: 0.12, clearProps: 'opacity,transform', scrollTrigger: { trigger: '.ap-text', start: 'top 85%', once: true } })
  gsap
    .timeline({ scrollTrigger: { trigger: '.ap-phone', start: 'top 70%', once: true } })
    .from('.ap-phone', { opacity: 0, y: 30, duration: MOTION.reveal + 0.2, clearProps: 'opacity,transform' })
    // The conversation plays itself: voice note, the bot asks, the answer, the draft, approve, delivered.
    .from('.bubble', { opacity: 0, y: 12, scale: 0.94, duration: 0.45, stagger: 0.55, ease: 'back.out(1.5)', clearProps: 'opacity,transform' }, 0.5)
})
</script>

<template>
  <section id="aprobacion" ref="root" class="bg-surface-0 py-20 md:py-28">
    <div class="mx-auto grid max-w-[1240px] items-center gap-12 px-6 md:grid-cols-2 lg:gap-20">
      <div>
        <LandingSectionHeading>{{ t('landing.approval.heading') }}</LandingSectionHeading>
        <p class="ap-text mb-0 mt-5 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.approval.paragraph1') }}</p>
        <p class="ap-text mb-0 mt-4 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.approval.paragraph2') }}</p>
        <div class="ap-text mt-8 flex flex-wrap items-center gap-3">
          <span class="rounded-full border border-capture-600 bg-surface-0 px-4 py-1.5 font-body text-sm font-semibold text-capture-600">
            {{ t('landing.approval.defaultChannelBadge') }}
          </span>
          <span class="rounded-full border border-ink-900/15 px-4 py-1.5 font-body text-sm text-ink-900/70">
            {{ t('landing.approval.otherChannelNote') }}
          </span>
        </div>
      </div>

      <div class="ap-phone w-full max-w-sm justify-self-center overflow-hidden rounded-2xl bg-surface-0 shadow-float ring-1 ring-ink-900/5 md:justify-self-end" aria-hidden="true">
        <div class="flex items-center gap-3 border-b border-paper-100 px-4 py-3">
          <span class="flex h-8 w-8 items-center justify-center rounded-full bg-ink-900 font-plan text-xs font-extrabold text-capture-500">R</span>
          <div class="leading-tight">
            <p class="m-0 font-body text-sm font-semibold text-ink-900">ReportAI</p>
            <p class="m-0 font-body text-[11px] text-ink-900/60">{{ t('landing.approval.mockup.channel') }}</p>
          </div>
        </div>
        <div class="space-y-3 p-4">
          <div class="bubble ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-capture-600 px-4 py-3 text-white">
            <div class="flex items-center gap-2">
              <svg viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5 shrink-0"><path d="M6 4.5v11l9-5.5-9-5.5Z" /></svg>
              <span class="flex items-end gap-0.5">
                <span v-for="(h, i) in WAVE_HEIGHTS" :key="i" class="w-0.5 rounded-full bg-white/70" :style="{ height: `${h}px` }" />
              </span>
              <span class="font-mono text-xs text-white">{{ t('landing.hero.stage.voiceDuration') }}</span>
            </div>
          </div>

          <div class="bubble w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-paper-50 px-4 py-3 font-body text-sm text-ink-900">
            {{ t('landing.approval.mockup.question') }}
          </div>

          <div class="bubble ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-capture-600 px-4 py-2 font-body text-sm text-white">
            {{ t('landing.approval.mockup.answer') }}
          </div>

          <div class="bubble w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-paper-50 px-4 py-3">
            <p class="m-0 font-body text-sm font-medium text-ink-900">{{ t('landing.approval.mockup.draftReady') }}</p>
            <div class="mt-2 space-y-1 font-mono text-xs text-ink-900">
              <p class="m-0"><span class="text-ink-900/60">{{ t('landing.approval.mockup.siteLabel') }}:</span> {{ t('landing.approval.mockup.site') }}</p>
              <p class="m-0"><span class="text-ink-900/60">{{ t('landing.approval.mockup.dateLabel') }}:</span> {{ t('landing.approval.mockup.date') }}</p>
              <p class="m-0"><span class="text-ink-900/60">{{ t('landing.approval.mockup.issuesLabel') }}:</span> 3</p>
            </div>
            <div class="mt-3 flex gap-2">
              <span class="rounded-md border border-approved-600 px-2.5 py-1 font-body text-xs font-medium text-approved-600">{{ t('landing.approval.mockup.approve') }}</span>
              <span class="rounded-md border border-ink-900/15 px-2.5 py-1 font-body text-xs text-ink-900/60">{{ t('landing.approval.mockup.correct') }}</span>
            </div>
          </div>

          <div class="bubble ml-auto w-fit rounded-2xl rounded-br-md bg-capture-600 px-4 py-2 font-body text-sm text-white">
            {{ t('landing.approval.mockup.approve') }}
          </div>

          <div class="bubble w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-paper-50 px-4 py-3">
            <div class="flex items-center gap-3">
              <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ink-900 text-white">
                <svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4">
                  <path d="M4 2h8l4 4v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm7 1.5V7h3.5L11 3.5ZM6 10h8v1.2H6V10Zm0 3h8v1.2H6V13Z" />
                </svg>
              </span>
              <div>
                <p class="m-0 break-all font-mono text-xs text-ink-900">{{ t('landing.approval.mockup.filename') }}</p>
                <p class="m-0 mt-0.5 font-body text-xs font-medium text-approved-600">{{ t('landing.approval.mockup.sentTo') }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
