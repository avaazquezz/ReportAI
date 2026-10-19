<script setup lang="ts">
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import type { SavingsInput } from '~/utils/savings'

const { t, locale } = useI18n()

// The page's third set-piece, and the only one the visitor drives: change the team's numbers and
// the result re-resolves. The model is app/utils/savings.ts; every default is an assumption and
// the section says so.
const FIELDS = ['technicians', 'reportsPerWeek', 'minutesBefore', 'minutesAfter', 'hourlyCost'] as const
const ADVANCED = ['aiCostPerReport', 'serverPerMonth', 'weeksPerYear'] as const
const STATS = ['reports', 'days', 'gross', 'running', 'net', 'netYear'] as const

const input = reactive<SavingsInput>({ ...SAVINGS_DEFAULTS })
const result = computed(() => computeSavings(input))

const intl = computed(() => (locale.value === 'es' ? 'es-ES' : 'en-US'))
const nf = computed(() => new Intl.NumberFormat(intl.value, { maximumFractionDigits: 0 }))
const eur = computed(() => new Intl.NumberFormat(intl.value, { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }))
const stat = (key: (typeof STATS)[number]) => {
  const r = result.value
  const values = {
    reports: nf.value.format(r.reportsMonth),
    days: nf.value.format(r.workdaysSavedMonth),
    gross: eur.value.format(r.grossMonth),
    running: eur.value.format(r.runningMonth),
    net: eur.value.format(r.netMonth),
    netYear: eur.value.format(r.netYear)
  }
  return values[key]
}

// Vue's template tokenizer reads a literal "{{" inside a mustache as a nested interpolation.
const tokenLabel = computed(() => `{{ ${t('landing.impact.token')} }}`)

// The big number counts up when it comes into view and re-counts when an input changes. Under
// reduced motion (or without JS) it simply shows the value.
const shown = reactive({ hours: result.value.hoursSavedMonth })
let animate = false
watch(
  () => result.value.hoursSavedMonth,
  (hours) => {
    if (animate) gsap.to(shown, { hours, duration: 0.6, ease: 'power2.out', overwrite: true })
    else shown.hours = hours
  }
)

// A spoken summary for screen readers, settled after the slider stops (not on every tick).
const liveText = ref('')
let liveTimer: ReturnType<typeof setTimeout> | undefined
watch(result, (r) => {
  clearTimeout(liveTimer)
  liveTimer = setTimeout(() => {
    liveText.value = t('landing.impact.live', { hours: nf.value.format(r.hoursSavedMonth), net: nf.value.format(r.netYear) })
  }, 700)
})
onBeforeUnmount(() => clearTimeout(liveTimer))

// A number box can be left empty or out of range: put it back inside the slider's limits.
function clamp(key: keyof SavingsInput) {
  const [min, max] = SAVINGS_LIMITS[key]
  const v = Number(input[key])
  input[key] = Number.isFinite(v) ? Math.min(Math.max(v, min), max) : SAVINGS_DEFAULTS[key]
}

const root = ref<HTMLElement | null>(null)
useMotionScope(root, (c) => {
  if (c.reduce) return
  animate = true
  const target = result.value.hoursSavedMonth
  shown.hours = 0
  gsap.from('.sv-card', {
    opacity: 0,
    y: 28,
    duration: MOTION.reveal + 0.2,
    stagger: 0.12,
    clearProps: 'opacity,transform',
    scrollTrigger: { trigger: root.value, start: 'top 75%', once: true }
  })
  ScrollTrigger.create({
    trigger: '.sv-result',
    start: 'top 80%',
    once: true,
    onEnter: () => {
      gsap.to(shown, { hours: result.value.hoursSavedMonth || target, duration: 1.4, ease: 'power3.out', overwrite: true })
    }
  })
  return () => {
    animate = false
    shown.hours = result.value.hoursSavedMonth
  }
})
</script>

