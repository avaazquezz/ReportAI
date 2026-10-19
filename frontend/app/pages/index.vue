<script setup lang="ts">
// The first screen paints with these two faces: fetch them before the stylesheet asks.
import archivo from '~/assets/fonts/archivo-w112.5-700-800-latin.woff2?url'
import plexMono from '~/assets/fonts/ibm-plex-mono-400-latin.woff2?url'

const { t } = useI18n()

useHead({
  link: [archivo, plexMono].map((href) => ({ rel: 'preload', as: 'font', type: 'font/woff2', href, crossorigin: '' }) as const)
})

useSeoMeta({
  description: () => t('landing.seo.description'),
  ogTitle: () => t('landing.seo.title'),
  ogDescription: () => t('landing.seo.description'),
  ogType: 'website'
})
</script>

<template>
  <div>
    <LandingHeroSection />
    <LandingStackStrip />
    <LandingRealDemoSection />
    <LandingArchitectureSection />
    <LandingDifferentiatorSection />
    <LandingSavingsSection />
    <LandingUseCasesSection />
    <LandingTemplateFidelitySection />
    <LandingApprovalSection />
    <LandingDecisionsSection />
    <LandingFinalCtaSection />
  </div>
</template>
