<script setup lang="ts">
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

// Sheet 1, the system at 1:1000: who uses it, what goes in and what comes out. The map is an
// illustration (wide screens only); what it says is also written below it, as the four steps and
// the legend of detail marks, so a screen reader and a phone get all of it. Its set-piece: the
// lines are drawn, then the datum (an orange stroke) travels the report's whole path once.
const { t } = useI18n()

// The map's coordinate space (the SVG viewBox); the HTML nodes are placed in % of it.
const W = 1100
const H = 540
const NODES = {
  tech: { x: 22, y: 222, w: 220 },
  core: { x: 440, y: 222, w: 220 },
  client: { x: 858, y: 222, w: 220 },
  voice: { x: 360, y: 24, w: 170 },
  model: { x: 570, y: 24, w: 170 },
  office: { x: 440, y: 432, w: 220 }
} as const
type Node = keyof typeof NODES
const box = (n: Node) => ({ left: `${(NODES[n].x / W) * 100}%`, top: `${(NODES[n].y / H) * 100}%`, width: `${(NODES[n].w / W) * 100}%` })

// The links, drawn under the nodes from centre to centre: each box (opaque, above the drawing)
// hides the part inside it, so a line always meets its box whatever the box's text makes its height.
const LINKS = ['M132 250 H550', 'M480 250 V52', 'M620 250 V52', 'M550 250 V460', 'M550 250 H968']
const LABELS = [
  { x: 341, y: 240, key: 'audio' },
  { x: 488, y: 170, key: 'audio', anchor: 'start' },
  { x: 628, y: 170, key: 'text', anchor: 'start' },
  { x: 558, y: 372, key: 'draft', anchor: 'start' },
  { x: 759, y: 240, key: 'pdf' }
]
// The report's whole trip, one stroke: phone → server → transcription → model → office → client.
const TRIP = 'M132 250 H480 V52 V250 H620 V52 V250 H550 V460 V250 H968'

// Detail marks, as on a drawing: a lettered circle that sends you to the sheet that zooms in.
const MARKS = [
  { letter: 'A', sheet: 'agent', key: 'agent', x: 652, y: 206 },
  { letter: 'B', sheet: 'tenancy', key: 'tenancy', x: 652, y: 300 },
  { letter: 'C', sheet: 'fieldApp', key: 'fieldApp', x: 234, y: 206 },
  { letter: 'D', sheet: 'server', key: 'server', x: 432, y: 300 }
] as const

const STEPS = ['dictate', 'fill', 'review', 'deliver'] as const

const root = ref<HTMLElement | null>(null)
const replaying = ref(false)

let play: () => void = () => {}

useMotionScope(root, (c) => {
  if (c.reduce) return
  const tl = gsap.timeline({ paused: true })
  tl.fromTo('.map-link', { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.7, stagger: 0.12, ease: 'power1.inOut' })
    .fromTo('.map-node', { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.06, clearProps: 'transform' }, 0.1)
    .fromTo('.map-label', { opacity: 0 }, { opacity: 1, duration: 0.4, stagger: 0.06 }, 0.6)
    .set('.map-trip', { opacity: 1 }, 1.1)
    .fromTo('.map-trip', { drawSVG: '0% 3%' }, { drawSVG: '97% 100%', duration: 4.2, ease: 'none' }, 1.1)
    .to('.map-trip', { opacity: 0, duration: 0.3 })
    .fromTo('.map-arrive', { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.4, ease: 'back.out(2)' }, '<')
  gsap.set('.map-trip', { opacity: 0 })
  play = () => {
    replaying.value = true
    tl.restart()
    tl.eventCallback('onComplete', () => (replaying.value = false))
  }
  ScrollTrigger.create({ trigger: '.map', start: 'top 70%', once: true, onEnter: () => play() })
})
</script>

