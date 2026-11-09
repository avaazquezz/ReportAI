<script setup lang="ts">
import gsap from 'gsap'

// What it gives back, in hours, from the visitor's own numbers. The model is utils/savings.ts
// (tested); the figure eases to each new result instead of jumping, unless motion is reduced.
const { t, locale } = useI18n()

const FIELDS = [
  { key: 'technicians', unit: 'unitTechnicians' },
  { key: 'reportsPerWeek', unit: 'unitReports' },
  { key: 'minutesBefore', unit: 'unitMinutes' },
  { key: 'minutesAfter', unit: 'unitMinutes' },
  { key: 'hourlyCost', unit: 'unitHour' }
] as const

const input = reactive({ ...SAVINGS_DEFAULTS })
const result = computed(() => computeSavings(input))
const shown = reactive({ hours: Math.round(result.value.hoursSavedMonth) })

const integer = (n: number) => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 0 }).format(n)
const oneDecimal = (n: number) => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 1 }).format(n)

const reduced = ref(false)
onMounted(() => (reduced.value = window.matchMedia('(prefers-reduced-motion: reduce)').matches))

watch(
  () => Math.round(result.value.hoursSavedMonth),
  (hours) => {
    if (reduced.value) shown.hours = hours
    else gsap.to(shown, { hours, duration: 0.45, ease: 'power2.out', snap: { hours: 1 }, overwrite: true })
  }
)
</script>

<template>
  <section class="space-l border-t border-ink-900/10" aria-labelledby="savings-title">
    <div class="home-grid gap-y-14">
      <div class="col-span-12 lg:col-span-6">
        <h2 id="savings-title" class="t-section m-0">{{ t('home.savings.heading') }}</h2>
        <p class="t-lead m-0 mt-8 max-w-[34rem] text-ink-900/80">{{ t('home.savings.sub') }}</p>
      </div>

      <fieldset class="col-span-12 m-0 border-0 p-0 lg:col-span-5 lg:col-start-1 lg:row-start-2">
        <legend class="mb-4 p-0 text-[0.85rem] font-semibold">{{ t('home.savings.inputs') }}</legend>
        <div v-for="field in FIELDS" :key="field.key" class="border-t border-ink-900/15 py-4">
          <label :for="`sv-${field.key}`" class="flex items-baseline justify-between gap-4 text-[0.95rem]">
            <span>{{ t(`home.savings.${field.key}`) }}</span>
            <span class="t-data shrink-0 text-ink-900/70">{{ input[field.key] }} {{ t(`home.savings.${field.unit}`) }}</span>
          </label>
          <input
            :id="`sv-${field.key}`"
            v-model.number="input[field.key]"
            type="range"
            class="savings-range mt-3 w-full"
            :min="SAVINGS_LIMITS[field.key][0]"
            :max="SAVINGS_LIMITS[field.key][1]"
            :step="SAVINGS_LIMITS[field.key][2]"
          >
        </div>
        <p class="m-0 mt-4 text-[0.8rem] leading-relaxed text-ink-900/60">{{ t('home.savings.assumption') }}</p>
      </fieldset>

      <div class="col-span-12 lg:col-span-6 lg:col-start-7 lg:row-start-2 lg:self-center" aria-live="polite">
        <p class="m-0 font-plan text-[clamp(5rem,2rem+13vw,12rem)] font-extrabold leading-[0.85] tracking-[-0.05em] [font-stretch:112.5%] [font-variant-numeric:tabular-nums]">
          {{ integer(shown.hours) }}
        </p>
        <p class="t-lead m-0 mt-4 max-w-[24rem]">{{ t('home.savings.result') }}</p>
        <div class="mt-10 grid max-w-md grid-cols-2 border-t border-ink-900/15">
          <p class="m-0 py-4 pr-4 text-[1.05rem] font-semibold">{{ t('home.savings.value', { value: integer(result.grossMonth) }) }}</p>
          <p class="m-0 border-l border-ink-900/15 py-4 pl-4 text-[1.05rem] font-semibold">{{ t('home.savings.days', { days: oneDecimal(result.workdaysSavedMonth) }) }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* A ruler, not a slider: ink track, the reviewer's red for the part already measured. */
.savings-range {
  appearance: none;
  height: 2px;
  background: color-mix(in srgb, var(--acta-ink) 20%, transparent);
  accent-color: var(--acta-red);
  cursor: pointer;
}
.savings-range::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--acta-ink);
  border: 3px solid var(--acta-paper);
  box-shadow: 0 0 0 1px var(--acta-ink);
}
.savings-range::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--acta-ink);
  border: 3px solid var(--acta-paper);
}
</style>
