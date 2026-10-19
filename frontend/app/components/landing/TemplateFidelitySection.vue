<script setup lang="ts">
import gsap from 'gsap'

const { t } = useI18n()

// Real docxtpl syntax: the sheet shows the client's .docx as the engine sees it, then does what
// the product does — each tag resolves into its value. The tag names are in i18n so each
// language reads its own.
// (Braces stay out of the i18n messages, where they are placeholder syntax: the loop is composed here.)
const forLoop = computed(() => `{% for e in ${t('landing.templateFidelity.tags.companies')} %}{{ e }}{% endfor %}`)

const root = ref<HTMLElement | null>(null)
useMotionScope(root, (c) => {
  if (c.reduce) {
    gsap.set('.tok-tag', { opacity: 0 })
    gsap.set('.tok-val', { opacity: 1 })
    return
  }
  gsap
    .timeline({ scrollTrigger: { trigger: root.value, start: 'top 65%', once: true } })
    .fromTo('.tf-paper', { clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0% 0)', duration: MOTION.piece + 0.3, ease: 'power3.inOut', clearProps: 'clipPath' })
    .from('.tf-file', { opacity: 0, y: -8, duration: 0.4, clearProps: 'opacity,transform' }, 0.7)
    .from('.tf-line', { opacity: 0, x: -8, duration: 0.45, stagger: 0.12, clearProps: 'opacity,transform' }, 0.6)
    .to('.tok-tag', { opacity: 0, duration: 0.3, stagger: 0.22 }, '+=0.5')
    .fromTo('.tok-val', { opacity: 0, y: 4, color: '#C0432A' }, { opacity: 1, y: 0, color: '#12151C', duration: 0.5, stagger: 0.22 }, '<')
    .from('.tf-check', { opacity: 0, y: 10, duration: 0.5, clearProps: 'opacity,transform' }, '-=0.3')
  gsap.from('.tf-text', { opacity: 0, y: 14, duration: MOTION.reveal, clearProps: 'opacity,transform', scrollTrigger: { trigger: '.tf-text', start: 'top 88%', once: true } })
})
</script>

<template>
  <section id="plantilla" ref="root" class="bg-paper-50 py-20 md:py-28">
    <div class="mx-auto grid max-w-[1240px] items-center gap-12 px-6 md:grid-cols-2 lg:gap-20">
      <div class="relative md:order-1">
        <div class="tf-file absolute -top-3 left-6 z-10 rounded-md bg-ink-900 px-2.5 py-1 font-mono text-[11px] text-white shadow-sm">
          {{ t('landing.templateFidelity.filename') }}
        </div>
        <div class="tf-paper rounded-[3px] bg-surface-0 px-7 pb-10 pt-9 shadow-page ring-1 ring-ink-900/5 sm:px-9">
          <p class="m-0 font-body text-xl font-bold leading-none tracking-tight text-doc-700">{{ t('landing.templateFidelity.docTitle') }}</p>
          <div class="mt-3 h-px w-full bg-doc-700/15" />

          <p class="tf-line mb-0 mt-5 font-body text-[13px] leading-6 text-ink-900">
            <b class="font-semibold">{{ t('landing.templateFidelity.labels.date') }}</b>
            <LandingToken class="ml-1" :tag="t('landing.templateFidelity.tags.date')" :value="t('landing.templateFidelity.values.date')" />
          </p>
          <p class="tf-line mb-0 mt-1 font-body text-[13px] leading-6 text-ink-900">
            <b class="font-semibold">{{ t('landing.templateFidelity.labels.site') }}</b>
            <LandingToken class="ml-1" :tag="t('landing.templateFidelity.tags.site')" :value="t('landing.templateFidelity.values.site')" />
          </p>
          <p class="tf-line mb-0 mt-4 font-body text-sm font-semibold text-doc-700">{{ t('landing.templateFidelity.labels.companies') }}</p>
          <p class="tf-line mb-0 mt-1 font-body text-[13px] leading-6 text-ink-900">
            <LandingToken :tag="forLoop" raw :value="t('landing.templateFidelity.values.companies')" />
          </p>
          <p class="tf-line mb-0 mt-4 font-body text-sm font-semibold text-doc-700">{{ t('landing.templateFidelity.labels.issue') }}</p>
          <p class="tf-line mb-0 mt-1 font-body text-[13px] leading-6 text-ink-900">
            <LandingToken :tag="t('landing.templateFidelity.tags.issue')" :value="t('landing.templateFidelity.values.issue')" />
          </p>
        </div>
      </div>

      <div class="md:order-2">
        <LandingSectionHeading>{{ t('landing.templateFidelity.heading') }}</LandingSectionHeading>
        <p class="tf-text mb-0 mt-5 font-body text-lg leading-relaxed text-ink-900/75">{{ t('landing.templateFidelity.paragraph') }}</p>
        <p class="tf-check mb-0 mt-6 flex gap-3 rounded-lg border border-approved-600/30 bg-approved-100/60 px-4 py-3 font-body text-sm leading-relaxed text-ink-900/80">
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mt-0.5 h-4 w-4 shrink-0 text-approved-600" aria-hidden="true">
            <path d="M4 10.5l4 4 8-9" />
          </svg>
          <span>{{ t('landing.templateFidelity.check') }}</span>
        </p>
      </div>
    </div>
  </section>
</template>
