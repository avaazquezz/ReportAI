<script setup lang="ts">
const SIZES = {
  lg: 'text-[clamp(2rem,4.4vw,3.75rem)]',
  md: 'text-[clamp(1.9rem,3.5vw,3rem)]',
  sm: 'text-[clamp(1.6rem,2.9vw,2.35rem)]'
}

withDefaults(defineProps<{ tone?: 'light' | 'dark'; as?: 'h2' | 'h3'; size?: 'lg' | 'md' | 'sm' }>(), {
  tone: 'light',
  as: 'h2',
  size: 'lg'
})

// SplitText replaces the heading's text with line wrappers, so Vue can no longer patch it when
// the language changes. Keying the element by locale renders a fresh heading instead of leaving
// the old language on screen (the new one is shown plain: it already did its reveal).
const { locale } = useI18n()

const el = ref<HTMLElement | null>(null)
useMotionScope(el, (c) => {
  if (c.motion) revealLines(el.value!)
})
</script>

<template>
  <component
    :is="as"
    :key="locale"
    ref="el"
    class="font-plan font-extrabold leading-[1.08] tracking-[-0.035em]"
    :class="[tone === 'dark' ? 'text-white' : 'text-ink-900', SIZES[size]]"
  >
    <slot />
  </component>
</template>
