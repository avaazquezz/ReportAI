<script setup lang="ts">
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

// Sheet 6, how I know it works: the measurements (each with where it comes from), how the work is
// done, and one real incident told as an incident report. Its set-piece replays that incident:
// twenty simultaneous requests against a limit of 3, before the fix (all twenty through) and after
// (three through, seventeen stopped at the gate). The dots are drawn at their end positions, so
// without motion the result is simply there; the animation only brings them in from the start.
const { t } = useI18n()

const FIGURES = ['tests', 'frontend', 'invented', 'a11y', 'cost'] as const
const METHOD = ['spec', 'build', 'review', 'ci'] as const
const ROWS = ['found', 'repro', 'cause', 'fix', 'result'] as const
const OTHERS = ['xss', 'tablet', 'audio'] as const
const PHASES = ['before', 'after'] as const

const REQUESTS = 20
const LIMIT = 3
const GATE = 150
const start = (i: number) => ({ x: 16 + (i % 2) * 14, y: 22 + Math.floor(i / 2) * 17 })
const accepted = (k: number) => ({ x: 236 + (k % 4) * 18, y: 40 + Math.floor(k / 4) * 18 })
const stopped = (k: number) => ({ x: 104 + (k % 3) * 15, y: 40 + Math.floor(k / 3) * 18 })
const DOTS = Array.from({ length: REQUESTS }, (_, i) => ({
  before: accepted(i),
  after: i < LIMIT ? accepted(i) : stopped(i - LIMIT),
  through: i < LIMIT
}))

const root = ref<HTMLElement | null>(null)
const replaying = ref(false)
let play: () => void = () => {}

useMotionScope(root, (c) => {
  if (c.reduce) return
  const tl = gsap.timeline({ paused: true, onComplete: () => (replaying.value = false) })
  // Before: no lock, everyone reads the counter at zero and all rush through at once.
  tl.from('.dot-before', { attr: { cx: (i: number) => start(i).x, cy: (i: number) => start(i).y }, duration: 0.9, stagger: 0.015, ease: 'power2.inOut' }, 0)
    // After: one at a time through the lock; three get in, the rest stop at the gate.
    .from('.dot-after', { attr: { cx: (i: number) => start(i).x, cy: (i: number) => start(i).y }, duration: 0.7, stagger: 0.12, ease: 'power2.out' }, 1.1)
    .from('.dot-after.is-stopped', { fill: '#FF6A45', duration: 0.3, stagger: 0.12 }, 1.6)
    .from('.viz-count', { opacity: 0, duration: 0.4, stagger: 0.6 }, 0.9)
  play = () => {
    replaying.value = true
    tl.restart()
  }
  ScrollTrigger.create({ trigger: '.viz', start: 'top 75%', once: true, onEnter: () => play() })
})
</script>

