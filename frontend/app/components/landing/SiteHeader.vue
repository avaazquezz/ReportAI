<script setup lang="ts">
const scrolled = ref(false)

function onScroll() {
  scrolled.value = window.scrollY > 8
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <header
    class="sticky top-0 z-50 transition-colors duration-300"
    :class="scrolled ? 'bg-surface-0/90 backdrop-blur border-b border-slate-300' : 'bg-transparent'"
  >
    <div class="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
      <NuxtLink to="/" class="font-display text-lg font-bold text-ink-900">ReportAI</NuxtLink>
      <nav class="hidden items-center gap-8 font-body text-sm md:flex">
        <a href="#como-funciona" class="text-ink-900 hover:text-capture-500">Cómo funciona</a>
        <a href="#diferencia" class="text-ink-900 hover:text-capture-500">Diferencia</a>
      </nav>
      <NuxtLink
        to="/login"
        class="rounded-md bg-ink-900 px-4 py-2 font-body text-sm font-medium text-white transition-transform hover:scale-[1.02]"
      >
        Acceder
      </NuxtLink>
    </div>
  </header>
</template>
