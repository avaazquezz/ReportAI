<script setup lang="ts">
const { t } = useI18n()

const ITEMS = ['minutes', 'visit', 'custom'] as const

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.head', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
    .fromTo('.case', { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.45, stagger: 0.12 }, '-=0.2')
})
</script>

<template>
  <section id="casos" ref="root" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto max-w-[1200px] px-6">
      <div class="head m-hide max-w-3xl">
        <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900 [text-wrap:balance]">
          {{ t('landing.useCases.heading') }}
        </h2>
        <p class="mt-4 font-body text-lg text-ink-900/75">{{ t('landing.useCases.sub') }}</p>
      </div>

      <ul class="mb-0 mt-12 list-none divide-y divide-ink-900/10 border-y border-ink-900/10 pl-0">
        <li
          v-for="key in ITEMS"
          :key="key"
          class="case m-hide grid gap-3 py-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.4fr)_minmax(0,0.9fr)] lg:items-baseline lg:gap-10"
        >
          <h3 class="font-display text-2xl font-bold leading-tight text-ink-900">{{ t(`landing.useCases.items.${key}.title`) }}</h3>
          <p class="font-body text-base leading-relaxed text-ink-900/75">{{ t(`landing.useCases.items.${key}.body`) }}</p>
          <p class="font-mono text-xs leading-relaxed text-capture-600 lg:text-right">
            <span class="text-ink-900/45">{{ t('landing.useCases.fieldsLabel') }} · </span>{{ t(`landing.useCases.items.${key}.fields`) }}
          </p>
        </li>
      </ul>
    </div>
  </section>
</template>
