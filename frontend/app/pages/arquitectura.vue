<script setup lang="ts">
// The first screen paints with these two faces: fetch them before the stylesheet asks.
import archivo from '~/assets/fonts/archivo-w112.5-700-800-latin.woff2?url'
import plexMono from '~/assets/fonts/ibm-plex-mono-400-latin.woff2?url'

// The engineering case study, for people who hire engineers: how ReportAI is built, told as a
// drawing set (utils/caseStudy.ts) — a cover anyone reads in a minute, then sheets at finer and
// finer scales for whoever wants the detail. /architecture is the same page, for links in English;
// the canonical address stays /arquitectura so the two don't compete.
definePageMeta({ layout: 'architecture', alias: ['/architecture'] })

const { t, locale } = useI18n()
const origin = useRequestURL().origin
const canonical = `${origin}/arquitectura`

useHead({
  title: () => t('landing.cover.seoTitle'),
  link: [
    ...[archivo, plexMono].map((href) => ({ rel: 'preload', as: 'font', type: 'font/woff2', href, crossorigin: '' }) as const),
    { rel: 'canonical', href: canonical }
  ]
})

useSeoMeta({
  description: () => t('landing.cover.seoDescription'),
  ogTitle: () => t('landing.cover.seoTitle'),
  ogDescription: () => t('landing.cover.seoDescription'),
  ogType: 'article',
  ogUrl: canonical,
  // The card a share shows, in the language the page was served in: a screenshot of the cover.
  ogImage: () => `${origin}/og-arquitectura-${locale.value}.png`,
  ogImageWidth: 1200,
  ogImageHeight: 630,
  ogImageAlt: () => t('landing.cover.seoTitle'),
  twitterCard: 'summary_large_image'
})
</script>

<template>
  <div>
    <LandingCover />
    <LandingStackStrip />
    <LandingSystemSheet />
    <LandingServerSheet />
    <LandingArchitectureSection />
    <LandingTenancySheet />
    <LandingFieldAppSheet />
    <LandingQualitySheet />
    <LandingRevisionsSheet />
    <LandingClosing />
  </div>
</template>