<template>
  <section :id="SHEET_IDS.system" ref="root" class="scroll-mt-20 border-t border-ink-900/10 bg-surface-0" data-tone="light">
    <div class="mx-auto max-w-[1240px] px-6 py-20 lg:py-28">
      <LandingSheetHead sheet="system" :heading="t('landing.system.heading')" :plain="t('landing.system.plain')" />

      <figure class="map relative mx-0 mb-0 mt-14 hidden lg:block" aria-labelledby="map-caption" style="aspect-ratio: 1100 / 540">
        <figcaption id="map-caption" class="sr-only">{{ t('landing.system.mapLabel') }}</figcaption>
        <svg :viewBox="`0 0 ${W} ${H}`" class="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
          <path v-for="(d, i) in LINKS" :key="i" :d="d" class="map-link" fill="none" stroke="#223552" stroke-width="1.5" />
          <text
            v-for="(label, i) in LABELS"
            :key="`l${i}`"
            :x="label.x"
            :y="label.y"
            :text-anchor="label.anchor ?? 'middle'"
            class="map-label fill-plano-700 font-mono text-[12px]"
          >
            {{ t(`landing.system.flow.${label.key}`) }}
          </text>
          <path :d="TRIP" class="map-trip" fill="none" stroke="#C0432A" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0" />
        </svg>

        <ul class="m-0 list-none p-0">
          <li
            v-for="(spec, node) in NODES"
            :key="node"
            class="map-node absolute border bg-surface-0 px-3.5 py-2.5"
            :class="node === 'core' ? 'border-2 border-ink-900' : node === 'voice' || node === 'model' ? 'border-dashed border-plano-700/70' : 'border-ink-900/40'"
            :style="box(node)"
          >
            <span class="block font-plan text-[15px] font-bold leading-tight text-ink-900">{{ t(`landing.system.nodes.${node}.name`) }}</span>
            <span class="mt-0.5 block font-body text-[12.5px] leading-snug text-ink-900/70">{{ t(`landing.system.nodes.${node}.via`) }}</span>
            <span v-if="node === 'client'" class="map-arrive absolute -right-2 -top-2 rounded-sm bg-capture-600 px-1.5 py-0.5 font-mono text-[11px] text-white" aria-hidden="true">PDF</span>
          </li>
        </ul>

        <!-- The marks repeat the legend below (which is what the keyboard reaches), so they stay out of the tab order. -->
        <a
          v-for="mark in MARKS"
          :key="mark.letter"
          :href="`#${SHEET_IDS[mark.sheet]}`"
          tabindex="-1"
          aria-hidden="true"
          class="absolute flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-capture-600 bg-surface-0 font-plan text-[12px] font-extrabold text-capture-600 transition-colors hover:bg-capture-600 hover:text-white"
          :style="{ left: `${(mark.x / W) * 100}%`, top: `${(mark.y / H) * 100}%` }"
          :title="t(`landing.system.markers.${mark.key}`)"
        >
          {{ mark.letter }}
        </a>

        <button
          type="button"
          class="absolute bottom-0 right-0 cursor-pointer border-0 bg-transparent p-0 font-body text-[13px] font-semibold text-plano-700 underline decoration-plano-700/40 underline-offset-4 hover:decoration-plano-700 disabled:cursor-default disabled:opacity-40 motion-reduce:hidden"
          :disabled="replaying"
          @click="play()"
        >
          {{ t('landing.incident.viz.replay') }}
        </button>
      </figure>

      <div class="mt-14 grid gap-12 lg:mt-12 lg:grid-cols-12">
        <ol class="m-0 grid list-none gap-6 p-0 sm:grid-cols-2 lg:col-span-7">
          <li v-for="(step, i) in STEPS" :key="step" class="border-t-2 border-ink-900 pt-3">
            <p class="m-0 font-plan text-[1.05rem] font-bold text-ink-900">
              <span class="mr-2 font-mono text-[12px] font-normal tabular-nums text-ink-900/60">{{ i + 1 }}</span>{{ t(`landing.system.steps.${step}.name`) }}
            </p>
            <p class="mb-0 mt-1.5 font-body text-[14.5px] leading-snug text-ink-900/75">{{ t(`landing.system.steps.${step}.body`) }}</p>
          </li>
        </ol>

        <div class="lg:col-span-5">
          <p class="m-0 font-body text-[13px] font-semibold text-ink-900/70">{{ t('landing.sheet.detail') }}</p>
          <ul class="m-0 mt-3 list-none p-0">
            <li v-for="mark in MARKS" :key="mark.letter">
              <a :href="`#${SHEET_IDS[mark.sheet]}`" class="flex items-center gap-3 border-b border-ink-900/10 py-2.5 text-ink-900 transition-colors hover:text-capture-600">
                <span class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-capture-600 font-plan text-[12px] font-extrabold text-capture-600" aria-hidden="true">{{ mark.letter }}</span>
                <span class="flex-1 font-body text-[15px] font-medium">{{ t(`landing.system.markers.${mark.key}`) }}</span>
                <span class="font-mono text-[12px] text-ink-900/60">{{ t('landing.sheet.toSheet', { n: sheetNumber(mark.sheet) }) }}</span>
              </a>
            </li>
          </ul>

          <div class="mt-10 border-2 border-ink-900">
            <p class="m-0 border-b-2 border-ink-900 px-4 py-2.5 font-plan text-[1rem] font-extrabold text-ink-900">{{ t('landing.system.modes.title') }}</p>
            <dl class="m-0 grid sm:grid-cols-2">
              <div v-for="mode in ['saas', 'self']" :key="mode" class="px-4 py-3 first:border-b first:border-ink-900/20 sm:first:border-b-0 sm:first:border-r">
                <dt class="font-body text-[14px] font-semibold text-ink-900">{{ t(`landing.system.modes.${mode}.name`) }}</dt>
                <dd class="m-0 mt-1 font-body text-[13.5px] leading-snug text-ink-900/75">{{ t(`landing.system.modes.${mode}.body`) }}</dd>
              </div>
            </dl>
            <p class="m-0 border-t border-ink-900/20 px-4 py-3 font-body text-[13.5px] leading-snug text-ink-900/75">{{ t('landing.system.modes.note') }}</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
