<script setup lang="ts">
import gsap from 'gsap'

const STEPS = [
  { title: 'Grabas una nota de voz', body: 'En el coche, en el pasillo, nada más colgar. Por Telegram, WhatsApp o email — el canal que ya usas.' },
  { title: 'Se transcribe', body: 'Groq Whisper convierte el audio en texto en segundos.' },
  { title: 'Se extraen los datos', body: 'Claude identifica fecha, asistentes, resumen y acuerdos según el schema de tu documento.' },
  { title: 'Lo apruebas tú', body: 'Revisas el borrador y confirmas, o pides una corrección puntual.' },
  { title: 'Se entrega', body: 'El documento se rellena en tu plantilla .docx y llega a quien corresponde.' }
]

const list = ref<HTMLElement | null>(null)
const items = ref<HTMLElement[]>([])
const inView = useInView(list, 0.2)

function setItemRef(el: unknown, i: number) {
  if (el) items.value[i] = el as HTMLElement
}

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set(items.value, { opacity: 1, y: 0 })
    return
  }

  gsap.fromTo(
    items.value,
    { opacity: 0, y: 16 },
    { opacity: 1, y: 0, duration: 0.5, stagger: 0.12, ease: 'power2.out' }
  )
})
</script>

<template>
  <section id="como-funciona" class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <h2 class="font-display text-4xl font-bold text-ink-900 md:text-5xl">Cómo funciona</h2>
    <ol ref="list" class="mt-10 grid gap-8 md:grid-cols-5 md:divide-x md:divide-slate-300">
      <li
        v-for="(step, i) in STEPS"
        :key="step.title"
        :ref="(el) => setItemRef(el, i)"
        class="opacity-0 md:px-6 md:first:pl-0"
      >
        <span class="font-mono text-sm text-capture-600">{{ String(i + 1).padStart(2, '0') }}</span>
        <h3 class="mt-2 font-body text-base font-semibold text-ink-900">{{ step.title }}</h3>
        <p class="mt-1 font-body text-sm text-ink-900/70">{{ step.body }}</p>
      </li>
    </ol>
  </section>
</template>
