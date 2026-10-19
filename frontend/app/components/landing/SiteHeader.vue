<script setup lang="ts">
const { t } = useI18n()
const contactHref = useContactHref()

const NAV = [
  { hash: '#ejemplo-real', key: 'realExample' },
  { hash: '#como-funciona', key: 'howItWorks' },
  { hash: '#impacto', key: 'impact' },
  { hash: '#decisiones', key: 'faq' }
] as const

const scrolled = ref(false)
const open = ref(false)
// Over the blueprint-blue architecture block the header turns dark with it.
const dark = ref(false)
// The section in view, for the nav, and how far down the page the visitor is.
const current = ref('')
const progress = ref(0)

let frame = 0
function onScroll() {
  scrolled.value = window.scrollY > 8
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    const max = document.documentElement.scrollHeight - window.innerHeight
    progress.value = max > 0 ? Math.min(window.scrollY / max, 1) : 0
  })
}

let observers: IntersectionObserver[] = []
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  // Native scroll restoration / hash-anchor jumps happen before this listener
  // attaches and fire no scroll event, so the header would stay transparent
  // over a page that loaded already scrolled.
  onScroll()

  const spy = new IntersectionObserver(
    (entries) => {
      for (const e of entries) if (e.isIntersecting) current.value = `#${e.target.id}`
    },
    { rootMargin: '-45% 0px -50% 0px' }
  )
  for (const { hash } of NAV) {
    const el = document.querySelector(hash)
    if (el) spy.observe(el)
  }
  // The band under the header (the top ~8% of the viewport).
  const tone = new IntersectionObserver(([e]) => (dark.value = !!e?.isIntersecting), { rootMargin: '0px 0px -92% 0px' })
  const plano = document.querySelector('#como-funciona')
  if (plano) tone.observe(plano)
  observers = [spy, tone]
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  cancelAnimationFrame(frame)
  observers.forEach((o) => o.disconnect())
})
</script>

<template>
  <header
    class="sticky top-0 z-50 backdrop-blur-md transition-[background-color,box-shadow] duration-300"
    :class="[
      dark ? 'bg-plano-900/85 shadow-[0_1px_0_0_rgba(143,176,227,0.18)]' : scrolled || open ? 'bg-paper-50/85 shadow-[0_1px_0_0_rgba(18,21,28,0.08)]' : 'bg-transparent'
    ]"
  >
    <div class="mx-auto flex max-w-[1240px] items-center justify-between px-6 py-4">
      <NuxtLink to="/" class="flex items-center gap-2.5" @click="open = false">
        <svg viewBox="0 0 100 100" class="h-8 w-8 shrink-0" aria-hidden="true">
          <rect width="100" height="100" rx="24" :class="dark ? 'fill-white' : 'fill-ink-900'" class="transition-[fill] duration-300" />
          <text x="50" y="70" font-size="60" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-weight="700" :class="dark ? 'fill-capture-600' : 'fill-capture-500'" class="transition-[fill] duration-300">R</text>
        </svg>
        <span class="font-plan text-lg font-extrabold tracking-[-0.03em] transition-colors duration-300" :class="dark ? 'text-white' : 'text-ink-900'">ReportAI</span>
      </NuxtLink>

      <nav class="hidden items-center gap-7 font-body text-sm lg:flex">
        <a
          v-for="item in NAV"
          :key="item.hash"
          :href="item.hash"
          class="relative py-1 transition-colors"
          :class="[dark ? 'text-white/70 hover:text-white' : 'text-ink-900/75 hover:text-ink-900', current === item.hash ? (dark ? '!text-white' : '!text-ink-900') : '']"
          :aria-current="current === item.hash ? 'location' : undefined"
        >
          {{ t(`landing.header.nav.${item.key}`) }}
          <span class="absolute inset-x-0 -bottom-0.5 h-px origin-left bg-capture-500 transition-transform duration-300" :class="current === item.hash ? 'scale-x-100' : 'scale-x-0'" />
        </a>
        <LanguageSwitcher />
        <a
          :href="contactHref"
          class="rounded-md px-4 py-2 font-semibold transition-colors"
          :class="dark ? 'bg-white text-ink-900 hover:bg-capture-500 hover:text-white' : 'bg-ink-900 text-white hover:bg-capture-600'"
        >
          {{ t('landing.cta.talk') }}
        </a>
      </nav>

      <button
        type="button"
        class="-mr-2 flex h-10 w-10 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent lg:hidden"
        :class="dark ? 'text-white' : 'text-ink-900'"
        :aria-label="open ? t('landing.header.closeMenu') : t('landing.header.openMenu')"
        :aria-expanded="open"
        aria-controls="mobile-nav"
        @click="open = !open"
      >
        <svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <path v-if="!open" d="M4 7h16M4 12h16M4 17h16" />
          <path v-else d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>

    <div class="absolute inset-x-0 bottom-0 h-px" aria-hidden="true">
      <div class="h-full origin-left bg-capture-600" :style="{ transform: `scaleX(${progress})` }" />
    </div>

    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="-translate-y-2 opacity-0"
      leave-active-class="transition duration-150 ease-in"
      leave-to-class="-translate-y-2 opacity-0"
    >
      <nav v-if="open" id="mobile-nav" class="border-t border-paper-100 bg-paper-50 px-6 pb-6 pt-2 lg:hidden">
        <a
          v-for="item in NAV"
          :key="item.hash"
          :href="item.hash"
          class="block border-b border-paper-100 py-3.5 font-plan text-lg font-bold text-ink-900"
          @click="open = false"
        >
          {{ t(`landing.header.nav.${item.key}`) }}
        </a>
        <div class="mt-5 flex items-center justify-between gap-4">
          <a :href="contactHref" class="flex-1 rounded-md bg-ink-900 px-4 py-3 text-center font-body text-sm font-semibold text-white">
            {{ t('landing.cta.talk') }}
          </a>
          <LanguageSwitcher />
        </div>
      </nav>
    </Transition>
  </header>
</template>
