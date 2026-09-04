<script setup lang="ts">
const { t } = useI18n()

// Each step's artifact is the output that feeds the next one, so the pipeline reads
// as data flowing along the rail. `you` marks the two steps a person performs.
const STEPS = [
  { key: 'record', you: true },
  { key: 'transcribe', you: false },
  { key: 'extract', you: false },
  { key: 'approve', you: true },
  { key: 'deliver', you: false }
] as const

const root = ref<HTMLElement | null>(null)
useSectionMotion(root, (tl) => {
  tl.fromTo('.head', { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.5 })
    .fromTo('.step', { opacity: 0, y: 18 }, { opacity: 1, y: 0, duration: 0.45, stagger: 0.14 }, '-=0.2')
    .addLabel('steps', '<')
    .fromTo('.badge', { borderColor: '#C6CCD3', color: 'rgba(18,21,28,0.5)' }, { borderColor: '#C0432A', color: '#C0432A', duration: 0.3, stagger: 0.14 }, 'steps+=0.1')
    .fromTo('.seg', { scaleX: 0 }, { scaleX: 1, duration: 0.32, stagger: 0.14, ease: 'power1.inOut' }, 'steps+=0.25')
    .fromTo('.rail-fill', { scaleY: 0 }, { scaleY: 1, duration: 1.1, ease: 'power1.inOut' }, 'steps+=0.1')
})
</script>

<template>
  <section id="como-funciona" ref="root" class="bg-surface-0 py-20 md:py-28">
    <div class="mx-auto max-w-[1200px] px-6">
      <div class="head m-hide max-w-2xl">
        <h2 class="font-display text-[clamp(1.9rem,3.4vw,2.9rem)] font-bold leading-[1.05] tracking-[-0.02em] text-ink-900">
          {{ t('landing.howItWorks.heading') }}
        </h2>
        <p class="mt-4 font-body text-lg text-ink-900/75">{{ t('landing.howItWorks.sub') }}</p>
      </div>

      <ol class="relative mb-0 mt-14 grid list-none gap-10 pl-0 lg:grid-cols-5 lg:gap-6">
        <div class="absolute bottom-10 left-4 top-4 w-px bg-paper-100 lg:hidden" aria-hidden="true">
          <div class="rail-fill h-full w-full origin-top scale-y-0 bg-capture-500" />
        </div>
        <li
          v-for="(step, i) in STEPS"
          :key="step.key"
          class="step m-hide relative pl-12 lg:pl-0 lg:pt-12"
        >
          <span
            class="badge absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-full border bg-surface-0 font-mono text-xs"
            aria-hidden="true"
          >
            {{ i + 1 }}
          </span>
          <span
            v-if="i < STEPS.length - 1"
            class="absolute left-11 right-2 top-4 hidden h-px bg-paper-100 lg:block"
            aria-hidden="true"
          >
            <span class="seg block h-full w-full origin-left scale-x-0 bg-capture-500" />
          </span>
          <span
            class="inline-block rounded-full px-2 py-0.5 font-body text-[11px] font-semibold"
            :class="step.you ? 'bg-capture-100 text-capture-600' : 'bg-paper-50 text-ink-900/60'"
          >
            {{ step.you ? t('landing.howItWorks.you') : t('landing.howItWorks.system') }}
          </span>
          <h3 class="mt-2 font-display text-lg font-bold leading-snug text-ink-900">{{ t(`landing.howItWorks.steps.${step.key}.title`) }}</h3>
          <p class="mt-1.5 font-body text-sm leading-relaxed text-ink-900/70">{{ t(`landing.howItWorks.steps.${step.key}.body`) }}</p>
          <code class="mt-3 inline-block rounded border border-paper-100 bg-paper-50 px-2 py-0.5 font-mono text-[11px] text-ink-900/80">
            {{ t(`landing.howItWorks.steps.${step.key}.artifact`) }}
          </code>
        </li>
      </ol>
    </div>
  </section>
</template>
