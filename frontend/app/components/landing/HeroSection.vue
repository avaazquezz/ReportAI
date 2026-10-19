<script setup lang="ts">
import gsap from 'gsap'

const { t, locale } = useI18n()

const COMPANIES = ['company1', 'company2', 'company3'] as const
const WAVE = [5, 9, 13, 8, 15, 6, 11, 16, 7, 12, 9, 5, 10, 14, 6]
const PROOF = ['audio', 'page', 'cost'] as const

// The page's first set-piece. The headline is pure CSS (main.css .h-line) so it paints at once;
// everything else is one timeline that tells the product's story — voice note in, fields
// resolve on the client's own document, approval stamp, delivery — once, with a replay.
const root = ref<HTMLElement | null>(null)
const ctaZone = ref<HTMLElement | null>(null)
const ctaButton = ref<HTMLElement | null>(null)
let story: gsap.core.Timeline | undefined
const replay = () => story?.restart()

useMotionScope(root, (c) => {
  const tl = gsap.timeline({ paused: true })
  story = tl
  tl.fromTo(['.hero-eyebrow', '.hero-sub', '.hero-ctas', '.hero-note', '.hero-proof'], { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: 0.6, stagger: 0.1 }, 0.35)
    .fromTo('.doc', { opacity: 0, y: 90, rotate: 1.4 }, { opacity: 1, y: 0, rotate: 0, duration: 1.1 }, 0.25)
    .fromTo('.cota-label', { opacity: 0 }, { opacity: 1, duration: 0.4 }, 0.9)
    .fromTo('.cota', { scaleX: 0 }, { scaleX: 1, duration: 0.8 }, 1.0)
    .fromTo('.cota-tick', { opacity: 0 }, { opacity: 1, duration: 0.3 }, 1.5)
    .fromTo('.chat', { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.6 }, 0.75)
    .fromTo('.b-voice', { opacity: 0, scale: 0.85, transformOrigin: '100% 100%' }, { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(1.6)' }, 1.1)
    .to('.wave > i', { scaleY: () => 0.35 + Math.random() * 0.65, duration: 0.22, ease: 'sine.inOut', stagger: { each: 0.035, repeat: 7, yoyo: true } }, 1.25)
    .fromTo('.b-status', { opacity: 0, scale: 0.85, transformOrigin: '0% 100%' }, { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(1.6)' }, 1.6)
    .to('.s1', { opacity: 0, duration: 0.2 }, 2.5)
    .to('.s2', { opacity: 1, duration: 0.2 }, '<')
    // The signature: each {{ tag }} resolves into the value the voice note carried.
    .to('.tok-tag', { opacity: 0, duration: 0.22, stagger: 0.16 }, 2.8)
    .fromTo('.tok-val', { opacity: 0, y: 4, color: '#C0432A' }, { opacity: 1, y: 0, color: '#12151C', duration: 0.5, stagger: 0.16 }, '<')
    .to('.s2', { opacity: 0, duration: 0.2 }, 4.0)
    .to('.s3', { opacity: 1, duration: 0.2 }, '<')
    .fromTo('.b-ok', { opacity: 0, scale: 0.85, transformOrigin: '100% 100%' }, { opacity: 1, scale: 1, duration: 0.3, ease: 'back.out(1.6)' }, 4.5)
    .fromTo('.stamp', { opacity: 0, scale: 1.9, rotate: -22 }, { opacity: 1, scale: 1, rotate: -8, duration: 0.35, ease: 'power3.in' }, 4.9)
    .fromTo('.doc', { y: 0 }, { y: 4, duration: 0.07, yoyo: true, repeat: 1, ease: 'power1.inOut', immediateRender: false }, 5.2)
    .fromTo('.b-sent', { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.35 }, 5.3)
    .to('.hero-replay', { opacity: 1, duration: 0.3 }, 5.7)

  if (c.reduce) {
    tl.progress(1)
    return
  }
  document.fonts.ready.then(() => tl.play())

  if (!c.finePointer) return

  // The grid under the headline wakes up where the pointer is.
  const section = root.value!
  let top = 0
  let left = 0
  const measure = () => {
    const r = section.getBoundingClientRect()
    top = r.top + window.scrollY
    left = r.left + window.scrollX
  }
  measure()
  const gx = gsap.quickTo(section, '--gx', { duration: 0.7, ease: 'power3' })
  const gy = gsap.quickTo(section, '--gy', { duration: 0.7, ease: 'power3' })
  const onGrid = (e: PointerEvent) => {
    gx(e.pageX - left)
    gy(e.pageY - top)
  }
  section.addEventListener('pointermove', onGrid, { passive: true })
  window.addEventListener('resize', measure)

  // The primary button leans toward the pointer, then springs back.
  const zone = ctaZone.value!
  const button = ctaButton.value!
  const bx = gsap.quickTo(button, 'x', { duration: 0.5, ease: 'power3' })
  const by = gsap.quickTo(button, 'y', { duration: 0.5, ease: 'power3' })
  let zoneRect = zone.getBoundingClientRect()
  const onEnter = () => {
    zoneRect = zone.getBoundingClientRect()
  }
  const onMagnet = (e: PointerEvent) => {
    bx((e.clientX - (zoneRect.left + zoneRect.width / 2)) * 0.22)
    by((e.clientY - (zoneRect.top + zoneRect.height / 2)) * 0.3)
  }
  const onLeave = () => gsap.to(button, { x: 0, y: 0, duration: 0.9, ease: 'elastic.out(1, 0.4)', overwrite: true })
  zone.addEventListener('pointerenter', onEnter)
  zone.addEventListener('pointermove', onMagnet, { passive: true })
  zone.addEventListener('pointerleave', onLeave)

  return () => {
    section.removeEventListener('pointermove', onGrid)
    window.removeEventListener('resize', measure)
    zone.removeEventListener('pointerenter', onEnter)
    zone.removeEventListener('pointermove', onMagnet)
    zone.removeEventListener('pointerleave', onLeave)
  }
})
</script>

<template>
  <section ref="root" class="grid-paper relative overflow-hidden">
    <div class="mx-auto max-w-[1240px] px-6 pt-10 md:pt-14">
      <p class="hero-eyebrow m-hide mb-6 max-w-xl font-mono text-[13px] leading-snug text-capture-600">
        {{ t('landing.hero.eyebrow') }}
      </p>
      <h1
        class="font-plan font-extrabold leading-[0.95] tracking-[-0.045em] text-ink-900"
        :class="locale === 'es' ? 'text-[clamp(2.4rem,7.4vw,6.9rem)]' : 'text-[clamp(2.1rem,5.4vw,5rem)]'"
      >
        <span class="h-line" style="--d: 0.05s"><span>{{ t('landing.hero.headlineLine1') }}</span></span>{{ ' ' }}
        <span class="h-line" style="--d: 0.17s"><span>{{ t('landing.hero.headlineLine2') }}</span></span>
      </h1>
    </div>

    <div class="mx-auto grid max-w-[1240px] gap-x-10 px-6 lg:grid-cols-12">
      <div class="pb-14 pt-8 md:pt-10 lg:col-span-5 lg:pb-20">
        <p class="hero-sub m-hide max-w-[34rem] font-body text-lg leading-relaxed text-ink-900/80 md:text-xl">
          {{ t('landing.hero.subheadline') }}
        </p>
        <div class="hero-ctas m-hide mt-9 flex flex-wrap items-center gap-x-6 gap-y-4">
          <div ref="ctaZone" class="-m-5 p-5">
            <a
              ref="ctaButton"
              href="#como-funciona"
              class="inline-block rounded-md bg-capture-600 px-7 py-3.5 font-body text-base font-semibold text-white transition-colors hover:bg-[#A93A24]"
            >
              {{ t('landing.cta.seeHow') }}
            </a>
          </div>
          <a href="#ejemplo-real" class="group inline-flex items-center gap-2.5 font-body text-base font-medium text-ink-900">
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
        <p class="hero-note m-hide mt-6 max-w-md font-body text-sm leading-relaxed text-ink-900/65">{{ t('landing.hero.note') }}</p>

        <dl class="hero-proof m-hide mb-0 mt-9 max-w-[30rem] border-t border-ink-900/15 pt-4">
          <dt class="mb-3 font-mono text-[11px] text-ink-900/60">{{ t('landing.hero.proof.caption') }}</dt>
          <dd class="m-0 flex flex-wrap gap-x-8 gap-y-4">
            <span v-for="key in PROOF" :key="key" class="block">
              <span class="block whitespace-nowrap font-plan text-[1.35rem] font-extrabold leading-none tracking-[-0.03em] text-ink-900">
                {{ key === 'audio' ? t('landing.hero.stage.voiceDuration') : t(`landing.hero.proof.${key}.value`) }}
              </span>
              <span class="mt-1.5 block font-body text-xs leading-snug text-ink-900/65">{{ t(`landing.hero.proof.${key}.label`) }}</span>
            </span>
          </dd>
        </dl>
      </div>

      <!-- Stage: the client's document rising from under the fold, the chat that produced it overlapping its corner. -->
      <div class="relative mx-auto h-[43rem] w-full max-w-[640px] sm:h-[32rem] lg:col-span-7 lg:mr-0 lg:h-[34rem] lg:max-w-none">
        <div class="absolute right-0 top-0 flex h-6 w-[88%] max-w-[460px] items-center sm:w-[72%]" aria-hidden="true">
          <span class="cota-tick h-2.5 w-px bg-ink-900/45" />
          <span class="cota h-px flex-1 origin-right bg-ink-900/45" />
          <span class="cota-label px-2.5 font-mono text-[11px] text-ink-900/60">210 mm</span>
          <span class="cota h-px flex-1 origin-left bg-ink-900/45" />
          <span class="cota-tick h-2.5 w-px bg-ink-900/45" />
        </div>

        <div class="doc m-hide absolute right-0 top-9 w-[88%] max-w-[460px] min-h-[42rem] rounded-[3px] bg-surface-0 pb-24 pl-12 pr-6 pt-7 shadow-page sm:w-[72%] sm:pl-14 sm:pr-8">
          <div class="flex items-center gap-3">
            <!-- The client's own logo, as in the real demo report (PL = Prevención Levante, NS = Northline Safety). -->
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-[6px] bg-doc-700 font-body text-[13px] font-semibold text-capture-500" aria-hidden="true">
              {{ locale === 'es' ? 'PL' : 'NS' }}
            </span>
            <div>
              <p class="font-body text-[1.15rem] font-bold leading-none tracking-tight text-doc-700">{{ t('landing.hero.stage.docTitle') }}</p>
              <p class="mt-1.5 font-body text-[13px] text-doc-700/70">{{ t('landing.hero.stage.company') }}</p>
            </div>
          </div>
          <div class="mt-4 h-px w-full bg-doc-700/15" />

          <p class="mt-4 font-body text-[13px] leading-6 text-ink-900">
            <b class="font-semibold">{{ t('landing.hero.stage.dateLabel') }}</b>
            <LandingToken class="ml-1" :tag="t('landing.hero.stage.tags.date')" :value="t('landing.hero.stage.values.date')" />
            <span class="ml-4 inline-block whitespace-nowrap max-[420px]:ml-0">
              <b class="font-semibold">{{ t('landing.hero.stage.stageLabel') }}</b>
              <LandingToken class="ml-1" :tag="t('landing.hero.stage.tags.stage')" :value="t('landing.hero.stage.values.stage')" />
            </span>
          </p>

          <p class="mt-4 font-body text-sm font-semibold text-doc-700">{{ t('landing.hero.stage.companiesLabel') }}</p>
          <ul class="mb-0 mt-1 space-y-0.5 pl-4 font-body text-[13px] leading-6 text-ink-900" style="list-style: disc">
            <li v-for="key in COMPANIES" :key="key">
              <LandingToken :tag="t(`landing.hero.stage.tags.${key}`)" :value="t(`landing.hero.stage.values.${key}`)" />
            </li>
          </ul>

          <p class="mt-4 font-body text-sm font-semibold text-doc-700">{{ t('landing.hero.stage.issueLabel') }}</p>
          <p class="mt-1 font-body text-[13px] leading-6 text-ink-900">
            <LandingToken :tag="t('landing.hero.stage.tags.issue')" :value="t('landing.hero.stage.values.issue')" />
          </p>

          <div class="mt-5 space-y-2" aria-hidden="true">
            <div class="h-1.5 w-full rounded-full bg-doc-700/10" />
            <div class="h-1.5 w-[86%] rounded-full bg-doc-700/10" />
            <div class="h-1.5 w-[64%] rounded-full bg-doc-700/10" />
          </div>

          <div
            class="stamp m-hide absolute right-5 top-[22rem] sm:top-[17.5rem] rounded-sm border-[3px] border-approved-600 px-3 py-1 font-plan text-lg font-extrabold tracking-[0.12em] text-approved-600 sm:right-7"
            aria-hidden="true"
          >
            {{ t('landing.hero.stage.stamp') }}
          </div>
        </div>

        <div class="chat m-hide absolute bottom-10 left-0 w-[64%] min-w-[210px] max-w-[262px] overflow-hidden rounded-2xl bg-surface-0 shadow-float" aria-hidden="true">
          <div class="flex items-center gap-2.5 border-b border-paper-100 px-3.5 py-2.5">
            <span class="flex h-7 w-7 items-center justify-center rounded-full bg-ink-900 font-plan text-[11px] font-extrabold text-capture-500">R</span>
            <div class="leading-tight">
              <p class="font-body text-xs font-semibold text-ink-900">ReportAI</p>
              <p class="font-body text-[10px] text-ink-900/60">Telegram</p>
            </div>
          </div>
          <div class="space-y-2 p-3">
            <div class="b-voice m-hide ml-auto flex w-fit items-center gap-2 rounded-2xl rounded-br-md bg-capture-600 px-3 py-2 text-white">
              <svg viewBox="0 0 20 20" fill="currentColor" class="h-4 w-4 shrink-0"><path d="M6 4.5v11l9-5.5-9-5.5Z" /></svg>
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

            <div class="b-sent m-hide flex w-fit max-w-full items-center gap-2.5 rounded-2xl rounded-bl-md bg-paper-50 px-3 py-2">
              <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-ink-900 text-white">
                <svg viewBox="0 0 20 20" fill="currentColor" class="h-3.5 w-3.5">
                  <path d="M4 2h8l4 4v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Zm7 1.5V7h3.5L11 3.5ZM6 10h8v1.2H6V10Zm0 3h8v1.2H6V13Z" />
                </svg>
              </span>
              <span class="min-w-0 leading-tight">
                <span class="block truncate font-mono text-[10px] text-ink-900/70">{{ t('landing.hero.stage.filename') }}</span>
                <span class="block font-body text-[11px] font-medium text-[#136B4F]">{{ t('landing.hero.stage.sent') }} ✓</span>
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          class="hero-replay m-hide absolute bottom-1 left-0 inline-flex cursor-pointer items-center gap-1.5 border-0 bg-transparent p-0 font-body text-xs text-ink-900/65 transition-colors hover:text-capture-600"
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