<template>
  <section :id="SHEET_IDS.quality" ref="root" class="grid-plano scroll-mt-20 bg-plano-900 text-white" data-tone="dark">
    <div class="mx-auto max-w-[1240px] px-6 py-20 lg:py-28">
      <LandingSheetHead sheet="quality" tone="dark" :heading="t('landing.quality.heading')" :plain="t('landing.quality.plain')" />

      <!-- Measurements, as the table of a drawing: value, what it measures, where it comes from. -->
      <dl class="m-0 mt-14 grid border-t border-plano-line/40 sm:grid-cols-2 lg:grid-cols-5">
        <div v-for="figure in FIGURES" :key="figure" class="flex flex-col border-b border-plano-line/25 py-5 sm:pr-6 lg:border-b-0 lg:border-r lg:px-5 lg:first:pl-0 lg:last:border-r-0">
          <dt class="order-2 mt-1.5 font-body text-[14px] font-medium text-white">{{ t(`landing.quality.figures.${figure}.label`) }}</dt>
          <dd class="order-1 m-0 font-plan text-[2rem] font-extrabold leading-none tracking-[-0.03em] text-white tabular-nums">{{ t(`landing.quality.figures.${figure}.value`) }}</dd>
          <dd class="order-3 m-0 mt-2 font-body text-[12.5px] leading-snug text-white/65">{{ t(`landing.quality.figures.${figure}.source`) }}</dd>
        </div>
      </dl>

      <div class="mt-20">
        <h3 class="m-0 font-plan text-[1.35rem] font-extrabold tracking-[-0.02em] text-white">{{ t('landing.quality.method.title') }}</h3>
        <ol class="m-0 mt-6 grid list-none gap-6 p-0 sm:grid-cols-2 lg:grid-cols-4">
          <li v-for="(step, i) in METHOD" :key="step" class="border-t-2 border-plano-line/60 pt-3">
            <p class="m-0 font-body text-[13px] font-semibold text-plano-line">{{ i + 1 }} · {{ t(`landing.quality.method.steps.${step}.who`) }}</p>
            <p class="mb-0 mt-1.5 font-plan text-[1.05rem] font-bold text-white">{{ t(`landing.quality.method.steps.${step}.name`) }}</p>
            <p class="mb-0 mt-1 font-body text-[14px] leading-snug text-white/75">{{ t(`landing.quality.method.steps.${step}.body`) }}</p>
          </li>
        </ol>
        <p class="mb-0 mt-8 max-w-3xl font-plan text-[clamp(1.25rem,0.9rem+1.2vw,1.75rem)] font-extrabold leading-snug tracking-[-0.02em] text-white">
          {{ t('landing.quality.method.motto') }}
        </p>
      </div>

      <!-- The incident, as an incident report. -->
      <article class="mt-20 grid gap-10 border border-plano-line/40 bg-plano-950/50 p-6 lg:grid-cols-12 lg:gap-12 lg:p-10" aria-labelledby="incident-title">
        <div class="lg:col-span-5">
          <h3 id="incident-title" class="m-0 font-plan text-[1.35rem] font-extrabold leading-snug tracking-[-0.02em] text-white">{{ t('landing.incident.title') }}</h3>
          <p class="mb-0 mt-3 font-body text-[14.5px] leading-relaxed text-white/75">{{ t('landing.incident.context') }}</p>
          <dl class="m-0 mt-6">
            <div v-for="row in ROWS" :key="row" class="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-3 border-t border-plano-line/25 py-3">
              <dt class="font-body text-[13px] font-semibold" :class="row === 'result' ? 'text-[#5FD3A6]' : 'text-capture-500'">{{ t(`landing.incident.rows.${row}.label`) }}</dt>
              <dd class="m-0 font-body text-[14px] leading-snug text-white/85">{{ t(`landing.incident.rows.${row}.body`) }}</dd>
            </div>
          </dl>
        </div>

        <figure class="viz m-0 flex flex-col lg:col-span-7" aria-labelledby="viz-caption">
          <figcaption id="viz-caption" class="font-body text-[13px] font-semibold text-white/75">{{ t('landing.incident.viz.label') }}</figcaption>
          <div class="mt-4 grid gap-6 sm:grid-cols-2">
            <div v-for="phase in PHASES" :key="phase">
              <p class="m-0 font-plan text-[1rem] font-bold text-white">{{ t(`landing.incident.viz.${phase}`) }}</p>
              <svg viewBox="0 0 320 200" class="mt-2 w-full" aria-hidden="true">
                <rect x="220" y="24" width="88" height="112" rx="4" fill="none" stroke="#8FB0E3" stroke-opacity="0.35" stroke-dasharray="3 3" />
                <line :x1="GATE" y1="14" :x2="GATE" y2="186" :stroke="phase === 'after' ? '#FF6A45' : '#8FB0E3'" :stroke-opacity="phase === 'after' ? 1 : 0.35" stroke-width="2" />
                <text :x="GATE" y="10" text-anchor="middle" class="fill-white/75 font-mono text-[13px]">{{ t('landing.incident.viz.limit') }}</text>
                <circle
                  v-for="(dot, i) in DOTS"
                  :key="i"
                  :cx="dot[phase].x"
                  :cy="dot[phase].y"
                  r="6"
                  :class="[`dot-${phase}`, phase === 'after' && !dot.through ? 'is-stopped' : '']"
                  :style="{ fill: phase === 'after' && !dot.through ? '#5B6B85' : '#FF6A45' }"
                />
              </svg>
              <p class="viz-count m-0 mt-1 font-mono text-[12px]" :class="phase === 'after' ? 'text-[#5FD3A6]' : 'text-capture-500'">
                {{ t(`landing.incident.viz.${phase}Count`) }}
              </p>
            </div>
          </div>
          <button
            type="button"
            class="mt-5 cursor-pointer self-start border-0 bg-transparent p-0 font-body text-[13px] font-semibold text-plano-line underline decoration-plano-line/40 underline-offset-4 hover:decoration-plano-line disabled:cursor-default disabled:opacity-40 motion-reduce:hidden"
            :disabled="replaying"
            @click="play()"
          >
            {{ t('landing.sheet.replay') }}
          </button>
        </figure>
      </article>

      <div class="mt-16">
        <h3 class="m-0 font-plan text-[1.15rem] font-extrabold tracking-[-0.02em] text-white">{{ t('landing.incident.others.title') }}</h3>
        <ul class="m-0 mt-5 grid list-none gap-6 p-0 lg:grid-cols-3">
          <li v-for="item in OTHERS" :key="item" class="border-t border-plano-line/40 pt-3">
            <p class="m-0 font-body text-[13px] font-semibold text-plano-line">{{ t(`landing.incident.others.items.${item}.by`) }}</p>
            <p class="mb-0 mt-1.5 font-body text-[14px] leading-relaxed text-white/85">{{ t(`landing.incident.others.items.${item}.body`) }}</p>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>
