<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'light' | 'dark'; as?: 'h2' | 'h3' }>(), { tone: 'light', as: 'h2' })

const el = ref<HTMLElement | null>(null)
useMotionScope(el, (c) => {
  if (c.motion) revealLines(el.value!)
})
</script>

<template>
  <component
    :is="as"
    ref="el"
    class="font-plan text-[clamp(2rem,4.4vw,3.75rem)] font-extrabold leading-[1.08] tracking-[-0.035em]"
    :class="tone === 'dark' ? 'text-white' : 'text-ink-900'"
  >
    <slot />
  </component>
</template>
