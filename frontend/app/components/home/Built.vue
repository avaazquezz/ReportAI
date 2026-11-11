<script setup lang="ts">
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

// The back of the acta: what runs between the dictation and the PDF, and who built it, for the
// visitor who wants to know how before trusting it. Drawn as a section of a plan, not a diagram of
// boxes: five stages along one measured rule, drawn once in reading order. Its figures are the case
// study's: backend/tests/test_case_study_figures.py checks the graph and isolation ones against the
// code and the golden set's against the case study and the number of cases.
const { t } = useI18n()

const STAGES = ['capture', 'transcribe', 'agent', 'document', 'delivery'] as const
const FACTS = ['tenancy', 'eval', 'install'] as const
const PROFILES = [
  { key: 'code', href: 'https://github.com/avaazquezz/ReportAI' },
  { key: 'portfolio', href: 'https://www.vazquezdev.pro' },
  { key: 'linkedin', href: 'https://www.linkedin.com/in/adrivaz/' }
] as const

const root = ref<HTMLElement | null>(null)

useMotionScope(root, (c) => {
  // Without motion (or without JS) the plan is simply there, whole.
  if (c.reduce) return
  // One rule, horizontal from lg up and vertical below it. Scaling both axes makes it grow along its
  // length at any width (across its 1px thickness the scale doesn't show), even after a rotation.
  const tl = gsap.timeline({ paused: true })
  tl.fromTo('.built-rule', { scaleX: 0, scaleY: 0 }, { scaleX: 1, scaleY: 1, duration: 1.1, ease: 'power2.inOut' }, 0)
    // Each stage is read as the rule reaches it.
    .fromTo('.built-stage', { opacity: 0 }, { opacity: 1, duration: 0.35, ease: 'power1.out', stagger: 0.2 }, 0.1)
  ScrollTrigger.create({ trigger: '.built-flow', start: 'top 78%', once: true, onEnter: () => tl.play() })
})
</script>

<template>
  <section id="por-dentro" ref="root" class="space-l border-t border-ink-900/10" aria-labelledby="built-title">
    <div class="home-grid gap-y-14">
      <div class="col-span-12 lg:col-span-5">
        <h2 id="built-title" class="t-section m-0">{{ t('home.built.heading') }}</h2>
      </div>
      <p class="t-lead col-span-12 m-0 max-w-[36rem] text-ink-900/80 lg:col-span-6 lg:col-start-7 lg:self-end">{{ t('home.built.lead') }}</p>

      <div class="col-span-12">
        <p class="m-0 mb-5 text-[0.85rem] font-semibold text-ink-900/60">{{ t('home.built.flowLabel') }}</p>
        <div class="built-flow relative pl-6 lg:pl-0 lg:pt-8">
          <span class="built-rule absolute left-0 top-0 h-full w-px origin-top bg-ink-900/40 lg:h-px lg:w-full lg:origin-left" aria-hidden="true" />
          <ol class="m-0 grid list-none gap-y-9 p-0 lg:grid-cols-5 lg:gap-x-8">
            <li v-for="(key, index) in STAGES" :key="key" class="built-stage relative">
              <span class="absolute -left-6 top-[0.7em] h-px w-3 bg-ink-900/40 lg:-top-8 lg:left-0 lg:h-3 lg:w-px" aria-hidden="true" />
              <p class="m-0 text-[0.85rem] font-semibold text-ink-900/60 [font-variant-numeric:tabular-nums]">{{ String(index + 1).padStart(2, '0') }}</p>
              <h3 class="m-0 mt-2 text-[1.15rem] font-semibold">{{ t(`home.built.stages.${key}.title`) }}</h3>
              <p class="t-body m-0 mt-2 max-w-[30rem] text-ink-900/75 [text-wrap:pretty]">{{ t(`home.built.stages.${key}.body`) }}</p>
              <p class="t-data m-0 mt-3 text-ink-900/60">{{ t(`home.built.stages.${key}.tech`) }}</p>
            </li>
          </ol>
        </div>
      </div>

      <dl class="col-span-12 m-0 grid gap-y-0 border-y border-ink-900/10 md:grid-cols-3">
        <div
          v-for="(key, index) in FACTS"
          :key="key"
          class="py-6 md:py-8"
          :class="[
            index > 0 ? 'border-t border-ink-900/10 md:border-l md:border-t-0 md:pl-6' : '',
            index < FACTS.length - 1 ? 'md:pr-6' : ''
          ]"
        >
          <dt class="text-[0.98rem] font-semibold">{{ t(`home.built.facts.${key}.title`) }}</dt>
          <dd class="m-0 mt-1 text-[0.9rem] leading-snug text-ink-900/65 [text-wrap:pretty]">{{ t(`home.built.facts.${key}.body`) }}</dd>
        </div>
      </dl>

      <div class="col-span-12 lg:col-span-5">
        <p class="m-0 text-[0.85rem] font-semibold text-ink-900/60">{{ t('home.built.who.label') }}</p>
        <p class="m-0 mt-3 text-[1.6rem] font-bold leading-tight">Adrián Vázquez</p>
        <p class="m-0 mt-1 text-[0.95rem] text-ink-900/60">{{ t('home.built.who.role') }}</p>
        <p class="t-body m-0 mt-4 max-w-[30rem] text-ink-900/75">{{ t('home.built.who.body') }}</p>
      </div>
      <div class="col-span-12 flex flex-wrap items-center gap-x-7 gap-y-4 lg:col-span-6 lg:col-start-7 lg:self-end">
        <NuxtLink to="/arquitectura" class="btn-quiet">{{ t('home.built.who.caseStudy') }}</NuxtLink>
        <a v-for="profile in PROFILES" :key="profile.key" :href="profile.href" target="_blank" rel="noopener" class="u-field font-semibold">
          {{ t(`home.built.who.${profile.key}`) }}
        </a>
      </div>
    </div>
  </section>
</template>
