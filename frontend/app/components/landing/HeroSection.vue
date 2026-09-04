<script setup lang="ts">
const { t } = useI18n()
const contactHref = useContactHref()

// Vue's own template tokenizer treats literal "{{"/"}}" inside a mustache
// expression as an unterminated nested interpolation — building the string in
// script and interpolating the result avoids that.
const placeholderTag = computed(() => `{{ ${t('landing.hero.placeholderTag')} }}`)
const tag = (key: string) => `{{ ${t(`landing.hero.stage.tags.${key}`)} }}`

// The page's one orchestrated moment: the copy lands, then the stage tells the
// product's story once — voice note in, fields resolve on the client's own
// document, approval stamp, delivery — and offers a replay.
const SLOTS = ['date', 'place', 'attendee1', 'attendee2', 'attendee3', 'decision'] as const
const WAVE = [5, 9, 13, 8, 15, 6, 11, 16, 7, 12, 9, 5, 10, 14, 6]

const root = ref<HTMLElement | null>(null)
const { replay } = useSectionMotion(
  root,
  (tl) => {
    tl.to('.hero-tag', { opacity: 0, y: -8, duration: 0.35 }, 0.55)
      .fromTo('.hero-h1', { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.5 }, '<')
      .fromTo(
        ['.hero-sub', '.hero-ctas', '.hero-note'],
        { opacity: 0, y: 14 },
        { opacity: 1, y: 0, duration: 0.55, stagger: 0.12 },
        '-=0.25'
      )
      .fromTo('.doc', { opacity: 0, y: 28 }, { opacity: 1, y: 0, duration: 0.7 }, 0.35)
      .fromTo('.chat', { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.55 }, 0.65)
      .fromTo(
        '.b-voice',
        { opacity: 0, scale: 0.85, transformOrigin: '100% 100%' },
        { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(1.6)' },
        1.0
      )
      .to(
        '.wave > i',
        {
          scaleY: () => 0.35 + Math.random() * 0.65,
          duration: 0.22,
          ease: 'sine.inOut',
          stagger: { each: 0.035, repeat: 7, yoyo: true }
        },
        1.15
      )
      .fromTo(
        '.b-status',
        { opacity: 0, scale: 0.85, transformOrigin: '0% 100%' },
        { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(1.6)' },
        1.5
      )
      .to('.s1', { opacity: 0, duration: 0.2 }, 2.4)
      .to('.s2', { opacity: 1, duration: 0.2 }, '<')
      .to('.tag', { opacity: 0, duration: 0.22, stagger: 0.16 }, 2.7)
      .to('.val', { opacity: 1, duration: 0.22, stagger: 0.16 }, '<')
      .to('.s2', { opacity: 0, duration: 0.2 }, 3.9)
      .to('.s3', { opacity: 1, duration: 0.2 }, '<')
      .fromTo(
        '.b-ok',
        { opacity: 0, scale: 0.85, transformOrigin: '100% 100%' },
        { opacity: 1, scale: 1, duration: 0.3, ease: 'back.out(1.6)' },
        4.4
      )
      .fromTo(
        '.stamp',
        { opacity: 0, scale: 1.8, rotate: -20 },
        { opacity: 1, scale: 1, rotate: -8, duration: 0.4, ease: 'power3.out' },
        4.8
      )
      .fromTo('.b-sent', { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.35 }, 5.1)
      .to('.hero-replay', { opacity: 1, duration: 0.3 }, 5.5)
  },
  { immediate: true }
)
</script>

<template>
  <section ref="root" class="relative overflow-hidden">
    <div
      class="mx-auto grid max-w-[1200px] items-center gap-14 px-6 pb-20 pt-10 md:pb-28 md:pt-16 lg:grid-cols-[1.2fr_0.8fr] lg:gap-16"
    >
      <div>
        <div class="relative">
          <p class="hero-tag absolute inset-0 font-mono text-2xl text-ink-900/30 md:text-3xl" aria-hidden="true">
            {{ placeholderTag }}
          </p>
          <h1
            class="hero-h1 m-hide font-display text-[clamp(2.75rem,5vw,3.75rem)] font-bold leading-[0.98] tracking-[-0.03em] text-ink-900"
          >
            <span class="block [text-wrap:balance]">{{ t('landing.hero.headlineLine1') }}</span>
            <span class="block [text-wrap:balance]">{{ t('landing.hero.headlineLine2') }}</span>
          </h1>
        </div>
        <p class="hero-sub m-hide mt-7 max-w-[34rem] font-body text-lg leading-relaxed text-ink-900/80 md:text-xl">
          {{ t('landing.hero.subheadline') }}
        </p>
        <div class="hero-ctas m-hide mt-9 flex flex-wrap items-center gap-x-6 gap-y-4">
          <a
            :href="contactHref"
            class="rounded-md bg-capture-600 px-7 py-3.5 font-body text-base font-semibold text-white transition-[transform,background-color] hover:-translate-y-0.5 hover:bg-[#A93A24]"
          >
            {{ t('landing.cta.becomeClient') }}
          </a>
          <a
            href="#ejemplo-real"
            class="group inline-flex items-center gap-2.5 font-body text-base font-medium text-ink-900"
          >
            <span
              class="flex h-9 w-9 items-center justify-center rounded-full border border-ink-900/20 transition-colors group-hover:border-capture-600 group-hover:text-capture-600"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="ml-0.5 h-3.5 w-3.5" aria-hidden="true">
                <path d="M6 4.5v11l9-5.5-9-5.5Z" />
              </svg>
            </span>
            {{ t('landing.cta.listenExample') }}
          </a>
        </div>
        <p class="hero-note m-hide mt-6 font-body text-sm text-ink-900/60">{{ t('landing.hero.note') }}</p>
      </div>

      <!-- Stage: the client's document, with the chat that produced it overlapping its corner. -->
      <div class="relative mx-auto w-full max-w-[470px] pb-36 md:pb-40 lg:ml-auto">
        <div class="doc m-hide relative ml-auto w-[88%] rounded-[3px] bg-surface-0 px-6 pb-16 pt-7 shadow-page sm:px-8">
          <p class="font-body text-[1.3rem] font-bold leading-none tracking-tight text-doc-700">
            {{ t('landing.hero.stage.docTitle') }}
          </p>
          <p class="mt-2 font-body text-sm text-doc-700/70">{{ t('landing.hero.stage.company') }}</p>
          <div class="mt-4 h-px w-full bg-doc-700/15" />

          <p class="mt-4 font-body text-[13px] leading-6 text-ink-900">
            <b class="font-semibold">{{ t('landing.hero.stage.dateLabel') }}</b>
            <span class="ml-1 inline-grid align-top">
              <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ tag('date') }}</span>
              <span class="val col-start-1 row-start-1 opacity-0">{{ t('landing.hero.stage.values.date') }}</span>
            </span>
            <b class="ml-4 font-semibold">{{ t('landing.hero.stage.placeLabel') }}</b>
            <span class="ml-1 inline-grid align-top">
              <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ tag('place') }}</span>
              <span class="val col-start-1 row-start-1 opacity-0">{{ t('landing.hero.stage.values.place') }}</span>
            </span>
          </p>

          <p class="mt-4 font-body text-sm font-semibold text-doc-700">{{ t('landing.hero.stage.attendeesLabel') }}</p>
          <ul class="mb-0 mt-1 space-y-0.5 pl-4 font-body text-[13px] leading-6 text-ink-900" style="list-style: disc">
            <li v-for="key in SLOTS.slice(2, 5)" :key="key">
              <span class="inline-grid align-top">
                <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ tag(key) }}</span>
                <span class="val col-start-1 row-start-1 opacity-0">{{ t(`landing.hero.stage.values.${key}`) }}</span>
              </span>
            </li>
          </ul>

          <p class="mt-4 hidden font-body text-sm font-semibold text-doc-700 sm:block">{{ t('landing.hero.stage.decisionsLabel') }}</p>
          <p class="mt-1 hidden font-body text-[13px] leading-6 text-ink-900 sm:block">
            <span class="inline-grid align-top">
              <span class="tag col-start-1 row-start-1 font-mono text-[12px] text-capture-600">{{ tag('decision') }}</span>
              <span class="val col-start-1 row-start-1 opacity-0">{{ t('landing.hero.stage.values.decision') }}</span>
            </span>
          </p>

          <div
            class="stamp m-hide absolute bottom-6 right-6 rounded-sm border-[3px] border-approved-600 px-3 py-1 font-display text-lg font-bold tracking-[0.14em] text-approved-600"
            aria-hidden="true"
          >
            {{ t('landing.hero.stage.stamp') }}
          </div>
        </div>

        <div class="chat m-hide absolute bottom-0 left-0 w-[62%] overflow-hidden rounded-2xl bg-surface-0 shadow-float" aria-hidden="true">
          <div class="flex items-center gap-2.5 border-b border-paper-100 px-3.5 py-2.5">
            <span class="flex h-7 w-7 items-center justify-center rounded-full bg-ink-900 font-display text-[11px] font-bold text-capture-500">R</span>
            <div class="leading-tight">
              <p class="font-body text-xs font-semibold text-ink-900">ReportAI</p>
              <p class="font-body text-[10px] text-ink-900/50">Telegram</p>
            </div>
          </div>
          <div class="space-y-2 p-3">
            <div class="b-voice m-hide ml-auto flex w-fit items-center gap-2 rounded-2xl rounded-br-md bg-capture-600 px-3 py-2 text-white">
              <svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4 shrink-0">
                <path d="M6 4.5v11l9-5.5-9-5.5Z" />
              </svg>
              <span class="wave flex h-4 items-end gap-[3px]">
                <i v-for="(h, i) in WAVE" :key="i" class="block w-[2px] origin-bottom rounded-full bg-white/80" :style="{ height: `${h}px`, transform: 'scaleY(0.4)' }" />
              </span>
              <span class="font-mono text-[11px]">{{ t('landing.hero.stage.voiceDuration') }}</span>
            </div>

            <div class="b-status m-hide w-fit rounded-2xl rounded-bl-md bg-paper-50 px-3 py-2 font-body text-xs text-ink-900">
              <span class="grid">
                <span class="s1 col-start-1 row-start-1">{{ t('landing.hero.stage.transcribing') }}</span>
                <span class="s2 col-start-1 row-start-1 opacity-0">{{ t('landing.hero.stage.extracting') }}</span>
                <span class="s3 col-start-1 row-start-1 font-medium opacity-0">{{ t('landing.hero.stage.draftReady') }}</span>
              </span>
            </div>

            <div class="b-ok m-hide ml-auto w-fit rounded-2xl rounded-br-md bg-capture-600 px-3 py-1.5 font-body text-xs text-white">
              {{ t('landing.hero.stage.approve') }}
            </div>

            <div class="b-sent m-hide flex w-fit items-center gap-2.5 rounded-2xl rounded-bl-md bg-paper-50 px-3 py-2">
              <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-ink-900 text-white">
                <svg viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5">
                  <path d="M4 2h8l4 4v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm7 1.5V7h3.5L11 3.5ZM6 10h8v1.2H6V10Zm0 3h8v1.2H6V13Z" />
                </svg>
              </span>
              <span class="leading-tight">
                <span class="block font-mono text-[10px] text-ink-900/70">acta_reunion.pdf</span>
                <span class="block font-body text-[11px] font-medium text-approved-600">{{ t('landing.hero.stage.sent') }} ✓</span>
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          class="hero-replay m-hide absolute bottom-2 right-0 inline-flex cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 font-body text-xs text-ink-900/60 transition-colors hover:text-capture-600"
          @click="replay()"
        >
          <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="h-3.5 w-3.5" aria-hidden="true">
            <path d="M4 10a6 6 0 1 1 1.76 4.24M4 15v-4h4" />
          </svg>
          {{ t('landing.hero.replay') }}
        </button>
      </div>
    </div>
  </section>
</template>
