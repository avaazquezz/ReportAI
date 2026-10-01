<script setup lang="ts">
import type { CheckResult } from '~/types'

// What a "Test" button found: a tick, or what went wrong in the reader's language with the
// provider's own answer under it.
defineProps<{ result: CheckResult | null; okText?: string }>()
const { t, te } = useI18n()
const reasonText = (reason: string | null) => (reason && te(`checks.${reason}`) ? t(`checks.${reason}`) : t('checks.other'))
</script>

<template>
  <span v-if="result?.ok" class="text-sm text-success">✓ {{ okText ?? t('checks.ok') }}</span>
  <v-alert v-else-if="result" type="error" variant="tonal" density="compact" class="mt-3" :title="reasonText(result.reason)">
    <span class="text-sm">{{ result.detail }}</span>
  </v-alert>
</template>
