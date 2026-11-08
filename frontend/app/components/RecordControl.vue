<script setup lang="ts">
// The record button: big enough to hit with a glove, one tap to start, one to stop.
withDefaults(defineProps<{ size?: 'large' | 'small'; disabled?: boolean }>(), { size: 'large', disabled: false })
const emit = defineEmits<{ recorded: [audio: Blob, seconds: number] }>()
const recording = defineModel<boolean>('recording', { default: false })

const { t } = useI18n()
const { state, seconds, level, start, stop } = useRecorder()

watch(state, (value) => (recording.value = value === 'recording'))

async function toggle() {
  if (state.value === 'recording') {
    const length = seconds.value
    emit('recorded', await stop(), length)
  } else await start()
}

watch(seconds, (value) => {
  if (value >= MAX_RECORDING_SECONDS && state.value === 'recording') toggle()
})
</script>

<template>
  <div class="flex flex-col items-center gap-3">
    <button
      type="button"
      class="flex items-center justify-center rounded-full text-white shadow-md transition-transform focus:outline-none focus-visible:ring-4 focus-visible:ring-capture-500/50 disabled:opacity-50 motion-safe:active:scale-95"
      :class="[size === 'large' ? 'h-32 w-32' : 'h-16 w-16', state === 'recording' ? 'bg-failed-600' : 'bg-capture-600']"
      :disabled="disabled"
      :aria-pressed="state === 'recording'"
      :aria-label="state === 'recording' ? t('admin.capture.record.stop') : t('admin.capture.record.start')"
      @click="toggle"
    >
      <v-icon :icon="state === 'recording' ? 'mdi-stop' : 'mdi-microphone'" :size="size === 'large' ? 56 : 30" aria-hidden="true" />
    </button>

    <div v-if="state === 'recording'" class="w-full max-w-xs" aria-hidden="true">
      <p class="text-center font-display text-2xl font-bold tabular-nums text-ink-900">{{ formatDuration(seconds) }}</p>
      <v-progress-linear :model-value="level * 100" color="failed" height="6" rounded />
    </div>
    <p v-else-if="size === 'large'" class="font-body text-sm text-ink-900/70">{{ t('admin.capture.record.hint') }}</p>
    <p class="sr-only" role="status">{{ state === 'recording' ? t('admin.capture.record.recording') : '' }}</p>

    <v-alert v-if="state === 'denied'" type="warning" variant="tonal" density="compact">{{ t('admin.capture.record.denied') }}</v-alert>
    <v-alert v-else-if="state === 'unsupported'" type="warning" variant="tonal" density="compact">
      {{ t('admin.capture.record.unsupported') }}
    </v-alert>
    <v-alert v-else-if="state === 'failed'" type="error" variant="tonal" density="compact">{{ t('admin.capture.record.failed') }}</v-alert>
  </div>
</template>
