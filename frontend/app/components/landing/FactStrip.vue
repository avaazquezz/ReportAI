<script setup lang="ts">
const { t } = useI18n()

const FACTS = ['noApp', 'yourTemplate', 'approval', 'realExample'] as const

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.fact', { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.08 })
})
</script>

<template>
  <section ref="root" class="border-y border-paper-100 bg-surface-0">
    <ul class="mx-auto grid max-w-[1200px] list-none gap-x-8 gap-y-7 px-6 py-9 sm:grid-cols-2 lg:grid-cols-4">
      <li v-for="key in FACTS" :key="key" class="fact m-hide border-l-2 border-capture-500 pl-4">
        <p class="font-display text-base font-bold text-ink-900">{{ t(`landing.facts.${key}.title`) }}</p>
        <p class="mt-1 font-body text-sm leading-relaxed text-ink-900/70">{{ t(`landing.facts.${key}.body`) }}</p>
      </li>
    </ul>
  </section>
</template>
