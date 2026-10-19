<script setup lang="ts">
const { t, locale } = useI18n()

useHead({
  title: computed(() => t('landing.seo.title')),
  htmlAttrs: { lang: locale },
  link: [
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
    {
      rel: 'stylesheet',
      href: 'https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@112.5,700;112.5,800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Space+Grotesk:wght@500;700&display=swap'
    },
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
