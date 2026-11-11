<script setup lang="ts">
import gsap from 'gsap'
import type { ActaRow } from './ActaSheet.vue'

const { t } = useI18n()
const contact = useContactHref('home.cta.mailSubject')

const FIELDS = ['site', 'date', 'deficiency', 'company', 'measure', 'deadline'] as const
// Which part of the dictated sentence each field comes from: the page's first argument is that
// every value has a sentence behind it. The date comes from the recording itself, not from words.
const SAID = [
  { key: 'site', fills: ['site'] },
  { key: 'deficiency', fills: ['deficiency'] },
  { key: 'action', fills: ['company', 'measure', 'deadline'] }
] as const
const WAVE = [8, 14, 22, 12, 19, 9, 16, 26, 13, 8, 18, 24, 10, 15, 21, 9, 13, 19, 11, 7]

const rows = computed<ActaRow[]>(() =>
  FIELDS.map((key) => ({
    key,
    tag: t(`home.hero.sheet.tags.${key}`),
    label: t(`home.hero.sheet.fields.${key}`),
    value: t(`home.hero.sheet.values.${key}`)
  }))
)

// The set-piece: the sheet's empty fields fill in as the sentence is "heard", fragment by
// fragment. The headline, the lead and the call to action are never animated: they paint first.
const root = ref<HTMLElement | null>(null)
let story: gsap.core.Timeline | undefined
const replay = () => story?.restart()

const fill = (tl: gsap.core.Timeline, field: string, at: number | string) =>
  tl
    .to(`[data-field="${field}"] .tok-tag`, { opacity: 0, duration: 0.18 }, at)
    .fromTo(
      `[data-field="${field}"] .tok-val`,
      { opacity: 0, y: 3, color: '#C0432A' },
      { opacity: 1, y: 0, color: '#12151C', duration: 0.55 },
      '<0.08'
    )
    .set(`[data-field="${field}"] dd`, { borderBottomStyle: 'solid', borderBottomColor: 'rgba(18, 21, 28, 0.35)' }, '<')

useMotionScope(root, (c) => {
  const tl = gsap.timeline({ paused: true })
  story = tl
  tl.fromTo('.cota-rule', { scaleX: 0 }, { scaleX: 1, duration: 0.7 }, 0)
    .fromTo('.wave i', { scaleY: 0.3 }, { scaleY: () => 0.45 + Math.random() * 0.55, duration: 0.18, ease: 'sine.inOut', stagger: { each: 0.03, repeat: 11, yoyo: true } }, 0.2)
    // Back to the recording's own shape once it has been "heard".
    .to('.wave i', { scaleY: 1, duration: 0.3 }, '>')
  fill(tl, 'date', 0.35)
  SAID.forEach(({ key, fills }, index) => {
    const at = 0.7 + index * 1.05
    tl.fromTo(`.said-${key}`, { backgroundColor: 'rgba(192, 67, 42, 0)' }, { backgroundColor: 'rgba(192, 67, 42, 0.14)', duration: 0.25 }, at)
    fills.forEach((field, n) => fill(tl, field, at + 0.25 + n * 0.22))
    tl.to(`.said-${key}`, { backgroundColor: 'rgba(192, 67, 42, 0)', duration: 0.6 }, at + 0.9)
  })
  tl.fromTo('.hero-ready', { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.45 }, '>-0.2')

  if (c.reduce) {
    tl.progress(1)
    return
  }
  document.fonts.ready.then(() => tl.play())
})
</script>

<template>
  <section ref="root" class="relative overflow-hidden" aria-labelledby="hero-title">
    <div class="home-grid pb-[clamp(4.5rem,2rem+8vw,9rem)] pt-[clamp(2.5rem,1rem+5vw,6.5rem)]">
      <h1 id="hero-title" class="t-display col-span-12 m-0 lg:col-span-11">
        <span class="block">{{ t('home.hero.line1') }}</span>
        <span class="block">{{ t('home.hero.line2') }}</span>
      </h1>

      <div class="col-span-12 mt-9 md:col-span-6 lg:col-span-5 lg:mt-14">
        <p class="t-lead m-0 max-w-[34rem] text-ink-900/80">{{ t('home.hero.sub') }}</p>
        <div class="mt-9 flex flex-wrap items-center gap-x-7 gap-y-4">
          <a :href="contact" class="btn-primary">{{ t('home.cta.write') }}</a>
          <a href="#pruebalo" class="u-field font-semibold">{{ t('home.cta.tryVoice') }}</a>
        </div>
        <p class="mt-4 text-[0.88rem] text-ink-900/60">{{ t('home.cta.note') }}</p>
      </div>

      <div class="relative col-span-12 mt-14 md:col-span-6 md:mt-9 lg:col-span-6 lg:col-start-7 lg:mt-14 lg:-mr-[clamp(2rem,9vw,10rem)]">
        <figure class="relative m-0 flex flex-col">
          <HomeCota :label="t('home.hero.sheet.size')" class="mb-4" />
          <HomeActaSheet
            :company="t('home.hero.sheet.company')"
            :mark="t('home.hero.sheet.mark')"
            :title="t('home.hero.sheet.title')"
            :rows="rows"
            tagged
          >
            <p class="hero-ready m-hide mt-7 inline-flex items-center gap-2 text-[0.82rem] font-semibold">
              <span class="h-2 w-2 rounded-full bg-ink-900" aria-hidden="true" />
              {{ t('home.hero.sheet.ready') }}
            </p>
          </HomeActaSheet>

          <!-- The voice note the sheet is filled from. -->
          <div
            class="sheet relative order-first mb-8 mt-0 w-full rounded-[2px] p-5 lg:absolute lg:order-none lg:mb-0 lg:left-[calc(-21rem+1.5rem)] lg:top-[56%] lg:mt-0 lg:w-[21rem]"
          >
            <div class="flex items-center gap-3">
              <button
                type="button"
                class="grid h-10 w-10 shrink-0 cursor-pointer place-items-center rounded-full border-0 bg-ink-900 text-white"
                :aria-label="`${t('home.hero.voiceLabel')} · ${t('home.hero.voiceLength')}`"
                @click="replay"
              >
                <svg viewBox="0 0 16 16" class="ml-0.5 h-3.5 w-3.5" aria-hidden="true"><path d="M4 2.5v11l9-5.5z" fill="currentColor" /></svg>
              </button>
              <span class="wave flex h-8 flex-1 items-center gap-[3px]" aria-hidden="true">
                <i v-for="(h, i) in WAVE" :key="i" class="block w-[3px] origin-center rounded-full bg-ink-900/70" :style="{ height: `${h}px` }" />
              </span>
              <span class="t-data text-ink-900/60">{{ t('home.hero.voiceLength') }}</span>
            </div>
            <p class="m-0 mt-4 text-[0.88rem] leading-relaxed text-ink-900/80">
              <span v-for="part in SAID" :key="part.key" :class="`said-${part.key}`" class="rounded-[2px] [box-decoration-break:clone]">{{ t(`home.hero.said.${part.key}`) }}{{ ' ' }}</span>
            </p>
          </div>
          <figcaption class="mt-4 text-[0.8rem] text-ink-900/60">{{ t('home.hero.example') }}</figcaption>
        </figure>
      </div>
    </div>
  </section>
</template>
