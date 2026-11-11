<script setup lang="ts">
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

// The last call, the hero's promise said another way, sealed once with the approval stamp.
const { t } = useI18n()
const contact = useContactHref('home.cta.mailSubject')
const root = ref<HTMLElement | null>(null)

useMotionScope(root, (c) => {
  const stamp = gsap.fromTo('.closing-stamp', { opacity: 0, scale: 1.8, rotate: -14 }, { opacity: 1, scale: 1, rotate: 0, duration: 0.32, ease: 'power3.in', paused: true })
  if (c.reduce) {
    stamp.progress(1)
    return
  }
  ScrollTrigger.create({ trigger: '.closing-stamp', start: 'top 80%', once: true, onEnter: () => stamp.play() })
})
</script>

<template>
  <section ref="root" class="space-l border-t border-ink-900/10" aria-labelledby="closing-title">
    <div class="home-grid">
      <div class="relative col-span-12 lg:col-span-10">
        <h2 id="closing-title" class="t-section m-0 max-w-[16ch] text-[clamp(2.4rem,1.2rem+4.4vw,5.6rem)]">{{ t('home.closing.heading') }}</h2>
        <div class="closing-stamp m-hide absolute -top-6 right-0 hidden md:block">
          <HomeStamp :label="t('home.review.stamp')" class="scale-125" />
        </div>
      </div>
      <div class="col-span-12 mt-12 flex flex-wrap items-center gap-x-7 gap-y-4">
        <a :href="contact" class="btn-primary">{{ t('home.cta.write') }}</a>
        <span class="text-[0.95rem] text-ink-900/65">{{ t('home.closing.sub') }}</span>
      </div>
    </div>
  </section>
</template>
