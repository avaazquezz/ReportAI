<script setup lang="ts">
const { t } = useI18n()
const contactHref = useContactHref()

const NAV = [
  { hash: '#ejemplo-real', key: 'realExample' },
  { hash: '#como-funciona', key: 'howItWorks' },
  { hash: '#diferencia', key: 'difference' },
  { hash: '#preguntas', key: 'faq' }
] as const

const scrolled = ref(false)
const open = ref(false)

function onScroll() {
  scrolled.value = window.scrollY > 8
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  // Native scroll restoration / hash-anchor jumps happen before this listener
  // attaches and fire no scroll event, so the header would stay transparent
  // over a page that loaded already scrolled.
  onScroll()
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <header
    class="sticky top-0 z-50 backdrop-blur-md transition-[background-color,box-shadow] duration-300"
    :class="scrolled || open ? 'bg-paper-50/85 shadow-[0_1px_0_0_rgba(18,21,28,0.08)]' : 'bg-transparent'"
  >
    <div class="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
      <NuxtLink to="/" class="flex items-center gap-2.5" @click="open = false">
        <svg viewBox="0 0 100 100" class="h-8 w-8 shrink-0" aria-hidden="true">
          <rect width="100" height="100" rx="24" class="fill-ink-900" />
          <text
            x="50"
            y="70"
            font-size="60"
            text-anchor="middle"
            font-family="Arial, Helvetica, sans-serif"
            font-weight="700"
            class="fill-capture-500"
          >R</text>
        </svg>
        <span class="font-display text-lg font-bold text-ink-900">ReportAI</span>
      </NuxtLink>

      <nav class="hidden items-center gap-7 font-body text-sm lg:flex">
        <a
          v-for="item in NAV"
          :key="item.hash"
          :href="item.hash"
          class="text-ink-900/80 transition-colors hover:text-ink-900"
        >
          {{ t(`landing.header.nav.${item.key}`) }}
        </a>
        <LanguageSwitcher />
        <a
          :href="contactHref"
          class="rounded-md bg-ink-900 px-4 py-2 font-semibold text-white transition-colors hover:bg-capture-600"
        >
          {{ t('landing.cta.becomeClient') }}
        </a>
      </nav>

      <button
        type="button"
        class="-mr-2 flex h-10 w-10 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent text-ink-900 lg:hidden"
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

    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="-translate-y-2 opacity-0"
      leave-active-class="transition duration-150 ease-in"
      leave-to-class="-translate-y-2 opacity-0"
    >
      <nav v-if="open" id="mobile-nav" class="border-t border-paper-100 px-6 pb-6 pt-2 lg:hidden">
        <a
          v-for="item in NAV"
          :key="item.hash"
          :href="item.hash"
          class="block border-b border-paper-100 py-3.5 font-display text-lg font-bold text-ink-900"
          @click="open = false"
        >
          {{ t(`landing.header.nav.${item.key}`) }}
        </a>
        <div class="mt-5 flex items-center justify-between gap-4">
          <a
            :href="contactHref"
            class="flex-1 rounded-md bg-ink-900 px-4 py-3 text-center font-body text-sm font-semibold text-white"
          >
            {{ t('landing.cta.becomeClient') }}
          </a>
          <LanguageSwitcher />
        </div>
      </nav>
    </Transition>
  </header>
</template>
