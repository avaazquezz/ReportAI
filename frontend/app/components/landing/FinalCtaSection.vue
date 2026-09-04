<script setup lang="ts">
const { t } = useI18n()
const contactHref = useContactHref()

// Vue's own template tokenizer treats literal "{{"/"}}" inside a mustache
// expression as an unterminated nested interpolation — building the string in
// script and interpolating the result avoids that.
const placeholderTag = computed(() => `{{ ${t('landing.finalCta.placeholderTag')} }}`)

// Closes the loop opened by the hero: the same placeholder-resolving signature,
// used exactly twice on the page.
const root = ref<HTMLElement | null>(null)
useSectionMotion(
  root,
  (tl) => {
    tl.to('.tag', { opacity: 0, y: -6, duration: 0.35 }, 0.4)
      .fromTo('.headline', { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4 }, '<')
      .fromTo(['.sub', '.actions'], { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.12 })
  },
  { start: 'top 65%' }
)
</script>

<template>
  <section class="bg-paper-50 px-6 pb-24 pt-8 md:pb-32">
    <div
      ref="root"
      class="relative mx-auto max-w-[1152px] overflow-hidden rounded-3xl bg-ink-900 px-6 py-20 text-center text-white md:px-8 md:py-28"
    >
      <div
        class="pointer-events-none absolute inset-0"
        style="background: radial-gradient(60% 70% at 50% 100%, rgba(255, 106, 69, 0.22), transparent 70%)"
        aria-hidden="true"
      />
      <div class="relative mx-auto flex max-w-3xl items-center justify-center">
        <p class="tag absolute inset-0 flex items-center justify-center font-mono text-lg text-white/30 md:text-xl" aria-hidden="true">
          {{ placeholderTag }}
        </p>
        <h2 class="headline m-hide font-display text-[clamp(2.2rem,5vw,4.2rem)] font-bold leading-[1.02] tracking-[-0.03em] [text-wrap:balance]">
          {{ t('landing.finalCta.headline') }}
        </h2>
      </div>
      <p class="sub m-hide relative mx-auto mt-6 max-w-xl font-body text-lg text-white/70">
        {{ t('landing.finalCta.sub') }}
      </p>
      <div class="actions m-hide relative mt-9 flex flex-col items-center gap-4">
        <a
          :href="contactHref"
          class="rounded-md bg-capture-600 px-8 py-4 font-body text-lg font-semibold text-white transition-[transform,background-color] hover:-translate-y-0.5 hover:bg-[#A93A24]"
        >
          {{ t('landing.cta.becomeClient') }}
        </a>
        <p class="font-body text-sm text-white/55">
          {{ t('landing.finalCta.or') }}
          <a :href="`mailto:${CONTACT_EMAIL}`" class="text-white/85 underline decoration-white/30 underline-offset-4 hover:text-capture-500">{{ CONTACT_EMAIL }}</a>
        </p>
      </div>
    </div>
  </section>
</template>
