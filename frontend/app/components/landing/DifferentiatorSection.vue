<script setup lang="ts">
import gsap from 'gsap'

const eyebrowTag = '{{ la_diferencia }}'

// Template tags that will never be filled — the inversion of the page's
// resolve-the-tag motif: what meeting bots require and ReportAI doesn't.
const NOT_NEEDED = [
  '{{ enlace_de_calendario }}',
  '{{ bot_en_la_videollamada }}',
  '{{ aplicacion_nueva }}'
]

const root = ref<HTMLElement | null>(null)
const head = ref<HTMLElement | null>(null)
const kicker = ref<HTMLElement | null>(null)
const tagEls = ref<HTMLElement[]>([])
const strikes = ref<HTMLElement[]>([])
const inView = useInView(root, 0.3)

function setTagRef(el: unknown, i: number) {
  if (el) tagEls.value[i] = el as HTMLElement
}
function setStrikeRef(el: unknown, i: number) {
  if (el) strikes.value[i] = el as HTMLElement
}

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set([head.value, kicker.value, ...tagEls.value], { opacity: 1, y: 0 })
    gsap.set(strikes.value, { scaleX: 1 })
    return
  }

  gsap
    .timeline()
    .fromTo(head.value, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.6, ease: 'power2.out' })
    .fromTo(
      tagEls.value,
      { opacity: 0, y: 8 },
      { opacity: 1, y: 0, duration: 0.4, stagger: 0.1, ease: 'power2.out' },
      '-=0.2'
    )
    .fromTo(
      strikes.value,
      { scaleX: 0 },
      { scaleX: 1, duration: 0.35, stagger: 0.2, ease: 'power2.inOut' },
      '+=0.2'
    )
    .fromTo(kicker.value, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, '-=0.1')
})
</script>

<template>
  <section id="diferencia" ref="root" class="bg-ink-900 py-16 text-white md:py-24">
    <div class="mx-auto max-w-[1200px] px-6">
      <div ref="head" class="opacity-0">
        <p class="mb-2 font-mono text-xs uppercase tracking-wide text-capture-500">{{ eyebrowTag }}</p>
        <h2 class="max-w-4xl font-display text-4xl font-bold md:text-5xl lg:text-6xl">
          No es un bot que se cuela en tu videollamada.
        </h2>
        <p class="mt-6 max-w-2xl font-body text-lg text-white/80">
          Otter, Fireflies o Fathom necesitan una videollamada programada con un enlace. La mayoría de
          tus visitas comerciales y llamadas no lo tienen. ReportAI funciona con una nota de voz
          grabada después — en el coche, en el pasillo, nada más colgar — y la convierte en el
          documento con el formato exacto que tu empresa ya usa.
        </p>
      </div>
      <div class="mt-10 flex flex-wrap gap-x-10 gap-y-4">
        <span
          v-for="(tag, i) in NOT_NEEDED"
          :key="tag"
          :ref="(el) => setTagRef(el, i)"
          class="relative font-mono text-sm text-white/60 opacity-0"
        >
          {{ tag }}
          <span
            :ref="(el) => setStrikeRef(el, i)"
            class="absolute left-0 top-1/2 h-px w-full origin-left scale-x-0 bg-capture-500"
            aria-hidden="true"
          />
        </span>
      </div>
      <p ref="kicker" class="mt-6 font-body text-base text-white/60 opacity-0">
        Nada de esto hace falta. Solo una nota de voz.
      </p>
    </div>
  </section>
</template>
