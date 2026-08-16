<script setup lang="ts">
import gsap from 'gsap'

const { t } = useI18n()

const card = ref<HTMLElement | null>(null)
const headlinePlaceholder = ref<HTMLElement | null>(null)
const headline = ref<HTMLElement | null>(null)
const sub = ref<HTMLElement | null>(null)
const actions = ref<HTMLElement | null>(null)
// Observe the card (always rendered), never a ref inside a v-if — an unmounted
// target would silently never trigger the reveal.
const inView = useInView(card, 0.4)

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set(headlinePlaceholder.value, { opacity: 0 })
    gsap.set([headline.value, sub.value, actions.value], { opacity: 1, y: 0 })
    return
  }

  gsap.set(headline.value, { y: 8 })
  gsap
    .timeline()
    .to(headlinePlaceholder.value, { opacity: 0, y: -6, duration: 0.35, ease: 'power2.out' }, '+=0.35')
    .to(headline.value, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, '<')
    .fromTo(
      [sub.value, actions.value],
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.5, stagger: 0.12, ease: 'power2.out' }
    )
})
</script>

<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <div
      ref="card"
      class="relative overflow-hidden rounded-2xl bg-ink-900 px-6 py-16 text-center text-white md:px-8 md:py-20"
      style="background-image: radial-gradient(circle at 50% 0%, rgba(255, 106, 69, 0.15), transparent 60%)"
    >
      <div class="relative mx-auto flex max-w-2xl items-center justify-center">
        <p
          ref="headlinePlaceholder"
          class="absolute inset-0 flex items-center justify-center font-mono text-lg text-white/30 md:text-xl"
          aria-hidden="true"
        >
          {{ t('landing.finalCta.placeholderTag') }}
        </p>
        <h2 ref="headline" class="font-display text-4xl font-bold opacity-0 md:text-6xl">
          {{ t('landing.finalCta.headline') }}
        </h2>
      </div>
      <p ref="sub" class="mx-auto mt-6 max-w-xl font-body text-lg text-white/70 opacity-0">
        {{ t('landing.finalCta.sub') }}
      </p>
      <div ref="actions" class="mt-8 flex justify-center opacity-0">
        <a
          href="mailto:adrian@vazquezdev.pro"
          class="rounded-md bg-capture-600 px-8 py-4 font-body text-lg font-semibold text-white transition-transform hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-capture-600 focus-visible:ring-offset-2"
        >
          {{ t('landing.cta.becomeClient') }}
        </a>
      </div>
    </div>
  </section>
</template>
