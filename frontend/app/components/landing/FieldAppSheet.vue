<script setup lang="ts">
// Sheet 5: the field app with no signal. A quiet sheet: a strip of coverage over the visit that
// drops to nothing in the middle, and under it the four things the app does, each under the
// stretch of signal it happens in.
const { t } = useI18n()

const STEPS = ['record', 'queue', 'sync', 'boot'] as const
// The coverage line (viewBox 0 0 1000 80): good, fading, none for a while, back.
const SIGNAL = 'M0 22 C70 18 140 24 200 30 S280 62 300 72 L540 72 C580 70 610 40 670 26 S860 18 1000 20'
</script>

<template>
  <section :id="SHEET_IDS.fieldApp" class="scroll-mt-20 border-t border-ink-900/10 bg-paper-50" data-tone="light">
    <div class="mx-auto max-w-[1240px] px-6 py-20 lg:py-28">
      <LandingSheetHead sheet="fieldApp" :heading="t('landing.fieldApp.heading')" :plain="t('landing.fieldApp.plain')" />

      <div class="mt-14">
        <div class="relative hidden h-20 sm:block" aria-hidden="true">
          <svg viewBox="0 0 1000 80" preserveAspectRatio="none" class="absolute inset-0 h-full w-full overflow-visible">
            <rect x="300" y="0" width="240" height="80" class="fill-ink-900/[0.05]" />
            <line x1="0" y1="72" x2="1000" y2="72" stroke="#12151C" stroke-opacity="0.2" stroke-dasharray="4 4" vector-effect="non-scaling-stroke" />
            <path :d="SIGNAL" fill="none" stroke="#223552" stroke-width="2" vector-effect="non-scaling-stroke" />
          </svg>
          <span class="absolute left-0 top-0 font-body text-[13px] text-ink-900/60">{{ t('landing.fieldApp.signal.label') }}</span>
          <span class="absolute left-[30%] top-1 w-[24%] text-center font-body text-[13px] text-ink-900/60">{{ t('landing.fieldApp.signal.none') }}</span>
        </div>

        <ol class="m-0 mt-4 grid list-none gap-8 p-0 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
          <li v-for="(step, i) in STEPS" :key="step" class="border-t-2 border-ink-900 pt-3">
            <p class="m-0 font-plan text-[1.05rem] font-bold text-ink-900">
              <span class="mr-2 font-mono text-[12px] font-normal tabular-nums text-ink-900/60">{{ i + 1 }}</span>{{ t(`landing.fieldApp.steps.${step}.name`) }}
            </p>
            <p class="mb-0 mt-1.5 font-body text-[14.5px] leading-relaxed text-ink-900/80">{{ t(`landing.fieldApp.steps.${step}.body`) }}</p>
          </li>
        </ol>
      </div>

      <div class="mt-14 grid gap-8 lg:grid-cols-2 lg:gap-10">
        <p class="m-0 font-body text-[15px] leading-relaxed text-ink-900/80">{{ t('landing.fieldApp.security') }}</p>
        <div class="border-l-2 border-capture-600 bg-cream-50 py-3 pl-4 pr-3">
          <p class="m-0 font-body text-[13px] font-semibold text-capture-600">{{ t('landing.sheet.why') }}</p>
          <p class="mb-0 mt-1 max-w-[62ch] font-body text-[14px] leading-snug text-ink-900/85">{{ t('landing.fieldApp.why') }}</p>
        </div>
      </div>
    </div>
  </section>
</template>
