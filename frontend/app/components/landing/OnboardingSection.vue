<script setup lang="ts">
const { t } = useI18n()

const STEPS = ['tell', 'configure', 'first'] as const
// Everything a tenant admin manages in the panel today — see PROJECT_ROADMAP.md Phase 2.
const PANEL = ['templates', 'channels', 'recipients', 'history', 'usage'] as const

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.head', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
    .fromTo('.ob', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.45, stagger: 0.14 }, '-=0.2')
    .fromTo('.panel', { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.45 }, '-=0.1')
})
</script>

<template>
  <section id="alta" ref="root" class="bg-surface-0 py-20 md:py-28">
    <div class="mx-auto max-w-[1200px] px-6">
      <div class="head m-hide max-w-2xl">
        <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900 [text-wrap:balance]">
          {{ t('landing.onboarding.heading') }}
        </h2>
        <p class="mt-4 font-body text-lg text-ink-900/75">{{ t('landing.onboarding.sub') }}</p>
      </div>

      <ol class="mb-0 mt-12 grid list-none gap-8 pl-0 md:grid-cols-3 md:gap-10">
        <li v-for="(key, i) in STEPS" :key="key" class="ob m-hide border-t-2 border-ink-900 pt-5">
          <span class="font-display text-4xl font-bold leading-none text-capture-600" aria-hidden="true">{{ i + 1 }}</span>
          <h3 class="mt-4 font-display text-xl font-bold leading-snug text-ink-900">{{ t(`landing.onboarding.steps.${key}.title`) }}</h3>
          <p class="mt-2 font-body text-base leading-relaxed text-ink-900/70">{{ t(`landing.onboarding.steps.${key}.body`) }}</p>
        </li>
      </ol>

      <div class="panel m-hide mt-14 flex flex-col gap-4 rounded-2xl border border-paper-100 bg-paper-50 px-6 py-5 md:flex-row md:items-center md:gap-8">
        <p class="shrink-0 font-body text-sm font-semibold text-ink-900">{{ t('landing.onboarding.panelLabel') }}</p>
        <ul class="m-0 flex list-none flex-wrap gap-2 pl-0">
          <li
            v-for="key in PANEL"
            :key="key"
            class="rounded-full border border-ink-900/15 bg-surface-0 px-3 py-1 font-body text-sm text-ink-900/80"
          >
            {{ t(`landing.onboarding.panel.${key}`) }}
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
