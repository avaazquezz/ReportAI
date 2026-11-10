<script setup lang="ts">
// How it works, in the three steps that really exist. On a wide screen one sheet stays in view and
// changes state as each step reaches the middle of the screen (no scroll-jacking: the page scrolls
// as usual); on a phone every step carries its own picture.
const { t } = useI18n()
const STEPS = ['dictate', 'review', 'sign'] as const

const active = ref(0)
const list = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | undefined

onMounted(() => {
  if (!list.value) return
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) if (entry.isIntersecting) active.value = Number((entry.target as HTMLElement).dataset.index)
    },
    { rootMargin: '-45% 0px -45% 0px' }
  )
  list.value.querySelectorAll('[data-index]').forEach((step) => observer!.observe(step))
})
onUnmounted(() => observer?.disconnect())
</script>

<template>
  <section id="como-funciona" class="space-l" aria-labelledby="steps-title">
    <div class="home-grid">
      <h2 id="steps-title" class="t-section col-span-12 m-0 lg:col-span-8">{{ t('home.steps.heading') }}</h2>

      <ol ref="list" class="col-span-12 m-0 mt-16 p-0 lg:col-span-5 lg:mt-24">
        <li
          v-for="(key, index) in STEPS"
          :key="key"
          :data-index="index"
          class="list-none border-t border-ink-900/15 pb-16 pt-6 lg:min-h-[62vh] lg:pb-0"
          :aria-current="active === index ? 'step' : undefined"
        >
          <p class="t-data m-0 transition-colors duration-300" :class="active === index ? 'text-[#C0432A]' : 'text-ink-900/60'">
            {{ index + 1 }}/{{ STEPS.length }} · {{ t(`home.steps.states.${key}`) }}
          </p>
          <h3 class="t-plan-lg m-0 mt-4">{{ t(`home.steps.items.${key}.title`) }}</h3>
          <p class="t-body m-0 mt-4 max-w-[30rem] text-ink-900/75">{{ t(`home.steps.items.${key}.body`) }}</p>
          <HomeStepPanel :step="key" class="mt-10 lg:hidden" />
        </li>
      </ol>

      <div class="relative col-span-6 col-start-7 mt-24 hidden lg:block" aria-hidden="true">
        <div class="sticky top-[18vh] grid">
          <HomeStepPanel
            v-for="(key, index) in STEPS"
            :key="key"
            :step="key"
            class="step-visual col-start-1 row-start-1 self-start transition-[opacity,transform] duration-500"
            :class="active === index ? 'opacity-100' : 'pointer-events-none translate-y-3 opacity-0'"
          />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.step-visual {
  transition-timing-function: var(--ease-ra);
}
@media (prefers-reduced-motion: reduce) {
  .step-visual {
    transition: none;
    transform: none;
  }
}
</style>
