<script setup lang="ts">
// The product's page, for the health-and-safety technicians and coordinators it is made for and for
// whoever wants to see how it is built. Concept "the report fills itself in" (the Fase 6 brief).
// Nothing is sold here: its one action is an email to try it. The full case study is /arquitectura.
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
    <HomeBuilt />
    <HomeFaq />
    <HomeClosing />
  </div>
</template>
