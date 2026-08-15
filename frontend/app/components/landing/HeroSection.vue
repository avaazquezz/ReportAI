<script setup lang="ts">
import gsap from 'gsap'

const placeholderTag = '{{ tu_informe }}'

const headlinePlaceholder = ref<HTMLElement | null>(null)
const headline = ref<HTMLElement | null>(null)
const subheadline = ref<HTMLElement | null>(null)
const ctas = ref<HTMLElement | null>(null)
const demo = ref<HTMLElement | null>(null)

onMounted(() => {
  if (usePrefersReducedMotion()) {
    gsap.set([subheadline.value, ctas.value, demo.value], { opacity: 1, y: 0 })
    gsap.set(headlinePlaceholder.value, { opacity: 0 })
    gsap.set(headline.value, { opacity: 1 })
    return
  }

  gsap.set([subheadline.value, ctas.value, demo.value], { opacity: 0, y: 16 })
  gsap.set(headline.value, { opacity: 0, y: 12 })

  gsap
    .timeline()
    // The headline opens as an unresolved template tag — the page's own signature —
    // then crossfades into its real value, echoing what the product itself does.
    .to(headlinePlaceholder.value, { opacity: 1, duration: 0.01 })
    .to(headlinePlaceholder.value, { opacity: 0, y: -6, duration: 0.35, ease: 'power2.out' }, '+=0.35')
    .to(headline.value, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, '<')
    .to([subheadline.value, ctas.value, demo.value], {
      opacity: 1,
      y: 0,
      duration: 0.6,
      stagger: 0.15,
      ease: 'power2.out'
    })
})
</script>

<template>
  <section class="mx-auto grid max-w-[1200px] items-center gap-12 px-6 py-16 md:grid-cols-2 md:py-28">
    <div>
      <div class="relative">
        <p
          ref="headlinePlaceholder"
          class="absolute inset-0 font-mono text-2xl text-ink-900/30 md:text-3xl"
          aria-hidden="true"
        >
          {{ placeholderTag }}
        </p>
        <h1
          ref="headline"
          class="font-display text-4xl font-bold leading-[1.05] tracking-tight text-ink-900 sm:text-5xl md:text-6xl lg:text-7xl"
        >
          Manda una nota de voz.<br>Recibe el acta en tu propia plantilla.
        </h1>
      </div>
      <p ref="subheadline" class="mt-6 max-w-md font-body text-lg text-ink-900/80">
        ReportAI transcribe la reunión, rellena el documento exacto que ya usas en tu empresa y lo
        envía a quien corresponde — por Telegram, el canal por defecto, o el que ya uses. Sin unirse
        a videollamadas, sin plantillas genéricas, sin instalar nada.
      </p>
      <div ref="ctas" class="mt-8">
        <a
          href="mailto:adrian@vazquezdev.pro"
          class="inline-block rounded-md bg-capture-600 px-8 py-4 font-body text-lg font-semibold text-white transition-transform hover:scale-[1.02] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-capture-600 focus-visible:ring-offset-2"
        >
          Quiero ser cliente
        </a>
      </div>
    </div>
    <div ref="demo" class="flex flex-col items-center gap-3 md:items-end">
      <div class="rotate-[-1deg] transition-transform hover:rotate-0">
        <LandingVoiceToDocDemo />
      </div>
      <a
        href="#ejemplo-real"
        class="font-body text-sm text-ink-900/60 transition-colors hover:text-capture-500"
      >
        Mira un ejemplo real ↓
      </a>
    </div>
  </section>
</template>
