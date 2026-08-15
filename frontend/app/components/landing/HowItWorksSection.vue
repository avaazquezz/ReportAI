<script setup lang="ts">
import gsap from 'gsap'

const eyebrowTag = '{{ como_funciona }}'

// Each step's mono artifact is the output that feeds the next step, so the
// pipeline reads as data flowing along the drawn line.
const STEPS = [
  {
    artifact: 'nota_de_voz.ogg',
    title: 'Grabas una nota de voz',
    body: 'En el coche, en el pasillo, nada más colgar. Por Telegram, el canal por defecto, o el que ya uses.'
  },
  {
    artifact: 'transcripcion.txt',
    title: 'Se transcribe',
    body: 'La IA convierte el audio en texto en segundos.'
  },
  {
    artifact: 'campos.json',
    title: 'Se extraen los datos',
    body: 'Identifica fecha, asistentes, resumen y acuerdos según los campos exactos de tu documento.'
  },
  {
    artifact: 'aprobado ✓',
    title: 'Lo apruebas tú',
    body: 'Revisas el borrador y confirmas, o pides una corrección puntual.'
  },
  {
    artifact: 'acta_reunion.docx',
    title: 'Se entrega',
    body: 'El documento se rellena en tu plantilla .docx y llega a quien corresponde.'
  }
]

const CAPTURE_600 = '#C0432A'

const list = ref<HTMLElement | null>(null)
const head = ref<HTMLElement | null>(null)
const railFill = ref<HTMLElement | null>(null)
const items = ref<HTMLElement[]>([])
const badges = ref<HTMLElement[]>([])
const segments = ref<HTMLElement[]>([])
const inView = useInView(list, 0.2)

function setItemRef(el: unknown, i: number) {
  if (el) items.value[i] = el as HTMLElement
}
function setBadgeRef(el: unknown, i: number) {
  if (el) badges.value[i] = el as HTMLElement
}
function setSegmentRef(el: unknown, i: number) {
  if (el) segments.value[i] = el as HTMLElement
}

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set([head.value, ...items.value], { opacity: 1, y: 0 })
    gsap.set(badges.value, { borderColor: CAPTURE_600, color: CAPTURE_600 })
    gsap.set(segments.value, { scaleX: 1 })
    gsap.set(railFill.value, { scaleY: 1 })
    return
  }

  gsap
    .timeline()
    .fromTo(head.value, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' })
    .fromTo(
      items.value,
      { opacity: 0, y: 16 },
      { opacity: 1, y: 0, duration: 0.45, stagger: 0.18, ease: 'power2.out' },
      '-=0.25'
    )
    .addLabel('items')
    .to(
      badges.value,
      { borderColor: CAPTURE_600, color: CAPTURE_600, duration: 0.3, stagger: 0.18 },
      'items+=0.05'
    )
    .fromTo(
      segments.value,
      { scaleX: 0 },
      { scaleX: 1, duration: 0.3, stagger: 0.18, ease: 'power1.inOut' },
      'items+=0.2'
    )
    .fromTo(railFill.value, { scaleY: 0 }, { scaleY: 1, duration: 1.1, ease: 'power1.inOut' }, 'items+=0.1')
})
</script>

<template>
  <section id="como-funciona" class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <div ref="head" class="opacity-0">
      <p class="mb-2 font-mono text-xs uppercase tracking-wide text-capture-600">{{ eyebrowTag }}</p>
      <h2 class="font-display text-3xl font-bold text-ink-900 md:text-4xl">
        De la nota de voz al acta entregada.
      </h2>
    </div>

    <ol ref="list" class="relative mt-12 list-none space-y-10 pl-0 lg:grid lg:grid-cols-5 lg:space-y-0">
      <div class="absolute bottom-28 left-4 top-4 w-px bg-slate-300 lg:hidden" aria-hidden="true">
        <div ref="railFill" class="h-full w-full origin-top scale-y-0 bg-capture-500" />
      </div>
      <li
        v-for="(step, i) in STEPS"
        :key="step.title"
        :ref="(el) => setItemRef(el, i)"
        class="relative pl-12 opacity-0 lg:pl-0 lg:pr-8 lg:pt-12"
      >
        <span
          :ref="(el) => setBadgeRef(el, i)"
          class="absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-full border border-slate-300 bg-paper-50 font-mono text-xs text-ink-900/50"
        >
          {{ String(i + 1).padStart(2, '0') }}
        </span>
        <span
          v-if="i < STEPS.length - 1"
          class="absolute left-11 right-3 top-4 hidden h-px bg-slate-300 lg:block"
          aria-hidden="true"
        >
          <span
            :ref="(el) => setSegmentRef(el, i)"
            class="block h-full w-full origin-left scale-x-0 bg-capture-500"
          />
        </span>
        <h3 class="font-body text-base font-semibold text-ink-900">{{ step.title }}</h3>
        <p class="mt-1 font-body text-sm text-ink-900/70">{{ step.body }}</p>
        <p class="mt-3 font-mono text-xs text-capture-600">→ {{ step.artifact }}</p>
      </li>
    </ol>
  </section>
</template>