<template>
  <section id="impacto" ref="root" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto max-w-[1240px] px-6">
      <div class="max-w-3xl">
        <LandingSectionHeading>{{ t('landing.impact.heading') }}</LandingSectionHeading>
        <p class="mb-0 mt-5 max-w-2xl font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.impact.sub') }}</p>
      </div>

      <div class="mt-12 grid items-start gap-6 lg:grid-cols-[0.92fr_1.08fr] lg:gap-8">
        <form class="sv-card rounded-2xl bg-surface-0 p-6 shadow-page md:p-8" @submit.prevent>
          <p class="m-0 font-mono text-[11px] text-capture-600">{{ t('landing.impact.inputsLabel') }}</p>
          <div
            v-for="key in FIELDS"
            :key="key"
            class="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 border-b border-paper-100 py-4 last:border-b-0"
          >
            <label :for="`sv-${key}`" class="font-body text-sm text-ink-900">{{ t(`landing.impact.fields.${key}.label`) }}</label>
            <span class="inline-flex items-baseline gap-1.5 font-mono text-xs text-ink-900/65">
              <input
                :id="`sv-${key}`"
                v-model.number="input[key]"
                type="number"
                inputmode="decimal"
                :min="SAVINGS_LIMITS[key][0]"
                :max="SAVINGS_LIMITS[key][1]"
                :step="SAVINGS_LIMITS[key][2]"
                class="w-16 rounded border border-ink-900/20 bg-surface-0 px-2 py-1 text-right font-mono text-sm text-ink-900"
                @change="clamp(key)"
              >
              {{ t(`landing.impact.fields.${key}.unit`) }}
            </span>
            <input
              v-model.number="input[key]"
              type="range"
              :min="SAVINGS_LIMITS[key][0]"
              :max="SAVINGS_LIMITS[key][1]"
              :step="SAVINGS_LIMITS[key][2]"
              :aria-label="t(`landing.impact.fields.${key}.label`)"
              class="col-span-2 block h-1.5 w-full cursor-pointer accent-capture-600"
            >
          </div>

          <details class="group mt-5 border-t border-paper-100 pt-4">
            <summary class="flex cursor-pointer items-center justify-between font-body text-sm font-medium text-ink-900">
              {{ t('landing.impact.advanced') }}
              <span class="flex h-6 w-6 items-center justify-center rounded-full border border-ink-900/20 transition-transform duration-300 group-open:rotate-45" aria-hidden="true">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" class="h-3 w-3"><path d="M10 4v12M4 10h12" /></svg>
              </span>
            </summary>
            <div v-for="key in ADVANCED" :key="key" class="mt-4 grid grid-cols-[1fr_auto] items-center gap-x-4">
              <label :for="`sv-${key}`" class="font-body text-sm text-ink-900/80">{{ t(`landing.impact.advancedFields.${key}.label`) }}</label>
              <span class="inline-flex items-baseline gap-1.5 font-mono text-xs text-ink-900/65">
                <input
                  :id="`sv-${key}`"
                  v-model.number="input[key]"
                  type="number"
                  inputmode="decimal"
                  :min="SAVINGS_LIMITS[key][0]"
                  :max="SAVINGS_LIMITS[key][1]"
                  :step="SAVINGS_LIMITS[key][2]"
                  class="w-16 rounded border border-ink-900/20 bg-surface-0 px-2 py-1 text-right font-mono text-sm text-ink-900"
                  @change="clamp(key)"
                >
                {{ t(`landing.impact.advancedFields.${key}.unit`) }}
              </span>
            </div>
          </details>
        </form>

        <div class="sv-card sv-result rounded-2xl bg-ink-900 p-6 text-white shadow-float md:p-8">
          <p class="m-0 font-mono text-[11px] text-capture-500">{{ t('landing.impact.resultLabel') }} · {{ tokenLabel }}</p>
          <p class="mb-0 mt-3 flex flex-wrap items-baseline gap-x-3">
            <span class="font-plan text-[clamp(3.6rem,8vw,6rem)] font-extrabold leading-none tracking-[-0.05em] tabular-nums">{{ nf.format(shown.hours) }}</span>
            <span class="font-body text-lg text-white/70">{{ t('landing.impact.hoursUnit') }}</span>
          </p>

          <div class="mt-8">
            <div class="flex items-baseline justify-between font-body text-xs text-white/70">
              <span>{{ t('landing.impact.before') }}</span>
              <span class="font-mono tabular-nums">{{ nf.format(result.hoursBeforeMonth) }} {{ t('landing.impact.hoursPerMonth') }}</span>
            </div>
            <div class="mt-1.5 h-3 rounded-sm bg-white/10"><div class="h-full rounded-sm bg-white/45" /></div>

            <div class="mt-4 flex items-baseline justify-between font-body text-xs text-white/70">
              <span>{{ t('landing.impact.after') }}</span>
              <span class="font-mono tabular-nums">{{ nf.format(result.hoursAfterMonth) }} {{ t('landing.impact.hoursPerMonth') }}</span>
            </div>
            <div class="mt-1.5 h-3 rounded-sm bg-white/10">
              <div
                class="h-full origin-left rounded-sm bg-capture-500 transition-transform duration-700 ease-[cubic-bezier(0.22,0.8,0.12,1)]"
                :style="{ transform: `scaleX(${result.afterShare})` }"
              />
            </div>

            <!-- The cota: the gap between the two bars, measured like on a drawing. -->
            <div class="relative mt-3 h-7" aria-hidden="true">
              <div class="absolute inset-y-0 right-0 transition-[left] duration-700 ease-[cubic-bezier(0.22,0.8,0.12,1)]" :style="{ left: `${result.afterShare * 100}%` }">
                <span class="absolute left-0 top-1 h-3 w-px bg-capture-500" />
                <span class="absolute right-0 top-1 h-3 w-px bg-capture-500" />
                <span class="absolute inset-x-0 top-[10px] h-px bg-capture-500" />
                <span class="absolute left-1/2 top-[15px] -translate-x-1/2 whitespace-nowrap font-mono text-[11px] text-capture-500">
                  −{{ nf.format(result.hoursSavedMonth) }} {{ t('landing.impact.hoursPerMonth') }} {{ t('landing.impact.saved') }}
                </span>
              </div>
            </div>
          </div>

          <dl class="mb-0 mt-8 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-white/10 pt-6 sm:grid-cols-3">
            <div v-for="key in STATS" :key="key">
              <dt class="font-body text-xs leading-snug text-white/60">{{ t(`landing.impact.stats.${key}`) }}</dt>
              <dd class="m-0 mt-1 font-plan text-xl font-bold tracking-[-0.02em] tabular-nums" :class="key === 'net' || key === 'netYear' ? 'text-capture-500' : 'text-white'">{{ stat(key) }}</dd>
            </div>
          </dl>

          <details class="group mt-6">
            <summary class="cursor-pointer font-body text-xs font-medium text-white/80">{{ t('landing.impact.howHeading') }}</summary>
            <ul class="mb-0 mt-3 list-none space-y-1.5 pl-0 font-mono text-[11.5px] leading-snug text-white/65">
              <li v-for="n in 4" :key="n">{{ t(`landing.impact.how[${n - 1}]`) }}</li>
            </ul>
          </details>
          <p class="mb-0 mt-5 font-body text-xs leading-relaxed text-white/60">{{ t('landing.impact.disclaimer') }}</p>
          <p class="sr-only" role="status" aria-live="polite">{{ liveText }}</p>
        </div>
      </div>
    </div>
  </section>
</template>
