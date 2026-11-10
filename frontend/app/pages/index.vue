<script setup lang="ts">
// The commercial landing: for the health-and-safety technicians and coordinators who would buy
// ReportAI. Concept "the report fills itself in" (docs: the Fase 6 brief). How it is built lives
// at /arquitectura.
import archivo from '~/assets/fonts/archivo-w112.5-700-800-latin.woff2?url'

const { t } = useI18n()

// The headline paints in Archivo: fetch it before the stylesheet asks for it.
useHead({ link: [{ rel: 'preload', as: 'font', type: 'font/woff2', href: archivo, crossorigin: '' }] })

useSeoMeta({
  title: () => t('home.seo.title'),
  description: () => t('home.seo.description'),
  ogTitle: () => t('home.seo.title'),
  ogDescription: () => t('home.seo.description'),
  ogType: 'website'
})
</script>

<template>
  <div>
    <HomeHero />
    <HomeFacts />
    <HomeNight />
    <HomeSteps />
    <HomeLiveDemo />
    <HomeTemplate />
    <HomeReview />
    <HomeSavings />
    <HomePricing />
    <HomeFaq />
    <HomeClosing />
  </div>
</template>
