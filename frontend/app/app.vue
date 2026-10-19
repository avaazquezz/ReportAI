<script setup lang="ts">
// Self-hosted fonts live in assets/css/fonts.css; the body face is preloaded for every page.
// The landing preloads its own headline and mono faces (pages/index.vue).
import plexSans from '~/assets/fonts/ibm-plex-sans-w100-400-600-latin.woff2?url'

const { t, locale } = useI18n()

useHead({
  title: computed(() => t('landing.seo.title')),
  htmlAttrs: { lang: locale },
  link: [
    { rel: 'preload', as: 'font', type: 'font/woff2', href: plexSans, crossorigin: '' },
    { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
    { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/favicon-32x32.png' },
    { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/favicon-16x16.png' },
    { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
    { rel: 'apple-touch-icon', sizes: '180x180', href: '/apple-touch-icon.png' }
  ],
  // Landing elements that start hidden (.m-hide) or as an unresolved {{ tag }} are revealed by
  // GSAP — without JS nothing would ever show them, so show the resolved state instead.
  noscript: [{ innerHTML: '<style>.m-hide{opacity:1}.tok-tag{display:none}.tok-val{opacity:1}.v-in{opacity:1!important}.v-mark{background-size:100% 100%!important}</style>' }]
})
</script>

<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
</template>
