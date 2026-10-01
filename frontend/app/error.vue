<script setup lang="ts">
import type { NuxtError } from '#app'

// Nuxt's built-in error screen is an English developer page; a client's staff see this one (FE-11).
const props = defineProps<{ error: NuxtError }>()
const { t } = useI18n()
const authStore = useAuthStore()

const notFound = computed(() => props.error.statusCode === 404)

useHead({ title: () => `${notFound.value ? t('common.error.notFoundTitle') : t('common.error.title')} · ReportAI` })

function goBack() {
  clearError({ redirect: authStore.isAuthenticated ? '/dashboard' : '/' })
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-paper-50 px-6">
    <div class="max-w-md text-center">
      <p class="font-mono text-sm text-ink-900/70">{{ error.statusCode }}</p>
      <h1 class="mt-2 font-display text-2xl font-bold text-ink-900">
        {{ notFound ? t('common.error.notFoundTitle') : t('common.error.title') }}
      </h1>
      <p class="mt-3 font-body text-ink-900/70">
        {{ notFound ? t('common.error.notFoundBody') : t('common.error.body') }}
      </p>
      <button
        type="button"
        class="mt-8 rounded-md bg-capture-600 px-4 py-2.5 font-body text-sm font-semibold text-white"
        @click="goBack"
      >
        {{ authStore.isAuthenticated ? t('common.error.backToPanel') : t('common.error.backHome') }}
      </button>
    </div>
  </div>
</template>
