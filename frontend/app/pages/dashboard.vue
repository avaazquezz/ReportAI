<script setup lang="ts">
definePageMeta({ middleware: 'auth', layout: 'app' })

const { t } = useI18n()
const authStore = useAuthStore()
</script>

<template>
  <div>
    <h1 class="font-display text-2xl font-bold text-ink-900">
      {{ t('admin.dashboard.greeting', { name: authStore.user?.full_name }) }}
    </h1>
    <div class="mt-8 rounded-2xl border border-slate-300 bg-surface-0 p-10 text-center">
      <p class="font-body text-ink-900/70">{{ t('admin.dashboard.hint') }}</p>
    </div>
  </div>
</template>
