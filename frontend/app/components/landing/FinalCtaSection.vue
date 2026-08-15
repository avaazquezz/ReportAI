<script setup lang="ts">
import gsap from 'gsap'

const placeholderTag = '{{ tu_proximo_informe }}'

const headlinePlaceholder = ref<HTMLElement | null>(null)
const headline = ref<HTMLElement | null>(null)
const inView = useInView(headline, 0.4)

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set(headlinePlaceholder.value, { opacity: 0 })
    gsap.set(headline.value, { opacity: 1 })
    return
  }

  gsap
    .timeline()
    .to(headlinePlaceholder.value, { opacity: 0, y: -6, duration: 0.35, ease: 'power2.out' }, '+=0.2')
    .to(headline.value, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, '<')
})
</script>

<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <LandingRevealOnScroll>
      <div
        class="relative overflow-hidden rounded-2xl bg-ink-900 px-8 py-16 text-center text-white"
        style="background-image: radial-gradient(circle at 50% 0%, rgba(255, 106, 69, 0.15), transparent 60%)"
      >
        <div class="relative mx-auto flex max-w-2xl items-center justify-center">
          <p
            ref="headlinePlaceholder"
            class="absolute inset-0 flex items-center justify-center font-mono text-lg text-white/30 md:text-xl"
            aria-hidden="true"
          >
            {{ placeholderTag }}
          </p>
          <h2 ref="headline" class="font-display text-4xl font-bold opacity-0 md:text-6xl">
            Manda una nota de voz. Recibe el acta.
          </h2>
        </div>
        <div class="mt-8 flex justify-center">
          <a
            href="mailto:adrian@vazquezdev.pro"
            class="rounded-md bg-capture-600 px-8 py-4 font-body text-lg font-semibold text-white transition-transform hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-capture-600 focus-visible:ring-offset-2"
          >
            Quiero ser cliente
          </a>
        </div>
      </div>
    </LandingRevealOnScroll>
  </section>
</template>
