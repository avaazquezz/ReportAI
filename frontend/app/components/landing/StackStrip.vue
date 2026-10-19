<script setup lang="ts">
import gsap from 'gsap'

const { t } = useI18n()

const ITEMS = ['fastapi', 'langgraph', 'pydantic', 'postgres', 'models', 'whisper', 'render', 'nuxt', 'docker'] as const

const root = ref<HTMLElement | null>(null)
useMotionScope(root, (c) => {
  if (!c.motion) return
  const scrollTrigger = { trigger: root.value, start: 'top 92%', once: true }
  gsap.from('.stack-rule', { scaleX: 0, transformOrigin: 'left', duration: MOTION.piece, scrollTrigger })
  gsap.from('.stack-item', { opacity: 0, x: -14, duration: MOTION.reveal, stagger: 0.05, clearProps: 'opacity,transform', scrollTrigger })
})
</script>

<template>
  <section ref="root" class="border-b border-paper-100 bg-surface-0">
    <div class="mx-auto max-w-[1240px] px-6 py-8">
      <div class="stack-rule mb-5 h-px w-full bg-ink-900/15" />
      <div class="flex flex-col gap-4 md:flex-row md:items-start md:gap-10">
        <p class="m-0 shrink-0 pt-1 font-mono text-[11px] text-capture-600 md:w-28">{{ t('landing.stack.label') }}</p>
        <ul class="m-0 grid list-none grid-cols-2 gap-x-6 gap-y-4 p-0 sm:flex sm:flex-wrap sm:gap-x-7">
          <li v-for="key in ITEMS" :key="key" class="stack-item">
            <span class="block font-plan text-[0.95rem] font-bold leading-tight tracking-[-0.01em] text-ink-900">{{ t(`landing.stack.items.${key}.name`) }}</span>
            <span class="mt-0.5 block font-mono text-[11px] text-ink-900/60">{{ t(`landing.stack.items.${key}.role`) }}</span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
