<script setup lang="ts">
import gsap from 'gsap'

const dateTag = ['{{', 'meeting_date', '}}'].join(' ')
const attendeesTag = '{% for a in attendees %}{{ a }}{% endfor %}'
const summaryTag = ['{{', 'summary', '}}'].join(' ')

const panel = ref<HTMLElement | null>(null)
const lines = ref<HTMLElement[]>([])
const inView = useInView(panel, 0.3)

function setLineRef(el: unknown, i: number) {
  if (el) lines.value[i] = el as HTMLElement
}

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set(lines.value, { clipPath: 'inset(0 0% 0 0)' })
    return
  }

  gsap.fromTo(
    lines.value,
    { clipPath: 'inset(0 100% 0 0)' },
    { clipPath: 'inset(0 0% 0 0)', duration: 0.5, stagger: 0.15, ease: 'power1.inOut' }
  )
})
</script>

<template>
  <section class="mx-auto max-w-[1200px] px-6 py-16 md:py-24">
    <div class="grid items-center gap-12 md:grid-cols-2">
      <div ref="panel" class="overflow-hidden rounded-2xl bg-ink-900 md:order-1">
        <div class="hidden items-center gap-1.5 border-b border-white/10 px-4 py-3 sm:flex">
          <span class="h-2.5 w-2.5 rounded-full bg-slate-300/30" />
          <span class="h-2.5 w-2.5 rounded-full bg-slate-300/30" />
          <span class="h-2.5 w-2.5 rounded-full bg-slate-300/30" />
          <span class="ml-3 font-mono text-xs text-white/50">acta_reunion.docx</span>
        </div>
        <div class="space-y-3 p-6 font-mono text-sm">
          <!-- Static initial clip (not just the GSAP "from" state) avoids a flash of
               fully-revealed text before the reveal timeline runs. -->
          <p :ref="(el) => setLineRef(el, 0)" class="[clip-path:inset(0_100%_0_0)]">
            <span class="text-white/70">Fecha: </span><span class="text-capture-500">{{ dateTag }}</span>
          </p>
          <p :ref="(el) => setLineRef(el, 1)" class="[clip-path:inset(0_100%_0_0)]">
            <span class="text-white/70">Asistentes: </span
            ><span class="text-capture-500">{{ attendeesTag }}</span>
          </p>
          <p :ref="(el) => setLineRef(el, 2)" class="pt-2 text-slate-300 [clip-path:inset(0_100%_0_0)]">Resumen</p>
          <p :ref="(el) => setLineRef(el, 3)" class="text-capture-500 [clip-path:inset(0_100%_0_0)]">{{ summaryTag }}</p>
        </div>
      </div>
      <div class="md:order-2">
        <h2 class="font-display text-3xl font-bold text-ink-900 md:text-4xl">Tu plantilla, no la nuestra.</h2>
        <p class="mt-6 font-body text-lg text-ink-900/80">
          Subes el .docx que ya usáis en la empresa. ReportAI rellena esos mismos campos, con ese
          mismo formato — nada de un PDF genérico con vuestro logo pegado encima.
        </p>
      </div>
    </div>
  </section>
</template>
