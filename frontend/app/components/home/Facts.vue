<script setup lang="ts">
// Four facts a buyer can check, in place of the logos and testimonials a new product doesn't have
// yet. Printed like the header row of a form: ruled, no icons, no animation.
const { t } = useI18n()
const FACTS = ['template', 'offline', 'review', 'team'] as const
</script>

<template>
  <section class="border-y border-ink-900/10" aria-labelledby="facts-title">
    <h2 id="facts-title" class="sr-only">{{ t('home.facts.label') }}</h2>
    <dl class="home-grid m-0 gap-y-0">
      <div
        v-for="(key, index) in FACTS"
        :key="key"
        class="col-span-6 py-6 lg:col-span-3 lg:py-8"
        :class="[
          index > 0 ? 'lg:border-l lg:border-ink-900/10 lg:pl-6' : '',
          index % 2 === 1 ? 'border-l border-ink-900/10 pl-4 lg:pl-6' : '',
          index > 1 ? 'border-t border-ink-900/10 lg:border-t-0' : ''
        ]"
      >
        <dt class="text-[0.98rem] font-semibold">{{ t(`home.facts.items.${key}.title`) }}</dt>
        <dd class="m-0 mt-1 text-[0.9rem] leading-snug text-ink-900/60 [text-wrap:pretty]">{{ t(`home.facts.items.${key}.body`) }}</dd>
      </div>
    </dl>
  </section>
</template>
