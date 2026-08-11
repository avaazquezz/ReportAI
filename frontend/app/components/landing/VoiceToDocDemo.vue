<script setup lang="ts">
import gsap from 'gsap'

const root = ref<HTMLElement | null>(null)
const bars = ref<HTMLElement[]>([])
const fieldLines = ref<HTMLElement[]>([])
const approvedMark = ref<HTMLElement | null>(null)

const FIELDS = [
  { label: 'fecha_reunión', value: '11/08/2026' },
  { label: 'asistentes', value: 'Javier Molina, Isabel Ortega' },
  { label: 'resumen', value: 'Revisión de pedido trimestral y condiciones de entrega.' }
]

function setBarRef(el: unknown, i: number) {
  if (el) bars.value[i] = el as HTMLElement
}

function setFieldRef(el: unknown, i: number) {
  if (el) fieldLines.value[i] = el as HTMLElement
}

onMounted(() => {
  if (!root.value) return

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const observer = new IntersectionObserver(
    ([entry]) => {
      if (!entry?.isIntersecting) return
      observer.disconnect()

      if (prefersReducedMotion) {
        gsap.set([...bars.value, ...fieldLines.value, approvedMark.value], { opacity: 1, scale: 1, y: 0 })
        return
      }

      const tl = gsap.timeline()
      tl.to(bars.value, {
        scaleY: () => 0.3 + Math.random() * 0.7,
        transformOrigin: 'bottom',
        duration: 0.3,
        stagger: { each: 0.04, repeat: 5, yoyo: true }
      })
        .to(bars.value, { opacity: 0.15, duration: 0.3 }, '+=0.1')
        .fromTo(
          fieldLines.value,
          { opacity: 0, y: 8 },
          { opacity: 1, y: 0, duration: 0.4, stagger: 0.15 },
          '-=0.1'
        )
        .fromTo(
          approvedMark.value,
          { opacity: 0, scale: 0.6 },
          { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' },
          '+=0.2'
        )
    },
    { threshold: 0.4 }
  )
  observer.observe(root.value)
  onUnmounted(() => observer.disconnect())
})
</script>

<template>
  <div ref="root" class="w-full max-w-sm rounded-2xl bg-surface-0 p-6 shadow-xl">
    <div class="mb-5 flex h-12 items-end gap-1">
      <span
        v-for="i in 16"
        :key="i"
        :ref="(el) => setBarRef(el, i - 1)"
        class="w-full rounded-full bg-capture-500 opacity-70"
        style="height: 100%; transform: scaleY(0.2)"
      />
    </div>

    <div class="space-y-2 border-t border-slate-300 pt-4 font-mono text-xs text-ink-900">
      <p v-for="(field, i) in FIELDS" :key="field.label" :ref="(el) => setFieldRef(el, i)" class="opacity-0">
        <span class="text-ink-900/50">{{ field.label }}:</span> {{ field.value }}
      </p>
    </div>

    <div ref="approvedMark" class="mt-5 flex items-center gap-2 border-t border-slate-300 pt-4 opacity-0">
      <span class="flex h-6 w-6 items-center justify-center rounded-full bg-approved-600 text-white">
        <svg viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5"><path d="M16.7 5.3a1 1 0 0 1 0 1.4l-7 7a1 1 0 0 1-1.4 0l-3-3a1 1 0 1 1 1.4-1.4l2.3 2.29 6.3-6.29a1 1 0 0 1 1.4 0Z" /></svg>
      </span>
      <span class="font-body text-sm font-medium text-approved-600">Aprobado · Enviado</span>
    </div>
  </div>
</template>
