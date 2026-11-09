<script setup lang="ts">
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

// "The AI doesn't sign for you": the page's third set-piece. A reviewer's red pen circles the
// deadline nobody said, notes it in the margin, the deadline gets filled in, and only then the
// approval stamp lands. Once, when the sheet comes into view; its end state is what shows without
// JS or with reduced motion (app.vue's <noscript> reveals .m-hide).
const { t } = useI18n()
const POINTS = ['evidence', 'missing', 'approval'] as const

const root = ref<HTMLElement | null>(null)

useMotionScope(root, (c) => {
  const tl = gsap.timeline({ paused: true })
  tl.fromTo('.red-circle', { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.9, ease: 'power1.inOut' }, 0)
    .fromTo('.margin-note', { opacity: 0, x: -6 }, { opacity: 1, x: 0, duration: 0.35 }, 0.7)
    .fromTo('.deadline-val', { opacity: 0, color: '#C0432A' }, { opacity: 1, color: '#12151C', duration: 0.5 }, 1.8)
    .set('.deadline-rule', { borderBottomStyle: 'solid', borderBottomColor: 'rgba(18, 21, 28, 0.35)' }, '<')
    .fromTo('.review-sheet .stamp-wrap', { opacity: 0, scale: 1.8, rotate: -14 }, { opacity: 1, scale: 1, rotate: 0, duration: 0.32, ease: 'power3.in' }, 2.5)
    .fromTo('.review-sheet', { y: 0 }, { y: 3, duration: 0.07, yoyo: true, repeat: 1, ease: 'power1.inOut', immediateRender: false }, '>')

  if (c.reduce) {
    tl.progress(1)
    return
  }
  // fromTo already drew the circle at 0%: the sheet waits, empty-handed, until it is in view.
  ScrollTrigger.create({ trigger: '.review-sheet', start: 'top 62%', once: true, onEnter: () => tl.play() })
})
</script>

<template>
  <section ref="root" class="space-l border-t border-ink-900/10" aria-labelledby="review-title">
    <div class="home-grid gap-y-14">
      <div class="col-span-12 lg:col-span-5">
        <h2 id="review-title" class="t-section m-0">{{ t('home.review.heading') }}</h2>
        <dl class="m-0 mt-12">
          <div v-for="key in POINTS" :key="key" class="border-t border-ink-900/15 py-6">
            <dt class="text-[1.2rem] font-semibold leading-snug">{{ t(`home.review.points.${key}.title`) }}</dt>
            <dd class="t-body m-0 mt-2 text-ink-900/70">{{ t(`home.review.points.${key}.body`) }}</dd>
          </div>
        </dl>
      </div>

      <div class="col-span-12 lg:col-span-6 lg:col-start-7 lg:mt-24">
        <div class="review-sheet sheet relative rounded-[2px] px-[clamp(1.25rem,0.6rem+2.6vw,2.75rem)] pb-14 pt-8">
          <dl class="m-0 grid gap-y-6">
            <div>
              <dt class="text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.company') }}</dt>
              <dd class="field-rule is-filled m-0 mt-1 pb-1.5 text-[0.95rem]">{{ t('home.hero.sheet.values.company') }}</dd>
            </div>
            <div>
              <dt class="text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.measure') }}</dt>
              <dd class="field-rule is-filled m-0 mt-1 pb-1.5 text-[0.95rem]">{{ t('home.hero.sheet.values.measure') }}</dd>
              <dd class="m-0 mt-2 border-l-2 border-ink-900/15 pl-3 text-[0.82rem] text-ink-900/60">{{ t('home.review.quote') }}</dd>
            </div>
            <div class="relative">
              <dt class="text-[0.75rem] font-semibold text-ink-900/60">{{ t('home.hero.sheet.fields.deadline') }}</dt>
              <dd class="deadline-rule field-rule relative m-0 mt-1 min-h-[1.9rem] pb-1.5 text-[0.95rem]">
                <span class="deadline-val m-hide">{{ t('home.hero.sheet.values.deadline') }}</span>
                <!-- The reviewer's red pen, around the field nobody filled in. -->
                <svg class="pointer-events-none absolute -inset-x-4 -inset-y-3 h-[calc(100%+1.5rem)] w-[calc(100%+2rem)] overflow-visible" viewBox="0 0 300 60" preserveAspectRatio="none" aria-hidden="true">
                  <path
                    class="red-circle"
                    d="M20 33 C24 11 118 4 208 8 C266 11 297 22 291 36 C285 52 190 58 110 55 C52 53 9 46 14 30 C18 19 44 12 76 10"
                    fill="none"
                    stroke="#C0432A"
                    stroke-width="2.4"
                    stroke-linecap="round"
                    vector-effect="non-scaling-stroke"
                  />
                </svg>
              </dd>
              <dd class="margin-note m-hide m-0 mt-3 text-[0.85rem] font-semibold text-[#C0432A] sm:absolute sm:right-0 sm:top-0 sm:mt-0">
                {{ t('home.review.marginNote') }}
              </dd>
            </div>
          </dl>
          <div class="stamp-wrap m-hide absolute bottom-5 right-6">
            <HomeStamp :label="t('home.review.stamp')" />
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
