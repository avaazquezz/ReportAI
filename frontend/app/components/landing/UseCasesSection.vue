<script setup lang="ts">
import gsap from 'gsap'

const { t } = useI18n()

const ITEMS = ['safetyVisit', 'incident', 'custom'] as const
// "campo_a · campo_b" in i18n: each one becomes a chip.
const fields = (key: (typeof ITEMS)[number]) => t(`landing.useCases.items.${key}.fields`).split(' · ')

const root = ref<HTMLElement | null>(null)
useMotionScope(root, (c) => {
  if (!c.motion) return
  gsap.utils.toArray<HTMLElement>('.uc-row').forEach((row) => {
    const scrollTrigger = { trigger: row, start: 'top 85%', once: true }
    gsap
      .timeline({ scrollTrigger })
      .from(row.querySelector('.uc-rule'), { scaleX: 0, transformOrigin: 'left', duration: MOTION.piece })
      .from(row.querySelectorAll('.uc-copy'), { opacity: 0, y: 14, duration: MOTION.reveal, stagger: 0.1, clearProps: 'opacity,transform' }, 0.15)
      .from(row.querySelectorAll('.uc-chip'), { opacity: 0, scale: 0.85, duration: 0.4, stagger: 0.06, ease: 'back.out(1.8)', clearProps: 'opacity,transform' }, 0.5)
  })
})
</script>

<template>
  <section id="casos" ref="root" class="bg-surface-0 py-20 md:py-28">
    <div class="mx-auto max-w-[1240px] px-6">
      <div class="max-w-3xl">
        <LandingSectionHeading>{{ t('landing.useCases.heading') }}</LandingSectionHeading>
        <p class="mb-0 mt-5 max-w-2xl font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.useCases.sub') }}</p>
      </div>

      <ul class="mb-0 mt-12 list-none pl-0">
        <li v-for="key in ITEMS" :key="key" class="uc-row">
          <div class="uc-rule h-px w-full bg-ink-900/20" />
          <div class="grid gap-4 py-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)_minmax(0,1fr)] lg:gap-10">
            <h3 class="uc-copy m-0 font-plan text-[1.5rem] font-extrabold leading-tight tracking-[-0.03em] text-ink-900">{{ t(`landing.useCases.items.${key}.title`) }}</h3>
            <p class="uc-copy m-0 font-body text-base leading-relaxed text-ink-900/75">{{ t(`landing.useCases.items.${key}.body`) }}</p>
            <div class="flex flex-wrap content-start gap-2 lg:justify-end">
              <span class="uc-copy w-full font-mono text-[11px] text-ink-900/55 lg:text-right">{{ t('landing.useCases.fieldsLabel') }}</span>
              <span v-for="f in fields(key)" :key="f" class="uc-chip rounded border border-capture-600/35 bg-capture-100/50 px-2 py-0.5 font-mono text-[11.5px] text-capture-600">{{ f }}</span>
            </div>
          </div>
        </li>
        <li class="uc-end h-px w-full bg-ink-900/20" aria-hidden="true" />
      </ul>
    </div>
  </section>
</template>
