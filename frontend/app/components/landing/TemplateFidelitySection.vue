<script setup lang="ts">
import gsap from 'gsap'

const { t, locale } = useI18n()
// Vue's own template tokenizer treats literal "{{"/"}}" inside a mustache
// expression as an unterminated nested interpolation — building the string in
// script and interpolating the result avoids that.
const eyebrowTag = computed(() => `{{ ${t('landing.templateFidelity.eyebrowTag')} }}`)

// Filled values reuse the RealDemoSection story (same fictional client across
// the whole page), so the panel shows the template resolving into that acta.
const dateTag = ['{{', 'meeting_date', '}}'].join(' ')
const attendeesTag = '{% for a in attendees %}{{ a }}{% endfor %}'
const summaryTag = ['{{', 'summary', '}}'].join(' ')

const dateValue = computed(() => (locale.value === 'es' ? '18 de agosto de 2025' : 'August 18, 2025'))
const attendeesValue = computed(() =>
  locale.value === 'es'
    ? 'Javier Molina, Marta Delgado, Óscar Ferreira, Laura Sanz'
    : 'James Whitfield, Sarah Mitchell, Marcus Reed, Emily Chen'
)
const summaryValue = computed(() =>
  locale.value === 'es'
    ? 'Pedido trimestral +15% con entrega en dos semanas y renovación del contrato de mantenimiento.'
    : 'Quarterly order +15% with two-week delivery and renewal of the maintenance contract.'
)

const panel = ref<HTMLElement | null>(null)
const textCol = ref<HTMLElement | null>(null)
const lines = ref<HTMLElement[]>([])
const tagSpans = ref<HTMLElement[]>([])
const valueSpans = ref<HTMLElement[]>([])
const inView = useInView(panel, 0.3)

function setLineRef(el: unknown, i: number) {
  if (el) lines.value[i] = el as HTMLElement
}
function setTagSpanRef(el: unknown, i: number) {
  if (el) tagSpans.value[i] = el as HTMLElement
}
function setValueSpanRef(el: unknown, i: number) {
  if (el) valueSpans.value[i] = el as HTMLElement
}

watch(inView, (visible) => {
  if (!visible) return

  if (usePrefersReducedMotion()) {
    gsap.set(textCol.value, { opacity: 1, y: 0 })
    gsap.set(lines.value, { clipPath: 'inset(0 0% 0 0)' })
    gsap.set(tagSpans.value, { opacity: 0 })
    gsap.set(valueSpans.value, { opacity: 1 })
    return
  }

  gsap
    .timeline()
    .fromTo(textCol.value, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' })
    .fromTo(
      lines.value,
      { clipPath: 'inset(0 100% 0 0)' },
      { clipPath: 'inset(0 0% 0 0)', duration: 0.5, stagger: 0.15, ease: 'power1.inOut' },
      '-=0.2'
    )
    // The panel does what the product does: after a beat, each tag resolves
    // into its real value.
    .to(tagSpans.value, { opacity: 0, duration: 0.3, stagger: 0.2 }, '+=0.8')
    .to(valueSpans.value, { opacity: 1, duration: 0.3, stagger: 0.2 }, '<')
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
          <span class="ml-3 font-mono text-xs text-white/50">{{ t('landing.templateFidelity.filename') }}</span>
        </div>
        <div class="space-y-3 p-6 font-mono text-sm">
          <!-- Static initial clip (not just the GSAP "from" state) avoids a flash of
               fully-revealed text before the reveal timeline runs. Tag and value are
               stacked in the same inline-grid cell so the swap never shifts layout. -->
          <p :ref="(el) => setLineRef(el, 0)" class="[clip-path:inset(0_100%_0_0)]">
            <span class="text-white/70">{{ t('landing.templateFidelity.labels.date') }} </span>
            <span class="inline-grid align-top">
              <span :ref="(el) => setTagSpanRef(el, 0)" class="col-start-1 row-start-1 text-capture-500">{{ dateTag }}</span>
              <span :ref="(el) => setValueSpanRef(el, 0)" class="col-start-1 row-start-1 text-white/90 opacity-0">{{ dateValue }}</span>
            </span>
          </p>
          <p :ref="(el) => setLineRef(el, 1)" class="[clip-path:inset(0_100%_0_0)]">
            <span class="text-white/70">{{ t('landing.templateFidelity.labels.attendees') }} </span>
            <span class="inline-grid align-top">
              <span :ref="(el) => setTagSpanRef(el, 1)" class="col-start-1 row-start-1 text-capture-500">{{ attendeesTag }}</span>
              <span :ref="(el) => setValueSpanRef(el, 1)" class="col-start-1 row-start-1 text-white/90 opacity-0">{{ attendeesValue }}</span>
            </span>
          </p>
          <p :ref="(el) => setLineRef(el, 2)" class="pt-2 text-slate-300 [clip-path:inset(0_100%_0_0)]">{{ t('landing.templateFidelity.labels.summary') }}</p>
          <p :ref="(el) => setLineRef(el, 3)" class="[clip-path:inset(0_100%_0_0)]">
            <span class="inline-grid align-top">
              <span :ref="(el) => setTagSpanRef(el, 2)" class="col-start-1 row-start-1 text-capture-500">{{ summaryTag }}</span>
              <span :ref="(el) => setValueSpanRef(el, 2)" class="col-start-1 row-start-1 text-white/90 opacity-0">{{ summaryValue }}</span>
            </span>
          </p>
        </div>
      </div>
      <div ref="textCol" class="opacity-0 md:order-2">
        <p class="mb-2 font-mono text-xs uppercase tracking-wide text-capture-600">{{ eyebrowTag }}</p>
        <h2 class="font-display text-3xl font-bold text-ink-900 md:text-4xl">{{ t('landing.templateFidelity.heading') }}</h2>
        <p class="mt-6 font-body text-lg text-ink-900/80">
          {{ t('landing.templateFidelity.paragraph') }}
        </p>
      </div>
    </div>
  </section>
</template>
