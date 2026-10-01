<script setup lang="ts">
// Sign-in, password and setup pages: on a company's own server there is no marketing site
// around them, so they stand alone.
const { status } = useInstance()
const { t } = useI18n()
const route = useRoute()
// Each page's own tab title, not the marketing site's.
useHead({ title: () => (route.meta.titleKey ? `${t(route.meta.titleKey)} · ReportAI` : 'ReportAI') })
</script>

<template>
  <v-app>
    <div class="min-h-screen bg-paper-50 font-body text-ink-900">
      <header class="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <NuxtLink :to="status?.single_tenant ? '/login' : '/'" class="font-display text-lg font-bold text-ink-900">
          ReportAI
        </NuxtLink>
        <LanguageSwitcher />
      </header>
      <main>
        <slot />
      </main>
    </div>
  </v-app>
</template>
