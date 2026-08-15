<script setup lang="ts">
import gsap from 'gsap'

const root = ref<HTMLElement | null>(null)
const mark = ref<HTMLElement | null>(null)
const text = ref<HTMLElement | null>(null)
const inView = useInView(root, 0.3)

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set([mark.value, text.value], { opacity: 1, scale: 1, y: 0 })
    return
  }

  gsap
    .timeline()
    .fromTo(mark.value, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'back.out(2)' })
    .fromTo(text.value, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, '+=0.1')
})
</script>

<template>
  <section ref="root" class="bg-ink-900 py-16 text-white md:py-24">
    <div class="mx-auto max-w-2xl px-6 text-center">
      <span
        ref="mark"
        class="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-approved-600 text-white opacity-0 md:h-20 md:w-20"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" class="h-8 w-8 md:h-10 md:w-10">
          <path d="M16.7 5.3a1 1 0 0 1 0 1.4l-7 7a1 1 0 0 1-1.4 0l-3-3a1 1 0 1 1 1.4-1.4l2.3 2.29 6.3-6.29a1 1 0 0 1 1.4 0Z" />
        </svg>
      </span>
      <div ref="text" class="opacity-0">
        <h2 class="mt-6 font-display text-4xl font-bold md:text-5xl">Nada sale sin que lo apruebes.</h2>
        <p class="mt-4 font-body text-lg text-white/80">
          Cada informe pasa por una revisión humana obligatoria antes de entregarse. Si algo no
          cuadra, corriges con una simple respuesta y ReportAI vuelve a intentarlo.
        </p>
      </div>
    </div>
  </section>
</template>
