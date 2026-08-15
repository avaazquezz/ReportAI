<script setup lang="ts">
const scrolled = ref(false)

function onScroll() {
  scrolled.value = window.scrollY > 8
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  // Native scroll restoration / hash-anchor jumps happen before this listener
  // attaches and fire no scroll event, so the header would stay transparent
  // over a page that loaded already scrolled.
  onScroll()
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <header
    class="sticky top-0 z-50 border-b transition-colors duration-300"
    :class="scrolled ? 'border-slate-300 bg-cream-50/90 backdrop-blur' : 'border-transparent bg-transparent'"
  >
    <div class="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
      <NuxtLink to="/" class="flex items-center gap-2.5">
        <svg viewBox="0 0 100 100" class="h-8 w-8 shrink-0" aria-hidden="true">
          <rect width="100" height="100" rx="24" class="fill-ink-900" />
          <text
            x="50"
            y="70"
            font-size="60"
            text-anchor="middle"
            font-family="Arial, Helvetica, sans-serif"
            font-weight="700"
            class="fill-capture-500"
          >R</text>
        </svg>
        <span class="font-display text-lg font-bold text-ink-900">ReportAI</span>
      </NuxtLink>
      <nav class="hidden items-center gap-8 font-body text-sm md:flex">
        <a href="#ejemplo-real" class="text-ink-900 hover:text-capture-500">Ejemplo real</a>
        <a href="#como-funciona" class="text-ink-900 hover:text-capture-500">Cómo funciona</a>
        <a href="#diferencia" class="text-ink-900 hover:text-capture-500">Diferencia</a>
      </nav>
    </div>
  </header>
</template>
