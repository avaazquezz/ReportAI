<script setup lang="ts">
const { t } = useI18n()
const cta = useTrialCta()

const NAV = [
  { href: '/#como-funciona', key: 'how' },
  { href: '/#pruebalo', key: 'demo' },
  { href: '/#precios', key: 'pricing' },
  { href: '/#preguntas', key: 'faq' }
] as const

const open = ref(false)
const scrolled = ref(false)
// Over the dark act the header turns dark with it.
const dark = ref(false)
const panel = ref<HTMLElement | null>(null)
const toggle = ref<HTMLButtonElement | null>(null)

function close(returnFocus = false) {
  open.value = false
  if (returnFocus) toggle.value?.focus()
}

async function openMenu() {
  open.value = true
  await nextTick()
  panel.value?.querySelector<HTMLElement>('a')?.focus()
}

const onKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && open.value) close(true)
}
const onScroll = () => (scrolled.value = window.scrollY > 8)

let observer: IntersectionObserver | undefined
onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('keydown', onKey)
  onScroll()
  const night = document.querySelector('#de-noche')
  if (night) {
    // The band under the header: the top ~8% of the viewport.
    observer = new IntersectionObserver(([entry]) => (dark.value = !!entry?.isIntersecting), { rootMargin: '0px 0px -92% 0px' })
    observer.observe(night)
  }
})
onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('keydown', onKey)
  observer?.disconnect()
})
</script>

<template>
  <header
    class="sticky top-0 z-40 transition-colors duration-300"
    :class="[
      dark ? 'bg-[#0D1015] text-white' : 'bg-[#F5F5F2] text-ink-900',
      scrolled && !dark ? 'shadow-[0_1px_0_rgb(18_21_28/0.08)]' : ''
    ]"
  >
    <div class="home-grid h-[4.25rem] items-center">
      <NuxtLink to="/" class="col-span-6 w-fit md:col-span-3">
        <HomeMark :dark="dark" />
      </NuxtLink>

      <nav class="col-span-6 hidden items-center justify-center gap-8 md:flex" :aria-label="t('home.nav.label')">
        <a v-for="item in NAV" :key="item.href" :href="item.href" class="u-nav text-[0.95rem]">
          {{ t(`home.nav.${item.key}`) }}
        </a>
      </nav>

      <div class="col-span-6 flex items-center justify-end gap-3 md:col-span-3">
        <LanguageSwitcher class="hidden sm:inline-flex" />
        <NuxtLink to="/login" class="u-field hidden text-[0.95rem] lg:inline">{{ t('home.nav.signIn') }}</NuxtLink>
        <a :href="cta.href" class="btn-primary hidden !min-h-[2.5rem] !px-4 text-[0.9rem] sm:inline-flex" :class="{ 'is-inverse': dark }">{{ cta.label }}</a>
        <button
          ref="toggle"
          type="button"
          class="border-hair inline-flex h-10 w-10 items-center justify-center rounded border md:hidden"
          :aria-expanded="open"
          aria-controls="home-menu"
          :aria-label="open ? t('home.nav.close') : t('home.nav.open')"
          @click="open ? close() : openMenu()"
        >
          <svg viewBox="0 0 20 20" class="h-5 w-5" aria-hidden="true">
            <path v-if="!open" d="M3 6h14M3 10h14M3 14h14" stroke="currentColor" stroke-width="1.6" fill="none" />
            <path v-else d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.6" fill="none" />
          </svg>
        </button>
      </div>
    </div>

    <div
      v-show="open"
      id="home-menu"
      ref="panel"
      class="border-hair border-t md:hidden"
      :class="dark ? 'bg-[#0D1015]' : 'bg-[#F5F5F2]'"
    >
      <nav class="home-grid py-4" :aria-label="t('home.nav.label')">
        <a
          v-for="item in NAV"
          :key="item.href"
          :href="item.href"
          class="border-hair col-span-12 border-b py-3.5 text-lg"
          @click="close()"
        >{{ t(`home.nav.${item.key}`) }}</a>
        <div class="col-span-12 mt-5 flex items-center justify-between gap-4">
          <NuxtLink to="/login" class="u-field">{{ t('home.nav.signIn') }}</NuxtLink>
          <LanguageSwitcher />
        </div>
        <a :href="cta.href" class="btn-primary col-span-12 mt-5 w-full" :class="{ 'is-inverse': dark }" @click="close()">{{ cta.label }}</a>
      </nav>
    </div>
  </header>
</template>
