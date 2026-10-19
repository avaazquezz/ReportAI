<script setup lang="ts">
import gsap from 'gsap'

const { t } = useI18n()

// Each row is one chore of today's inspection report, next to what replaces it.
const ROWS = ['notes', 'word', 'missing', 'send', 'find'] as const

const root = ref<HTMLElement | null>(null)
useMotionScope(root, (c) => {
  if (c.reduce) {
    gsap.set('.strike', { backgroundSize: '100% 2px' })
    return
  }
  const scrollTrigger = { trigger: '.dp-panel', start: 'top 72%', once: true }
  gsap
    .timeline({ scrollTrigger })
    .from('.dp-panel', { opacity: 0, y: 24, duration: MOTION.reveal, clearProps: 'opacity,transform' })
    // The old way is crossed out, row by row, and the new one is ticked.
    .to('.strike', { backgroundSize: '100% 2px', duration: 0.5, stagger: 0.28 }, 0.5)
    .from('.dp-after', { opacity: 0, x: 10, duration: 0.5, stagger: 0.28, clearProps: 'opacity,transform' }, 0.7)
    .from('.dp-check', { scale: 0, duration: 0.4, stagger: 0.28, ease: 'back.out(2.2)', transformOrigin: '50% 50%' }, 0.7)
  gsap.from('.dp-kicker', { opacity: 0, y: 10, duration: MOTION.reveal, scrollTrigger: { trigger: '.dp-kicker', start: 'top 90%', once: true } })
})
</script>

<template>
  <section id="problema" ref="root" class="bg-surface-0 py-20 md:py-28">
    <div class="mx-auto grid max-w-[1240px] items-start gap-12 px-6 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
      <div>
        <LandingSectionHeading>{{ t('landing.differentiator.heading') }}</LandingSectionHeading>
        <p class="mb-0 mt-6 max-w-xl font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.differentiator.paragraph') }}</p>
        <p class="dp-kicker mb-0 mt-8 font-plan text-xl font-bold tracking-[-0.02em] text-capture-600">{{ t('landing.differentiator.kicker') }}</p>
      </div>

      <div class="dp-panel overflow-hidden rounded-2xl border border-ink-900/10 bg-paper-50">
        <table class="w-full border-collapse font-body text-sm">
          <caption class="sr-only">{{ t('landing.differentiator.table.caption') }}</caption>
          <thead>
            <tr class="border-b border-ink-900/10">
              <th scope="col" class="w-1/2 px-5 py-4 text-left text-xs font-medium text-ink-900/60">{{ t('landing.differentiator.table.before') }}</th>
              <th scope="col" class="w-1/2 bg-capture-100/70 px-5 py-4 text-left font-plan text-sm font-bold text-capture-600">{{ t('landing.differentiator.table.after') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in ROWS" :key="key" class="border-b border-ink-900/10 align-top last:border-b-0">
              <td class="px-5 py-4 text-ink-900/60">
                <span class="strike" style="background: linear-gradient(currentColor, currentColor) no-repeat 0 56% / 0% 2px">{{ t(`landing.differentiator.table.rows.${key}.before`) }}</span>
              </td>
              <td class="dp-after bg-capture-100/70 px-5 py-4 font-medium text-ink-900">
                <span class="flex gap-2.5">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" class="dp-check mt-0.5 h-4 w-4 shrink-0 text-approved-600" aria-hidden="true">
                    <path d="M4 10.5l4 4 8-9" />
                  </svg>
                  {{ t(`landing.differentiator.table.rows.${key}.after`) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
